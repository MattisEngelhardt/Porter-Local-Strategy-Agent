"""Tests for the matplotlib image-chart engine (core/charts_image.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core import charts_image
from core.config import AppConfig
from models.visuals import ChartSeries, ChartSpec, ChartType

pytest.importorskip("matplotlib")

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _spec(kind: ChartType) -> ChartSpec:
    if kind == ChartType.DONUT:
        return ChartSpec(
            chart_type=kind,
            categories=["Auto", "Logistics", "Other"],
            series=[ChartSeries(values=[55, 30, 15])],
        )
    return ChartSpec(
        chart_type=kind,
        categories=["Apptronik", "Neura"],
        series=[ChartSeries(name="Funding", values=[935, 130])],
        caption="Funding round size",
        unit="m",
    )


@pytest.mark.parametrize("kind", list(ChartType))
def test_every_chart_family_renders_a_png(kind: ChartType) -> None:
    """Each ChartType produces a non-empty PNG (themed image, labeled axes)."""
    cfg = AppConfig()
    png = charts_image.render_chart_png(_spec(kind), cfg.output.colors, cfg.output.style)
    assert png is not None
    assert png.startswith(_PNG_SIGNATURE)
    assert len(png) > 1000


def test_add_image_chart_places_a_picture(tmp_path: Path) -> None:
    """The image chart is inserted as a picture on a real slide (fail-open returns True here)."""
    pptx = pytest.importorskip("pptx")
    prs = pptx.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    cfg = AppConfig()
    ok = charts_image.add_image_chart(
        slide,
        _spec(ChartType.COLUMN),
        cfg.output.colors,
        cfg.output.style,
        left_in=0.7,
        top_in=2.0,
        width_in=11.0,
        height_in=3.4,
    )
    assert ok is True
    assert any(shape.shape_type is not None for shape in slide.shapes)
    out = tmp_path / "deck.pptx"
    prs.save(str(out))
    assert out.exists()
