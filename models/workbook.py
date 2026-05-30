"""Workbook-layer Pydantic models: Excel template selection, sheets, and content.

Used by the Excel builder (Phase 4). Phase 1 only defines the contracts.
SPEC §15 explicitly requires these (ExcelTemplate, WorkbookContent, SheetDefinition)
to exist in Phase 1.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from models.task import Language

# A single Excel cell value. Avoids ``Any`` while covering all openpyxl-writable scalars.
CellValue = str | int | float | bool | None


class ExcelTemplate(StrEnum):
    """The four Excel templates (SPEC §12)."""

    DECISION_MATRIX = "decision_matrix"  # E-1
    BENCHMARK_TABLE = "benchmark_table"  # E-2
    BUSINESS_CASE_MODEL = "business_case_model"  # E-3
    TRACKER_DASHBOARD = "tracker_dashboard"  # E-4


class SheetDefinition(BaseModel):
    """One worksheet (tab). Tab names should be <=20 chars, no spaces (enforced by the
    Phase 4 builder per output_playbook, not validated here)."""

    name: str
    description: str = ""
    headers: list[str] = Field(default_factory=list)
    rows: list[list[CellValue]] = Field(default_factory=list)


class WorkbookContent(BaseModel):
    """A complete workbook definition rendered by openpyxl."""

    template: ExcelTemplate
    title: str
    language: Language
    sheets: list[SheetDefinition] = Field(default_factory=list)
