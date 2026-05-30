"""Pydantic v2 data contracts shared across the Strategy Agent.

All data flowing between modules uses these types — no untyped dicts (WORKFLOW §4).
"""

from __future__ import annotations

from models.deck import DeckStructure, SlideContent, SlideType
from models.research import (
    DocContent,
    FetchedContent,
    SearchQuery,
    SearchResult,
    SourceTier,
)
from models.synthesis import (
    AnalysisOutput,
    Section,
    SourceRef,
    SynthesisInput,
)
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
from models.workbook import (
    CellValue,
    ExcelTemplate,
    SheetDefinition,
    WorkbookContent,
)

__all__ = [
    # task
    "Audience",
    "ClarificationRound",
    "Depth",
    "Intent",
    "Language",
    "OutputFormat",
    "TaskRequest",
    "TaskType",
    # research
    "DocContent",
    "FetchedContent",
    "SearchQuery",
    "SearchResult",
    "SourceTier",
    # synthesis
    "AnalysisOutput",
    "Section",
    "SourceRef",
    "SynthesisInput",
    # deck
    "DeckStructure",
    "SlideContent",
    "SlideType",
    # workbook
    "CellValue",
    "ExcelTemplate",
    "SheetDefinition",
    "WorkbookContent",
]
