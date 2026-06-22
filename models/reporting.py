"""Pydantic models for the Builder (Finance / Controlling) dimension: management reporting.

Local, zero-hallucination consolidation of internal figures into a management/board report.
Every :class:`KeyFigure` carries its ``source`` (file / sheet / page) so each number is traceable
back to the documents — the cardinal rule of the doc-prep / finance playbooks.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class KeyFigure(BaseModel):
    """One reported figure, quoted verbatim with its provenance."""

    metric: str
    value: str  # kept as text to preserve exact formatting/unit (e.g. "€4.2M", "12.3%")
    period: str = ""
    source: str = ""  # file / sheet / page the figure came from


class ReportSection(BaseModel):
    """One themed section of the management report (a 'so-what' heading + bullets)."""

    heading: str
    bullets: list[str] = Field(default_factory=list)


class ManagementReport(BaseModel):
    """A consolidated management/board report built from internal documents (Builder dimension)."""

    title: str = ""
    period: str = ""
    bottom_line: str = ""
    key_figures: list[KeyFigure] = Field(default_factory=list)
    sections: list[ReportSection] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)  # what the documents do NOT answer
    sources: list[str] = Field(default_factory=list)  # source document file names
    language: str = "en"
