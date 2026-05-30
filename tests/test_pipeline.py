"""Tests for the agent pipeline (core/pipeline.py).

The LLM is scripted (responses keyed on the stage's system prompt) and the research manager is a
fake async stub, so the full advanced loop runs offline and deterministically.
"""

from __future__ import annotations

from typing import Any

from core.config import AppConfig
from core.pipeline import AutoInteraction, plan_subqueries, run_pipeline
from models.research import (
    Confidence,
    FetchedContent,
    Finding,
    ResearchReport,
    WorkerFindings,
)
from models.task import EffortLevel, Intent, Language, OutputFormat, TaskRequest, TaskType

_PASS_CRITIQUE = '{"score": 90, "criteria": [], "issues": [], "summary": "Strong."}'


class _ScriptedClient:
    """Returns a canned response chosen by which stage's system prompt is in use."""

    def __init__(
        self,
        *,
        intent: str,
        subqueries: str = "[]",
        analysis: str = "{}",
        quick: str = "QUICK",
        critiques: list[str] | None = None,
    ) -> None:
        self.intent = intent
        self.subqueries = subqueries
        self.analysis = analysis
        self.quick = quick
        self._critiques = list(critiques or [_PASS_CRITIQUE])
        self.systems: list[str] = []

    def generate(self, prompt: str, system: str = "", use_thinking: Any = None, **kw: Any) -> str:
        self.systems.append(system)
        lowered = system.lower()
        if "intent classifier" in lowered:
            return self.intent
        if "editorial critic" in lowered:
            # Consume critiques in order, then keep returning the last one.
            return self._critiques.pop(0) if len(self._critiques) > 1 else self._critiques[0]
        if "decompose" in lowered:
            return self.subqueries
        if "senior strategy analyst" in lowered:
            return self.analysis
        return self.quick


class _FakeManager:
    """Async research-manager stub returning a fixed report and recording the effort it ran at."""

    def __init__(self, report: ResearchReport) -> None:
        self.report = report
        self.efforts: list[EffortLevel] = []

    async def run(
        self,
        client: Any,
        config: Any,
        intent: Intent,
        plan: Any,
        interaction: Any,
        effort_cfg: Any,
        searx: Any = None,
        fetcher: Any = None,
    ) -> ResearchReport:
        self.efforts.append(intent.effort)
        return self.report


def _report() -> ResearchReport:
    return ResearchReport(
        query="Analyze 1X",
        sub_topics=["funding", "technology", "team"],
        worker_findings=[
            WorkerFindings(
                sub_topic="funding",
                findings=[
                    Finding(
                        claim="1X raised $100M",
                        source_url="https://reuters.com/a",
                        date="2026-01",
                        confidence=Confidence.HIGH,
                    )
                ],
                sources=[FetchedContent(url="https://reuters.com/a", text="evidence")],
            )
        ],
        evidence=[FetchedContent(url="https://reuters.com/a", text="evidence", word_count=1)],
        rounds_used=2,
        workers_used=3,
        sources_evaluated=12,
    )


def _intent(**kw: Any) -> Intent:
    base: dict[str, Any] = {
        "task_type": TaskType.COMPETITOR_ANALYSIS,
        "output_formats": [OutputFormat.BRIEF],
        "language": Language.EN,
        "summary": "Analyze 1X",
    }
    base.update(kw)
    return Intent(**base)


# ----------------------------------------------------------------- full run
def test_run_pipeline_full_analysis() -> None:
    """A confirmed run researches via the manager, synthesizes, critiques, and reports telemetry."""
    client = _ScriptedClient(
        intent='{"task_type":"competitor_analysis","depth":"standard","audience":"strategy_team","summary":"Analyze 1X"}',  # noqa: E501
        subqueries='["1X funding", "1X technology", "1X team"]',
        analysis='{"title":"1X Brief","bottom_line":"BL","sections":[{"heading":"Tech","body":"x"}],"sources":[{"url":"https://reuters.com/a","tier":"tier_1"}]}',  # noqa: E501
    )
    manager = _FakeManager(_report())
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        AppConfig(),
        TaskRequest(raw_input="Analyze 1X Technologies"),
        AutoInteraction(),
        manager=manager,  # type: ignore[arg-type]
    )
    assert result.declined is False
    assert result.analysis is not None
    assert result.analysis.title == "1X Brief"
    assert result.routed_formats == [OutputFormat.BRIEF]
    # Effort auto-detected (no keyword / hint) → HIGH default; the manager ran at that effort.
    assert result.effort == EffortLevel.HIGH
    assert manager.efforts == [EffortLevel.HIGH]
    # Telemetry + a passing critique flow into the result.
    assert result.research_report is not None
    assert result.research_report.workers_used == 3
    assert result.critique is not None and result.critique.passed
    assert result.revisions == 0


def test_run_pipeline_business_case_dual_output() -> None:
    """A business case routes to the dual Deck + Excel output and still synthesizes."""
    client = _ScriptedClient(
        intent='{"task_type":"business_case","depth":"deep","audience":"ceo_board","summary":"Japan BC"}',  # noqa: E501
        subqueries='["japan market size", "japan robotics demand"]',
        analysis='{"title":"BC","bottom_line":"b","sections":[],"sources":[]}',
    )
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        AppConfig(),
        TaskRequest(raw_input="Business case for Japan expansion: market size, investment, ROI"),
        AutoInteraction(),
        manager=_FakeManager(_report()),  # type: ignore[arg-type]
    )
    assert result.routed_formats == [OutputFormat.DECK, OutputFormat.EXCEL]
    assert result.analysis is not None
    assert result.effort == EffortLevel.HIGH  # business_case floors at HIGH


def test_run_pipeline_decline_gives_quick_answer() -> None:
    """Declining the research plan returns a brain-based quick answer; research is skipped."""
    client = _ScriptedClient(
        intent='{"task_type":"industry_news","depth":"quick","audience":null,"summary":"news"}',
        subqueries='["humanoid news"]',
        quick="Here is a quick take.",
    )
    manager = _FakeManager(_report())
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        AppConfig(),
        TaskRequest(raw_input="Latest humanoid robotics news?"),
        AutoInteraction(accept=False),
        manager=manager,  # type: ignore[arg-type]
    )
    assert result.declined is True
    assert result.quick_answer == "Here is a quick take."
    assert result.analysis is None
    assert manager.efforts == []  # research never ran


def test_run_pipeline_preserves_german() -> None:
    """German input → German intent and German analysis."""
    client = _ScriptedClient(
        intent='{"task_type":"market_analysis","depth":"standard","audience":"strategy_team","summary":"Markt"}',  # noqa: E501
        subqueries='["markt groesse"]',
        analysis='{"title":"M","bottom_line":"b","sections":[],"sources":[]}',
    )
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        AppConfig(),
        TaskRequest(raw_input="Marktanalyse Humanoid Robotics für uns"),
        AutoInteraction(),
        manager=_FakeManager(_report()),  # type: ignore[arg-type]
    )
    assert result.intent.language == Language.DE
    assert result.analysis is not None
    assert result.analysis.language == Language.DE


def test_run_pipeline_low_effort_caps_and_skips_critique() -> None:
    """A low-effort task tightens clarifications AND skips the critic (effort master dial)."""
    client = _ScriptedClient(
        intent='{"task_type":"competitor_analysis","depth":"quick","audience":null,"summary":"x"}',
        subqueries='["a"]',
        analysis='{"title":"t","bottom_line":"b","sections":[],"sources":[]}',
    )
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        AppConfig(),
        TaskRequest(raw_input="quick competitor overview of Figure AI"),
        AutoInteraction(),
        manager=_FakeManager(_report()),  # type: ignore[arg-type]
    )
    assert result.intent.effort == EffortLevel.LOW  # "quick"/"overview" → low
    assert len(result.answered) <= 1  # low.max_clarifications == 1
    assert result.critique is None  # low disables critique
    assert result.revisions == 0


def test_run_pipeline_effort_override_wins() -> None:
    """An explicit effort_override beats auto-detection (the manager runs at the override)."""
    client = _ScriptedClient(
        intent='{"task_type":"competitor_analysis","depth":"standard","audience":null,"summary":"x"}',
        subqueries='["a"]',
        analysis='{"title":"t","bottom_line":"b","sections":[],"sources":[]}',
    )
    manager = _FakeManager(_report())
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        AppConfig(),
        TaskRequest(raw_input="quick overview of Figure AI"),  # would auto-detect LOW
        AutoInteraction(),
        manager=manager,  # type: ignore[arg-type]
        effort_override=EffortLevel.ULTRA,
    )
    assert result.effort == EffortLevel.ULTRA
    assert manager.efforts == [EffortLevel.ULTRA]


def test_run_pipeline_critique_triggers_revision() -> None:
    """A failing critique drives a bounded revision loop until it passes (evaluator-optimizer)."""
    fail = '{"score": 55, "criteria": [], "issues": ["add a second funding source"], "summary": "weak"}'  # noqa: E501
    client = _ScriptedClient(
        intent='{"task_type":"competitor_analysis","depth":"standard","audience":null,"summary":"x"}',
        subqueries='["a"]',
        analysis='{"title":"1X","bottom_line":"b","sections":[{"heading":"h","body":"x"}],"sources":[{"url":"https://reuters.com/a"}]}',  # noqa: E501
        critiques=[fail, _PASS_CRITIQUE],
    )
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        AppConfig(),
        TaskRequest(raw_input="Analyze 1X Technologies"),  # HIGH effort → critique on, 1 revision
        AutoInteraction(),
        manager=_FakeManager(_report()),  # type: ignore[arg-type]
    )
    assert result.revisions == 1
    assert result.critique is not None and result.critique.passed
    assert result.critique.score == 90


def test_auto_interaction_ask_text() -> None:
    """AutoInteraction.ask_text replays canned answers then returns "" (assume-and-proceed)."""
    auto = AutoInteraction(text_answers=["industrial"])
    assert auto.ask_text("Which segment?") == "industrial"
    assert auto.ask_text("Anything else?") == ""  # exhausted → empty (caller assumes)
    assert auto.asked_text == ["Which segment?", "Anything else?"]


# ------------------------------------------------------------ sub-queries
def test_plan_subqueries_parses_and_falls_back() -> None:
    """plan_subqueries parses a JSON array and falls back to the raw task on bad output."""
    good = _ScriptedClient(intent="{}", subqueries='["a", "b", "c"]')
    plan = plan_subqueries(good, AppConfig(), _intent(), TaskRequest(raw_input="X"))  # type: ignore[arg-type]
    assert plan.sub_questions == ["a", "b", "c"]
    assert "Go?" in plan.summary

    bad = _ScriptedClient(intent="{}", subqueries="not json at all")
    plan2 = plan_subqueries(bad, AppConfig(), _intent(), TaskRequest(raw_input="My task"))  # type: ignore[arg-type]
    assert plan2.sub_questions == ["My task"]


def test_plan_summary_surfaces_effort_and_language() -> None:
    """The plan confirmation line is localized and surfaces the effort level (SPEC §15.5)."""
    client = _ScriptedClient(intent="{}", subqueries='["a"]')
    plan = plan_subqueries(
        client,  # type: ignore[arg-type]
        AppConfig(),
        _intent(language=Language.DE, effort=EffortLevel.ULTRA),
        TaskRequest(raw_input="Aufgabe"),
    )
    assert "Los?" in plan.summary
    assert "ultra" in plan.summary  # effort surfaced in the plan
