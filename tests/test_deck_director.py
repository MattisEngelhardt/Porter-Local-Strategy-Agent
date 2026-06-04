"""Tests for the Porter design-director (core/deck_director.py).

Pure, deterministic planning. Locks: determinism, the rhythm invariant (no two heavy canvases in a
row), the diversity guard (no endless run of one archetype), restrained-mode collapse to the calm
board-safe set, and that explicit archetype / whitelisted emphasis hints are honored.
"""

from __future__ import annotations

from core.deck_director import CanvasRole, plan_deck
from models.deck import Archetype, SlideContent, SlideType

_HEAVY = {CanvasRole.DARK, CanvasRole.FIELD}
_EXPRESSIVE = {
    Archetype.STATEMENT,
    Archetype.COLORBLOCK_GRID,
    Archetype.QUOTE,
    Archetype.METRIC_HERO,
    Archetype.EDITORIAL_SPLIT,
}


def _slide(st: SlideType, headline: str = "A claim", **kw: object) -> SlideContent:
    return SlideContent(slide_type=st, headline=headline, **kw)  # type: ignore[arg-type]


def _varied_deck() -> list[SlideContent]:
    return [
        _slide(SlideType.TITLE, "Cover"),
        _slide(SlideType.EXECUTIVE_SUMMARY, "Runway is 9 months", bullets=["Cash 10m", "Burn 1m"]),
        _slide(
            SlideType.MARKET_LANDSCAPE, "Three rivals", bullets=["A is big", "B is fast", "C new"]
        ),
        _slide(SlideType.STRATEGIC_SIGNALS, "Momentum builds", body="One bold sentence."),
        _slide(
            SlideType.COMPETITIVE_COMPARISON,
            "Neura vs rivals",
            table=[["d", "N", "F"], ["x", "1", "2"]],
        ),
        _slide(SlideType.SWOT, "The 2x2", table=[["S", "a"], ["W", "b"], ["O", "c"], ["T", "d"]]),
        _slide(SlideType.RECOMMENDATION, "Approve the bridge round", body="GO — raise now"),
        _slide(SlideType.APPENDIX, "Sources", bullets=["https://x"]),
    ]


def test_plan_deck_is_deterministic() -> None:
    slides = _varied_deck()
    assert plan_deck(slides) == plan_deck(slides)
    assert len(plan_deck(slides)) == len(slides)


def test_no_two_heavy_canvases_in_a_row() -> None:
    plans = plan_deck(_varied_deck())
    slides = _varied_deck()
    for i in range(1, len(plans)):
        if plans[i].canvas in _HEAVY and plans[i - 1].canvas in _HEAVY:
            # The only allowed adjacency is the dark recommendation moment (intentionally dark).
            assert slides[i].slide_type == SlideType.RECOMMENDATION


def test_diversity_guard_breaks_long_runs() -> None:
    # Eight near-identical grid-shaped content slides must NOT all become the same archetype.
    slides = [
        _slide(SlideType.STRATEGIC_SIGNALS, f"Signal {i}", bullets=["a x", "b y", "c z"])
        for i in range(8)
    ]
    arches = [p.archetype for p in plan_deck(slides)]
    assert len(set(arches)) >= 2  # variety injected, not one repeated layout


def test_consecutive_appendix_pages_stay_uniform() -> None:
    # A 4-page bibliography must render with one consistent layout — the diversity guard must NOT
    # flip "Sources 3/4" to EDITORIAL_SPLIT (the v4 inconsistent-bibliography bug).
    slides = [
        _slide(SlideType.APPENDIX, f"Sources ({i + 1}/4)", bullets=["https://x"]) for i in range(4)
    ]
    arches = [p.archetype for p in plan_deck(slides)]
    assert arches == [Archetype.APPENDIX] * 4


def test_restrained_collapses_to_calm_set() -> None:
    plans = plan_deck(_varied_deck(), editorial=False)
    for p in plans:
        assert p.canvas != CanvasRole.FIELD  # no saturated full-bleed fields
        assert p.canvas != CanvasRole.CREAM_HI
        assert p.archetype not in _EXPRESSIVE  # expressive layouts collapse to calm content


def test_explicit_archetype_and_emphasis_are_honored() -> None:
    forced = _slide(SlideType.MARKET_LANDSCAPE, "Forced", archetype=Archetype.QUOTE)
    assert plan_deck([forced])[0].archetype == Archetype.QUOTE
    hinted = _slide(SlideType.MARKET_LANDSCAPE, "Hinted", emphasis="matrix")
    assert plan_deck([hinted])[0].archetype == Archetype.MATRIX
    # An unknown hint is ignored → falls back to inference (not a crash).
    unknown = _slide(SlideType.MARKET_LANDSCAPE, "Unknown", emphasis="sparkles", bullets=["a", "b"])
    assert plan_deck([unknown])[0].archetype in set(Archetype)
