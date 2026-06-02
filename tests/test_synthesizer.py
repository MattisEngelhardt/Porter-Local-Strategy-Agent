"""Tests for the synthesis layer (core/synthesizer.py). LLM calls are faked (offline)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.playbooks import load_playbooks
from core.synthesizer import (
    build_system_prompt,
    build_user_prompt,
    compile_cited_sources,
    parse_analysis,
    quality_check,
    synthesize,
)
from llm.local_llm_client import LLMError
from models.research import (
    DocContent,
    FetchedContent,
    Finding,
    ResearchReport,
    SourceTier,
    WorkerFindings,
)
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


# ------------------------------------------------ belegt bibliography (Phase 3.5)
def test_compile_cited_sources_dedups_and_merges_provenance() -> None:
    """The belegt set unions worker findings + read sources, deduped by URL, tier-ordered."""
    report = ResearchReport(
        worker_findings=[
            WorkerFindings(
                sub_topic="funding",
                findings=[
                    Finding(claim="raised $100M", source_url="https://reuters.com/a", date="2026-03"),
                    Finding(claim="hq move", source_url="https://reuters.com/a/"),  # trailing-slash dup
                    Finding(claim="founder quote", source_url="https://blog.example/post"),
                ],
                sources=[
                    FetchedContent(url="https://reuters.com/a", title="Reuters A", text="t"),
                    FetchedContent(url="https://crunchbase.com/org/x", title="CB X", text="t"),
                ],
            ),
        ],
        sources_evaluated=300,  # the scanned hundreds must NOT leak into the bibliography
    )
    refs = compile_cited_sources(report)
    urls = [r.url for r in refs]

    # dedup: reuters collapses to one entry despite 3 mentions (incl. the trailing-slash variant)
    assert sum("reuters.com/a" in u for u in urls) == 1
    # merge: title comes from the fetched page, date from the finding, tier is computed
    reuters = next(r for r in refs if "reuters.com/a" in r.url)
    assert reuters.title == "Reuters A"
    assert reuters.date == "2026-03"
    assert reuters.tier == SourceTier.TIER_1
    # union of every belegt URL (finding-only + source-only), nothing from sources_evaluated
    assert "https://blog.example/post" in urls
    assert "https://crunchbase.com/org/x" in urls
    assert len(refs) == 3
    # tier-ordered: Tier 1 reuters precedes the lower-tier blog
    assert urls.index("https://reuters.com/a") < urls.index("https://blog.example/post")


def test_synthesize_always_merges_cited_sources_with_sparse_llm() -> None:
    """Regression for the '<5 sources' bug: the belegt set is merged even when the LLM cites a few."""
    cited = [
        SourceRef(url="https://reuters.com/a", title="Reuters A", date="2026-03", tier=SourceTier.TIER_1),
        SourceRef(url="https://crunchbase.com/org/x", tier=SourceTier.TIER_2),
    ]
    response = json.dumps(
        {
            "title": "T",
            "bottom_line": "BL",
            "sections": [{"heading": "H", "body": "B"}],
            "sources": [
                {"url": "https://reuters.com/a", "tier": "tier_1"},  # duplicate of a belegt source
                {"url": "https://llm-only.example/z", "tier": "tier_3"},  # LLM-only extra
            ],
        }
    )
    out = synthesize(_CaptureClient(response), _si(cited_sources=cited))  # type: ignore[arg-type]
    urls = [r.url for r in out.sources]
    assert "https://reuters.com/a" in urls  # belegt preserved
    assert "https://crunchbase.com/org/x" in urls  # belegt the LLM omitted is still present
    assert "https://llm-only.example/z" in urls  # LLM-only extra merged in
    assert sum(u == "https://reuters.com/a" for u in urls) == 1  # shared URL not duplicated
    assert len(out.sources) == 3


def test_cited_sources_empty_falls_back_to_research_then_merges_llm() -> None:
    """With no belegt set, the read research is the deterministic base, still merged with LLM extras."""
    si = _si(research=[FetchedContent(url="https://ft.com/a", title="FT", text="t")])
    response = json.dumps(
        {"title": "T", "bottom_line": "BL", "sections": [], "sources": [{"url": "https://llm.example/z"}]}
    )
    out = synthesize(_CaptureClient(response), si)  # type: ignore[arg-type]
    urls = [r.url for r in out.sources]
    assert "https://ft.com/a" in urls  # research fallback
    assert "https://llm.example/z" in urls  # LLM extra merged


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
