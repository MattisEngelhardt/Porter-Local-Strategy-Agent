"""Unit tests for the deck composer + templates (Block 2.3 / 2.4).

Pure planning — no python-pptx. Asserts the slide-type coverage matrix, the legibility guardrail +
per-type fallback, canvas/chrome resolution, determinism, and the model-agnostic content arranging.
"""

from __future__ import annotations

from pathlib import Path

from core import templates
from core.composer import DeckContext, SlideComposition, compose, compose_deck
from core.config import AppConfig
from core.templates import FULL_BLEED
from models.deck import SlideContent, SlideRecipe, SlideType
from models.task import Language
from models.visuals import ChartSeries, ChartSpec, ChartType


def _ctx(tmp_path: Path, *, editorial: bool = True) -> DeckContext:
    cfg = AppConfig()
    return DeckContext(
        colors=cfg.output.colors,
        style=cfg.output.style,
        language=Language.EN,
        editorial=editorial,
        imagery_dir=str(tmp_path / "no_images"),  # empty/missing → deterministic gradient cover
    )


def _chart() -> ChartSpec:
    return ChartSpec(
        chart_type=ChartType.COLUMN,
        categories=["Neura", "Rival"],
        series=[ChartSeries(name="Funding", values=[935.0, 130.0])],
        unit="m",
    )


def _headline_text(comp: SlideComposition) -> str:
    for block in comp.blocks:
        if block.kind in ("headline", "pull_quote"):
            return str(block.params.get("text", ""))
    return ""


def test_title_maps_to_cover_photo_without_images(tmp_path: Path) -> None:
    sc = SlideContent(slide_type=SlideType.TITLE, headline="Neura vs the field")
    comp = compose(sc, _ctx(tmp_path))
    assert comp.template == "cover_photo"
    assert comp.canvas.role == "dark"  # no image library → gradient cover
    assert comp.chrome is False


def test_recommendation_is_the_restrained_decision_slide(tmp_path: Path) -> None:
    sc = SlideContent(
        slide_type=SlideType.RECOMMENDATION,
        headline="Accelerate — secure one marquee industrial partner",
        bullets=["Sign a flagship pilot in 12 months", "Stand up a deployment team"],
        body="Proceed now while the window is open.",
    )
    comp = compose(sc, _ctx(tmp_path))
    assert comp.template == "decision"
    assert comp.canvas.role == "white" and comp.canvas.on_dark is False
    assert comp.chrome is False
    labels = [b.params.get("label") for b in comp.blocks if b.kind == "decision_chip"]
    assert labels == ["GO"]  # derived from "Accelerate/secure/proceed" — not invented


def test_appendix_swot_comparison_matrix(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    appendix = compose(
        SlideContent(slide_type=SlideType.APPENDIX, headline="Sources", bullets=["01 a", "02 b"]),
        ctx,
    )
    assert appendix.template == "bibliography"
    swot = compose(SlideContent(slide_type=SlideType.SWOT, headline="Position"), ctx)
    assert swot.template == "swot_matrix"
    table = [["Metric", "Neura", "Rival"], ["Funding", "935", "130"]]
    comp = compose(
        SlideContent(
            slide_type=SlideType.COMPETITIVE_COMPARISON, headline="Head to head", table=table
        ),
        ctx,
    )
    assert comp.template == "comparison_table"


def test_metric_hero_when_two_numbers_present(tmp_path: Path) -> None:
    sc = SlideContent(
        slide_type=SlideType.EXECUTIVE_SUMMARY,
        headline="The gap is closing",
        bullets=["Funding reached $935M", "Fleet grew to 12 robots", "Talent base doubled"],
    )
    comp = compose(sc, _ctx(tmp_path))
    assert comp.template == "metric_hero"
    assert sum(1 for b in comp.blocks if b.kind == "metric") >= 2


def test_data_chart_when_visual_present_else_flow_or_cards(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    fin = compose(
        SlideContent(
            slide_type=SlideType.FINANCIAL_OVERVIEW, headline="Funding curve", visual=_chart()
        ),
        ctx,
    )
    assert fin.template == "data_chart"
    signals = compose(
        SlideContent(
            slide_type=SlideType.STRATEGIC_SIGNALS,
            headline="Three moves",
            bullets=["Assess the field", "Pick a partner", "Deploy at scale"],
        ),
        ctx,
    )
    assert signals.template == "process_flow"
    plain = compose(
        SlideContent(
            slide_type=SlideType.MARKET_LANDSCAPE,
            headline="Market shape",
            bullets=["Fragmented today", "Consolidating fast"],
        ),
        ctx,
    )
    assert plain.template == "content_cards"


def test_every_composition_carries_a_headline_and_is_not_overloaded(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    for st in SlideType:
        sc = SlideContent(
            slide_type=st,
            headline=f"A clear so-what for {st.value}",
            bullets=["Point one", "Point two", "Point three"],
        )
        comp = compose(sc, ctx)
        assert _headline_text(comp).strip(), f"{st} produced no headline"
        assert len(comp.blocks) <= 8


def test_full_bleed_templates_skip_chrome(tmp_path: Path) -> None:
    ctx = _ctx(tmp_path)
    decision = compose(
        SlideContent(slide_type=SlideType.RECOMMENDATION, headline="Go now", body="Proceed."), ctx
    )
    cover = compose(SlideContent(slide_type=SlideType.TITLE, headline="Cover"), ctx)
    assert decision.template in FULL_BLEED and decision.chrome is False
    assert cover.template in FULL_BLEED and cover.chrome is False
    content = compose(
        SlideContent(
            slide_type=SlideType.MARKET_LANDSCAPE, headline="X", bullets=["a", "b", "c", "d", "e"]
        ),
        ctx,
    )
    assert content.template not in FULL_BLEED and content.chrome is True


def test_compose_deck_positions_and_count(tmp_path: Path) -> None:
    slides = [
        SlideContent(slide_type=SlideType.TITLE, headline="Cover"),
        SlideContent(
            slide_type=SlideType.EXECUTIVE_SUMMARY, headline="Summary", bullets=["$1M raised"]
        ),
        SlideContent(slide_type=SlideType.APPENDIX, headline="Sources", bullets=["01 a"]),
    ]
    comps = compose_deck(slides, _ctx(tmp_path))
    assert len(comps) == 3
    assert [c.position for c in comps] == [1, 2, 3]


def test_composition_is_deterministic(tmp_path: Path) -> None:
    sc = SlideContent(
        slide_type=SlideType.STRATEGIC_SIGNALS,
        headline="Momentum builds",
        bullets=["Signal one", "Signal two", "Signal three"],
    )
    ctx = _ctx(tmp_path)
    assert compose(sc, ctx) == compose(sc, ctx)


def test_restrained_mode_does_not_inject_statement(tmp_path: Path) -> None:
    sc = SlideContent(
        slide_type=SlideType.MARKET_LANDSCAPE,
        headline="A single thought",
        body="One long reflective paragraph that would otherwise become a statement divider.",
    )
    comp = compose(sc, _ctx(tmp_path, editorial=False))
    assert comp.template not in ("statement", "quote")


def test_template_registry_is_self_consistent() -> None:
    assert FULL_BLEED <= templates.TEMPLATE_IDS
    for name in templates.template_names():
        assert name in templates.TEMPLATE_IDS


# ----------------------------------------------------------------- hybrid recipe (2.6)
def _table_slide() -> SlideContent:
    return SlideContent(
        slide_type=SlideType.COMPETITIVE_COMPARISON,
        headline="Head to head",
        table=[["Metric", "Neura", "Rival"], ["Funding", "120", "675"]],
    )


def test_recipe_absent_is_byte_identical_to_an_all_none_recipe(tmp_path: Path) -> None:
    """A recipe with no applicable field leaves the composition untouched (byte-identical floor)."""
    ctx = _ctx(tmp_path)
    base = _table_slide()
    withrecipe = base.model_copy(update={"recipe": SlideRecipe()})
    assert compose(base, ctx) == compose(withrecipe, ctx)


def test_recipe_forces_a_whitelisted_template(tmp_path: Path) -> None:
    sc = SlideContent(
        slide_type=SlideType.MARKET_LANDSCAPE,
        headline="A single thought",
        body="One reflective paragraph.",
        recipe=SlideRecipe(template="statement"),
    )
    comp = compose(sc, _ctx(tmp_path))
    assert comp.template == "statement" and comp.chrome is False


def test_recipe_unknown_template_is_ignored(tmp_path: Path) -> None:
    sc = _table_slide().model_copy(update={"recipe": SlideRecipe(template="does_not_exist")})
    comp = compose(sc, _ctx(tmp_path))
    assert comp.template == "comparison_table"  # the matrix choice stands


def test_recipe_overrides_table_style_and_emphasis(tmp_path: Path) -> None:
    sc = _table_slide().model_copy(
        update={"recipe": SlideRecipe(table_style="minimal", emphasis_col=1)}
    )
    comp = compose(sc, _ctx(tmp_path))
    table = next(b for b in comp.blocks if b.kind == "table")
    assert table.params["style"] == "minimal"
    assert table.params["emphasis_col"] == 1


def test_recipe_bad_style_value_is_ignored(tmp_path: Path) -> None:
    sc = _table_slide().model_copy(update={"recipe": SlideRecipe(table_style="rainbow")})
    comp = compose(sc, _ctx(tmp_path))
    table = next(b for b in comp.blocks if b.kind == "table")
    assert table.params["style"] == "compare"  # comparison_table's default, unchanged
