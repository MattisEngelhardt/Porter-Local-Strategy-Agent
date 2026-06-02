"""Tests for the Porter visual engine (models/visuals.py + core/visuals.py).

Cover the chart-spec contract, the anti-hallucination validation gate, the deterministic
extractors, the pure SVG renderer, and the native python-pptx chart builder (fail-open).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from core.config import ColorsConfig, StyleConfig
from core.visuals import (
    add_native_chart,
    chart_from_pairs,
    numbers_from_text,
    numbers_in_text,
    render_chart_svg,
    timeline_from_findings,
    validate_spec,
)
from models.research import Finding, ResearchReport, WorkerFindings
from models.task import Language
from models.visuals import ChartSeries, ChartSpec, ChartType


def _spec(chart_type: ChartType = ChartType.COLUMN) -> ChartSpec:
    return ChartSpec(
        chart_type=chart_type,
        categories=["Figure AI", "1X", "Apptronik"],
        series=[ChartSeries(name="Funding (EUR m)", values=[39.0, 12.0, 7.0])],
        caption="Figure AI leads on funding",
        unit="m",
    )


# --- ChartSpec contract ------------------------------------------------------------------
def test_chartspec_valid_build() -> None:
    spec = _spec()
    assert spec.chart_type == ChartType.COLUMN
    assert len(spec.series[0].values) == len(spec.categories)


def test_chartspec_rejects_length_mismatch() -> None:
    with pytest.raises(ValidationError):
        ChartSpec(
            chart_type=ChartType.COLUMN,
            categories=["a", "b", "c"],
            series=[ChartSeries(values=[1.0, 2.0])],  # too short
        )


def test_chartspec_rejects_empty_and_nonfinite() -> None:
    with pytest.raises(ValidationError):
        ChartSpec(chart_type=ChartType.BAR, categories=[], series=[ChartSeries(values=[])])
    with pytest.raises(ValidationError):
        ChartSpec(
            chart_type=ChartType.LINE,
            categories=["a", "b"],
            series=[ChartSeries(values=[float("nan"), 1.0])],
        )


# --- validation gate (anti-hallucination) ------------------------------------------------
def test_validate_spec_passes_grounded() -> None:
    spec = _spec()
    evidence = "Figure AI raised 39, 1X has 12, Apptronik 7 — funding in EUR m."
    assert validate_spec(spec, evidence) is spec


def test_validate_spec_drops_ungrounded() -> None:
    spec = _spec()
    # none of 39/12/7 appear in the evidence → invented numbers → dropped
    assert validate_spec(spec, "The market is growing and competition intensifies.") is None


def test_validate_spec_drops_thin_or_flat() -> None:
    assert validate_spec(None) is None
    one_cat = ChartSpec(
        chart_type=ChartType.COLUMN, categories=["a"], series=[ChartSeries(values=[1.0])]
    )
    assert validate_spec(one_cat) is None  # < 2 categories
    flat = ChartSpec(
        chart_type=ChartType.COLUMN, categories=["a", "b"], series=[ChartSeries(values=[5.0, 5.0])]
    )
    assert validate_spec(flat) is None  # every value identical → says nothing


def test_validate_spec_skips_grounding_without_evidence() -> None:
    assert validate_spec(_spec()) is not None  # no evidence text → grounding skipped
    assert validate_spec(_spec(), "") is not None  # empty evidence → grounding skipped


# --- numeric helpers ---------------------------------------------------------------------
def test_numbers_in_text() -> None:
    present = numbers_in_text("Revenue 4.2M, burn 1,200 per month, 35%")
    assert "4.2" in present and "4" in present
    assert "1200" in present
    assert "35" in present


def test_numbers_from_text_pairs() -> None:
    text = "Figure AI: $39B\n1X: $12B\nApptronik: $7B"
    pairs = numbers_from_text(text)
    labels = [label for label, _ in pairs]
    assert "Figure AI" in labels and "1X" in labels
    assert len(pairs) == 3


def test_chart_from_pairs() -> None:
    spec = chart_from_pairs([("A", 1.0), ("B", 2.0)], ChartType.COLUMN, caption="x")
    assert spec is not None and spec.categories == ["A", "B"]
    assert chart_from_pairs([("A", 1.0)]) is None  # < 2 points


# --- timeline extraction -----------------------------------------------------------------
def test_timeline_from_findings_builds_line() -> None:
    report = ResearchReport(
        worker_findings=[
            WorkerFindings(
                sub_topic="funding",
                findings=[
                    Finding(claim="Series B of $120M", date="2025-01"),
                    Finding(claim="Seed of $55M", date="2023-07"),
                    Finding(claim="Series C of $300M", date="2026-03"),
                ],
            )
        ]
    )
    spec = timeline_from_findings(report, Language.EN)
    assert spec is not None
    assert spec.chart_type == ChartType.LINE
    assert spec.categories == ["2023-07", "2025-01", "2026-03"]  # sorted by date
    assert spec.series[0].values == [55.0, 120.0, 300.0]


def test_timeline_rejects_mixed_scales_and_thin() -> None:
    mixed = ResearchReport(
        worker_findings=[
            WorkerFindings(
                sub_topic="x",
                findings=[
                    Finding(claim="raised $55M", date="2023"),
                    Finding(claim="now 3 offices", date="2025"),  # bare number, different scale
                ],
            )
        ]
    )
    assert timeline_from_findings(mixed, Language.EN) is None
    assert timeline_from_findings(None, Language.EN) is None


# --- SVG rendering -----------------------------------------------------------------------
@pytest.mark.parametrize(
    "chart_type", [ChartType.COLUMN, ChartType.BAR, ChartType.LINE, ChartType.AREA, ChartType.DONUT]
)
def test_render_chart_svg_each_type(chart_type: ChartType) -> None:
    svg = render_chart_svg(_spec(chart_type), ColorsConfig(), StyleConfig())
    assert svg.startswith("<svg") and svg.endswith("</svg>")
    assert "Figure AI leads on funding" in svg  # caption rendered
    assert "Apptronik" in svg  # a category label/legend entry is rendered
    if chart_type == ChartType.DONUT:
        assert "%" in svg  # donut shows shares
    else:
        assert "39" in svg  # value labels present


def test_render_bars_have_rects_lines_have_paths() -> None:
    cols = render_chart_svg(_spec(ChartType.COLUMN), ColorsConfig(), StyleConfig())
    assert "<rect" in cols
    line = render_chart_svg(_spec(ChartType.LINE), ColorsConfig(), StyleConfig())
    assert "<path" in line and "<circle" in line
    donut = render_chart_svg(_spec(ChartType.DONUT), ColorsConfig(), StyleConfig())
    assert "<path" in donut


def test_render_chart_svg_on_dark_uses_light_text() -> None:
    colors = ColorsConfig()
    svg = render_chart_svg(_spec(), colors, StyleConfig(), on_dark=True)
    assert colors.white.upper() in svg.upper()


# --- native PPTX chart (fail-open) -------------------------------------------------------
def test_add_native_chart_creates_editable_chart() -> None:
    pptx = pytest.importorskip("pptx")
    prs = pptx.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ok = add_native_chart(
        slide, _spec(), ColorsConfig(), left_in=1.0, top_in=1.0, width_in=6.0, height_in=4.0
    )
    assert ok is True
    assert any(getattr(shape, "has_chart", False) for shape in slide.shapes)


def test_add_native_chart_donut() -> None:
    pptx = pytest.importorskip("pptx")
    prs = pptx.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    ok = add_native_chart(
        slide,
        _spec(ChartType.DONUT),
        ColorsConfig(),
        left_in=1.0,
        top_in=1.0,
        width_in=5.0,
        height_in=4.0,
    )
    assert ok is True
