"""Agent pipeline (Phase 3 + 3.5): the non-linear, self-correcting reasoning chain end-to-end.

Wires the master loop (SPEC §5.3 + §15.5):

    inject brain → parse intent + AUTO-DETECT effort → clarify (≤ effort budget) →
    research plan + effort shown → confirm (decline → brain quick answer) →
    ResearchManager.run(effort): decompose → N parallel workers → mid-research clarification →
    aggregated ResearchReport → synthesize (brain + playbooks + validated findings digest) →
    if effort.critique: critique → revise loop (≤ effort.revisions) → re-critique →
    quality-check (deterministic floor) → PipelineResult (analysis + effort + critique + telemetry)

Effort is the master dial: it sets every budget via ``config.effort.level_for(intent.effort)``.
Advisory layers (workers / critic) are fail-open; hard deps (SearXNG all-fail, LLM down) keep the
Phase-3 fail-fast policy. No output file is rendered (Phase 4); no ChromaDB memory (Phase 5).

Interaction with the user is abstracted behind :class:`Interaction` so the chain is pure and
testable: the REPL supplies a rich implementation (in ``core/intake.py``), CLI/tests supply the
headless :class:`AutoInteraction` here. This module imports no presentation library.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from core.clarification import clarify
from core.config import AppConfig, EffortLevelConfig
from core.critic import critique, revise
from core.intent_parser import parse_intent
from core.json_utils import extract_json_array
from core.memory import load_brain
from core.playbooks import load_playbooks
from core.research_agent import ResearchManager
from core.synthesizer import quality_check, synthesize
from llm.local_llm_client import LLMError, LocalLLMClient
from models.research import DocContent, ResearchReport
from models.synthesis import AnalysisOutput, Critique, PipelineResult, SynthesisInput
from models.task import EffortLevel, Intent, Language, OutputFormat, ResearchPlan, TaskRequest


class Interaction(Protocol):
    """How the pipeline talks to the user (REPL impl in intake.py; AutoInteraction for tests)."""

    def ask_choice(self, question: str, options: list[str]) -> str:
        """Ask a multiple-choice question and return the chosen answer (one word)."""
        ...

    def ask_text(self, question: str) -> str:
        """Ask a free-form, precise question (mid-research clarification) and return the answer.

        An empty string means "no answer" — the caller should log an assumption and proceed
        (mid-research clarification must never block delivery).
        """
        ...

    def confirm(self, prompt: str) -> bool:
        """Ask a yes/no question and return the decision."""
        ...

    def notify(self, message: str) -> None:
        """Show a progress/status message (no return)."""
        ...


class AutoInteraction:
    """Headless interaction: replays canned answers (then first option) and auto-confirms.

    Used by the non-interactive ``analyze`` CLI command and by tests.
    """

    def __init__(
        self,
        answers: list[str] | None = None,
        accept: bool = True,
        text_answers: list[str] | None = None,
    ) -> None:
        """Configure canned clarification + mid-research answers and the confirm decision."""
        self._answers = list(answers or [])
        self._text_answers = list(text_answers or [])
        self._accept = accept
        self.notes: list[str] = []
        self.asked_text: list[str] = []  # mid-research questions, inspectable in tests

    def ask_choice(self, question: str, options: list[str]) -> str:
        """Return the next canned answer, or the first option if none remain."""
        return self._answers.pop(0) if self._answers else options[0]

    def ask_text(self, question: str) -> str:
        """Return the next canned free-form answer, or "" (→ caller assumes and proceeds)."""
        self.asked_text.append(question)
        return self._text_answers.pop(0) if self._text_answers else ""

    def confirm(self, prompt: str) -> bool:
        """Return the preconfigured confirm decision."""
        return self._accept

    def notify(self, message: str) -> None:
        """Record the message (inspectable in tests)."""
        self.notes.append(message)


# --- bilingual snippets + plan summary ---------------------------------------------------
_OUTPUT_LABEL = {
    OutputFormat.BRIEF: "Brief",
    OutputFormat.DECK: "Deck",
    OutputFormat.EXCEL: "Excel",
}
# Time estimate is derived from effort (the master dial) for display only.
_EFFORT_MINUTES = {EffortLevel.LOW: 12, EffortLevel.HIGH: 30, EffortLevel.ULTRA: 60}

_SUBQ_SYSTEM = (
    "You decompose a strategy/research task into 3-5 concrete, independently-searchable "
    "sub-questions. Respond with ONLY a JSON array of short search-query strings — no prose."
)


def _t(language: Language, de: str, en: str) -> str:
    """Pick the German or English string for the language."""
    return de if language == Language.DE else en


def _format_labels(formats: list[OutputFormat]) -> str:
    """Human label for the routed output formats (e.g. 'Deck + Excel')."""
    return " + ".join(_OUTPUT_LABEL.get(fmt, fmt.value) for fmt in formats) or "Brief"


def _plan_summary(intent: Intent, effort_cfg: EffortLevelConfig) -> str:
    """Build the bilingual research-plan confirmation line, surfacing the effort (SPEC §15.5)."""
    minutes = _EFFORT_MINUTES.get(intent.effort, 30)
    outputs = _format_labels(intent.output_formats)
    workers = effort_cfg.research_workers
    rounds = effort_cfg.max_research_rounds
    fetch = effort_cfg.max_fetch_per_worker
    return _t(
        intent.language,
        f"Effort {intent.effort.value}: {workers} parallele Research-Worker, {rounds} Runden, "
        f"bis zu {fetch} Quellen je Worker, {outputs} erstellen, ~{minutes} Min. Los?",
        f"Effort {intent.effort.value}: {workers} parallel research workers, {rounds} rounds, "
        f"up to {fetch} sources each, produce {outputs}, ~{minutes} min. Go?",
    )


def plan_subqueries(
    client: LocalLLMClient, config: AppConfig, intent: Intent, task: TaskRequest
) -> ResearchPlan:
    """Build the confirm summary + fallback sub-queries for the research manager (SPEC §5.3/§15.5).

    The manager owns the real decomposition; these 3-5 sub-queries are its fallback (used if its
    own decomposition fails) and the basis of the plan the user confirms. Falls back to the raw
    task as a single query if the LLM fails or returns nothing.
    """
    sub_questions: list[str] = []
    try:
        response = client.generate(
            f'Task: "{task.raw_input}"\nReturn the JSON array of 3-5 sub-queries now.',
            system=_SUBQ_SYSTEM,
            use_thinking=False,
        )
        array = extract_json_array(response)
    except LLMError:
        array = None
    if array:
        sub_questions = [str(x).strip() for x in array if isinstance(x, str) and str(x).strip()][:5]
    if not sub_questions:
        fallback = task.raw_input.strip() or intent.summary
        sub_questions = [fallback] if fallback else []

    summary = _plan_summary(intent, config.effort.level_for(intent.effort))
    return ResearchPlan(sub_questions=sub_questions, summary=summary)


def _quick_answer(client: LocalLLMClient, task: TaskRequest, brain: str, intent: Intent) -> str:
    """Produce a short, brain-grounded answer (no web research) for the decline path."""
    language = "German" if intent.language == Language.DE else "English"
    context = (brain.strip() + "\n\n") if brain.strip() else ""
    system = (
        f"{context}Answer briefly and directly in {language}, using the context above where "
        "relevant. Note that this is a quick answer without fresh web research."
    )
    try:
        return client.generate(task.raw_input, system=system, use_thinking=False).strip()
    except LLMError as exc:
        return f"(Could not generate a quick answer: {exc})"


def _findings_digest(report: ResearchReport) -> str:
    """Render the workers' validated findings (claim + confidence + date + source) for synthesis."""
    lines: list[str] = []
    for wf in report.worker_findings:
        if not wf.findings and not wf.gaps:
            continue
        lines.append(f"[{wf.sub_topic}] (overall confidence: {wf.confidence.value})")
        for finding in wf.findings:
            date = f" ({finding.date})" if finding.date else ""
            flag = f" [{finding.recency_flag}]" if finding.recency_flag else ""
            source = f" — {finding.source_url}" if finding.source_url else ""
            lines.append(f"  - [{finding.confidence.value}] {finding.claim}{date}{flag}{source}")
        for gap in wf.gaps:
            lines.append(f"  - GAP: {gap}")
    return "\n".join(lines)


def _run_research(
    client: LocalLLMClient,
    config: AppConfig,
    intent: Intent,
    plan: ResearchPlan,
    interaction: Interaction,
    effort_cfg: EffortLevelConfig,
    manager: ResearchManager | None,
) -> ResearchReport:
    """Run the multi-agent research via the manager (built from config unless one is injected)."""
    active = manager or ResearchManager()
    report = asyncio.run(active.run(client, config, intent, plan, interaction, effort_cfg))
    interaction.notify(
        _t(
            intent.language,
            f"{report.workers_used} Worker, {report.sources_evaluated} Quellen geprüft, "
            f"{len(report.evidence)} gelesen — synthetisiere…",
            f"{report.workers_used} workers, {report.sources_evaluated} sources evaluated, "
            f"{len(report.evidence)} read — synthesizing…",
        )
    )
    return report


def _critique_and_revise(
    client: LocalLLMClient,
    config: AppConfig,
    intent: Intent,
    analysis: AnalysisOutput,
    synthesis_input: SynthesisInput,
    interaction: Interaction,
    effort_cfg: EffortLevelConfig,
) -> tuple[AnalysisOutput, Critique | None, int]:
    """Critique the draft and revise it up to ``effort.revisions`` times (effort-gated, fail-open).

    Returns the (possibly revised) analysis, the final critique, and the revision count. When the
    effort level disables critique, returns the draft unchanged with ``(analysis, None, 0)``.
    """
    if not effort_cfg.critique:
        return analysis, None, 0

    playbooks = load_playbooks()
    min_score = config.effort.critique_min_score
    crit = critique(client, intent, analysis, playbooks, min_score)
    revisions = 0
    while not crit.passed and revisions < effort_cfg.revisions:
        interaction.notify(
            _t(
                intent.language,
                f"Kritik {crit.score}/{min_score} — überarbeite (Runde {revisions + 1})…",
                f"Critique {crit.score}/{min_score} — revising (round {revisions + 1})…",
            )
        )
        analysis = revise(client, intent, analysis, crit, synthesis_input, playbooks)
        revisions += 1
        crit = critique(client, intent, analysis, playbooks, min_score)
    return analysis, crit, revisions


def run_pipeline(
    client: LocalLLMClient,
    config: AppConfig,
    task: TaskRequest,
    interaction: Interaction,
    manager: ResearchManager | None = None,
    documents: list[DocContent] | None = None,
    effort_override: EffortLevel | None = None,
) -> PipelineResult:
    """Run the full advanced agent loop for one task (SPEC §5.3 + §15.5).

    Args:
        client: The LLM client (all reasoning calls go through it).
        config: The application config (the ``effort`` block drives every budget).
        task: The raw request (with any ``/effort`` prefix already stripped by the caller).
        interaction: How to ask clarifications / mid-research questions / confirm / show progress.
        manager: Optional research manager (tests inject a stub; otherwise built from config).
        documents: Optional already-read documents to feed into synthesis.
        effort_override: An explicit effort (``/effort`` / ``--effort``) that beats auto-detect.

    Returns:
        A :class:`PipelineResult` — either a full ``analysis`` (with effort/critique/revisions/
        research telemetry) or, if the user declined the research plan, ``declined=True`` with a
        brain-based ``quick_answer``.

    Raises:
        SearXNGError: If every research worker is starved (fail fast, SPEC REQ-5) — caller-handled.
    """
    brain = load_brain(config.memory)
    intent = parse_intent(client, config, task, brain, effort_override=effort_override)
    effort_cfg = config.effort.level_for(intent.effort)
    # Upfront clarification budget = the smaller of the agent ceiling and the effort allowance.
    max_clarifications = min(config.agent.max_clarification_rounds, effort_cfg.max_clarifications)
    intent, answered = clarify(intent, task, interaction.ask_choice, max_clarifications)
    plan = plan_subqueries(client, config, intent, task)

    confirmed = interaction.confirm(plan.summary) if config.agent.show_research_plan else True
    if not confirmed:
        quick = _quick_answer(client, task, brain, intent)
        offer = interaction.confirm(
            _t(
                intent.language,
                "Trotzdem volle Recherche starten?",
                "Run the full research anyway?",
            )
        )
        if not offer:
            return PipelineResult(
                intent=intent,
                routed_formats=intent.output_formats,
                answered=answered,
                declined=True,
                quick_answer=quick,
                effort=intent.effort,
            )

    report = _run_research(client, config, intent, plan, interaction, effort_cfg, manager)
    synthesis_input = SynthesisInput(
        intent=intent,
        research=report.evidence,
        documents=documents or [],
        brain_context=brain,
        findings_digest=_findings_digest(report),
    )
    analysis = synthesize(client, synthesis_input)

    analysis, crit, revisions = _critique_and_revise(
        client, config, intent, analysis, synthesis_input, interaction, effort_cfg
    )

    floor_issues = quality_check(analysis)
    if floor_issues:
        interaction.notify(
            _t(
                intent.language,
                f"Hinweis (Qualitäts-Check): {', '.join(floor_issues)}",
                f"Note (quality check): {', '.join(floor_issues)}",
            )
        )

    return PipelineResult(
        intent=intent,
        routed_formats=intent.output_formats,
        answered=answered,
        analysis=analysis,
        declined=False,
        effort=intent.effort,
        critique=crit,
        revisions=revisions,
        research_report=report,
    )
