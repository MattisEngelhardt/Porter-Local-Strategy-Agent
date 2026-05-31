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


# --- Phase 4: structured per-template content (populated by core.content_shaper) ----------
class ScoringCriterion(BaseModel):
    """One weighted criterion of a decision/scoring matrix (E-1)."""

    name: str
    weight: float = Field(ge=0.0)  # relative weight; normalized to sum to 1 by the builder
    definition: str = ""  # how to score 1 (worst) .. 5 (best) — for the Criteria guide tab


class EntityScores(BaseModel):
    """One scored entity (company/option/partner) in a decision matrix (E-1)."""

    name: str
    scores: list[int] = Field(default_factory=list)  # one 1-5 score per criterion (in order)
    notes: list[str] = Field(default_factory=list)  # evidence per criterion (Research Notes tab)


class DecisionMatrixData(BaseModel):
    """Structured input for the E-1 Decision/Scoring Matrix (weighted SUMPRODUCT + RANK)."""

    title: str
    language: Language
    criteria: list[ScoringCriterion] = Field(default_factory=list)
    entities: list[EntityScores] = Field(default_factory=list)
