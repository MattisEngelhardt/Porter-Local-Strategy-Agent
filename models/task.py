"""Task-layer Pydantic models: the user's request and its parsed intent.

These types flow from the intake/intent layer (Phase 3) onward. Phase 1 only
defines them. No behavior lives here — pure data contracts (WORKFLOW §4).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class OutputFormat(StrEnum):
    """The three first-class output types (SPEC §4.6)."""

    BRIEF = "brief"  # PDF brief
    DECK = "deck"  # PPTX deck
    EXCEL = "excel"  # .xlsx workbook


class Language(StrEnum):
    """Detected I/O language. Config may use 'auto'; detection resolves to one of these."""

    DE = "de"
    EN = "en"


class TaskType(StrEnum):
    """Task categories the agent recognizes (SPEC §3.4 / §5.4)."""

    COMPETITOR_ANALYSIS = "competitor_analysis"
    MARKET_RESEARCH = "market_research"
    MARKET_ANALYSIS = "market_analysis"
    TARGET_SCREENING = "target_screening"
    PARTNERSHIP_EVALUATION = "partnership_evaluation"
    BUSINESS_CASE = "business_case"
    BOARD_PREP = "board_prep"
    MEETING_BRIEFING = "meeting_briefing"
    DOCUMENT_SYNTHESIS = "document_synthesis"
    OPTION_COMPARISON = "option_comparison"
    FINANCIAL_BENCHMARK = "financial_benchmark"
    STRATEGIC_INITIATIVE = "strategic_initiative"
    PIPELINE_TRACKING = "pipeline_tracking"
    INDUSTRY_NEWS = "industry_news"
    ADHOC = "adhoc"


class Depth(StrEnum):
    """Research depth (SPEC §5.2)."""

    QUICK = "quick"  # 10-15 min
    STANDARD = "standard"  # 25-35 min
    DEEP = "deep"  # 45-60 min


class EffortLevel(StrEnum):
    """Effort master dial (Phase 3.5, SPEC §15.5): one knob for the whole loop's intensity.

    Auto-detected from task complexity and overridable (``/effort`` in the REPL, ``--effort`` on
    ``analyze``). Drives every budget via ``config.effort.level_for(...)``. ``Depth`` is derived
    from effort for the time estimate only; effort is the gating dial everywhere.
    """

    LOW = "low"  # ~12 min: 1 worker, 1 round, no critique
    HIGH = "high"  # ~30 min: 3 workers, 2 rounds, critique + 1 revision (default when unsure)
    ULTRA = "ultra"  # ~60+ min: 5 workers, 3 rounds, critique + 2 revisions


class Audience(StrEnum):
    """Intended audience for the output (SPEC §5.2)."""

    CEO_BOARD = "ceo_board"
    STRATEGY_TEAM = "strategy_team"
    PERSONAL = "personal"


class TaskRequest(BaseModel):
    """A raw request entering the agent (text + optional attached files)."""

    raw_input: str
    attachments: list[Path] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)


class Intent(BaseModel):
    """Parsed intent for a request (produced by the intent parser in Phase 3)."""

    task_type: TaskType
    output_formats: list[OutputFormat]
    language: Language
    depth: Depth = Depth.STANDARD
    effort: EffortLevel = EffortLevel.HIGH  # master dial (Phase 3.5); default never shallow
    audience: Audience | None = None
    summary: str = ""  # short restatement of what the user wants


class ClarificationRound(BaseModel):
    """One clarification turn (max 3 per task — user-authorized override of SPEC §5.2)."""

    question: str
    answer: str | None = None


class ResearchPlan(BaseModel):
    """Decomposed research plan: 3-5 concrete sub-questions + a confirm summary (SPEC §5.3)."""

    sub_questions: list[str] = Field(default_factory=list)
    summary: str = ""  # the bilingual "N Suchanfragen, … ~25 Min. Los?" confirmation line
