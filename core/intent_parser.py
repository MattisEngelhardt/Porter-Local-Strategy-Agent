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
from models.task import Audience, Depth, Intent, Language, OutputFormat, TaskRequest, TaskType

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
{brain_block}
Respond with ONLY a JSON object, no prose:
{{"task_type": "...", "depth": "...", "audience": "..." or null, "summary": "one short \
sentence restating the task"}}"""


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
    client: LocalLLMClient, config: AppConfig, task: TaskRequest, brain: str = ""
) -> Intent:
    """Parse a raw request into a structured :class:`Intent`.

    Language is heuristic (robust). The task type / depth / audience come from one fast LLM
    classification call; output formats are derived deterministically (SPEC §5.4). On any LLM
    or parse failure, conservative defaults are used (ADHOC / STANDARD / brief).

    Args:
        client: The LLM client (classification uses ``use_thinking=False``).
        config: The application config (``agent.default_language`` can force the language).
        task: The raw request.
        brain: Optional brain.md context to help infer audience/focus.

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

    return Intent(
        task_type=task_type,
        output_formats=route_outputs(task_type, explicit),
        language=language,
        depth=depth,
        audience=audience,
        summary=summary,
    )
