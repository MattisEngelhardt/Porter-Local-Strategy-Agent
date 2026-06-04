"""Porter diagram engine: source-grounded native schematics (Schaubilder) for the PPTX deck.

Pure, deterministic, fail-open. Two responsibilities (the python-pptx rendering lives in
``core/exporter.py`` where the shape primitives are):

* **Extraction** — build a :class:`~models.diagram.DiagramSpec` from content Porter already has
  (a slide's bullets / table), arranging existing labels and numbers, never inventing.
* **Validation** (:func:`validate_diagram`) — gate a spec so only grounded ones reach the renderer
  (anti-hallucination, mirroring :func:`core.visuals.validate_spec`): any numeric token in the spec
  must be traceable to the evidence text. Ungrounded → ``None`` (the renderer falls back).
"""

from __future__ import annotations

import math

from core.visuals import numbers_from_text, numbers_in_text
from models.diagram import DiagramColumn, DiagramNode, DiagramSpec, DiagramType

_MAX_NODES = 6


def _trim(text: str, max_words: int) -> str:
    """Trim a label to a word budget (keeps it inside a fixed diagram slot)."""
    words = " ".join(str(text).split()).split()
    return " ".join(words[:max_words])


def _try(diagram_type: DiagramType, **kwargs: object) -> DiagramSpec | None:
    """Construct a DiagramSpec, swallowing the validator's ValueError (fail-open)."""
    try:
        return DiagramSpec(diagram_type=diagram_type, **kwargs)  # type: ignore[arg-type]
    except ValueError:
        return None


# ---- deterministic extraction (from existing content only) ---------------------------------
def process_from_bullets(
    bullets: list[str], *, caption: str = "", source: str = ""
) -> DiagramSpec | None:
    """Build an ordered PROCESS flow from 2–6 step-like bullets (sequence preserved)."""
    labels = [_trim(b, 7) for b in bullets if str(b).strip()][:_MAX_NODES]
    if len(labels) < 2:
        return None
    nodes = [DiagramNode(label=label) for label in labels]
    return _try(DiagramType.PROCESS, nodes=nodes, caption=caption, source=source)


def matrix_from_table(
    table: list[list[str]] | None,
    *,
    caption: str = "",
    source: str = "",
    axis_x: str = "",
    axis_y: str = "",
) -> DiagramSpec | None:
    """Build a 2x2 MATRIX from a 4-row table ([label, content]); generalizes the SWOT grid."""
    if not table or len(table) < 4:
        return None
    nodes: list[DiagramNode] = []
    for row in table[:4]:
        label = str(row[0]) if row else ""
        detail = str(row[1]) if len(row) > 1 else ""
        nodes.append(DiagramNode(label=_trim(label, 5), detail=_trim(detail, 16)))
    return _try(
        DiagramType.MATRIX_2X2,
        nodes=nodes,
        caption=caption,
        source=source,
        axis_x=axis_x,
        axis_y=axis_y,
    )


def pyramid_from_bullets(
    bullets: list[str], *, caption: str = "", source: str = ""
) -> DiagramSpec | None:
    """Build an ordered PYRAMID (broad base → narrow top) from 2–5 tiers."""
    labels = [_trim(b, 8) for b in bullets if str(b).strip()][:5]
    if len(labels) < 2:
        return None
    return _try(
        DiagramType.PYRAMID,
        nodes=[DiagramNode(label=label) for label in labels],
        caption=caption,
        source=source,
    )


def funnel_from_bullets(
    bullets: list[str], *, caption: str = "", source: str = ""
) -> DiagramSpec | None:
    """Build an ordered FUNNEL from 2–5 stages, attaching a grounded number per stage if present."""
    items = [str(b) for b in bullets if str(b).strip()][:5]
    if len(items) < 2:
        return None
    nodes: list[DiagramNode] = []
    for item in items:
        pair = numbers_from_text(item, max_points=1)
        value = f"{pair[0][1]:g}" if pair else ""
        nodes.append(DiagramNode(label=_trim(item, 8), value=value))
    return _try(DiagramType.FUNNEL, nodes=nodes, caption=caption, source=source)


def kpi_strip_from_lines(
    lines: list[str], *, unit: str = "", caption: str = "", source: str = ""
) -> DiagramSpec | None:
    """Build a KPI strip of 2–5 (label, value) tiles from numeric lines (numbers grounded)."""
    pairs = numbers_from_text("\n".join(str(line) for line in lines), max_points=5)
    if len(pairs) < 2:
        return None
    nodes = [
        DiagramNode(label=_trim(label, 6), value=f"{value:g}{unit}".strip())
        for label, value in pairs
    ]
    return _try(DiagramType.KPI_STRIP, nodes=nodes, caption=caption, source=source)


def compare_columns_from_table(
    table: list[list[str]] | None, *, caption: str = "", source: str = ""
) -> DiagramSpec | None:
    """Build a 2–3 column comparison ("vs.") from a comparison table (header row = entities)."""
    if not table or len(table) < 2:
        return None
    header = table[0]
    entities = [str(cell) for cell in header[1:]][:3]
    if len(entities) < 2:
        return None
    columns: list[DiagramColumn] = []
    for col_idx, title in enumerate(entities, start=1):
        cells: list[str] = []
        for row in table[1:]:
            attribute = str(row[0]) if row else ""
            value = str(row[col_idx]) if col_idx < len(row) else ""
            cell = f"{attribute}: {value}".strip(": ")
            if cell:
                cells.append(_trim(cell, 10))
        columns.append(DiagramColumn(title=_trim(title, 4), cells=cells[:5]))
    return _try(DiagramType.COMPARE_COLUMNS, columns=columns, caption=caption, source=source)


# ---- validation (anti-hallucination, mirrors core.visuals.validate_spec) -------------------
def _spec_text(spec: DiagramSpec) -> str:
    """All free text a spec carries (labels/values/cells) for grounding against the evidence."""
    parts: list[str] = [spec.caption]
    for node in spec.nodes:
        parts.extend([node.label, node.value, node.detail])
    for column in spec.columns:
        parts.append(column.title)
        parts.extend(column.cells)
    return "\n".join(part for part in parts if part)


def validate_diagram(
    spec: DiagramSpec | None,
    evidence_text: str = "",
    *,
    ground_ratio: float = 0.5,
) -> DiagramSpec | None:
    """Return ``spec`` only if it is grounded; otherwise ``None`` (fail-open, never raises).

    Structural renderability is already guaranteed by the model. Here, when ``evidence_text`` is
    supplied, every numeric token the spec puts on the slide must be traceable to the evidence: at
    least ``ground_ratio`` of the spec's numbers must appear in the evidence (no invented figures).
    Diagrams built by the extractors above pass by construction (they read the same text).
    """
    if spec is None:
        return None
    evidence = evidence_text.strip()
    if not evidence:
        return spec
    spec_numbers = numbers_in_text(_spec_text(spec))
    if not spec_numbers:
        return spec  # a purely qualitative schematic invents no figures
    present = numbers_in_text(evidence)
    grounded = len(spec_numbers & present)
    if grounded < math.ceil(ground_ratio * len(spec_numbers)):
        return None
    return spec
