"""Porter design-director: deterministic slide → (archetype, canvas) planning (Editorial v4.0).

Pure and LLM-free. Given the full slide list it assigns each slide a visual **archetype** and a
**canvas role** from a rhythmic "color score", so the deck has intentional variety (the user's core
complaint was one repeated layout). Decisions are config-driven via the palette/`statement_fields`
(RULE 4). The small local model stays semantic — it only writes content (+ may emit a coarse
``archetype``/``emphasis`` hint, honored here when present). ``restrained`` intensity collapses the
expressive archetypes to the calm, board-safe set so the intensity toggle stays meaningful.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from core import design
from core.config import ColorsConfig
from models.deck import Archetype, SlideContent, SlideType

_NUM_RE = re.compile(r"\d")

# Coarse, whitelisted LLM hints → archetype (unknown strings are ignored, falling back to AUTO).
_EMPHASIS_MAP: dict[str, Archetype] = {
    "statement": Archetype.STATEMENT,
    "metric": Archetype.METRIC_HERO,
    "metric_hero": Archetype.METRIC_HERO,
    "grid": Archetype.COLORBLOCK_GRID,
    "colorblock_grid": Archetype.COLORBLOCK_GRID,
    "split": Archetype.EDITORIAL_SPLIT,
    "editorial_split": Archetype.EDITORIAL_SPLIT,
    "quote": Archetype.QUOTE,
    "matrix": Archetype.MATRIX,
    "table": Archetype.TABLE,
    "chart": Archetype.CHART,
}

# Expressive archetypes that lose their drama in restrained mode (collapse → calm CONTENT).
_EXPRESSIVE = {
    Archetype.STATEMENT,
    Archetype.COLORBLOCK_GRID,
    Archetype.QUOTE,
    Archetype.METRIC_HERO,
    Archetype.EDITORIAL_SPLIT,
}


class CanvasRole(StrEnum):
    """The canvas a slide sits on. ``FIELD`` resolves to a rotating saturated statement color."""

    CREAM = "cream"
    SAND = "sand"
    CREAM_HI = "cream_hi"
    DARK = "dark"
    FIELD = "field"


@dataclass(frozen=True)
class SlidePlan:
    """The director's per-slide decision: which archetype to render, on which canvas."""

    archetype: Archetype
    canvas: CanvasRole
    accent_index: int = 0  # rotates the statement-field color (FIELD canvas / colorblock cards)


def canvas_hex(role: CanvasRole, colors: ColorsConfig, accent_index: int = 0) -> str:
    """Resolve a :class:`CanvasRole` to a concrete background hex (config-driven palette)."""
    if role == CanvasRole.DARK:
        return colors.canvas_dark
    if role == CanvasRole.SAND:
        return colors.sand
    if role == CanvasRole.CREAM_HI:
        return colors.cream_hi
    if role == CanvasRole.FIELD:
        fields = design.statement_fields(colors)
        return fields[accent_index % len(fields)]
    return colors.paper


# ---- content-shape inference ---------------------------------------------------------------
def _has_number(text: str | None) -> bool:
    return bool(_NUM_RE.search(text or ""))


def _metric_count(sc: SlideContent) -> int:
    """How many of the slide's lines carry a number (signals a metric-led slide)."""
    return sum(1 for b in sc.bullets if _has_number(b)) + (1 if _has_number(sc.headline) else 0)


def _infer_archetype(sc: SlideContent) -> Archetype:
    """Infer an archetype from a slide's semantic type + content shape (no LLM)."""
    st = sc.slide_type
    has_table = bool(sc.table and len(sc.table) >= 2)
    has_visual = sc.visual is not None or sc.diagram is not None
    bullets = len([b for b in sc.bullets if str(b).strip()])
    body_only = bool(sc.body and sc.body.strip()) and bullets == 0 and not has_table
    metrics = _metric_count(sc)

    if st == SlideType.APPENDIX:
        return Archetype.APPENDIX
    if st == SlideType.SWOT:
        return Archetype.MATRIX
    if st == SlideType.COMPETITIVE_COMPARISON:
        return Archetype.TABLE if has_table else Archetype.CONTENT
    if st == SlideType.RECOMMENDATION:
        return Archetype.QUOTE if body_only else Archetype.CONTENT
    if st == SlideType.EXECUTIVE_SUMMARY:
        return Archetype.METRIC_HERO if metrics >= 2 else Archetype.CONTENT
    # market / company / financial / strategic-signals content slides:
    if has_visual:
        return Archetype.CHART
    if metrics >= 2 and bullets <= 4:
        return Archetype.METRIC_HERO
    if 2 <= bullets <= 4:
        return Archetype.COLORBLOCK_GRID
    if body_only:
        return Archetype.STATEMENT
    return Archetype.CONTENT


def _resolve_archetype(sc: SlideContent) -> Archetype:
    """Explicit archetype > whitelisted emphasis hint > inferred (AUTO)."""
    if sc.archetype != Archetype.AUTO:
        return sc.archetype
    if sc.emphasis:
        hinted = _EMPHASIS_MAP.get(sc.emphasis.strip().lower())
        if hinted is not None:
            return hinted
    return _infer_archetype(sc)


def _diversify(arches: list[Archetype]) -> list[Archetype]:
    """Break long runs of the same archetype so the deck never feels monotonous (v3 complaint)."""
    out = list(arches)
    run = 1
    for i in range(1, len(out)):
        if out[i] == out[i - 1]:
            run += 1
            if run >= 3:
                out[i] = (
                    Archetype.EDITORIAL_SPLIT
                    if out[i] != Archetype.EDITORIAL_SPLIT
                    else Archetype.CONTENT
                )
                run = 1
        else:
            run = 1
    return out


def _cap_statements(arches: list[Archetype]) -> list[Archetype]:
    """Keep the full-bleed STATEMENT special: at most ~one per four slides; demote the rest."""
    out = list(arches)
    cap = max(1, len(out) // 4)
    used = 0
    for i, arch in enumerate(out):
        if arch != Archetype.STATEMENT:
            continue
        if used < cap:
            used += 1
        else:
            out[i] = Archetype.COLORBLOCK_GRID
    return out


def color_score(slides: list[SlideContent], *, editorial: bool = True) -> list[CanvasRole]:
    """The rhythmic sequence of canvas roles across the deck (pure; used by :func:`plan_deck`)."""
    return [plan.canvas for plan in plan_deck(slides, editorial=editorial)]


def plan_deck(slides: list[SlideContent], *, editorial: bool = True) -> list[SlidePlan]:
    """Map every slide → ``(archetype, canvas, accent_index)`` deterministically (the design score).

    One pass with a small look-back enforces the rhythm invariant — never two consecutive heavy
    canvases (dark/saturated) except the cover→follow-up — by demoting a would-be heavy slide to a
    calm one. ``restrained`` collapses the expressive archetypes so the layout stays board-safe.
    """
    arches = [_resolve_archetype(sc) for sc in slides]
    if not editorial:
        arches = [Archetype.CONTENT if a in _EXPRESSIVE else a for a in arches]
    else:
        arches = _cap_statements(_diversify(arches))

    plans: list[SlidePlan] = []
    prev_heavy = False
    accent = 0
    light_toggle = 0
    for arch, sc in zip(arches, slides, strict=True):
        st = sc.slide_type
        # base canvas + whether it is a "heavy" (dark/saturated) moment
        if st == SlideType.TITLE:
            canvas, heavy = CanvasRole.DARK, True
        elif st == SlideType.RECOMMENDATION:
            canvas, heavy = CanvasRole.DARK, True
        elif editorial and arch == Archetype.STATEMENT:
            canvas, heavy = CanvasRole.FIELD, True
        elif editorial and arch == Archetype.QUOTE:
            canvas, heavy = CanvasRole.DARK, True
        elif arch == Archetype.EDITORIAL_SPLIT:
            canvas, heavy = CanvasRole.CREAM_HI, False
        elif arch == Archetype.APPENDIX:
            canvas, heavy = CanvasRole.SAND, False
        else:
            canvas = CanvasRole.CREAM if light_toggle % 2 == 0 else CanvasRole.SAND
            heavy = False
            light_toggle += 1

        # Rhythm invariant: no two heavy canvases back to back (cover/recommendation excepted).
        if heavy and prev_heavy and st not in {SlideType.TITLE, SlideType.RECOMMENDATION}:
            arch = Archetype.COLORBLOCK_GRID if arch == Archetype.STATEMENT else Archetype.CONTENT
            canvas = CanvasRole.CREAM if light_toggle % 2 == 0 else CanvasRole.SAND
            heavy = False
            light_toggle += 1

        accent_index = accent
        if canvas == CanvasRole.FIELD or arch == Archetype.COLORBLOCK_GRID:
            accent += 1
        plans.append(SlidePlan(archetype=arch, canvas=canvas, accent_index=accent_index))
        prev_heavy = heavy

    return plans
