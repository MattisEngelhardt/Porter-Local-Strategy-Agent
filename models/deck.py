"""Deck-layer Pydantic models: PPTX slide content and deck structure.

Used by the PPTX exporter (Phase 4). Phase 1 only defines the contracts.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from models.task import Audience, Language


class SlideType(StrEnum):
    """The 10 slide types (SPEC §11)."""

    TITLE = "title"
    EXECUTIVE_SUMMARY = "executive_summary"
    MARKET_LANDSCAPE = "market_landscape"
    COMPANY_DEEP_DIVE = "company_deep_dive"
    FINANCIAL_OVERVIEW = "financial_overview"
    COMPETITIVE_COMPARISON = "competitive_comparison"
    STRATEGIC_SIGNALS = "strategic_signals"
    SWOT = "swot"
    RECOMMENDATION = "recommendation"
    APPENDIX = "appendix"


class SlideContent(BaseModel):
    """Content for a single slide. ``headline`` is the 'so what', never a topic label."""

    slide_type: SlideType
    headline: str
    bullets: list[str] = Field(default_factory=list)
    body: str | None = None
    table: list[list[str]] | None = None  # row-major; row 0 = header
    notes: str | None = None  # speaker notes


class DeckStructure(BaseModel):
    """A complete deck definition rendered by python-pptx."""

    title: str
    language: Language
    slides: list[SlideContent] = Field(default_factory=list)
    audience: Audience | None = None
