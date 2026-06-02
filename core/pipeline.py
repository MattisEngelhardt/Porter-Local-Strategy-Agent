"""Agent pipeline (Phase 3 + 3.5): the non-linear, self-correcting reasoning chain end-to-end.

Wires the master loop (SPEC §5.3 + §15.5):

    inject brain → parse intent + AUTO-DETECT effort → clarify (≤ effort budget) →
    research plan + effort shown → confirm (decline → brain quick answer) →
    ResearchManager.run(effort): decompose → N parallel workers → mid-research clarification →
    aggregated ResearchReport → synthesize (brain + playbooks + validated findings digest) →
    if effort.critique: critique → revise loop (≤ effort.revisions) → re-critique →
    quality-check (deterministic floor) → PipelineResult (analysis + effort + critique + telemetry)

Effort is the master dial: it sets every budget via ``config.effort.level_for(intent.effort)``.
Advisory layers (workers / critic / renderers) are fail-open; hard deps (SearXNG all-fail, LLM down)
keep the Phase-3 fail-fast policy. The routed deliverables (PDF brief / PPTX deck / Excel workbook,
Phase 4) are rendered at the end via ``_render_outputs``; no ChromaDB memory yet (Phase 5).

Interaction with the user is abstracted behind :class:`Interaction` so the chain is pure and
testable: the REPL supplies a rich implementation (in ``core/intake.py``), CLI/tests supply the
headless :class:`AutoInteraction` here. This module imports no presentation library.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from core.clarification import clarify, propose_scoping_questions
from core.config import AppConfig, EffortLevelConfig
from core.content_shaper import shape_deck, shape_workbook
from core.critic import critique, revise
from core.demo_showcase import maybe_promote_demo
from core.doc_synthesis import (
    propose_doc_questions,
    synthesize_briefing,
    to_management_markdown,
    write_briefing_md,
)
from core.excel_builder import ExcelBuildError, build_workbook
from core.exporter import ExportError, build_brief_pdf, build_deck
from core.intent_parser import classify_work_mode, parse_intent
from core.json_utils import extract_json_array
from core.memory import (
    MemoryLayerError,
    MemoryStore,
    extract_entities,
    load_brain,
    make_record,
    open_memory,
    propose_brain_additions,
    recall,
)
from core.playbooks import load_playbooks
from core.research_agent import ResearchManager
from core.synthesizer import compile_cited_sources, quality_check, synthesize
from llm.local_llm_client import LLMError, LocalLLMClient
from models.research import DocContent, ResearchReport
from models.synthesis import AnalysisOutput, Critique, PipelineResult, SynthesisInput
from models.task import (
    ClarificationRound,
    EffortLevel,
    Intent,
    Language,
    OutputFormat,
    ResearchPlan,
    TaskRequest,
    WorkMode,
)


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
    client: LocalLLMClient,
    config: AppConfig,
    intent: Intent,
    task: TaskRequest,
    guidance: str = "",
) -> ResearchPlan:
    """Build the confirm summary + fallback sub-queries for the research manager (SPEC §5.3/§15.5).

    The manager owns the real decomposition; these 3-5 sub-queries are its fallback (used if its
    own decomposition fails) and the basis of the plan the user confirms. ``guidance`` carries the
    user's answers to the situation-specific scoping questions, so the decomposition is steered by
    what the user actually cares about. Falls back to the raw task as a single query if the LLM
    fails or returns nothing.
    """
    sub_questions: list[str] = []
    guidance_block = (
        f"\nUser guidance (answers to scoping questions — focus the sub-queries on these):\n"
        f"{guidance.strip()}\n"
        if guidance.strip()
        else ""
    )
    try:
        response = client.generate(
            f'Task: "{task.raw_input}"{guidance_block}\n'
            "Return the JSON array of 3-5 sub-queries now.",
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


def _ask_questions(
    interaction: Interaction, questions: list[str]
) -> tuple[str, list[ClarificationRound]]:
    """Ask each free-form question one at a time; return (guidance, answered rounds).

    Shared by the research-path scoping intake and the document-prep clarifications. Every question
    is recorded as a round; only answered ones contribute to the guidance string. An empty answer
    means "no answer" — the caller proceeds on a stated assumption (clarification never blocks
    delivery, SPEC §5.2).
    """
    rounds: list[ClarificationRound] = []
    parts: list[str] = []
    for question in questions:
        answer = interaction.ask_text(question).strip()
        rounds.append(ClarificationRound(question=question, answer=answer or None))
        if answer:
            parts.append(f"Q: {question}\nA: {answer}")
    return "\n\n".join(parts), rounds


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


def _resolve_doc_mode(task_text: str, interaction: Interaction, language: Language) -> WorkMode:
    """Resolve the work mode when documents are attached; ask the user if it is unclear (§15.5).

    A clear "consolidate for management" phrase → DOCUMENT_PREP; a clear web-research phrase →
    RESEARCH; otherwise the agent does not guess — it asks the user which mode to use. Headless
    interactions (no human) pick the first option (prepare-only), since documents are present.
    """
    decided = classify_work_mode(task_text, has_documents=True)
    if decided is not None:
        return decided
    prepare_label = _t(language, "Nur fürs Management aufbereiten", "Only prepare for management")
    research_label = _t(language, "Recherchieren", "Research the web")
    choice = interaction.ask_choice(
        _t(
            language,
            "Du hast Dokumente angehängt. Soll ich sie nur fürs Management aufbereiten "
            "(keine Recherche) oder dazu im Web recherchieren?",
            "You attached documents. Should I only prepare them for management (no research), "
            "or also research the web?",
        ),
        [prepare_label, research_label],
    )
    lowered = choice.strip().lower()
    if "rech" in lowered or "research" in lowered or lowered in {"2", research_label.lower()}:
        return WorkMode.RESEARCH
    return WorkMode.DOCUMENT_PREP


def _render_outputs(
    client: LocalLLMClient,
    config: AppConfig,
    intent: Intent,
    analysis: AnalysisOutput,
    interaction: Interaction,
    effort_cfg: EffortLevelConfig,
) -> list[Path]:
    """Render all routed deliverables (PDF brief, PPTX deck, Excel). Fail-open per renderer.

    Decks and Excel are shaped from the prose analysis by ``content_shaper`` (one LLM call each)
    before rendering. A renderer failure (e.g. WeasyPrint's GTK runtime missing, or a shaping/build
    error) never loses the analysis — it is reported via ``notify`` and the other outputs still ship
    (SPEC REQ-5). Business Case routes to Deck + Excel together (N-6, already in output_formats).
    """
    files: list[Path] = []
    out_dir = config.output.output_dir
    think = effort_cfg.thinking

    if OutputFormat.BRIEF in intent.output_formats:
        try:
            pdf = build_brief_pdf(
                analysis, config, out_dir, task_type=intent.task_type, audience=intent.audience
            )
            files.append(pdf)
            interaction.notify(_t(intent.language, f"PDF erstellt: {pdf}", f"PDF created: {pdf}"))
        except ExportError as exc:
            interaction.notify(
                _t(intent.language, f"PDF übersprungen: {exc}", f"PDF skipped: {exc}")
            )

    if OutputFormat.DECK in intent.output_formats:
        try:
            deck_structure = shape_deck(client, intent, analysis, use_thinking=think)
            deck = build_deck(deck_structure, config, out_dir, analysis=analysis)
            files.append(deck)
            interaction.notify(
                _t(intent.language, f"Deck erstellt: {deck}", f"Deck created: {deck}")
            )
        except ExportError as exc:
            interaction.notify(
                _t(intent.language, f"PPTX übersprungen: {exc}", f"PPTX skipped: {exc}")
            )

    if OutputFormat.EXCEL in intent.output_formats:
        try:
            template, data = shape_workbook(client, intent, analysis, use_thinking=think)
            workbook = build_workbook(template, data, config, out_dir)
            files.append(workbook)
            interaction.notify(
                _t(intent.language, f"Excel erstellt: {workbook}", f"Excel created: {workbook}")
            )
        except ExcelBuildError as exc:
            interaction.notify(
                _t(intent.language, f"Excel übersprungen: {exc}", f"Excel skipped: {exc}")
            )
    return files


def _run_document_prep(
    client: LocalLLMClient,
    config: AppConfig,
    intent: Intent,
    documents: list[DocContent],
    brain: str,
    interaction: Interaction,
) -> PipelineResult:
    """Internal doc-prep mode: deep-read → targeted clarifications → briefing + .md blueprint."""
    interaction.notify(
        _t(
            intent.language,
            f"Lese {len(documents)} Dokument(e) und erkenne die Themen…",
            f"Reading {len(documents)} document(s) and identifying the themes…",
        )
    )
    playbooks = load_playbooks()

    # Targeted, theme-specific clarifications (effort-budgeted; fail-open via empty answers).
    effort_cfg = config.effort.level_for(intent.effort)
    budget = min(config.agent.max_clarification_rounds, effort_cfg.max_clarifications)
    questions = propose_doc_questions(client, intent, documents, budget)
    guidance, answered = _ask_questions(interaction, questions)
    if guidance:
        interaction.notify(
            _t(
                intent.language,
                "Antworten übernommen — erstelle die Management-Aufbereitung…",
                "Answers captured — preparing the management briefing…",
            )
        )

    analysis = synthesize_briefing(client, intent, documents, brain, playbooks, guidance)
    markdown = to_management_markdown(analysis, documents, intent.language)
    path = write_briefing_md(markdown, config.output.output_dir, analysis.title)
    interaction.notify(
        _t(intent.language, f"Blueprint geschrieben: {path}", f"Blueprint written: {path}")
    )
    output_files = _render_outputs(client, config, intent, analysis, interaction, effort_cfg)
    return PipelineResult(
        intent=intent,
        routed_formats=intent.output_formats,
        answered=answered,
        analysis=analysis,
        effort=intent.effort,
        output_files=output_files,
        mode=WorkMode.DOCUMENT_PREP.value,
        artifact_path=path,
    )


def resolve_memory(
    config: AppConfig,
    client: LocalLLMClient,
    on_unavailable: Callable[[str], None] | None = None,
) -> MemoryStore | None:
    """Open the ChromaDB memory store, or return ``None`` (memory is advisory — never blocks).

    A disabled config yields ``None`` silently. A real failure (ChromaDB missing / path unusable)
    yields ``None`` but surfaces the exact fix via ``on_unavailable`` so it is never a silent
    degrade (SPEC REQ-5). Callers (REPL / CLI) open it once and pass it into :func:`run_pipeline`.
    """
    if not config.memory.enabled:
        return None
    try:
        return open_memory(config.memory, client)
    except MemoryLayerError as exc:
        if on_unavailable is not None:
            on_unavailable(str(exc))
        return None


def _quality_score(analysis: AnalysisOutput, critique_result: Critique | None) -> int:
    """Quality rating stored with a run: the critic's score, else a deterministic floor proxy."""
    if critique_result is not None:
        return critique_result.score
    return max(0, 100 - 25 * len(quality_check(analysis)))


def run_pipeline(
    client: LocalLLMClient,
    config: AppConfig,
    task: TaskRequest,
    interaction: Interaction,
    manager: ResearchManager | None = None,
    documents: list[DocContent] | None = None,
    effort_override: EffortLevel | None = None,
    doc_formats: list[OutputFormat] | None = None,
    memory: MemoryStore | None = None,
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
        memory: Optional ChromaDB memory store (from :func:`resolve_memory`). When present, prior
            findings are retrieved before synthesis (delta injected) and the run is written after
            delivery. ``None`` = memory off (the default; advisory layer, never blocks).

    Returns:
        A :class:`PipelineResult` — either a full ``analysis`` (with effort/critique/revisions/
        research telemetry) or, if the user declined the research plan, ``declined=True`` with a
        brain-based ``quick_answer``.

    Raises:
        SearXNGError: If every research worker is starved (fail fast, SPEC REQ-5) — caller-handled.
    """
    brain = load_brain(config.memory)
    intent = parse_intent(client, config, task, brain, effort_override=effort_override)

    docs = documents or []
    if docs and _resolve_doc_mode(task.raw_input, interaction, intent.language) == (
        WorkMode.DOCUMENT_PREP
    ):
        # Internal document-preparation mode: no research, no planning — read + consolidate.
        if doc_formats:  # explicit format choice (e.g. `prepare --format deck`) wins over routing
            intent = intent.model_copy(update={"output_formats": doc_formats})
        return _run_document_prep(client, config, intent, docs, brain, interaction)

    effort_cfg = config.effort.level_for(intent.effort)
    # Upfront clarification budget = the smaller of the agent ceiling and the effort allowance.
    max_clarifications = min(config.agent.max_clarification_rounds, effort_cfg.max_clarifications)

    # Intake (SPEC §5.2): proactive comprehension, not a fixed checklist. Reflect the understood
    # task, then run a genuine sufficiency self-check — the agent asks itself whether it already
    # has enough to go in, and surfaces ONLY the situation-specific blockers it truly needs (often
    # nothing). Output format is deterministic and is confirmed at the plan step below, so the
    # canned format/audience triple is a fallback that fires ONLY when the self-check asked nothing
    # — the user is never handed a generic checklist on top of a sharp, task-specific question.
    if intent.summary:
        interaction.notify(
            _t(intent.language, f"Verstanden: {intent.summary}", f"Got it: {intent.summary}")
        )
    scoping_questions = propose_scoping_questions(client, intent, task, brain, max_clarifications)
    guidance, scoping_rounds = _ask_questions(interaction, scoping_questions)

    routing_rounds: list[ClarificationRound] = []
    if not scoping_rounds:
        intent, routing_rounds = clarify(intent, task, interaction.ask_choice, max_clarifications)
    answered = scoping_rounds + routing_rounds

    plan = plan_subqueries(client, config, intent, task, guidance)

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
    findings_digest = _findings_digest(report)

    # SPEC §5.3 step 6 — retrieve relevant prior research + inject the delta (fail-open).
    prior_findings, delta_note, entities = "", None, []
    if memory is not None:
        try:
            entities = extract_entities(client, intent, task.raw_input)
            prior = recall(memory, client, intent, entities, findings_digest)
            prior_findings, delta_note = prior.prior_findings, prior.delta_note
            if delta_note:
                interaction.notify(delta_note)
        except MemoryLayerError as exc:
            interaction.notify(_t(intent.language, f"Memory aus: {exc}", f"Memory off: {exc}"))
            memory = None

    injected_prior = f"{delta_note}\n\n{prior_findings}".strip() if delta_note else prior_findings
    synthesis_input = SynthesisInput(
        intent=intent,
        research=report.evidence,
        documents=documents or [],
        brain_context=brain,
        findings_digest=findings_digest,
        prior_findings=injected_prior,
        cited_sources=compile_cited_sources(report),
        guidance=guidance,
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

    # Render the routed deliverables (PDF / PPTX / Excel) — Business Case = Deck + Excel (N-6).
    output_files = _render_outputs(client, config, intent, analysis, interaction, effort_cfg)

    # Showcase: if this run's deck beats the published demo's critic score, swap the README's
    # "best demo output" link and push it (fail-open; demos are test runs). N/A when no deck.
    maybe_promote_demo(
        output_files=output_files,
        critique_score=crit.score if crit is not None else None,
        title=analysis.title,
        auto_promote=config.output.auto_promote_demo,
        min_score=config.output.demo_min_score,
        notify=interaction.notify,
    )

    # SPEC §5.3 / §15 — write this run to memory after delivery (fail-open).
    if memory is not None:
        try:
            memory.write(make_record(intent, analysis, entities, _quality_score(analysis, crit)))
        except MemoryLayerError as exc:
            interaction.notify(
                _t(
                    intent.language,
                    f"Memory-Write übersprungen: {exc}",
                    f"Memory write skipped: {exc}",
                )
            )

    # Brain-update flow (SPEC §4.5/§15): propose durable additions; the REPL confirms + appends.
    proposed: list[str] = []
    if config.memory.enabled and intent.effort != EffortLevel.LOW:
        proposed = propose_brain_additions(client, intent, analysis, brain)

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
        output_files=output_files,
        delta_note=delta_note,
        proposed_brain_additions=proposed,
    )
