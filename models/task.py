"""Task-layer Pydantic models: the user's request and its parsed intent.

These types flow from the intake/intent layer (Phase 3) onward. Phase 1 only
defines them. No behavior lives here — pure data contracts (WORKFLOW §4).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class OutputFormat(str, Enum):
    """The three first-class output types (SPEC §4.6)."""

    BRIEF = "brief"  # PDF brief
    DECK = "deck"  # PPTX deck
    EXCEL = "excel"  # .xlsx workbook


class Language(str, Enum):
    """Detected I/O language. Config may use 'auto'; detection resolves to one of these."""

    DE = "de"
    EN = "en"


class TaskType(str, Enum):
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


class Depth(str, Enum):
    """Research depth (SPEC §5.2)."""

    QUICK = "quick"  # 10-15 min
    STANDARD = "standard"  # 25-35 min
    DEEP = "deep"  # 45-60 min


class Audience(str, Enum):
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
    audience: Audience | None = None
    summary: str = ""  # short restatement of what the user wants


class ClarificationRound(BaseModel):
    """One clarification turn (max 2 per task, SPEC §5.2)."""

    question: str
    answer: str | None = None
