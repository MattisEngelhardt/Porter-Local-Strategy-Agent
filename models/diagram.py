"""Diagram-layer Pydantic models: typed schematic specifications for the PPTX deck.

A :class:`DiagramSpec` is a canonical, render-agnostic description of a *schematic* (process flow,
2x2 matrix, pyramid, funnel, KPI strip, comparison columns) — the shape-based counterpart to the
data :class:`~models.visuals.ChartSpec`. ``core/diagrams.py`` turns it into native python-pptx
shapes; ``core/design.py`` supplies the palette/fonts. A spec only ever arranges labels/numbers
already present in the analysis — anti-hallucination lives in ``core.diagrams.validate_diagram``.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field, model_validator


class DiagramType(StrEnum):
    """The native schematic families Porter can draw from existing content (Schaubilder)."""

    PROCESS = "process"  # ordered steps connected left→right (sequence)
    MATRIX_2X2 = "matrix_2x2"  # four quadrants (SWOT / positioning map)
    PYRAMID = "pyramid"  # ordered tiers, broad base → narrow top
    FUNNEL = "funnel"  # ordered stages narrowing top → bottom (optional values)
    KPI_STRIP = "kpi_strip"  # 2–5 (label, value) metric tiles
    COMPARE_COLUMNS = "compare_columns"  # 2–3 entity columns of attributes ("vs.")


class DiagramNode(BaseModel):
    """One node/tier/tile. ``value`` is an optional grounded metric string (e.g. ``"40%"``)."""

    label: str = ""
    value: str = ""
    detail: str = ""


class DiagramColumn(BaseModel):
    """One comparison column: a ``title`` plus ordered attribute ``cells`` (compare_columns)."""

    title: str = ""
    cells: list[str] = Field(default_factory=list)


_MAX_NODES = 6


class DiagramSpec(BaseModel):
    """A render-agnostic schematic description. Any constructed instance is structurally renderable.

    Structural invariants are enforced here (node/column counts per type); semantic gating — every
    label/number traceable to the evidence — lives in :func:`core.diagrams.validate_diagram` so the
    fail-open guard can drop an ungrounded spec without raising.
    """

    diagram_type: DiagramType
    nodes: list[DiagramNode] = Field(default_factory=list)
    columns: list[DiagramColumn] = Field(default_factory=list)
    caption: str = ""  # the "so what" one-liner shown with the diagram
    source: str = ""  # short provenance label (never invented)
    axis_x: str = ""  # optional x-axis label (matrix_2x2)
    axis_y: str = ""  # optional y-axis label (matrix_2x2)

    @model_validator(mode="after")
    def _check_renderable(self) -> DiagramSpec:
        """Enforce the per-type structural invariants every renderable diagram must satisfy."""
        t = self.diagram_type
        if t == DiagramType.COMPARE_COLUMNS:
            if not 2 <= len(self.columns) <= 3:
                raise ValueError("compare_columns needs 2–3 columns")
            if any(not col.cells for col in self.columns):
                raise ValueError("each compare_columns column needs at least one cell")
            return self
        n = len(self.nodes)
        if t == DiagramType.MATRIX_2X2:
            if n != 4:
                raise ValueError("matrix_2x2 needs exactly 4 nodes")
            return self
        if not 2 <= n <= _MAX_NODES:
            raise ValueError(f"{t.value} needs 2–{_MAX_NODES} nodes")
        if t == DiagramType.KPI_STRIP and any(not node.value.strip() for node in self.nodes):
            raise ValueError("each kpi_strip node needs a value")
        return self
