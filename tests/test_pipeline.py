"""Tests for the agent pipeline (core/pipeline.py).

The LLM is scripted (responses keyed on the stage's system prompt) and the research manager is a
fake async stub, so the full advanced loop runs offline and deterministically.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import AppConfig
from core.memory import MemoryLayerError, MemoryRecord
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
        entities: str = "[]",
        delta: str = "DELTA-BODY",
        propose: str = "[]",
        scoping: str = "[]",
    ) -> None:
        self.intent = intent
        self.subqueries = subqueries
        self.analysis = analysis
        self.quick = quick
        self._critiques = list(critiques or [_PASS_CRITIQUE])
        self.entities = entities
        self.delta = delta
        self.propose = propose
        self.scoping = scoping
        self.systems: list[str] = []
        self.prompts: list[str] = []

    def generate(self, prompt: str, system: str = "", use_thinking: Any = None, **kw: Any) -> str:
        self.systems.append(system)
        self.prompts.append(prompt)
        lowered = system.lower()
        if "intent classifier" in lowered:
            return self.intent
        if "editorial critic" in lowered:
            # Consume critiques in order, then keep returning the last one.
            return self._critiques.pop(0) if len(self._critiques) > 1 else self._critiques[0]
        if "decompose" in lowered:
            return self.subqueries
        if "named entities" in lowered:
            return self.entities
        if "compare a prior analysis" in lowered or "vergleichst" in lowered:
            return self.delta
        if "maintain brain.md" in lowered:
            return self.propose
        if "intake strategist" in lowered:
            return self.scoping
        if "senior strategy analyst" in lowered:
            return self.analysis
        return self.quick

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(len(t) % 7), 1.0, 0.0] for t in texts]


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


def _config(tmp_path: Path) -> AppConfig:
    """An AppConfig whose deliverables are written under ``tmp_path`` (never pollute ./output)."""
    config = AppConfig()
    config.output.output_dir = str(tmp_path)
    return config


# ----------------------------------------------------------------- full run
def test_run_pipeline_full_analysis(tmp_path: Path) -> None:
    """A confirmed run researches via the manager, synthesizes, critiques, and reports telemetry."""
    client = _ScriptedClient(
        intent='{"task_type":"competitor_analysis","depth":"standard","audience":"strategy_team","summary":"Analyze 1X"}',  # noqa: E501
        subqueries='["1X funding", "1X technology", "1X team"]',
        analysis='{"title":"1X Brief","bottom_line":"BL","sections":[{"heading":"Tech","body":"x"}],"sources":[{"url":"https://reuters.com/a","tier":"tier_1"}]}',  # noqa: E501
    )
    manager = _FakeManager(_report())
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        _config(tmp_path),
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


def test_run_pipeline_scoping_guidance_shapes_research_and_synthesis(tmp_path: Path) -> None:
    """A situation-specific scoping question is asked; its answer steers research AND synthesis."""
    client = _ScriptedClient(
        intent='{"task_type":"competitor_analysis","depth":"standard","audience":"strategy_team","summary":"Assess Figure AI"}',  # noqa: E501
        subqueries='["Figure AI commercial traction"]',
        analysis='{"title":"Figure","bottom_line":"BL","sections":[{"heading":"h","body":"x"}],"sources":[{"url":"https://reuters.com/a"}]}',  # noqa: E501
        scoping='["For Figure AI, does the tech moat or the commercial traction matter more?"]',
    )
    interaction = AutoInteraction(text_answers=["commercial traction and the BMW deal"])
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        _config(tmp_path),
        TaskRequest(raw_input="Assess Figure AI as a competitor"),
        interaction,
        manager=_FakeManager(_report()),  # type: ignore[arg-type]
    )
    # The generated, task-specific question was asked and recorded with the user's answer — and the
    # generic format/audience triple was suppressed (no checklist piled on top of the sharp one).
    assert len(result.answered) == 1
    assert "Figure AI" in (result.answered[0].question or "")
    assert result.answered[0].answer == "commercial traction and the BMW deal"
    # The guidance reached BOTH the sub-query planner and the synthesizer's user prompt.
    subq_prompts = [p for p in client.prompts if "sub-queries" in p]
    assert subq_prompts and "commercial traction and the BMW deal" in subq_prompts[0]
    synth_prompts = [
        p
        for p, s in zip(client.prompts, client.systems, strict=True)
        if "senior strategy analyst" in s.lower()
    ]
    assert synth_prompts and "commercial traction and the BMW deal" in synth_prompts[0]


def test_run_pipeline_routing_fallback_when_self_check_is_silent(tmp_path: Path) -> None:
    """When the self-check has enough context (asks nothing), the format/audience triple still runs
    as a fallback so packaging is never left unresolved."""
    client = _ScriptedClient(
        intent='{"task_type":"competitor_analysis","depth":"standard","audience":null,"summary":"x"}',
        subqueries='["a"]',
        analysis='{"title":"t","bottom_line":"b","sections":[{"heading":"h","body":"x"}],"sources":[{"url":"https://reuters.com/a"}]}',  # noqa: E501
        scoping="[]",  # self-check decides it already has enough → asks nothing
    )
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        _config(tmp_path),
        TaskRequest(raw_input="Analyze Figure AI"),  # no explicit format keyword
        AutoInteraction(),  # ask_choice → first scope option (Quick brief)
        manager=_FakeManager(_report()),  # type: ignore[arg-type]
    )
    # The fallback triple fired (exactly one routing round) and resolved packaging to a brief.
    assert len(result.answered) == 1
    assert result.routed_formats == [OutputFormat.BRIEF]


def test_run_pipeline_business_case_dual_output(tmp_path: Path) -> None:
    """A business case routes to Deck + Excel AND renders both files in one run (N-6)."""
    client = _ScriptedClient(
        intent='{"task_type":"business_case","depth":"deep","audience":"ceo_board","summary":"Japan BC"}',  # noqa: E501
        subqueries='["japan market size", "japan robotics demand"]',
        analysis='{"title":"BC","bottom_line":"b","sections":[],"sources":[]}',
    )
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        _config(tmp_path),
        TaskRequest(raw_input="Business case for Japan expansion: market size, investment, ROI"),
        AutoInteraction(),
        manager=_FakeManager(_report()),  # type: ignore[arg-type]
    )
    assert result.routed_formats == [OutputFormat.DECK, OutputFormat.EXCEL]
    assert result.analysis is not None
    assert result.effort == EffortLevel.HIGH  # business_case floors at HIGH
    # N-6: both deliverables generated in one run (shaping falls back deterministically offline).
    suffixes = sorted(p.suffix for p in result.output_files)
    assert suffixes == [".pptx", ".xlsx"]
    assert all(p.exists() for p in result.output_files)


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


def test_run_pipeline_preserves_german(tmp_path: Path) -> None:
    """German input → German intent and German analysis."""
    client = _ScriptedClient(
        intent='{"task_type":"market_analysis","depth":"standard","audience":"strategy_team","summary":"Markt"}',  # noqa: E501
        subqueries='["markt groesse"]',
        analysis='{"title":"M","bottom_line":"b","sections":[],"sources":[]}',
    )
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        _config(tmp_path),
        TaskRequest(raw_input="Marktanalyse Humanoid Robotics für uns"),
        AutoInteraction(),
        manager=_FakeManager(_report()),  # type: ignore[arg-type]
    )
    assert result.intent.language == Language.DE
    assert result.analysis is not None
    assert result.analysis.language == Language.DE


def test_run_pipeline_low_effort_caps_and_skips_critique(tmp_path: Path) -> None:
    """A low-effort task tightens clarifications AND skips the critic (effort master dial)."""
    client = _ScriptedClient(
        intent='{"task_type":"competitor_analysis","depth":"quick","audience":null,"summary":"x"}',
        subqueries='["a"]',
        analysis='{"title":"t","bottom_line":"b","sections":[],"sources":[]}',
    )
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        _config(tmp_path),
        TaskRequest(raw_input="quick competitor overview of Figure AI"),
        AutoInteraction(),
        manager=_FakeManager(_report()),  # type: ignore[arg-type]
    )
    assert result.intent.effort == EffortLevel.LOW  # "quick"/"overview" → low
    assert len(result.answered) <= 1  # low.max_clarifications == 1
    assert result.critique is None  # low disables critique
    assert result.revisions == 0


def test_run_pipeline_effort_override_wins(tmp_path: Path) -> None:
    """An explicit effort_override beats auto-detection (the manager runs at the override)."""
    client = _ScriptedClient(
        intent='{"task_type":"competitor_analysis","depth":"standard","audience":null,"summary":"x"}',
        subqueries='["a"]',
        analysis='{"title":"t","bottom_line":"b","sections":[],"sources":[]}',
    )
    manager = _FakeManager(_report())
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        _config(tmp_path),
        TaskRequest(raw_input="quick overview of Figure AI"),  # would auto-detect LOW
        AutoInteraction(),
        manager=manager,  # type: ignore[arg-type]
        effort_override=EffortLevel.ULTRA,
    )
    assert result.effort == EffortLevel.ULTRA
    assert manager.efforts == [EffortLevel.ULTRA]


def test_run_pipeline_critique_triggers_revision(tmp_path: Path) -> None:
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
        _config(tmp_path),
        TaskRequest(raw_input="Analyze 1X Technologies"),  # HIGH effort → critique on, 1 revision
        AutoInteraction(),
        manager=_FakeManager(_report()),  # type: ignore[arg-type]
    )
    assert result.revisions == 1
    assert result.critique is not None and result.critique.passed
    assert result.critique.score == 90


class _FakeMemoryStore:
    """Records writes and returns canned priors (duck-typed for the real ``recall`` function)."""

    def __init__(self, priors: list[MemoryRecord]) -> None:
        self._priors = priors
        self.written: list[MemoryRecord] = []

    def retrieve(self, query_text: str, top_k: int | None = None) -> list[MemoryRecord]:
        return list(self._priors)

    def write(self, record: MemoryRecord) -> None:
        self.written.append(record)


class _BrokenMemoryStore:
    """A store that fails on every op — exercises the fail-open path (never blocks delivery)."""

    def retrieve(self, query_text: str, top_k: int | None = None) -> list[MemoryRecord]:
        raise MemoryLayerError("boom")

    def write(self, record: MemoryRecord) -> None:
        raise MemoryLayerError("boom")


def _prior_record() -> MemoryRecord:
    return MemoryRecord(
        record_id="r1",
        document="1X Technologies raised $100M in early 2025; focused on consumer humanoids.",
        title="1X Brief",
        entities=["1X Technologies"],
        task_type="competitor_analysis",
        language="en",
        timestamp="2026-05-11",
        quality_score=88,
    )


def test_run_pipeline_memory_delta_inject_and_write(tmp_path: Path) -> None:
    """Memory: a same-entity prior drives a delta, injects priors, and the run is written."""
    client = _ScriptedClient(
        intent='{"task_type":"competitor_analysis","depth":"standard","audience":"strategy_team","summary":"Analyze 1X"}',  # noqa: E501
        subqueries='["1X funding"]',
        analysis='{"title":"1X Brief","bottom_line":"BL","sections":[{"heading":"Funding","body":"x"}],"sources":[{"url":"https://reuters.com/a","tier":"tier_1"}]}',  # noqa: E501
        entities='["1X Technologies"]',
        delta="Funding doubled and a Tier-1 customer signed since the last analysis.",
        propose='["1X Technologies is a high-priority watch target"]',
    )
    store = _FakeMemoryStore([_prior_record()])
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        _config(tmp_path),
        TaskRequest(raw_input="Analyze 1X Technologies"),
        AutoInteraction(),
        manager=_FakeManager(_report()),  # type: ignore[arg-type]
        memory=store,  # type: ignore[arg-type]
    )
    # Delta surfaced, naming the entity + the prior date.
    assert result.delta_note is not None
    assert result.delta_note.startswith("Since our last analysis of 1X Technologies")
    assert "2026-05-11" in result.delta_note
    assert "Funding doubled" in result.delta_note
    # Prior findings reached synthesis (injected into the user prompt).
    synth_prompts = [
        p
        for p, s in zip(client.prompts, client.systems, strict=True)
        if "senior strategy analyst" in s.lower()
    ]  # noqa: E501
    assert synth_prompts and "PRIOR FINDINGS" in synth_prompts[0]
    # The run was written to memory with its entities + a quality score.
    assert len(store.written) == 1
    assert store.written[0].entities == ["1X Technologies"]
    assert store.written[0].quality_score == 90  # passing critique score
    # Brain-update proposals surfaced for the REPL to confirm.
    assert result.proposed_brain_additions == ["1X Technologies is a high-priority watch target"]


def test_run_pipeline_memory_fail_open(tmp_path: Path) -> None:
    """A broken memory store never blocks delivery — the analysis still ships, delta is None."""
    client = _ScriptedClient(
        intent='{"task_type":"competitor_analysis","depth":"standard","audience":null,"summary":"x"}',
        subqueries='["a"]',
        analysis='{"title":"t","bottom_line":"b","sections":[{"heading":"h","body":"x"}],"sources":[{"url":"https://reuters.com/a"}]}',  # noqa: E501
    )
    result = run_pipeline(
        client,  # type: ignore[arg-type]
        _config(tmp_path),
        TaskRequest(raw_input="Analyze 1X Technologies"),
        AutoInteraction(),
        manager=_FakeManager(_report()),  # type: ignore[arg-type]
        memory=_BrokenMemoryStore(),  # type: ignore[arg-type]
    )
    assert result.analysis is not None  # delivered despite the broken store
    assert result.delta_note is None


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
