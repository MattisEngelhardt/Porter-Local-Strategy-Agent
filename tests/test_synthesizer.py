"""Tests for the synthesis layer (core/synthesizer.py). LLM calls are faked (offline)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.playbooks import load_playbooks
from core.synthesizer import (
    build_system_prompt,
    build_user_prompt,
    parse_analysis,
    quality_check,
    synthesize,
)
from llm.local_llm_client import LLMError
from models.research import DocContent, FetchedContent, SourceTier
from models.synthesis import AnalysisOutput, Section, SourceRef, SynthesisInput
from models.task import Depth, Intent, Language, OutputFormat, TaskType


class _CaptureClient:
    """Records generate() kwargs and returns a fixed response."""

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def generate(self, prompt: str, system: str = "", use_thinking: Any = None, **kw: Any) -> str:
        self.calls.append({"prompt": prompt, "system": system, "use_thinking": use_thinking})
        return self.response


class _RaiseClient:
    def generate(self, prompt: str, **kw: Any) -> str:
        raise LLMError("backend down")


def _intent(**kw: Any) -> Intent:
    base: dict[str, Any] = {
        "task_type": TaskType.COMPETITOR_ANALYSIS,
        "output_formats": [OutputFormat.BRIEF],
        "language": Language.EN,
        "depth": Depth.STANDARD,
        "audience": None,
        "summary": "Analyze 1X Technologies",
    }
    base.update(kw)
    return Intent(**base)


def _si(**kw: Any) -> SynthesisInput:
    base: dict[str, Any] = {"intent": _intent()}
    base.update(kw)
    return SynthesisInput(**base)


# ------------------------------------------------------------- prompt assembly
def test_build_system_prompt_injects_brain_and_playbooks() -> None:
    """System prompt carries language + brain + all three playbooks + response format."""
    system = build_system_prompt(_intent(language=Language.DE), "BRAIN_FACT_XYZ", load_playbooks())
    assert "German" in system
    assert "BRAIN_FACT_XYZ" in system
    assert "Job Posting Intelligence" in system  # research playbook
    assert "The Neura Lens" in system  # analysis playbook
    assert "so what" in system  # output playbook
    assert "RESPONSE FORMAT" in system


def test_build_user_prompt_includes_evidence_with_tier() -> None:
    """User prompt lists the task, tiered research sources, and provided documents."""
    si = _si(
        research=[FetchedContent(url="https://reuters.com/x", title="T", text="news " * 40)],
        documents=[
            DocContent(
                source_path=Path("memo.pdf"),
                doc_type="pdf",
                text="DOC_BODY_TEXT",
                extraction_method="pdfplumber",
            )
        ],
    )
    user = build_user_prompt(si)
    assert "TASK (competitor_analysis)" in user
    assert "https://reuters.com/x" in user
    assert "tier_1" in user  # reuters classified Tier 1
    assert "memo.pdf" in user
    assert "DOC_BODY_TEXT" in user


def test_build_user_prompt_flags_no_evidence() -> None:
    """With no research or documents, the prompt flags the data gap."""
    assert "data gap" in build_user_prompt(_si())


# -------------------------------------------------------------- synthesize
def test_synthesize_parses_json() -> None:
    """A well-formed JSON response becomes a structured AnalysisOutput."""
    response = json.dumps(
        {
            "title": "1X Brief",
            "bottom_line": "Bottom line here.",
            "sections": [{"heading": "Technology", "body": "Strong moat."}],
            "sources": [{"url": "https://reuters.com/a", "tier": "tier_1"}],
        }
    )
    out = synthesize(_CaptureClient(response), _si())  # type: ignore[arg-type]
    assert out.title == "1X Brief"
    assert out.bottom_line == "Bottom line here."
    assert out.sections[0].heading == "Technology"
    assert out.language == Language.EN
    assert out.recommended_formats == [OutputFormat.BRIEF]
    assert out.sources[0].tier == SourceTier.TIER_1


def test_synthesize_thinking_follows_depth() -> None:
    """Thinking mode is on for standard/deep, off for quick (SPEC §5.3 / N-2)."""
    quick = _CaptureClient('{"title":"t","bottom_line":"b","sections":[],"sources":[]}')
    synthesize(quick, _si(intent=_intent(depth=Depth.QUICK)))  # type: ignore[arg-type]
    assert quick.calls[0]["use_thinking"] is False

    deep = _CaptureClient('{"title":"t","bottom_line":"b","sections":[],"sources":[]}')
    synthesize(deep, _si(intent=_intent(depth=Depth.DEEP)))  # type: ignore[arg-type]
    assert deep.calls[0]["use_thinking"] is True


def test_synthesize_json_failure_wraps_raw_text() -> None:
    """Non-JSON output is wrapped in one section; sources fall back to the research."""
    si = _si(research=[FetchedContent(url="https://x.com/a", text="t")])
    out = synthesize(_CaptureClient("This is plain prose, not JSON."), si)  # type: ignore[arg-type]
    assert out.sections and out.sections[0].body.startswith("This is plain prose")
    assert out.bottom_line.startswith("This is plain prose")
    assert out.sources[0].url == "https://x.com/a"


def test_synthesize_llm_error_degrades() -> None:
    """An LLM error yields a graceful error analysis, not an exception."""
    out = synthesize(_RaiseClient(), _si())  # type: ignore[arg-type]
    assert "Synthesis failed" in out.bottom_line
    assert out.recommended_formats == [OutputFormat.BRIEF]


# -------------------------------------------------------------- parse_analysis (Phase 3.5)
def test_parse_analysis_shared_path() -> None:
    """parse_analysis turns JSON into AnalysisOutput and wraps raw prose on bad JSON."""
    out = parse_analysis(
        '{"title":"T","bottom_line":"BL","sections":[{"heading":"H","body":"B"}],"sources":[]}',
        _si(),
    )
    assert out.title == "T"
    assert out.sections[0].heading == "H"

    raw = parse_analysis(
        "not json", _si(research=[FetchedContent(url="https://x.com/a", text="t")])
    )
    assert raw.sections[0].body.startswith("not json")
    assert raw.sources[0].url == "https://x.com/a"


# -------------------------------------------------------------- quality check
def test_quality_check_flags() -> None:
    """quality_check returns issue flags for incomplete output, none for complete."""
    good = AnalysisOutput(
        title="t",
        language=Language.EN,
        bottom_line="bl",
        sections=[Section(heading="h", body="b")],
        sources=[SourceRef(url="u")],
    )
    assert quality_check(good) == []
    bad = AnalysisOutput(title="t", language=Language.EN, bottom_line="")
    assert set(quality_check(bad)) == {
        "missing bottom line",
        "no analysis sections",
        "no sources cited",
    }
