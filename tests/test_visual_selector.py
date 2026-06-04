"""Tests for the Editorial visual selector (core/visual_selector.py).

Deterministic chart attachment (0 LLM): a grounded column/timeline is attached to the right
slides/sections, an ungrounded or invented spec is dropped (anti-hallucination), tables are kept
(no info loss), and the master switch / budget contracts hold. Pure — no LLM, no I/O.
"""

from __future__ import annotations

from core.config import StyleConfig
from core.visual_selector import (
    attach_brief_visuals,
    attach_deck_diagrams,
    attach_deck_visuals,
)
from models.deck import DeckStructure, SlideContent, SlideType
from models.diagram import DiagramType
from models.research import Finding, ResearchReport, WorkerFindings
from models.synthesis import AnalysisOutput, Section
from models.task import Language
from models.visuals import ChartSeries, ChartSpec, ChartType


def _analysis(sections: list[Section] | None = None) -> AnalysisOutput:
    """An analysis whose evidence text carries the numbers 39 / 12 / 7 (for grounding).

    Labels start with letters (not digits) so the deterministic extractor reads the amount, not a
    company name like ``1X`` — the leading-digit edge case is covered in ``test_visuals``.
    """
    return AnalysisOutput(
        title="Funding race",
        language=Language.EN,
        bottom_line="Figure 39M, Apptronik 12M, Sanctuary 7M; rivals are better capitalized.",
        sections=sections
        or [Section(heading="Funding by company", body="Figure 39M; Apptronik 12M; Sanctuary 7M.")],
        sources=[],
    )


def _timeline_report() -> ResearchReport:
    """A report with three dated funding findings (55 / 120 / 300, consistent scale)."""
    return ResearchReport(
        worker_findings=[
            WorkerFindings(
                sub_topic="funding",
                findings=[
                    Finding(claim="Seed of $55M", date="2023-07"),
                    Finding(claim="Series B of $120M", date="2025-01"),
                    Finding(claim="Series C of $300M", date="2026-03"),
                ],
            )
        ]
    )


def _invented_spec() -> ChartSpec:
    """A chart whose values (888 / 999) never appear in the evidence → must be dropped."""
    return ChartSpec(
        chart_type=ChartType.COLUMN,
        categories=["Mars", "Venus"],
        series=[ChartSeries(name="x", values=[888.0, 999.0])],
    )


# ----------------------------------------------------------------- deck selection
def test_attach_deck_visuals_derives_grounded_column() -> None:
    """A data slide whose bullets carry grounded numbers gets a column chart."""
    deck = DeckStructure(
        title="t",
        language=Language.EN,
        slides=[
            SlideContent(slide_type=SlideType.TITLE, headline="t"),
            SlideContent(
                slide_type=SlideType.STRATEGIC_SIGNALS,
                headline="Rivals pull ahead on funding",
                bullets=["Figure 39M", "Apptronik 12M", "Sanctuary 7M"],
            ),
        ],
    )
    out = attach_deck_visuals(deck, _analysis(), None, StyleConfig())
    signal = out.slides[1]
    assert signal.visual is not None
    assert signal.visual.chart_type == ChartType.COLUMN
    assert signal.visual.series[0].values == [39.0, 12.0, 7.0]
    assert out.slides[0].visual is None  # title never charted


def test_attach_deck_visuals_drops_ungrounded() -> None:
    """A slide whose numbers are not in the evidence yields no chart (anti-hallucination)."""
    deck = DeckStructure(
        title="t",
        language=Language.EN,
        slides=[
            SlideContent(
                slide_type=SlideType.STRATEGIC_SIGNALS,
                headline="Invented",
                bullets=["Mars 888", "Venus 999"],
            )
        ],
    )
    out = attach_deck_visuals(deck, _analysis(), None, StyleConfig())
    assert out.slides[0].visual is None


def test_attach_deck_visuals_attaches_timeline_to_financial_slide() -> None:
    """A financial slide gets the report's dated-findings timeline (LINE) when available."""
    deck = DeckStructure(
        title="t",
        language=Language.EN,
        slides=[SlideContent(slide_type=SlideType.FINANCIAL_OVERVIEW, headline="Funding history")],
    )
    out = attach_deck_visuals(deck, _analysis(), _timeline_report(), StyleConfig())
    visual = out.slides[0].visual
    assert visual is not None and visual.chart_type == ChartType.LINE
    assert visual.categories == ["2023-07", "2025-01", "2026-03"]


def test_attach_deck_visuals_keeps_table_no_chart() -> None:
    """A slide carrying a richer table is left as a table (no derived chart → no info loss)."""
    deck = DeckStructure(
        title="t",
        language=Language.EN,
        slides=[
            SlideContent(
                slide_type=SlideType.COMPETITIVE_COMPARISON,
                headline="Comparison",
                bullets=["Figure 39M", "Apptronik 12M"],
                table=[
                    ["Co", "Funding", "HQ"],
                    ["Figure", "39M", "US"],
                    ["Apptronik", "12M", "US"],
                ],
            )
        ],
    )
    out = attach_deck_visuals(deck, _analysis(), None, StyleConfig())
    assert out.slides[0].visual is None


def test_attach_deck_visuals_regrounds_llm_proposed() -> None:
    """A folded-LLM ``visual`` is kept only if it grounds; an invented one is dropped."""
    grounded = ChartSpec(
        chart_type=ChartType.COLUMN,
        categories=["Figure", "1X", "Apptronik"],
        series=[ChartSeries(name="Funding (m)", values=[39.0, 12.0, 7.0])],
    )
    deck = DeckStructure(
        title="t",
        language=Language.EN,
        slides=[
            SlideContent(slide_type=SlideType.MARKET_LANDSCAPE, headline="A", visual=grounded),
            SlideContent(
                slide_type=SlideType.COMPANY_DEEP_DIVE, headline="B", visual=_invented_spec()
            ),
        ],
    )
    out = attach_deck_visuals(deck, _analysis(), None, StyleConfig())
    assert out.slides[0].visual is grounded  # grounded LLM proposal kept
    assert out.slides[1].visual is None  # invented LLM proposal dropped


def test_attach_deck_visuals_respects_master_switch() -> None:
    """``charts_enabled=False`` attaches nothing (the deck is returned unchanged)."""
    deck = DeckStructure(
        title="t",
        language=Language.EN,
        slides=[
            SlideContent(
                slide_type=SlideType.STRATEGIC_SIGNALS,
                headline="h",
                bullets=["Figure 39M", "Apptronik 12M", "Sanctuary 7M"],
            )
        ],
    )
    style = StyleConfig()
    style.charts_enabled = False
    out = attach_deck_visuals(deck, _analysis(), None, style)
    assert out is deck and out.slides[0].visual is None


# ----------------------------------------------------------------- brief selection
def test_attach_deck_diagrams_grounded_kpi_strip() -> None:
    """A data slide with grounded numbers and no chart gets a native KPI-strip diagram."""
    deck = DeckStructure(
        title="T",
        language=Language.EN,
        slides=[
            SlideContent(
                slide_type=SlideType.STRATEGIC_SIGNALS,
                headline="Signals",
                bullets=["Figure 39", "Apptronik 12", "Sanctuary 7"],
            )
        ],
    )
    out = attach_deck_diagrams(deck, _analysis(), None, StyleConfig())
    assert out.slides[0].diagram is not None
    assert out.slides[0].diagram.diagram_type == DiagramType.KPI_STRIP


def test_attach_deck_diagrams_chart_wins_over_diagram() -> None:
    """A slide already carrying a chart keeps it — no diagram is attached (one big visual)."""
    deck = DeckStructure(
        title="T",
        language=Language.EN,
        slides=[
            SlideContent(
                slide_type=SlideType.STRATEGIC_SIGNALS,
                headline="Has chart",
                bullets=["Figure 39", "Apptronik 12"],
                visual=ChartSpec(
                    chart_type=ChartType.COLUMN,
                    categories=["a", "b"],
                    series=[ChartSeries(name="x", values=[1.0, 2.0])],
                ),
            )
        ],
    )
    out = attach_deck_diagrams(deck, _analysis(), None, StyleConfig())
    assert out.slides[0].diagram is None


def test_attach_deck_diagrams_respects_budget() -> None:
    """``max_diagrams_per_deck`` of 0 attaches no diagrams (the budget contract)."""
    deck = DeckStructure(
        title="T",
        language=Language.EN,
        slides=[
            SlideContent(
                slide_type=SlideType.STRATEGIC_SIGNALS,
                headline="Signals",
                bullets=["Figure 39", "Apptronik 12"],
            )
        ],
    )
    out = attach_deck_diagrams(deck, _analysis(), None, StyleConfig(max_diagrams_per_deck=0))
    assert out.slides[0].diagram is None


def test_attach_brief_visuals_column_and_copy_is_nondestructive() -> None:
    """A numeric section body gets a captioned column chart; the original analysis is untouched."""
    analysis = _analysis(
        sections=[
            Section(heading="Funding by company", body="Figure 39M; Apptronik 12M; Sanctuary 7M.")
        ]
    )
    out = attach_brief_visuals(analysis, None, StyleConfig())
    assert out.sections[0].visual is not None
    assert out.sections[0].visual.caption == "Funding by company"
    assert analysis.sections[0].visual is None  # input not mutated (returns a copy)


def test_attach_brief_visuals_timeline_on_finance_section() -> None:
    """A funding/financial section is the home for the report's dated-findings timeline."""
    analysis = _analysis(
        sections=[Section(heading="Funding accelerates", body="The round momentum is real.")]
    )
    out = attach_brief_visuals(analysis, _timeline_report(), StyleConfig())
    visual = out.sections[0].visual
    assert visual is not None and visual.chart_type == ChartType.LINE


def test_attach_brief_visuals_drops_invented_preset() -> None:
    """A pre-set section visual whose values are not in the evidence is dropped (grounding gate)."""
    analysis = _analysis(
        sections=[Section(heading="Outlook", body="No numbers here.", visual=_invented_spec())]
    )
    out = attach_brief_visuals(analysis, None, StyleConfig())
    assert out.sections[0].visual is None
