"""Tests for the Phase-3.5 model contracts (effort, deep-research, critique).

Pure Pydantic construction tests — no LLM, no I/O. They lock the defaults that keep the
Phase-3 code paths valid while the advanced loop fills in the new fields.
"""

from __future__ import annotations

from models.research import (
    Confidence,
    CoverageGap,
    CoverageReport,
    FetchedContent,
    Finding,
    ResearchReport,
    WorkerFindings,
)
from models.synthesis import CriterionResult, Critique, PipelineResult
from models.task import (
    ClarificationRound,
    EffortLevel,
    Intent,
    Language,
    OutputFormat,
    TaskType,
)


def _intent() -> Intent:
    return Intent(
        task_type=TaskType.COMPETITOR_ANALYSIS,
        output_formats=[OutputFormat.BRIEF],
        language=Language.EN,
    )


# --- effort ------------------------------------------------------------------------------
def test_effort_level_values() -> None:
    """EffortLevel is a StrEnum with the three master-dial levels."""
    assert {e.value for e in EffortLevel} == {"low", "high", "ultra"}
    assert EffortLevel.HIGH == "high"  # StrEnum equals its string value (used by level_for)


def test_intent_defaults_to_high_effort() -> None:
    """A freshly parsed Intent is never silently shallow — defaults to HIGH (RULE 9)."""
    assert _intent().effort == EffortLevel.HIGH


# --- deep-research contracts -------------------------------------------------------------
def test_finding_carries_source_date_confidence() -> None:
    """Every Finding carries provenance: source + date + confidence + recency flag."""
    f = Finding(
        claim="1X raised $100M",
        source_url="https://reuters.com/x",
        date="2026-03",
        confidence=Confidence.HIGH,
        recency_flag=None,
    )
    assert f.confidence == Confidence.HIGH
    assert f.source_url.startswith("https://")
    # defaults: medium confidence, no date
    assert Finding(claim="x").confidence == Confidence.MEDIUM


def test_worker_findings_and_report_aggregate() -> None:
    """ResearchReport aggregates worker findings, evidence, and telemetry."""
    wf = WorkerFindings(
        sub_topic="funding",
        queries=["1X funding 2026"],
        findings=[Finding(claim="raised $100M", confidence=Confidence.HIGH)],
        sources=[FetchedContent(url="https://reuters.com/x", text="t")],
        gaps=["valuation unconfirmed"],
        confidence=Confidence.HIGH,
    )
    report = ResearchReport(
        query="Analyze 1X",
        sub_topics=["funding", "technology"],
        worker_findings=[wf],
        evidence=[FetchedContent(url="https://reuters.com/x", text="t")],
        rounds_used=2,
        workers_used=3,
        sources_evaluated=12,
        midresearch=[ClarificationRound(question="Which segment?", answer="industrial")],
        coverage=CoverageReport(covered=False, gaps=[CoverageGap(sub_topic="team", issue="thin")]),
    )
    assert report.workers_used == 3
    assert report.worker_findings[0].findings[0].claim == "raised $100M"
    assert report.midresearch[0].answer == "industrial"
    assert report.coverage is not None and report.coverage.covered is False


def test_research_report_defaults_are_empty() -> None:
    """An empty ResearchReport is valid (advisory layers fail open to an empty report)."""
    report = ResearchReport()
    assert report.worker_findings == []
    assert report.sources_evaluated == 0
    assert report.coverage is None


# --- critique ----------------------------------------------------------------------------
def test_critique_and_criterion() -> None:
    """Critique holds a score, issues, and per-criterion verdicts."""
    crit = Critique(
        passed=False,
        score=60,
        issues=["financials single-sourced"],
        criteria=[CriterionResult(name="sourcing", passed=False, comment="needs 2 sources")],
        summary="Revise sourcing.",
    )
    assert crit.passed is False
    assert crit.criteria[0].name == "sourcing"


# --- pipeline result back-compat ---------------------------------------------------------
def test_pipeline_result_phase3_construction_still_valid() -> None:
    """A Phase-3-style PipelineResult (no 3.5 fields) constructs with safe defaults."""
    result = PipelineResult(intent=_intent(), routed_formats=[OutputFormat.BRIEF])
    assert result.effort == EffortLevel.HIGH
    assert result.critique is None
    assert result.revisions == 0
    assert result.research_report is None
