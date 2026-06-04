"""Editorial visual selection (Block 4): attach source-grounded charts to decks & briefs.

This is the intelligence layer that turns the dormant visual engine (Blocks 1-3) into live
charts on real slides/sections. It is **deterministic and adds 0 extra LLM calls on the laptop
default** — a chart is derived from data Porter already has:

* a **timeline** (LINE) from the report's dated, numeric findings (SPEC §11 slide 5), and
* a **column** chart from numeric lines in a slide's bullets / a section's body
  (:func:`core.visuals.numbers_from_text` → :func:`core.visuals.chart_from_pairs`).

**Every** spec — deterministic *or* folded-LLM-proposed (``shape_deck`` on server/ultra) — passes
through :func:`core.visuals.validate_spec` against the analysis/evidence, so a value that is not
traceable to the evidence is never charted (anti-hallucination). Nothing is invented here; the
renderers own the per-deck/brief chart budget and the fail-open fallbacks. Pure, no LLM, no I/O.
"""

from __future__ import annotations

from core.config import StyleConfig
from core.diagrams import (
    kpi_strip_from_lines,
    process_from_bullets,
    validate_diagram,
)
from core.visuals import (
    chart_from_pairs,
    numbers_from_text,
    timeline_from_findings,
    validate_spec,
)
from models.deck import DeckStructure, SlideContent, SlideType
from models.diagram import DiagramSpec
from models.research import ResearchReport
from models.synthesis import AnalysisOutput, Section
from models.visuals import ChartSpec, ChartType

# Slide types whose message is data-comparison-shaped → a derived column chart can carry it.
# (TITLE/APPENDIX = never; EXECUTIVE_SUMMARY keeps its proof-card identity; SWOT keeps its grid;
# RECOMMENDATION stays a decision moment — any of these still keep an LLM-proposed, grounded chart.)
_DATA_SLIDE_TYPES = frozenset(
    {
        SlideType.MARKET_LANDSCAPE,
        SlideType.COMPANY_DEEP_DIVE,
        SlideType.FINANCIAL_OVERVIEW,
        SlideType.COMPETITIVE_COMPARISON,
        SlideType.STRATEGIC_SIGNALS,
    }
)
# Where a trend/timeline belongs, in attach priority order.
_TIMELINE_SLIDE_TYPES = (
    SlideType.FINANCIAL_OVERVIEW,
    SlideType.MARKET_LANDSCAPE,
    SlideType.COMPANY_DEEP_DIVE,
)
# Section heading/body cues that make a brief section the right home for a funding/metric timeline.
_FINANCE_HINTS = (
    "fund",
    "raise",
    "raised",
    "revenue",
    "valuation",
    "round",
    "capital",
    "burn",
    "arr",
    "investment",
    "umsatz",
    "finanz",
    "kapital",
    "€",
    "$",
    "eur",
    "usd",
)


def _evidence_corpus(analysis: AnalysisOutput, report: ResearchReport | None) -> str:
    """Concatenate everything Porter knows (analysis prose + finding claims) for grounding.

    A deterministic extractor reads the same text, so its chart grounds by construction; a folded
    LLM chart is gated against this same corpus — a value not present in it is dropped.
    """
    parts: list[str] = [analysis.bottom_line]
    parts.extend(section.body for section in analysis.sections)
    if report is not None:
        parts.extend(
            finding.claim for worker in report.worker_findings for finding in worker.findings
        )
    return "\n".join(part for part in parts if part)


def _column_from_text(text: str, *, caption: str) -> ChartSpec | None:
    """Build a single-series COLUMN chart from numeric lines in ``text`` (fail-open → ``None``)."""
    return chart_from_pairs(numbers_from_text(text), ChartType.COLUMN, caption=caption)


def _grounded(spec: ChartSpec | None, evidence: str) -> ChartSpec | None:
    """Pass a candidate spec through the anti-hallucination grounding gate."""
    return validate_spec(spec, evidence)


def _is_finance_section(section: Section) -> bool:
    """Whether a brief section is the natural home for a funding/metric timeline."""
    haystack = f"{section.heading}\n{section.body}".lower()
    return any(hint in haystack for hint in _FINANCE_HINTS)


def attach_deck_visuals(
    deck: DeckStructure,
    analysis: AnalysisOutput,
    report: ResearchReport | None,
    style: StyleConfig,
) -> DeckStructure:
    """Return a copy of ``deck`` with grounded ``SlideContent.visual`` filled where it adds value.

    Laptop default = deterministic, 0 extra LLM calls: a financial/market slide gets the report's
    dated-findings **timeline** (once), other data slides get a **column** chart derived from their
    own numeric bullets/body. A folded-LLM ``visual`` already on a slide (``shape_deck`` server/
    ultra) is kept only if it grounds. Slides with a ``table`` keep the richer table (no info loss);
    the renderer enforces ``style.max_charts_per_deck`` and falls back when a chart can't render.
    """
    if not style.charts_enabled:
        return deck
    evidence = _evidence_corpus(analysis, report)
    timeline = _grounded(timeline_from_findings(report, deck.language), evidence)
    timeline_used = False
    updated: list[SlideContent] = []
    for slide in deck.slides:
        visual: ChartSpec | None
        if slide.visual is not None:
            # A folded-LLM proposal (shape_deck, server/ultra) is re-grounded (anti-hallucination).
            visual = _grounded(slide.visual, evidence)
        elif slide.slide_type in _DATA_SLIDE_TYPES and not slide.table:
            wants_timeline = (
                not timeline_used
                and timeline is not None
                and slide.slide_type in _TIMELINE_SLIDE_TYPES
            )
            if wants_timeline:
                visual = timeline
                timeline_used = True
            else:
                text = "\n".join([*slide.bullets, slide.body or ""])
                visual = _grounded(_column_from_text(text, caption=""), evidence)
        else:
            visual = None
        updated.append(
            slide if visual is slide.visual else slide.model_copy(update={"visual": visual})
        )
    return deck.model_copy(update={"slides": updated})


def _diagram_for_slide(slide: SlideContent) -> DiagramSpec | None:
    """Pick a native schematic for a data slide that has no chart (KPI strip / process flow)."""
    if slide.slide_type not in _DATA_SLIDE_TYPES or slide.table:
        return None  # comparison tables keep their table; non-data slides keep their identity
    bullets = [str(b) for b in slide.bullets if str(b).strip()]
    kpi = kpi_strip_from_lines(bullets)
    if kpi is not None:
        return kpi
    if slide.slide_type == SlideType.STRATEGIC_SIGNALS:
        return process_from_bullets(bullets)
    return None


def attach_deck_diagrams(
    deck: DeckStructure,
    analysis: AnalysisOutput,
    report: ResearchReport | None,
    style: StyleConfig,
) -> DeckStructure:
    """Attach a grounded native diagram to data slides that did NOT get a chart (one big visual).

    Runs AFTER :func:`attach_deck_visuals` so charts win (a slide already carrying a ``visual`` is
    skipped). A KPI strip is derived from a slide's numeric bullets, a process flow from a
    strategic-signals slide's steps — both arrange existing content only and pass
    :func:`validate_diagram` (anti-hallucination). Respects ``style.max_diagrams_per_deck``.
    """
    if not style.charts_enabled or style.max_diagrams_per_deck <= 0:
        return deck
    evidence = _evidence_corpus(analysis, report)
    used = 0
    updated: list[SlideContent] = []
    for slide in deck.slides:
        spec: DiagramSpec | None = None
        if slide.diagram is None and slide.visual is None and used < style.max_diagrams_per_deck:
            spec = validate_diagram(_diagram_for_slide(slide), evidence)
        if spec is not None:
            used += 1
            updated.append(slide.model_copy(update={"diagram": spec}))
        else:
            updated.append(slide)
    return deck.model_copy(update={"slides": updated})


def attach_brief_visuals(
    analysis: AnalysisOutput,
    report: ResearchReport | None,
    style: StyleConfig,
) -> AnalysisOutput:
    """Return a copy of ``analysis`` with grounded ``Section.visual`` filled where it adds value.

    Deterministic + 0 extra LLM calls: a funding/financial section gets the report's dated-findings
    **timeline** (once), other sections get a **column** chart from numeric lines in their body. A
    pre-set section ``visual`` is kept only if it grounds. The PDF renderer enforces
    ``style.max_charts_per_brief`` and renders text-only when a chart is absent (fail-open).
    """
    if not style.charts_enabled:
        return analysis
    evidence = _evidence_corpus(analysis, report)
    timeline = _grounded(timeline_from_findings(report, analysis.language), evidence)
    timeline_used = False
    sections: list[Section] = []
    for section in analysis.sections:
        visual: ChartSpec | None
        if section.visual is not None:
            visual = _grounded(section.visual, evidence)
        elif not timeline_used and timeline is not None and _is_finance_section(section):
            visual = timeline
            timeline_used = True
        else:
            visual = _grounded(_column_from_text(section.body, caption=section.heading), evidence)
        sections.append(
            section if visual is section.visual else section.model_copy(update={"visual": visual})
        )
    return analysis.model_copy(update={"sections": sections})
