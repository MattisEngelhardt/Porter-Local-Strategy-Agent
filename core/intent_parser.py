"""Intent parser (Phase 3): classify the task, route to output format(s), detect language.

The reasoning chain (SPEC §5.3 step 1) starts here. One fast LLM classification call (no
thinking) yields the ``task_type`` / ``depth`` / ``audience`` / ``summary``; the output
format(s) are derived **deterministically** from the SPEC §5.4 task→output map plus any format
the user named explicitly (so dual-output detection — e.g. Business Case = Deck + Excel, N-6 —
is decided by the SPEC table, never by the LLM). Language is detected by a deterministic
heuristic, never from the LLM, so it can never silently flip on a bad JSON parse (SPEC REQ-5).
brain.md is injected so the model can infer audience/focus before the agent asks anything.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, TypeVar

from core.config import AppConfig
from core.json_utils import extract_json_object
from llm.local_llm_client import LLMError, LocalLLMClient
from models.task import (
    Audience,
    Depth,
    EffortLevel,
    Intent,
    Language,
    OutputFormat,
    TaskRequest,
    TaskType,
    WorkMode,
)

# --- language detection ------------------------------------------------------------------
# German function words (no umlaut) — umlauts/ß are detected separately and are decisive.
_GERMAN_WORDS = frozenset(
    {
        "der",
        "die",
        "das",
        "und",
        "oder",
        "ein",
        "eine",
        "einen",
        "ist",
        "sind",
        "mit",
        "von",
        "auf",
        "wir",
        "uns",
        "unsere",
        "unser",
        "soll",
        "sollen",
        "bitte",
        "erstelle",
        "erstellen",
        "bereite",
        "analysiere",
        "vergleiche",
        "screen",
        "nicht",
        "auch",
        "bei",
        "zum",
        "zur",
        "im",
        "den",
        "dem",
        "des",
        "wie",
        "was",
        "welche",
        "kunden",
        "markt",
        "unternehmen",
        "gegen",
        "mehr",
        "sehr",
        "kurze",
        "fuer",
        "diese",
        "dieser",
        "dieses",
        "als",
        "aus",
        "dass",
        "ich",
        "du",
        "sie",
        "er",
        "es",
        "neue",
        "neuen",
        "zwischen",
        "ohne",
        "nach",
        "vor",
        "um",
        "kann",
        "koennen",
        "muss",
        "wird",
        "haben",
        "hat",
        "sowie",
        "gegenueber",
        "machen",
        "mach",
        "geben",
        "moegliche",
    }
)
_WORD_RE = re.compile(r"[a-zà-ÿ]+")


def detect_language(text: str, default_language: str = "auto") -> Language:
    """Detect DE/EN deterministically; ``default_language`` (de/en) overrides ``auto``."""
    forced = (default_language or "auto").lower()
    if forced == "de":
        return Language.DE
    if forced == "en":
        return Language.EN
    lowered = text.lower()
    if any(ch in lowered for ch in "äöüß"):
        return Language.DE
    hits = sum(1 for token in _WORD_RE.findall(lowered) if token in _GERMAN_WORDS)
    return Language.DE if hits >= 2 else Language.EN


# --- output routing (SPEC §5.4) ----------------------------------------------------------
_OUTPUT_ROUTE: dict[TaskType, list[OutputFormat]] = {
    TaskType.COMPETITOR_ANALYSIS: [OutputFormat.BRIEF],
    TaskType.MARKET_RESEARCH: [OutputFormat.BRIEF],
    TaskType.MARKET_ANALYSIS: [OutputFormat.BRIEF],
    TaskType.TARGET_SCREENING: [OutputFormat.EXCEL, OutputFormat.BRIEF],
    TaskType.PARTNERSHIP_EVALUATION: [OutputFormat.EXCEL],
    TaskType.BUSINESS_CASE: [OutputFormat.DECK, OutputFormat.EXCEL],  # dual output (N-6)
    TaskType.BOARD_PREP: [OutputFormat.DECK],
    TaskType.MEETING_BRIEFING: [OutputFormat.BRIEF],
    TaskType.DOCUMENT_SYNTHESIS: [OutputFormat.BRIEF],
    TaskType.OPTION_COMPARISON: [OutputFormat.EXCEL],
    TaskType.FINANCIAL_BENCHMARK: [OutputFormat.EXCEL, OutputFormat.BRIEF],
    TaskType.STRATEGIC_INITIATIVE: [OutputFormat.BRIEF, OutputFormat.EXCEL],
    TaskType.PIPELINE_TRACKING: [OutputFormat.EXCEL],
    TaskType.INDUSTRY_NEWS: [OutputFormat.BRIEF],
    TaskType.ADHOC: [OutputFormat.BRIEF],
}

# Stable display order when the user names formats explicitly.
_FORMAT_ORDER = [OutputFormat.BRIEF, OutputFormat.DECK, OutputFormat.EXCEL]

_FORMAT_KEYWORDS: dict[OutputFormat, tuple[str, ...]] = {
    OutputFormat.DECK: (
        "deck",
        "slides",
        "präsentation",
        "presentation",
        "powerpoint",
        "pptx",
        "folien",
    ),
    OutputFormat.EXCEL: (
        "excel",
        "xlsx",
        "spreadsheet",
        "matrix",
        "matrize",
        "benchmark table",
        "tracker",
        "workbook",
        "tabelle",
    ),
    OutputFormat.BRIEF: ("brief", "one-pager", "onepager", "memo"),
}


def detect_explicit_formats(text: str) -> list[OutputFormat]:
    """Return the output formats the user named explicitly (keyword scan), in display order."""
    lowered = text.lower()
    found = {fmt for fmt, kws in _FORMAT_KEYWORDS.items() if any(kw in lowered for kw in kws)}
    return [fmt for fmt in _FORMAT_ORDER if fmt in found]


def route_outputs(
    task_type: TaskType, explicit: list[OutputFormat] | None = None
) -> list[OutputFormat]:
    """Map a task type to its default output format(s); an explicit user request overrides."""
    if explicit:
        return [fmt for fmt in _FORMAT_ORDER if fmt in explicit]
    return list(_OUTPUT_ROUTE.get(task_type, [OutputFormat.BRIEF]))


# --- work-mode routing (Phase 3.5: internal doc-prep vs web research) --------------------
# Phrases that force fresh web research even when documents are attached (e.g. "compare the
# attached memo against the latest market data online").
_RESEARCH_FORCE_KEYWORDS = (
    "recherchiere",
    "recherche",
    "research online",
    "research the",
    "search the web",
    "im internet",
    "aktuelle news",
    "latest news",
    "market data",
    "marktdaten",
    "wettbewerb",
    "competitor",
    "online suchen",
    "find out about",
    "such nach",
)

# Phrases that clearly mean "consolidate these internal documents for management" (doc-prep).
_DOCPREP_KEYWORDS = (
    "fasse",
    "zusammenfass",
    "zusammen fass",
    "aufbereit",
    "aufzubereiten",
    "bündel",
    "buendel",
    "konsolidier",
    "consolidate",
    "summarize",
    "summarise",
    "summary of",
    "prepare",
    "fürs management",
    "für das management",
    "for management",
    "for the board",
    "fürs board",
    "board-ready",
    "briefing",
    "one-pager",
    "aus diesen dokumenten",
    "aus den dokumenten",
    "from these documents",
    "based on the attached",
    "based on these",
)


def classify_work_mode(task_text: str, has_documents: bool) -> WorkMode | None:
    """Classify the work mode, or return ``None`` when it is genuinely ambiguous (Phase 3.5).

    No documents → always RESEARCH. With documents: an explicit web-research phrase → RESEARCH; an
    explicit "consolidate for management" phrase → DOCUMENT_PREP; otherwise ``None`` — the caller
    should ask the user rather than guess (the agent must be sure which mode it is in).
    """
    if not has_documents:
        return WorkMode.RESEARCH
    lowered = task_text.lower()
    research = any(kw in lowered for kw in _RESEARCH_FORCE_KEYWORDS)
    docprep = any(kw in lowered for kw in _DOCPREP_KEYWORDS)
    if research and not docprep:
        return WorkMode.RESEARCH
    if docprep and not research:
        return WorkMode.DOCUMENT_PREP
    return None  # unclear (both or neither signal) → ask the user


def route_mode(task_text: str, has_documents: bool, task_type: TaskType) -> WorkMode:
    """Resolve a definite work mode (non-interactive). Ambiguity defaults to DOCUMENT_PREP.

    Documents attached → DOCUMENT_PREP (consolidate them for management) unless the task clearly
    asks to pull fresh web data. No documents → RESEARCH. Interactive callers should prefer
    :func:`classify_work_mode` and ask the user when it returns ``None``.
    """
    decided = classify_work_mode(task_text, has_documents)
    if decided is not None:
        return decided
    return WorkMode.DOCUMENT_PREP


# --- effort detection + override (Phase 3.5, SPEC §15.5) ---------------------------------
# Effort ordering for "take the higher of" combinations.
_EFFORT_ORDER: dict[EffortLevel, int] = {
    EffortLevel.LOW: 0,
    EffortLevel.HIGH: 1,
    EffortLevel.ULTRA: 2,
}

# Explicit user words that pin the effort (the user's words win over inference).
_ULTRA_KEYWORDS = (
    "ultra",
    "vollständig",
    "vollstaendig",
    "umfassend",
    "tiefgehend",
    "tiefe analyse",
    "in die tiefe",
    "deep dive",
    "deep-dive",
    "deepdive",
    "in-depth",
    "in depth",
    "exhaustive",
    "comprehensive",
    "thorough",
    "gründlich",
    "gruendlich",
    "detaillierte analyse",
    "sehr detailliert",
)
_LOW_KEYWORDS = (
    "quick",
    "schnell",
    "kurz",
    "kurzer",
    "kurze",
    "kurzen",
    "überblick",
    "ueberblick",
    "overview",
    "tl;dr",
    "tldr",
    "in a nutshell",
    "auf die schnelle",
)

# Task types heavy enough to floor effort at HIGH (never run shallow even if unsure).
_HIGH_FLOOR_TASKS = frozenset(
    {
        TaskType.TARGET_SCREENING,
        TaskType.BUSINESS_CASE,
        TaskType.BOARD_PREP,
        TaskType.FINANCIAL_BENCHMARK,
        TaskType.PARTNERSHIP_EVALUATION,
        TaskType.MARKET_ANALYSIS,
        TaskType.STRATEGIC_INITIATIVE,
    }
)

_EFFORT_OVERRIDE_RE = re.compile(r"^\s*/effort\s+(low|high|ultra)\b[\s:,-]*", re.IGNORECASE)


def _coerce_effort(value: object) -> EffortLevel | None:
    """Coerce a raw value (LLM hint / token) into :class:`EffortLevel` or ``None``."""
    if isinstance(value, str):
        try:
            return EffortLevel(value.strip().lower())
        except ValueError:
            return None
    return None


def _effort_keyword(text: str) -> EffortLevel | None:
    """Return the effort a user pinned with explicit words (ULTRA beats LOW), or ``None``."""
    lowered = text.lower()
    if any(kw in lowered for kw in _ULTRA_KEYWORDS):
        return EffortLevel.ULTRA
    if any(kw in lowered for kw in _LOW_KEYWORDS):
        return EffortLevel.LOW
    return None


def _higher(a: EffortLevel, b: EffortLevel) -> EffortLevel:
    """Return the more intensive of two effort levels."""
    return a if _EFFORT_ORDER[a] >= _EFFORT_ORDER[b] else b


def detect_effort(
    task_text: str, task_type: TaskType, llm_suggestion: EffortLevel | None
) -> EffortLevel:
    """Auto-detect the effort level (master dial) for a task (SPEC §15.5).

    Precedence: an explicit user keyword (``ultra``/``vollständig`` → ULTRA; ``quick``/``kurz`` →
    LOW) wins. Otherwise the LLM's suggestion is combined with a task-type floor (heavy task types
    floor at HIGH). When nothing is clear, default to **HIGH** — never silently shallow (RULE 9).
    """
    keyword = _effort_keyword(task_text)
    if keyword is not None:
        return keyword

    floor = EffortLevel.HIGH if task_type in _HIGH_FLOOR_TASKS else None
    if llm_suggestion is None:
        return floor or EffortLevel.HIGH
    return _higher(llm_suggestion, floor) if floor is not None else llm_suggestion


def parse_effort_override(text: str) -> tuple[EffortLevel | None, str]:
    """Strip a leading ``/effort low|high|ultra`` token (REPL/CLI), returning (level, rest).

    Explicit override always wins over auto-detection. With no valid token the text is returned
    unchanged and the level is ``None``.
    """
    match = _EFFORT_OVERRIDE_RE.match(text)
    if match is None:
        return None, text
    level = _coerce_effort(match.group(1))
    return level, text[match.end() :].strip()


# --- LLM classification ------------------------------------------------------------------
_E = TypeVar("_E", bound=StrEnum)

_CLASSIFIER_SYSTEM = """You are the intent classifier of a local strategy/research agent used \
at Neura Robotics. Classify the user's task into ONE task_type, a depth, and (if clear) an \
audience.

Allowed task_type:
- competitor_analysis: deep-dive on ONE company
- market_research / market_analysis: a market or sector overview
- target_screening: screen/compare MULTIPLE companies as M&A/investment targets
- partnership_evaluation: score/evaluate potential partners
- business_case: build a business/investment case (market size, investment, ROI)
- board_prep: prepare a board/management presentation
- meeting_briefing: prep for a meeting with a person/company
- document_synthesis: summarize/analyze a provided document
- option_comparison: compare a few options/choices
- financial_benchmark: funding/valuation/financial comparison across companies
- strategic_initiative: strategic initiative / make-vs-buy / expansion analysis
- pipeline_tracking: build a tracker/dashboard for ongoing items
- industry_news: recent news/developments synthesis
- adhoc: anything else / quick ad-hoc question

Allowed depth: quick | standard | deep
Allowed audience: ceo_board | strategy_team | personal | null
Allowed effort: low | high | ultra — how much research effort the task warrants. low = a quick \
fact/news lookup; high = a normal multi-angle analysis; ultra = an exhaustive deep-dive across \
many angles. Default to high when unsure.
{brain_block}
Respond with ONLY a JSON object, no prose:
{{"task_type": "...", "depth": "...", "effort": "...", "audience": "..." or null, "summary": \
"one short sentence restating the task"}}"""


def _coerce_enum(enum_cls: type[_E], value: object, default: _E) -> _E:
    """Coerce a raw JSON value into ``enum_cls`` (case-insensitive), or return ``default``."""
    if isinstance(value, str):
        try:
            return enum_cls(value.strip().lower())
        except ValueError:
            return default
    return default


def _coerce_audience(value: object) -> Audience | None:
    """Coerce a raw JSON audience value into :class:`Audience` or ``None``."""
    if not isinstance(value, str):
        return None
    cleaned = value.strip().lower()
    if cleaned in {"", "none", "null", "unknown"}:
        return None
    try:
        return Audience(cleaned)
    except ValueError:
        return None


def _classify(client: LocalLLMClient, raw_input: str, brain: str) -> dict[str, Any] | None:
    """Run the fast classification call and return the parsed JSON object (or ``None``)."""
    brain_block = f"\nPersistent context (may inform audience/focus):\n{brain}\n" if brain else "\n"
    system = _CLASSIFIER_SYSTEM.format(brain_block=brain_block)
    prompt = f'Task:\n"""\n{raw_input}\n"""\n\nReturn the JSON object now.'
    try:
        response = client.generate(prompt, system=system, use_thinking=False)
    except LLMError:
        return None
    return extract_json_object(response)


def parse_intent(
    client: LocalLLMClient,
    config: AppConfig,
    task: TaskRequest,
    brain: str = "",
    effort_override: EffortLevel | None = None,
) -> Intent:
    """Parse a raw request into a structured :class:`Intent`.

    Language is heuristic (robust). The task type / depth / audience / effort hint come from one
    fast LLM classification call; output formats are derived deterministically (SPEC §5.4) and the
    effort master dial is resolved by :func:`detect_effort` (or forced by ``effort_override``). On
    any LLM or parse failure, conservative defaults are used (ADHOC / STANDARD / HIGH / brief).

    Args:
        client: The LLM client (classification uses ``use_thinking=False``).
        config: The application config (``agent.default_language`` can force the language).
        task: The raw request (with any ``/effort`` prefix already stripped by the caller).
        brain: Optional brain.md context to help infer audience/focus.
        effort_override: An explicit effort (``/effort`` / ``--effort``) that wins over auto-detect.

    Returns:
        A fully populated :class:`Intent`.
    """
    language = detect_language(task.raw_input, config.agent.default_language)
    data = _classify(client, task.raw_input, brain) or {}

    task_type = _coerce_enum(TaskType, data.get("task_type"), TaskType.ADHOC)
    depth = _coerce_enum(Depth, data.get("depth"), Depth.STANDARD)
    audience = _coerce_audience(data.get("audience"))
    summary = str(data.get("summary") or "").strip()
    explicit = detect_explicit_formats(task.raw_input)
    effort = effort_override or detect_effort(
        task.raw_input, task_type, _coerce_effort(data.get("effort"))
    )

    return Intent(
        task_type=task_type,
        output_formats=route_outputs(task_type, explicit),
        language=language,
        depth=depth,
        effort=effort,
        audience=audience,
        summary=summary,
    )
