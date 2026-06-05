"""Unit tests for the pure layout scaffolds (Block 2.1).

Geometry only — every region must stay inside the 16:9 frame, splits must tile without overlap, and
every registered scaffold must resolve to in-bounds regions. No pptx, no rendering.
"""

from __future__ import annotations

import pytest

from core import layout
from core.layout import FULL, Region


def test_region_edges_and_center() -> None:
    r = Region(1.0, 2.0, 4.0, 2.0)
    assert r.right == 5.0
    assert r.bottom == 4.0
    assert r.cx == 3.0
    assert r.cy == 3.0


def test_pad_one_two_four_args() -> None:
    r = Region(0.0, 0.0, 10.0, 6.0)
    assert r.pad(1.0) == Region(1.0, 1.0, 8.0, 4.0)
    assert r.pad(1.0, 2.0) == Region(1.0, 2.0, 8.0, 2.0)
    assert r.pad(1.0, 1.0, 1.0, 1.0) == Region(1.0, 1.0, 8.0, 4.0)


def test_columns_tile_without_overlap() -> None:
    r = Region(0.0, 0.0, 12.0, 4.0)
    cols = r.columns(3, gap=0.0)
    assert len(cols) == 3
    assert all(c.width == pytest.approx(4.0) for c in cols)
    # contiguous (no gap) and within the parent
    assert cols[0].right == pytest.approx(cols[1].left)
    assert cols[2].right == pytest.approx(12.0)
    assert all(r.contains(c) for c in cols)


def test_columns_with_gap_sum_to_width() -> None:
    r = Region(0.0, 0.0, 12.0, 4.0)
    cols = r.columns(4, gap=0.3)
    total = sum(c.width for c in cols) + 0.3 * 3
    assert total == pytest.approx(12.0)
    assert all(r.contains(c) for c in cols)


def test_grid_is_row_major() -> None:
    r = Region(0.0, 0.0, 10.0, 6.0)
    cells = r.grid(2, 2, gap=0.0)
    assert len(cells) == 4
    # row-major: index 0,1 on the top row; 2,3 on the bottom row
    assert cells[0].top == pytest.approx(cells[1].top)
    assert cells[2].top > cells[0].top
    assert all(r.contains(c) for c in cells)


def test_split_x_and_y_respect_gap_and_bounds() -> None:
    r = Region(0.0, 0.0, 10.0, 6.0)
    left, right = r.split_x(4.0, gap=0.4)
    assert left.width == pytest.approx(3.8)
    assert right.left == pytest.approx(4.2)
    assert r.contains(left) and r.contains(right)
    top, bottom = r.split_y(3.0, gap=0.0)
    assert top.height == pytest.approx(3.0)
    assert bottom.height == pytest.approx(3.0)


def test_split_x_frac() -> None:
    r = Region(0.0, 0.0, 10.0, 6.0)
    left, right = r.split_x_frac(0.5)
    assert left.width == pytest.approx(5.0)
    assert right.width == pytest.approx(5.0)


@pytest.mark.parametrize("name", layout.scaffold_names())
def test_every_scaffold_region_is_in_bounds(name: str) -> None:
    regions = layout.scaffold(name)
    assert regions, f"{name} produced no regions"
    for key, region in regions.items():
        assert FULL.contains(region), f"{name}.{key} {region} escapes the slide frame"
        assert region.width > 0 and region.height > 0, f"{name}.{key} is empty"


def test_unknown_scaffold_falls_back_to_content_stack() -> None:
    assert layout.scaffold("does-not-exist").keys() == layout.scaffold("content_stack").keys()


@pytest.mark.parametrize("n", [1, 2, 3, 4])
def test_parametric_scaffolds_honor_n(n: int) -> None:
    panels = [k for k in layout.scaffold("three_panel", n=n) if k.startswith("panel")]
    assert len(panels) == n
    heroes = [k for k in layout.scaffold("big_number_hero", n=n) if k.startswith("hero")]
    assert len(heroes) == min(n, 3)  # hero band caps at 3 giant numerals
