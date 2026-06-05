"""Porter layout scaffolds: named geometric regions for the composable deck library (Block 2).

A *scaffold* is a deterministic map of named :class:`Region` rectangles (in inches) into which the
composer drops blocks. This is the layer where asymmetry, overlap and editorial negative space live
— a slide is *assembled into a scaffold*, never poured into one card helper (the v4 complaint).

Pure geometry only: **no python-pptx, no colors, no fonts, no LLM** — just inches and arithmetic, so
it is trivially unit-testable and model-agnostic (the architecture test forbids a design module from
importing ``llm``). The PPTX widescreen frame is 13.333 × 7.5 in; the content band sits inside a
consistent margin, clear of the editorial spine (left) and the footer rule (bottom).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

# 16:9 widescreen frame (matches ``core/exporter._SLIDE_W_IN`` / ``_SLIDE_H_IN``).
SLIDE_W = 13.333
SLIDE_H = 7.5

# Content margins. The editorial frame draws a spine at x≈0–0.205 and a footer rule at y≈6.93, so
# the content band is inset clear of both; the cover/statement scaffolds use the full bleed instead.
CONTENT_LEFT = 0.72
CONTENT_RIGHT = 12.47
CONTENT_W = CONTENT_RIGHT - CONTENT_LEFT  # 11.75 — the width every existing renderer already uses
HEAD_TOP = 0.55
HEAD_H = 1.06
BODY_TOP = 1.82
BODY_BOTTOM = 6.74
BODY_H = BODY_BOTTOM - BODY_TOP


@dataclass(frozen=True)
class Region:
    """An axis-aligned rectangle in inches (origin top-left), with pure layout helpers.

    All helpers return new :class:`Region` values (frozen/immutable) so a scaffold can be sliced
    without side effects. Geometry only — nothing here knows about pptx, color or type.
    """

    left: float
    top: float
    width: float
    height: float

    # --- derived edges -----------------------------------------------------------------
    @property
    def right(self) -> float:
        return self.left + self.width

    @property
    def bottom(self) -> float:
        return self.top + self.height

    @property
    def cx(self) -> float:
        return self.left + self.width / 2

    @property
    def cy(self) -> float:
        return self.top + self.height / 2

    # --- transforms --------------------------------------------------------------------
    def pad(
        self,
        left: float = 0.0,
        top: float | None = None,
        right: float | None = None,
        bottom: float | None = None,
    ) -> Region:
        """Shrink inward. One arg pads all sides; two pads (x, y); four pads each side."""
        top = left if top is None else top
        right = left if right is None else right
        bottom = top if bottom is None else bottom
        return Region(
            self.left + left,
            self.top + top,
            max(0.0, self.width - left - right),
            max(0.0, self.height - top - bottom),
        )

    def with_(
        self,
        *,
        left: float | None = None,
        top: float | None = None,
        width: float | None = None,
        height: float | None = None,
    ) -> Region:
        """Return a copy overriding any of the four fields."""
        return replace(
            self,
            left=self.left if left is None else left,
            top=self.top if top is None else top,
            width=self.width if width is None else width,
            height=self.height if height is None else height,
        )

    def columns(self, n: int, gap: float = 0.3) -> list[Region]:
        """Split into ``n`` equal-width columns separated by ``gap`` (left → right)."""
        n = max(1, n)
        w = (self.width - gap * (n - 1)) / n
        return [Region(self.left + i * (w + gap), self.top, w, self.height) for i in range(n)]

    def rows(self, n: int, gap: float = 0.28) -> list[Region]:
        """Split into ``n`` equal-height rows separated by ``gap`` (top → bottom)."""
        n = max(1, n)
        h = (self.height - gap * (n - 1)) / n
        return [Region(self.left, self.top + i * (h + gap), self.width, h) for i in range(n)]

    def grid(self, rows: int, cols: int, gap: float = 0.3) -> list[Region]:
        """Row-major grid of ``rows × cols`` equal cells separated by ``gap`` in both axes."""
        out: list[Region] = []
        for row in self.rows(rows, gap):
            out.extend(row.columns(cols, gap))
        return out

    def split_x(self, at: float, gap: float = 0.0) -> tuple[Region, Region]:
        """Split into (left, right) at ``at`` inches from the left edge (gap carved out of both)."""
        at = min(max(at, 0.0), self.width)
        half = gap / 2
        left = Region(self.left, self.top, max(0.0, at - half), self.height)
        right_w = max(0.0, self.width - at - half)
        right = Region(self.left + at + half, self.top, right_w, self.height)
        return left, right

    def split_x_frac(self, frac: float, gap: float = 0.0) -> tuple[Region, Region]:
        """Split into (left, right) at a fraction ``0..1`` of the width."""
        return self.split_x(self.width * frac, gap)

    def split_y(self, at: float, gap: float = 0.0) -> tuple[Region, Region]:
        """Split into (top, bottom) at ``at`` inches from the top edge (gap carved out of both)."""
        at = min(max(at, 0.0), self.height)
        half = gap / 2
        top = Region(self.left, self.top, self.width, max(0.0, at - half))
        bottom_h = max(0.0, self.height - at - half)
        bottom = Region(self.left, self.top + at + half, self.width, bottom_h)
        return top, bottom

    def slice_top(self, height: float, gap: float = 0.0) -> tuple[Region, Region]:
        """Carve a band of ``height`` off the top; return (band, remainder)."""
        return self.split_y(height, gap)

    def contains(self, other: Region, *, eps: float = 1e-6) -> bool:
        """Whether ``other`` lies within this region (used by the layout unit tests)."""
        return (
            other.left >= self.left - eps
            and other.top >= self.top - eps
            and other.right <= self.right + eps
            and other.bottom <= self.bottom + eps
        )


# The canonical regions every scaffold is carved from.
FULL = Region(0.0, 0.0, SLIDE_W, SLIDE_H)
CONTENT = Region(CONTENT_LEFT, BODY_TOP, CONTENT_W, BODY_H)
HEADLINE = Region(0.9, HEAD_TOP, CONTENT_W - 0.18, HEAD_H)


# ----------------------------------------------------------------- scaffold builders
def _content_stack() -> dict[str, Region]:
    """Headline over a single full-width content band (the universal content slide)."""
    return {"headline": HEADLINE, "body": CONTENT}


def _full_bleed_hero() -> dict[str, Region]:
    """The photo/gradient cover: a kicker, a big woven headline, a subtitle, a corner date."""
    return {
        "kicker": Region(0.82, 0.72, 8.0, 0.3),
        "headline": Region(0.8, 2.35, 11.7, 2.8),
        "subtitle": Region(0.84, 5.3, 11.0, 0.9),
        "date": Region(10.2, 0.7, 2.3, 0.3),
        "accent_number": Region(10.6, 5.4, 1.9, 1.6),
    }


def _statement() -> dict[str, Region]:
    """Full-bleed manifesto / divider: kicker, oversized headline, optional body, big numeral."""
    return {
        "kicker": Region(0.82, 0.7, 10.0, 0.32),
        "headline": Region(0.8, 1.85, 11.7, 3.5),
        "body": Region(0.84, 5.65, 10.2, 1.0),
        "accent_number": Region(10.7, 5.4, 2.1, 1.7),
    }


def _editorial_split() -> dict[str, Region]:
    """Asymmetric serif headline left, a divider rule, supporting body/bullets right."""
    return {
        "headline": Region(0.7, BODY_TOP, 6.55, BODY_H),
        "divider": Region(7.5, 1.95, 0.014, 3.85),
        "body": Region(7.9, 1.96, 4.57, BODY_BOTTOM - 1.96),
    }


def _image_text_split() -> dict[str, Region]:
    """A full-height brand image on the left, headline + body on the right (company profile)."""
    return {
        "image": Region(0.0, 0.0, 5.55, SLIDE_H),
        "headline": Region(6.05, HEAD_TOP + 0.25, 6.55, HEAD_H + 0.2),
        "body": Region(6.05, 2.2, 6.55, 4.4),
    }


def _sidebar() -> dict[str, Region]:
    """A narrow accent sidebar (kicker/metric) + the main content column."""
    return {
        "headline": HEADLINE,
        "sidebar": Region(CONTENT_LEFT, BODY_TOP, 3.45, BODY_H),
        "main": Region(4.5, BODY_TOP, CONTENT_RIGHT - 4.5, BODY_H),
    }


def _quadrant() -> dict[str, Region]:
    """Headline over a 2×2 grid (SWOT / positioning matrix)."""
    band = Region(CONTENT_LEFT, 1.95, CONTENT_W, BODY_BOTTOM - 1.95)
    cells = band.grid(2, 2, gap=0.3)
    return {"headline": HEADLINE, "band": band, **{f"q{i}": cells[i] for i in range(4)}}


def _three_panel(n: int = 3) -> dict[str, Region]:
    """Headline over ``n`` equal columns (compare columns / triad)."""
    band = Region(CONTENT_LEFT, 1.95, CONTENT_W, BODY_BOTTOM - 1.95)
    cols = band.columns(n, gap=0.3)
    return {"headline": HEADLINE, "band": band, **{f"panel{i}": cols[i] for i in range(n)}}


def _big_number_hero(n: int = 3) -> dict[str, Region]:
    """Headline over 1–3 giant numerals, each with a supporting label (metric hero)."""
    band = Region(CONTENT_LEFT, 2.2, CONTENT_W, 3.6)
    cols = band.columns(max(1, min(n, 3)), gap=0.4)
    return {"headline": HEADLINE, "band": band, **{f"hero{i}": cols[i] for i in range(len(cols))}}


def _process_band() -> dict[str, Region]:
    """Headline over a horizontal flow band (ordered steps → never a block grid)."""
    return {
        "headline": HEADLINE,
        "band": Region(CONTENT_LEFT, 2.55, CONTENT_W, 2.4),
    }


def _data_band() -> dict[str, Region]:
    """Headline (+ optional callout) over a wide band for a chart / diagram / table."""
    return {
        "headline": HEADLINE,
        "callout": Region(CONTENT_LEFT, 1.6, CONTENT_W, 1.18),
        "band": Region(CONTENT_LEFT, BODY_TOP, CONTENT_W, BODY_H),
        "band_below_callout": Region(CONTENT_LEFT, 3.05, CONTENT_W, BODY_BOTTOM - 3.05),
    }


def _quote() -> dict[str, Region]:
    """An oversized serif pull-statement with a quote glyph and an attribution line."""
    return {
        "glyph": Region(0.55, 0.35, 3.0, 2.4),
        "quote": Region(1.2, 2.05, 11.0, 3.3),
        "attribution": Region(1.2, 5.7, 10.0, 0.5),
    }


def _decision() -> dict[str, Region]:
    """The restrained Neura black/white CEO decision slide (verdict · decision · actions · ask)."""
    return {
        "kicker": Region(0.82, 0.72, 9.0, 0.32),
        "verdict": Region(0.8, 1.35, 8.7, 2.0),
        "decision_chip": Region(9.7, 1.4, 2.85, 0.95),
        "actions": Region(0.82, 3.75, 8.6, 2.55),
        "ask": Region(0.82, 6.35, 11.6, 0.7),
        "rule": Region(0.84, 3.5, 11.6, 0.014),
    }


def _appendix_list() -> dict[str, Region]:
    """Headline over a two-column dense reference list (paginated bibliography)."""
    return {
        "headline": HEADLINE,
        "list": Region(0.75, BODY_TOP, CONTENT_RIGHT - 0.75, BODY_H),
    }


# name → builder (builders taking an ``n`` are dispatched with the kwarg in :func:`scaffold`).
_SCAFFOLDS: dict[str, Callable[[], dict[str, Region]]] = {
    "content_stack": _content_stack,
    "full_bleed_hero": _full_bleed_hero,
    "statement": _statement,
    "editorial_split": _editorial_split,
    "image_text_split": _image_text_split,
    "sidebar": _sidebar,
    "quadrant": _quadrant,
    "three_panel": _three_panel,
    "big_number_hero": _big_number_hero,
    "process_band": _process_band,
    "data_band": _data_band,
    "compare_columns": _three_panel,
    "quote": _quote,
    "decision": _decision,
    "appendix_list": _appendix_list,
}

_PARAMETRIC = {"three_panel", "big_number_hero", "compare_columns"}


def scaffold_names() -> list[str]:
    """All registered scaffold names (stable order)."""
    return list(_SCAFFOLDS.keys())


def scaffold(name: str, *, n: int | None = None) -> dict[str, Region]:
    """Resolve a scaffold name to its named regions; unknown names fall back to ``content_stack``.

    ``n`` configures the parametric scaffolds (column / hero count); ignored otherwise.
    """
    builder = _SCAFFOLDS.get(name, _content_stack)
    if name in _PARAMETRIC and n is not None:
        return builder(n)  # type: ignore[call-arg]
    return builder()
