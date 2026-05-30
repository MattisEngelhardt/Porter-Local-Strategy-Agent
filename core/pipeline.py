"""Agent pipeline (Phase 3): the multi-step reasoning chain (SPEC §5.3) end-to-end.

Wires the pieces into one run:

    decompose → inject brain → clarify (≤3, one at a time) → confirm research plan →
    search (parallel SearXNG) → fetch top sources → synthesize with playbooks + brain →
    quality-check → structured AnalysisOutput

No output file is rendered (that is Phase 4) and no ChromaDB memory is read/written (Phase 5):
the decline path's "memory" is brain.md only. Justified addition to the SPEC §7 tree — the SPEC
describes the reasoning chain but names no orchestrator module (documented in PROGRESS.md).

Interaction with the user is abstracted behind :class:`Interaction` so the chain is pure and
testable: the REPL supplies a rich implementation (in ``core/intake.py``), CLI/tests supply the
headless :class:`AutoInteraction` here. This module imports no presentation library.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from core.clarification import clarify
from core.config import AppConfig
from core.intent_parser import parse_intent
from core.json_utils import extract_json_array
from core.memory import load_brain
from core.researcher import ResearchEngine, SearchCache
from core.synthesizer import synthesize
from llm.local_llm_client import LLMError, LocalLLMClient
from models.research import DocContent, ResearchBundle
from models.synthesis import PipelineResult, SynthesisInput
from models.task import Depth, Intent, Language, OutputFormat, ResearchPlan, TaskRequest


class Interaction(Protocol):
    """How the pipeline talks to the user (REPL impl in intake.py; AutoInteraction for tests)."""

    def ask_choice(self, question: str, options: list[str]) -> str:
        """Ask a multiple-choice question and return the chosen answer (one word)."""
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

    def __init__(self, answers: list[str] | None = None, accept: bool = True) -> None:
        """Configure canned clarification answers and the confirm decision."""
        self._answers = list(answers or [])
        self._accept = accept
        self.notes: list[str] = []

    def ask_choice(self, question: str, options: list[str]) -> str:
        """Return the next canned answer, or the first option if none remain."""
        return self._answers.pop(0) if self._answers else options[0]

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
_DEPTH_MINUTES = {Depth.QUICK: 12, Depth.STANDARD: 30, Depth.DEEP: 55}

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


def _plan_summary(intent: Intent, num_queries: int, max_fetch: int) -> str:
    """Build the bilingual research-plan confirmation line (SPEC §5.2)."""
    minutes = _DEPTH_MINUTES.get(intent.depth, 30)
    outputs = _format_labels(intent.output_formats)
    return _t(
        intent.language,
        f"{num_queries} parallele Suchanfragen, Top-{max_fetch} Quellen lesen, "
        f"{outputs} erstellen, ~{minutes} Min. Los?",
        f"{num_queries} parallel searches, read top {max_fetch} sources, "
        f"produce {outputs}, ~{minutes} min. Go?",
    )


def plan_subqueries(
    client: LocalLLMClient, config: AppConfig, intent: Intent, task: TaskRequest
) -> ResearchPlan:
    """Decompose the task into 3-5 sub-queries + a confirm summary (SPEC §5.3 step 1).

    Falls back to the raw task as a single query if the LLM fails or returns nothing.
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

    summary = _plan_summary(intent, len(sub_questions), config.research.max_fetch_per_run)
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


def _research(
    config: AppConfig,
    intent: Intent,
    task: TaskRequest,
    plan: ResearchPlan,
    engine: ResearchEngine | None,
    interaction: Interaction,
) -> ResearchBundle:
    """Run the research phase (cache-backed engine unless one is injected)."""
    query = task.raw_input.strip() or intent.summary
    interaction.notify(
        _t(
            intent.language,
            f"Recherchiere ({len(plan.sub_questions)} Suchanfragen)…",
            f"Researching ({len(plan.sub_questions)} searches)…",
        )
    )
    own_cache: SearchCache | None = None
    active = engine
    if active is None:
        own_cache = SearchCache(config.research)
        active = ResearchEngine(config.research, cache=own_cache)
    try:
        bundle = asyncio.run(
            active.run(
                query, sub_queries=plan.sub_questions, max_fetch=config.research.max_fetch_per_run
            )
        )
    finally:
        if own_cache is not None:
            own_cache.close()
    interaction.notify(
        _t(
            intent.language,
            f"{len(bundle.fetched)} Quellen gelesen, synthetisiere…",
            f"Read {len(bundle.fetched)} sources, synthesizing…",
        )
    )
    return bundle


def run_pipeline(
    client: LocalLLMClient,
    config: AppConfig,
    task: TaskRequest,
    interaction: Interaction,
    engine: ResearchEngine | None = None,
    documents: list[DocContent] | None = None,
) -> PipelineResult:
    """Run the full agent reasoning chain for one task (SPEC §5.3).

    Args:
        client: The LLM client (all reasoning calls go through it).
        config: The application config.
        task: The raw request.
        interaction: How to ask clarifications / confirm the plan / show progress.
        engine: Optional research engine (tests inject a stub; otherwise built from config).
        documents: Optional already-read documents to feed into synthesis.

    Returns:
        A :class:`PipelineResult` — either a full ``analysis`` or, if the user declined the
        research plan, ``declined=True`` with a brain-based ``quick_answer``.

    Raises:
        SearXNGError: If every search fails (fail fast, SPEC REQ-5) — handled by the caller.
    """
    brain = load_brain(config.memory)
    intent = parse_intent(client, config, task, brain)
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
            )

    bundle = _research(config, intent, task, plan, engine, interaction)
    synthesis_input = SynthesisInput(
        intent=intent,
        research=bundle.fetched,
        documents=documents or [],
        brain_context=brain,
        prior_findings="",
    )
    analysis = synthesize(client, synthesis_input)

    return PipelineResult(
        intent=intent,
        routed_formats=intent.output_formats,
        answered=answered,
        analysis=analysis,
        declined=False,
    )
