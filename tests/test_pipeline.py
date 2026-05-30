"""Tests for the agent pipeline (core/pipeline.py).

The LLM is scripted (responses keyed on the system prompt) and the research engine is a fake
async stub, so the full reasoning chain runs offline and deterministically.
"""

from __future__ import annotations

from typing import Any

from core.config import AppConfig
from core.pipeline import AutoInteraction, plan_subqueries, run_pipeline
from models.research import FetchedContent, ResearchBundle
from models.task import EffortLevel, Intent, Language, OutputFormat, TaskRequest, TaskType


class _ScriptedClient:
    """Returns a canned response chosen by which stage's system prompt is in use."""

    def __init__(
        self, *, intent: str, subqueries: str, analysis: str, quick: str = "QUICK"
    ) -> None:
        self.intent = intent
        self.subqueries = subqueries
        self.analysis = analysis
        self.quick = quick
        self.systems: list[str] = []

    def generate(self, prompt: str, system: str = "", use_thinking: Any = None, **kw: Any) -> str:
        self.systems.append(system)
        lowered = system.lower()
        if "intent classifier" in lowered:
            return self.intent
        if "decompose" in lowered:
            return self.subqueries
        if "senior strategy analyst" in lowered:
            return self.analysis
        return self.quick


class _FakeEngine:
    """Async research engine stub returning a fixed bundle and recording calls."""

    def __init__(self, bundle: ResearchBundle) -> None:
        self.bundle = bundle
        self.calls: list[tuple[str, list[str] | None, int | None]] = []

    async def run(
        self, query: str, sub_queries: list[str] | None = None, max_fetch: int | None = None
    ) -> ResearchBundle:
        self.calls.append((query, sub_queries, max_fetch))
        return self.bundle


def _bundle() -> ResearchBundle:
    return ResearchBundle(
        query="q",
        sub_queries=["a", "b"],
        fetched=[FetchedContent(url="https://reuters.com/a", text="evidence", word_count=1)],
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
    """A confirmed run decomposes, researches, and synthesizes a structured analysis."""
    client = _ScriptedClient(
        intent='{"task_type":"competitor_analysis","depth":"standard","audience":"strategy_team","summary":"Analyze 1X"}',  # noqa: E501
        subqueries='["1X funding", "1X technology", "1X team"]',
        analysis='{"title":"1X Brief","bottom_line":"BL","sections":[{"heading":"Tech","body":"x"}],"sources":[{"url":"https://reuters.com/a","tier":"tier_1"}]}',  # noqa: E501
    )
    engine = _FakeEngine(_bundle())
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        AppConfig(),
        TaskRequest(raw_input="Analyze 1X Technologies"),
        AutoInteraction(),
        engine=engine,  # type: ignore[arg-type]
    )
    assert result.declined is False
    assert result.analysis is not None
    assert result.analysis.title == "1X Brief"
    assert result.routed_formats == [OutputFormat.BRIEF]
    assert engine.calls[0][1] == ["1X funding", "1X technology", "1X team"]


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
        engine=_FakeEngine(_bundle()),  # type: ignore[arg-type]
    )
    assert result.routed_formats == [OutputFormat.DECK, OutputFormat.EXCEL]
    assert result.analysis is not None


def test_run_pipeline_decline_gives_quick_answer() -> None:
    """Declining the research plan returns a brain-based quick answer; research is skipped."""
    client = _ScriptedClient(
        intent='{"task_type":"industry_news","depth":"quick","audience":null,"summary":"news"}',
        subqueries='["humanoid news"]',
        analysis="{}",
        quick="Here is a quick take.",
    )
    engine = _FakeEngine(_bundle())
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        AppConfig(),
        TaskRequest(raw_input="Latest humanoid robotics news?"),
        AutoInteraction(accept=False),
        engine=engine,  # type: ignore[arg-type]
    )
    assert result.declined is True
    assert result.quick_answer == "Here is a quick take."
    assert result.analysis is None
    assert engine.calls == []  # research never ran


def test_run_pipeline_preserves_german() -> None:
    """German input → German intent and German analysis."""
    client = _ScriptedClient(
        intent='{"task_type":"market_analysis","depth":"standard","audience":"strategy_team","summary":"Markt"}',
        subqueries='["markt groesse"]',
        analysis='{"title":"M","bottom_line":"b","sections":[],"sources":[]}',
    )
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        AppConfig(),
        TaskRequest(raw_input="Marktanalyse Humanoid Robotics für uns"),
        AutoInteraction(),
        engine=_FakeEngine(_bundle()),  # type: ignore[arg-type]
    )
    assert result.intent.language == Language.DE
    assert result.analysis is not None
    assert result.analysis.language == Language.DE


def test_run_pipeline_low_effort_caps_clarifications() -> None:
    """A low-effort task tightens the clarification budget (effort master dial drives it)."""
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
        engine=_FakeEngine(_bundle()),  # type: ignore[arg-type]
    )
    assert result.intent.effort == EffortLevel.LOW  # "quick"/"overview" → low
    # low.max_clarifications == 1, so at most one question is asked (vs. 2 at high).
    assert len(result.answered) <= 1


# ------------------------------------------------------------ sub-queries
def test_plan_subqueries_parses_and_falls_back() -> None:
    """plan_subqueries parses a JSON array and falls back to the raw task on bad output."""
    good = _ScriptedClient(intent="{}", subqueries='["a", "b", "c"]', analysis="{}")
    plan = plan_subqueries(good, AppConfig(), _intent(), TaskRequest(raw_input="X"))  # type: ignore[arg-type]
    assert plan.sub_questions == ["a", "b", "c"]
    assert "Go?" in plan.summary

    bad = _ScriptedClient(intent="{}", subqueries="not json at all", analysis="{}")
    plan2 = plan_subqueries(bad, AppConfig(), _intent(), TaskRequest(raw_input="My task"))  # type: ignore[arg-type]
    assert plan2.sub_questions == ["My task"]


def test_plan_summary_is_german_for_german_intent() -> None:
    """The plan confirmation line is localized to the intent language."""
    client = _ScriptedClient(intent="{}", subqueries='["a"]', analysis="{}")
    plan = plan_subqueries(
        client,  # type: ignore[arg-type]
        AppConfig(),
        _intent(language=Language.DE),
        TaskRequest(raw_input="Aufgabe"),
    )
    assert "Los?" in plan.summary
