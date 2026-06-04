"""Tests for the Porter diagram engine (core/diagrams.py + models/diagram.py).

Pure extraction + anti-hallucination grounding (no pptx here). Locks: extractors arrange existing
content (order preserved, counts right), numbers are grounded by construction, validate_diagram
drops ungrounded figures, and the spec's structural invariants reject malformed diagrams.
"""

from __future__ import annotations

import pytest

from core.diagrams import (
    compare_columns_from_table,
    funnel_from_bullets,
    kpi_strip_from_lines,
    matrix_from_table,
    process_from_bullets,
    validate_diagram,
)
from models.diagram import DiagramNode, DiagramSpec, DiagramType


def test_process_from_bullets_preserves_order() -> None:
    spec = process_from_bullets(["Discover", "Design", "Deliver"])
    assert spec is not None and spec.diagram_type == DiagramType.PROCESS
    assert [n.label for n in spec.nodes] == ["Discover", "Design", "Deliver"]
    assert process_from_bullets(["only one"]) is None  # needs >= 2 steps


def test_matrix_from_table_makes_four_quadrants() -> None:
    table = [
        ["Strengths", "a"],
        ["Weaknesses", "b"],
        ["Opportunities", "c"],
        ["Threats", "d"],
    ]
    spec = matrix_from_table(table)
    assert spec is not None and len(spec.nodes) == 4
    assert spec.nodes[0].label == "Strengths"
    assert matrix_from_table([["only", "three"], ["rows", "here"], ["x", "y"]]) is None


def test_kpi_strip_grounds_numbers_by_construction() -> None:
    spec = kpi_strip_from_lines(["Revenue: 40", "Users: 12"], unit="m")
    assert spec is not None and spec.diagram_type == DiagramType.KPI_STRIP
    assert all(node.value for node in spec.nodes)  # every tile carries a value
    assert validate_diagram(spec, "Revenue 40 and users 12") is spec  # grounded → kept


def test_funnel_attaches_number_when_present() -> None:
    spec = funnel_from_bullets(["Leads 1000", "Qualified 200", "Won 40"])
    assert spec is not None and spec.diagram_type == DiagramType.FUNNEL
    assert spec.nodes[0].value  # a stage number was attached


def test_compare_columns_from_table() -> None:
    table = [["Dimension", "Neura", "Figure"], ["Funding", "X", "Y"], ["HQ", "DE", "US"]]
    spec = compare_columns_from_table(table)
    assert spec is not None and len(spec.columns) == 2
    assert spec.columns[0].title == "Neura"
    assert spec.columns[0].cells  # attributes captured


def test_validate_diagram_drops_ungrounded_numbers() -> None:
    spec = DiagramSpec(
        diagram_type=DiagramType.KPI_STRIP,
        nodes=[DiagramNode(label="Revenue", value="999"), DiagramNode(label="Users", value="888")],
    )
    assert validate_diagram(spec, "Users grew strongly with no figures") is None  # 0/2 grounded
    assert validate_diagram(spec, "Revenue 999 and users 888") is spec  # both grounded
    assert validate_diagram(spec, "") is spec  # no evidence → grounding not applied


def test_validate_diagram_keeps_qualitative_schematic() -> None:
    proc = DiagramSpec(
        diagram_type=DiagramType.PROCESS,
        nodes=[DiagramNode(label="Plan"), DiagramNode(label="Build"), DiagramNode(label="Ship")],
    )
    # No numbers at all → invents no figures → always grounded.
    assert validate_diagram(proc, "any evidence text") is proc


def test_diagram_spec_rejects_malformed_counts() -> None:
    with pytest.raises(ValueError):
        DiagramSpec(diagram_type=DiagramType.MATRIX_2X2, nodes=[DiagramNode(label="only one")])
    with pytest.raises(ValueError):
        DiagramSpec(diagram_type=DiagramType.PROCESS, nodes=[DiagramNode(label="only one")])
