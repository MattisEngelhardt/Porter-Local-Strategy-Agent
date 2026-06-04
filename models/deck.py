"""Deck-layer Pydantic models: PPTX slide content and deck structure.

Used by the PPTX exporter (Phase 4). Phase 1 only defines the contracts.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from models.diagram import DiagramSpec
from models.task import Audience, Language
from models.visuals import ChartSpec


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


class Archetype(StrEnum):
    """A visual layout archetype (Editorial v4.0). ``AUTO`` lets the design-director decide.

    Decoupled from :class:`SlideType` (the *semantic* kind): the director maps a slide's type +
    content shape + deck position onto one of these layouts so the deck has intentional variety.
    """

    AUTO = "auto"
    STATEMENT = "statement"  # full-bleed saturated manifesto
    METRIC_HERO = "metric_hero"  # one/two giant numerals
    COLORBLOCK_GRID = "colorblock_grid"  # saturated numbered cards
    EDITORIAL_SPLIT = "editorial_split"  # asymmetric serif + negative space
    QUOTE = "quote"  # oversized pull-statement
    TABLE = "table"  # comparison table
    MATRIX = "matrix"  # 2x2 quadrants
    CHART = "chart"  # native data chart
    APPENDIX = "appendix"  # sources / reference list
    CONTENT = "content"  # universal fallback (cards)


class SlideContent(BaseModel):
    """Content for a single slide. ``headline`` is the 'so what', never a topic label."""

    slide_type: SlideType
    headline: str
    bullets: list[str] = Field(default_factory=list)
    body: str | None = None
    table: list[list[str]] | None = None  # row-major; row 0 = header
    notes: str | None = None  # speaker notes
    visual: ChartSpec | None = None  # optional data chart for this slide (Editorial visual engine)
    diagram: DiagramSpec | None = None  # optional native schematic (Schaubild) for this slide
    archetype: Archetype = Archetype.AUTO  # AUTO → director decides; a high-effort LLM may hint
    emphasis: str | None = None  # optional coarse layout hint (whitelisted; ignored if unknown)


class DeckStructure(BaseModel):
    """A complete deck definition rendered by python-pptx."""

    title: str
    language: Language
    slides: list[SlideContent] = Field(default_factory=list)
    audience: Audience | None = None
