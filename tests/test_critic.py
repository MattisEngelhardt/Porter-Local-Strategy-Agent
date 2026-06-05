"""Tests for the output critic + revision loop (core/critic.py). LLM calls are faked (offline)."""

from __future__ import annotations

from typing import Any

from core.critic import critique, revise
from core.playbooks import load_playbooks
from llm.local_llm_client import LLMError
from models.synthesis import AnalysisOutput, Critique, Section, SourceRef, SynthesisInput
from models.task import Intent, Language, OutputFormat, TaskType


class _Client:
    """Returns a fixed response and records generate() kwargs."""

    num_ctx = 32768

    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def generate(self, prompt: str, system: str = "", use_thinking: Any = None, **kw: Any) -> str:
        self.calls.append({"prompt": prompt, "system": system, "use_thinking": use_thinking})
        return self.response


class _RaiseClient:
    num_ctx = 32768

    def generate(self, prompt: str, **kw: Any) -> str:
        raise LLMError("backend down")


def _intent() -> Intent:
    return Intent(
        task_type=TaskType.COMPETITOR_ANALYSIS,
        output_formats=[OutputFormat.BRIEF],
        language=Language.EN,
        summary="Analyze 1X",
    )


def _analysis(title: str = "1X Brief") -> AnalysisOutput:
    return AnalysisOutput(
        title=title,
        language=Language.EN,
        bottom_line="Bottom line.",
        sections=[Section(heading="Tech", body="moat")],
        sources=[SourceRef(url="https://reuters.com/a")],
    )


def _si() -> SynthesisInput:
    return SynthesisInput(intent=_intent())


# ------------------------------------------------------------------ critique
def test_critique_passes_above_threshold() -> None:
    """A high score (>= min_score) yields a passing critique with parsed criteria."""
    client = _Client(
        '{"score": 88, "criteria": [{"name": "sourced", "passed": true, "comment": "ok"}], '
        '"issues": [], "summary": "Strong."}'
    )
    result = critique(client, _intent(), _analysis(), load_playbooks(), min_score=75)  # type: ignore[arg-type]
    assert result.passed is True
    assert result.score == 88
    assert result.criteria[0].name == "sourced"
    assert client.calls[0]["use_thinking"] is True  # critic always thinks


def test_critique_fails_below_threshold() -> None:
    """A low score (< min_score) fails and surfaces concrete issues to fix."""
    client = _Client(
        '{"score": 55, "criteria": [], "issues": ["financials single-sourced", "no Neura lens"], '
        '"summary": "Needs work."}'
    )
    result = critique(client, _intent(), _analysis(), load_playbooks(), min_score=75)  # type: ignore[arg-type]
    assert result.passed is False
    assert result.score == 55
    assert "financials single-sourced" in result.issues


def test_critique_fail_open_on_llm_error() -> None:
    """An LLM error yields a passing 'critic unavailable' critique (never blocks delivery)."""
    result = critique(_RaiseClient(), _intent(), _analysis(), load_playbooks(), min_score=75)  # type: ignore[arg-type]
    assert result.passed is True
    assert "unavailable" in result.summary


def test_critique_fail_open_on_bad_json() -> None:
    """Unparseable critic output is treated as passing (fail-open)."""
    result = critique(_Client("not json"), _intent(), _analysis(), load_playbooks(), min_score=75)  # type: ignore[arg-type]
    assert result.passed is True
    assert "unavailable" in result.summary


def test_critique_clamps_garbage_score() -> None:
    """A non-numeric / out-of-range score is clamped (defaults low → fails)."""
    client = _Client('{"score": "lol", "criteria": [], "issues": ["x"], "summary": "s"}')
    result = critique(client, _intent(), _analysis(), load_playbooks(), min_score=75)  # type: ignore[arg-type]
    assert 0 <= result.score <= 100
    assert result.passed is False


# ------------------------------------------------------------------ revise
def test_revise_produces_improved_analysis() -> None:
    """revise reuses the synthesis path and returns the rewritten analysis."""
    client = _Client(
        '{"title": "1X Brief v2", "bottom_line": "Improved.", '
        '"sections": [{"heading": "Tech", "body": "stronger moat, sourced"}], '
        '"sources": [{"url": "https://reuters.com/a", "tier": "tier_1"}]}'
    )
    crit = Critique(passed=False, score=55, issues=["add a second funding source"])
    out = revise(client, _intent(), _analysis(), crit, _si(), load_playbooks())  # type: ignore[arg-type]
    assert out.title == "1X Brief v2"
    assert out.bottom_line == "Improved."
    # The revision prompt carries the prior draft and the concrete issue.
    assert "add a second funding source" in client.calls[0]["prompt"]
    assert client.calls[0]["use_thinking"] is True


def test_revise_fail_open_keeps_draft() -> None:
    """If the revision LLM call fails, the original draft is returned unchanged."""
    crit = Critique(passed=False, score=40, issues=["fix sourcing"])
    out = revise(_RaiseClient(), _intent(), _analysis("Keep Me"), crit, _si(), load_playbooks())  # type: ignore[arg-type]
    assert out.title == "Keep Me"
