"""Visual-layer Pydantic models: typed chart specifications for PDF/PPTX rendering.

A :class:`ChartSpec` is a canonical, render-agnostic description of a data chart (the
"structured chart spec" pattern — far more reliable for small local models than generated plot
code). The renderers in ``core/visuals.py`` turn it into native ``python-pptx`` charts and
hand-built SVG; ``core/design.py`` supplies the palette/fonts. Specs only ever carry numbers
already present in the analysis/evidence — anti-hallucination is enforced in ``core.visuals``.
"""

from __future__ import annotations

import math
from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class ChartType(StrEnum):
    """The core data-chart families (SPEC §11 + output_playbook)."""

    COLUMN = "column"  # vertical bars — ranking/comparison across categories
    BAR = "bar"  # horizontal bars — ranking with long labels
    LINE = "line"  # trend/timeline over an ordered axis
    AREA = "area"  # trend with magnitude emphasis
    DONUT = "donut"  # share of a whole (categories sum to ~100%)


class ChartSeries(BaseModel):
    """One named data series. ``values`` align positionally with the spec's ``categories``."""

    name: str = ""
    values: list[float] = Field(default_factory=list)


class ChartSpec(BaseModel):
    """A render-agnostic chart description. Any constructed instance is structurally renderable.

    Structural invariants (enforced here): at least one category and one series, every series has
    exactly one value per category, and all values are finite. Semantic gating (>=2 data points,
    every number traceable to the evidence) lives in :func:`core.visuals.validate_spec` so the
    fail-open guard can drop a thin/hallucinated spec without raising.
    """

    chart_type: ChartType
    categories: list[str] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)
    caption: str = ""  # the "so what" one-liner shown with the chart
    unit: str = ""  # e.g. "EUR m", "%", "x"
    source: str = ""  # short provenance label (never invented)
    note: str = ""  # optional small footnote (e.g. recency/evidence flag)

    @model_validator(mode="after")
    def _check_renderable(self) -> ChartSpec:
        """Enforce the structural invariants every renderable chart must satisfy."""
        if not self.categories:
            raise ValueError("ChartSpec needs at least one category")
        if not self.series:
            raise ValueError("ChartSpec needs at least one series")
        n = len(self.categories)
        for s in self.series:
            if len(s.values) != n:
                raise ValueError(f"series '{s.name}' has {len(s.values)} values, expected {n}")
            if any(not math.isfinite(v) for v in s.values):
                raise ValueError(f"series '{s.name}' has non-finite values")
        return self
