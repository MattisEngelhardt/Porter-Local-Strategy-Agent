"""Clarification dialog (Phase 3): proactive, conversational, one question at a time.

The agent infers everything it can from the input + brain.md (via the intent parser) and only
asks what genuinely cannot be inferred (SPEC §5.2). Behaviour (user-authorized, overrides the
SPEC §5.2 "max 2"):

* **One question at a time** — never bundled. After each answer the remaining gaps are
  re-evaluated before the next question is chosen.
* **Each question is multi-dimensional** — a single binary/triple choice resolves several of
  {depth, output format, audience} at once, answerable in one word.
* **Budget scales with complexity** — quick 0–1, standard 1–2, complex (business case / board
  deck / multi-format) up to 3. Hard-capped by ``agent.max_clarification_rounds`` (3).

The question loop is pure: the ``ask`` callable is injected (the REPL prompts the user; tests
pass canned answers), so the whole dialog is deterministic and offline-testable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from core.intent_parser import detect_explicit_formats
from core.json_utils import extract_json_array
from llm.local_llm_client import LLMError, LocalLLMClient
from models.task import (
    Audience,
    ClarificationRound,
    Depth,
    Intent,
    Language,
    OutputFormat,
    TaskRequest,
    TaskType,
)

# Signature of the question asker: (question_text, option_labels) -> chosen answer (one word).
AskFn = Callable[[str, list[str]], str]

# Task types where a brief-vs-deck narrative choice (and audience) is genuinely open.
_NARRATIVE = frozenset(
    {
        TaskType.COMPETITOR_ANALYSIS,
        TaskType.MARKET_RESEARCH,
        TaskType.MARKET_ANALYSIS,
        TaskType.INDUSTRY_NEWS,
        TaskType.MEETING_BRIEFING,
        TaskType.DOCUMENT_SYNTHESIS,
        TaskType.ADHOC,
    }
)
# Excel-comparison tasks where scored-matrix vs benchmark-table is a real choice (SPEC §5.2).
_EXCEL_COMPARE = frozenset(
    {
        TaskType.OPTION_COMPARISON,
        TaskType.TARGET_SCREENING,
        TaskType.FINANCIAL_BENCHMARK,
        TaskType.PARTNERSHIP_EVALUATION,
    }
)


def _set(intent: Intent, **updates: Any) -> Intent:
    """Return a copy of ``intent`` with the given fields updated (immutable update)."""
    return intent.model_copy(update=updates)


@dataclass(frozen=True)
class _Option:
    """One answer option with bilingual labels and the intent update it applies."""

    de: str
    en: str
    apply: Callable[[Intent], Intent]

    def label(self, language: Language) -> str:
        """Return the option label in the given language."""
        return self.de if language == Language.DE else self.en


@dataclass(frozen=True)
class _Question:
    """A multi-dimensional clarification question with bilingual text and options."""

    kind: str
    de: str
    en: str
    options: tuple[_Option, ...]

    def text(self, language: Language) -> str:
        """Return the question text in the given language."""
        return self.de if language == Language.DE else self.en

    def labels(self, language: Language) -> list[str]:
        """Return the option labels in the given language."""
        return [option.label(language) for option in self.options]


# The primary triple: resolves depth + output format + audience in one question.
_SCOPE = _Question(
    kind="scope",
    de="Quick Brief für dich, Strategy Brief fürs Team, oder Management Deck?",
    en="Quick brief for you, a strategy brief for the team, or a management deck?",
    options=(
        _Option(
            "Quick Brief",
            "Quick brief",
            lambda i: _set(
                i,
                depth=Depth.QUICK,
                output_formats=[OutputFormat.BRIEF],
                audience=Audience.PERSONAL,
            ),
        ),
        _Option(
            "Strategy Brief",
            "Strategy brief",
            lambda i: _set(
                i,
                depth=Depth.STANDARD,
                output_formats=[OutputFormat.BRIEF],
                audience=Audience.STRATEGY_TEAM,
            ),
        ),
        _Option(
            "Management Deck",
            "Management deck",
            lambda i: _set(
                i, depth=Depth.DEEP, output_formats=[OutputFormat.DECK], audience=Audience.CEO_BOARD
            ),
        ),
    ),
)

# Excel sub-style (SPEC §5.2 Excel variant). Recorded in the answered round for synthesis /
# Phase-4 template selection (no Intent field for it yet); audience is the open dim it can set.
_EXCEL_KIND = _Question(
    kind="excel_kind",
    de="Scorierter Vergleich (Decision Matrix) oder Benchmark Table mit Rohdaten?",
    en="A scored comparison (decision matrix) or a benchmark table with raw data?",
    options=(
        _Option("Decision Matrix", "Decision matrix", lambda i: i),
        _Option("Benchmark Table", "Benchmark table", lambda i: i),
    ),
)

# Audience-only (with a depth bump for management): used when the format is already fixed.
_AUDIENCE = _Question(
    kind="audience",
    de="Für dich zum Arbeiten, fürs Strategy-Team, oder fürs Management?",
    en="For your own work, for the strategy team, or for management?",
    options=(
        _Option("Für dich", "For you", lambda i: _set(i, audience=Audience.PERSONAL)),
        _Option(
            "Strategy-Team", "Strategy team", lambda i: _set(i, audience=Audience.STRATEGY_TEAM)
        ),
        _Option(
            "Management",
            "Management",
            lambda i: _set(
                i,
                audience=Audience.CEO_BOARD,
                depth=Depth.DEEP if i.depth == Depth.QUICK else i.depth,
            ),
        ),
    ),
)


def question_budget(intent: Intent, max_rounds: int) -> int:
    """Return how many questions may be asked, scaling with task complexity (capped)."""
    if (
        intent.task_type in {TaskType.BUSINESS_CASE, TaskType.BOARD_PREP}
        or len(intent.output_formats) > 1
    ):
        budget = 3
    elif intent.task_type in {TaskType.INDUSTRY_NEWS, TaskType.ADHOC}:
        budget = 1
    else:
        budget = 2
    return max(0, min(budget, max_rounds))


def _scope_relevant(intent: Intent, explicit_format: bool) -> bool:
    """Scope is open when the user named no format and the task is narrative-capable."""
    return not explicit_format and intent.task_type in _NARRATIVE


def _excel_kind_relevant(intent: Intent) -> bool:
    """The matrix-vs-benchmark choice applies to excel-comparison tasks."""
    return OutputFormat.EXCEL in intent.output_formats and intent.task_type in _EXCEL_COMPARE


def _audience_relevant(intent: Intent) -> bool:
    """Audience is asked when still unknown for a task where it shapes the output."""
    return intent.audience is None and intent.task_type not in {
        TaskType.ADHOC,
        TaskType.INDUSTRY_NEWS,
    }


def _next_question(intent: Intent, explicit_format: bool, asked: set[str]) -> _Question | None:
    """Pick the highest-priority still-relevant question not yet asked (or ``None``)."""
    if "scope" not in asked and _scope_relevant(intent, explicit_format):
        return _SCOPE
    if "excel_kind" not in asked and _excel_kind_relevant(intent):
        return _EXCEL_KIND
    if "audience" not in asked and _audience_relevant(intent):
        return _AUDIENCE
    return None


def _match_option(question: _Question, choice: str, language: Language) -> _Option:
    """Match a one-word answer to an option (label / index / keyword); default to the first."""
    cleaned = choice.strip().lower()
    options = question.options
    labels = [opt.label(language).lower() for opt in options]

    for opt, label in zip(options, labels, strict=True):
        if cleaned == label:
            return opt
    if cleaned.isdigit():
        idx = int(cleaned)
        for candidate in (idx, idx - 1):
            if 0 <= candidate < len(options):
                return options[candidate]
    for opt, label in zip(options, labels, strict=True):
        first_word = label.split()[0] if label.split() else label
        if cleaned and (cleaned == first_word or cleaned in label or label in cleaned):
            return opt
    return options[0]


def clarify(
    intent: Intent, task: TaskRequest, ask: AskFn, max_rounds: int
) -> tuple[Intent, list[ClarificationRound]]:
    """Run the clarification dialog, asking one multi-dimensional question at a time.

    Args:
        intent: The inferred intent (already filled in as far as possible).
        task: The original request (used to tell whether a format was named explicitly).
        ask: Callable ``(question_text, option_labels) -> answer`` (REPL or test stub).
        max_rounds: Hard cap on questions (``agent.max_clarification_rounds``).

    Returns:
        The (possibly updated) intent and the list of answered clarification rounds.
    """
    explicit_format = bool(detect_explicit_formats(task.raw_input))
    budget = question_budget(intent, max_rounds)
    answered: list[ClarificationRound] = []
    asked: set[str] = set()

    while len(answered) < budget:
        question = _next_question(intent, explicit_format, asked)
        if question is None:
            break
        text = question.text(intent.language)
        choice = ask(text, question.labels(intent.language))
        intent = _match_option(question, choice, intent.language).apply(intent)
        answered.append(ClarificationRound(question=text, answer=choice))
        asked.add(question.kind)

    return intent, answered


# --- situation-specific scoping (the research-path counterpart of propose_doc_questions) -----
# Unlike the fixed routing catalog above, these questions are generated per task: the agent reads
# the actual request + brain.md and asks only what genuinely shapes THIS analysis. This is what
# makes the intake read like comprehension instead of a keyword checklist.
_SCOPING_SYSTEM = (
    "You are the intake strategist of a local strategy/research agent at Neura Robotics (pre-IPO "
    "cognitive humanoid robotics, Metzingen, Germany). A task just arrived. Before any research, "
    "judge ONE thing: do you already have enough context to produce an excellent, decision-ready "
    "analysis? If yes, ask nothing. If not, surface ONLY the question(s) whose answers would "
    "genuinely change HOW you research this or WHAT you conclude — the real decision behind the "
    "request, scope boundaries, which angle / rivals / region / time-horizon / metrics matter "
    "most, and any hard constraints. RULES: (1) never ask to fill a quota — a well-specified task "
    "needs ZERO questions, and [] is the correct, expected answer for it; (2) ask only what "
    "materially changes the result AND is not already clear from the task or the persistent "
    "context below; (3) never ask about output format, length, or audience — those are decided "
    "elsewhere; (4) name the actual company / market / decision so the question could not be "
    "copy-pasted onto any other task; (5) one sharp question beats several shallow ones. Respond "
    "with ONLY a JSON array of question strings (at most {n}, or [] when you already have enough) "
    "— no prose."
)


def propose_scoping_questions(
    client: LocalLLMClient,
    intent: Intent,
    task: TaskRequest,
    brain: str,
    max_questions: int,
) -> list[str]:
    """Propose up to ``max_questions`` situation-specific scoping questions for a research task.

    The research-path counterpart of :func:`core.doc_synthesis.propose_doc_questions`: instead of
    picking from the fixed routing catalog, the agent reads the real request + persistent context
    and asks only what genuinely shapes *this* analysis (the decision behind it, the angle that
    matters, the boundaries). Fail-open — a zero budget or an LLM/parse error yields no questions,
    and the run proceeds on the routing answers alone (clarification must never block delivery).
    """
    if max_questions <= 0:
        return []
    language = "German" if intent.language == Language.DE else "English"
    system = _SCOPING_SYSTEM.format(n=max_questions) + f" Ask in {language}."
    context = f"\n\nPERSISTENT CONTEXT (brain.md):\n{brain.strip()}" if brain.strip() else ""
    user = (
        f"TASK ({intent.task_type.value}): {task.raw_input.strip()}\n"
        f"Restated intent: {intent.summary or '(none)'}{context}\n\n"
        "Return the JSON array of scoping questions now."
    )
    try:
        response = client.generate(user, system=system, use_thinking=False)
        array = extract_json_array(response)
    except LLMError:
        return []
    if not array:
        return []
    questions = [str(q).strip() for q in array if isinstance(q, str) and str(q).strip()]
    return questions[:max_questions]
