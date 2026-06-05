"""Porter deck composer (Block 2.3): slide content → a deterministic :class:`SlideComposition`.

This is the brain of the composable library. For each slide it:

* picks a **template** from the slide-type coverage matrix, adapted to the content's *shape*
  (metrics → hero, table → comparison, steps → flow, body-only → split/statement, …);
* resolves the **canvas + accent** from the deck-wide **color rhythm** (reusing the tested
  :func:`core.deck_director.plan_deck`: never two heavy canvases back-to-back, statement cap,
  structural slides stay uniform);
* sanitizes the content (the 4B-safety layer: strip markdown / label prefixes);
* enforces a **legibility guardrail** (a composition must carry a headline) with a per-type
  **fallback** to the calm card layout, so the engine can never emit a bad page.

Pure + model-agnostic (the architecture test forbids importing ``llm``): it only arranges content
the model already wrote — never invents a number, label or decision (RULE 14). ``restrained``
intensity collapses the expressive canvases via :func:`core.deck_director.plan_deck` just as before.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core import deck_director, design, imagery, templates
from core.config import ColorsConfig, StyleConfig
from core.deck_director import CanvasRole, SlidePlan
from core.templates import Build, CanvasSpec, PlacedBlock
from models.deck import Archetype, SlideContent, SlideRecipe, SlideType
from models.task import Language


@dataclass(frozen=True)
class DeckContext:
    """Deck-wide inputs the composer needs (config + the curated imagery dir). No LLM."""

    colors: ColorsConfig
    style: StyleConfig
    language: Language
    editorial: bool
    imagery_dir: str


@dataclass(frozen=True)
class SlideComposition:
    """The composer's per-slide plan: template id + canvas + placed blocks + chrome flag.

    ``chrome`` is True for content slides (the renderer draws the editorial spine / label / page
    rail); full-bleed templates (cover / statement / quote / decision) own their whole canvas.
    """

    template: str
    slide_type: SlideType
    canvas: CanvasSpec
    blocks: tuple[PlacedBlock, ...]
    accent: str
    position: int
    chrome: bool


_MAX_BLOCKS = 8

# An explicit (non-AUTO) ``SlideContent.archetype`` hint (a high-effort LLM may emit one) maps onto
# a template, overriding the slide-type matrix — the hint stays meaningful in the composable engine.
_ARCH_TEMPLATE: dict[Archetype, str] = {
    Archetype.STATEMENT: "statement",
    Archetype.QUOTE: "quote",
    Archetype.METRIC_HERO: "metric_hero",
    Archetype.COLORBLOCK_GRID: "color_cards",
    Archetype.EDITORIAL_SPLIT: "editorial_split",
    Archetype.TABLE: "comparison_table",
    Archetype.MATRIX: "swot_matrix",
    Archetype.CHART: "data_chart",
    Archetype.CONTENT: "content_cards",
}
# Expressive hints collapse to the calm card layout under ``restrained`` (board-safe), mirroring
# ``deck_director``'s intensity behavior so the toggle stays meaningful.
_EXPRESSIVE_ARCH = {
    Archetype.STATEMENT,
    Archetype.QUOTE,
    Archetype.COLORBLOCK_GRID,
    Archetype.METRIC_HERO,
    Archetype.EDITORIAL_SPLIT,
}


# ----------------------------------------------------------------- accent + shape helpers
def _accent_for(sc: SlideContent, colors: ColorsConfig) -> str:
    """Semantic accent color for a slide (mirrors the renderer's ``_accent``)."""
    if sc.slide_type == SlideType.RECOMMENDATION:
        return colors.artifact_teal
    if sc.slide_type in {SlideType.SWOT, SlideType.FINANCIAL_OVERVIEW}:
        return colors.artifact_gold
    if sc.slide_type == SlideType.APPENDIX:
        return colors.charcoal
    return colors.accent_cyan


def _metric_count(bullets: list[str], headline: str) -> int:
    """How many lines carry a grounded number token (signals a metric-led slide)."""
    lines = [*bullets, headline]
    count = 0
    for line in lines:
        _, token, _ = design.split_for_highlight(line)
        if token and any(ch.isdigit() for ch in token):
            count += 1
    return count


def _is_body_only(bullets: list[str], body: str | None, table: list[list[str]] | None) -> bool:
    return bool(body and body.strip()) and not bullets and not table


def _brand_image(ctx: DeckContext, seed: str) -> str | None:
    """Pick a non-cover brand image (robot/product) for a split/profile panel, by seed (stable)."""
    images = imagery.list_images(ctx.imagery_dir)
    if not images:
        return None
    index = (sum(ord(c) for c in seed) % len(images)) if seed else 0
    return str(images[index])


def _split_cover(seed: str) -> bool:
    """Deterministically alternate the two cover treatments (photo vs. split) by seed parity."""
    return bool(seed) and sum(ord(c) for c in seed) % 2 == 1


# ----------------------------------------------------------------- template selection (the matrix)
def _select_template(
    sc: SlideContent, ctx: DeckContext, plan: SlidePlan, bullets: list[str]
) -> str:
    """Map a slide → a template id from the coverage matrix, adapted to its content shape."""
    st = sc.slide_type
    has_table = bool(sc.table and len(sc.table) >= 2)
    has_chart = sc.visual is not None
    metrics = _metric_count(bullets, sc.headline)
    body_only = _is_body_only(bullets, sc.body, sc.table)
    has_image = bool(_brand_image(ctx, sc.headline))

    if st == SlideType.TITLE:
        cover_img = imagery.cover_image(ctx.imagery_dir, seed=sc.headline)
        if cover_img is not None and has_image and _split_cover(sc.headline):
            return "cover_split"
        return "cover_photo"
    if st == SlideType.APPENDIX:
        return "bibliography"
    # An explicit archetype hint overrides the matrix (collapsing expressive ones if restrained).
    if sc.archetype != Archetype.AUTO:
        if not ctx.editorial and sc.archetype in _EXPRESSIVE_ARCH:
            return "content_cards"
        mapped = _ARCH_TEMPLATE.get(sc.archetype)
        if mapped is not None:
            return mapped
    if st == SlideType.RECOMMENDATION:
        return "decision"
    if st == SlideType.SWOT:
        return "swot_matrix"
    if st == SlideType.COMPETITIVE_COMPARISON:
        if has_table:
            return "comparison_table"
        return "data_chart" if has_chart else "content_cards"
    if st == SlideType.EXECUTIVE_SUMMARY:
        return "metric_hero" if metrics >= 2 else "content_cards"
    if st == SlideType.FINANCIAL_OVERVIEW:
        if has_chart:
            return "data_chart"
        if has_table:
            return "comparison_table"
        return "metric_hero" if metrics >= 2 else "content_cards"
    if st == SlideType.MARKET_LANDSCAPE:
        if has_chart:
            return "data_chart"
        return "comparison_table" if has_table else "content_cards"
    if st == SlideType.STRATEGIC_SIGNALS:
        if has_chart:
            return "data_chart"
        return "process_flow" if 2 <= len(bullets) <= 5 else "content_cards"
    if st == SlideType.COMPANY_DEEP_DIVE:
        if has_image:
            return "image_profile"
        return "editorial_split" if body_only else "content_cards"
    # Inject an expressive divider/quote from the rhythm only for an otherwise-plain body slide.
    if ctx.editorial and body_only:
        if plan.archetype == Archetype.QUOTE:
            return "quote"
        if plan.archetype == Archetype.STATEMENT:
            return "statement"
    return "content_cards"


# ----------------------------------------------------------------- canvas resolution
def _canvas_for(
    sc: SlideContent, template_id: str, ctx: DeckContext, plan: SlidePlan
) -> CanvasSpec:
    """Resolve the slide's background from the template + the deck-wide color rhythm."""
    colors = ctx.colors
    if template_id == "cover_photo":
        cover = imagery.cover_image(ctx.imagery_dir, seed=sc.headline)
        if cover is not None:
            return CanvasSpec("image", colors.canvas_dark, on_dark=True, image_path=str(cover))
        return CanvasSpec("dark", colors.canvas_dark, on_dark=True)
    if template_id == "cover_split":
        return CanvasSpec("dark", colors.canvas_dark, on_dark=True)
    if template_id == "decision":
        return CanvasSpec("white", colors.cream_hi, on_dark=False)  # restrained Neura near-white
    if template_id == "quote":
        return CanvasSpec("dark", colors.canvas_dark, on_dark=True)
    if template_id == "statement":
        field = design.statement_fields(colors)[
            plan.accent_index % len(design.statement_fields(colors))
        ]
        return CanvasSpec("field", field, on_dark=design.luminance(field) < 0.6, field_hex=field)
    role = plan.canvas
    fill = deck_director.canvas_hex(role, colors, plan.accent_index)
    on_dark = design.luminance(fill) < 0.55
    return CanvasSpec(
        role.value, fill, on_dark, field_hex=fill if role == CanvasRole.FIELD else None
    )


def _build_image(ctx: DeckContext, template_id: str, seed: str) -> str | None:
    """The image a *block* consumes (split-cover/profile panel); the photo cover owns its own."""
    if template_id in ("cover_split", "image_profile"):
        return _brand_image(ctx, seed)
    return None


# ----------------------------------------------------------------- hybrid recipe (2.6)
_RECIPE_TABLE_STYLES = {"editorial", "minimal", "emphasis", "compare"}
_RECIPE_CARDS_STYLES = {"system", "color"}


def _apply_recipe(placed: list[PlacedBlock], recipe: SlideRecipe) -> list[PlacedBlock]:
    """Apply a validated/whitelisted recipe's style tweaks to a built composition (no-op if none).

    Only whitelisted style fields touch a renderer (a table style / emphasis column / card style);
    an unknown value is ignored. Blocks that change get a new ``PlacedBlock``; everything else is
    returned unchanged, so a recipe with no applicable field leaves the composition untouched.
    """
    out: list[PlacedBlock] = []
    for block in placed:
        params = block.params
        if block.kind == "table":
            updates: dict[str, Any] = {}
            if recipe.table_style in _RECIPE_TABLE_STYLES:
                updates["style"] = recipe.table_style
            if recipe.emphasis_col is not None and recipe.emphasis_col >= 0:
                updates["emphasis_col"] = recipe.emphasis_col
            if updates:
                params = {**params, **updates}
        elif block.kind == "cards" and recipe.cards_style in _RECIPE_CARDS_STYLES:
            params = {**params, "style": recipe.cards_style}
        out.append(
            block if params is block.params else PlacedBlock(block.kind, block.region, params)
        )
    return out


# ----------------------------------------------------------------- guardrail
def _legible(placed: list[PlacedBlock]) -> bool:
    """Legible only if the composition carries a non-empty headline/quote and isn't overloaded."""
    if not placed or len(placed) > _MAX_BLOCKS:
        return False
    for block in placed:
        if block.kind in ("headline", "pull_quote") and str(block.params.get("text", "")).strip():
            return True
    return False


# ----------------------------------------------------------------- compose
def compose(
    sc: SlideContent, ctx: DeckContext, *, plan: SlidePlan | None = None, position: int = 1
) -> SlideComposition:
    """Compose one slide → a :class:`SlideComposition` (template + canvas + blocks)."""
    if plan is None:
        plan = deck_director.plan_deck([sc], editorial=ctx.editorial)[0]
    headline = design.strip_label_prefix(design.strip_inline_markdown(sc.headline))
    bullets = [design.strip_inline_markdown(b) for b in sc.bullets if str(b).strip()]
    body = design.strip_inline_markdown(sc.body) if sc.body else None

    template_id = _select_template(sc, ctx, plan, bullets)
    # Hybrid override: a recipe may force a *whitelisted* template (unknown ids ignored, 2.6).
    if sc.recipe is not None and sc.recipe.template in templates.TEMPLATE_IDS:
        template_id = sc.recipe.template or template_id
    canvas = _canvas_for(sc, template_id, ctx, plan)
    accent = _accent_for(sc, ctx.colors)
    build = Build(
        slide_type=sc.slide_type,
        headline=headline,
        bullets=bullets,
        body=body,
        table=sc.table,
        visual=sc.visual,
        colors=ctx.colors,
        language=ctx.language,
        canvas=canvas,
        accent=accent,
        accent_index=plan.accent_index,
        position=position,
        image_path=_build_image(ctx, template_id, sc.headline),
    )
    placed = templates.build(template_id, build)
    if not _legible(placed):
        template_id = "content_cards"
        canvas = _canvas_for(sc, template_id, ctx, plan)
        placed = templates.build(template_id, build)
    if sc.recipe is not None:
        placed = _apply_recipe(placed, sc.recipe)
    return SlideComposition(
        template=template_id,
        slide_type=sc.slide_type,
        canvas=canvas,
        blocks=tuple(placed),
        accent=accent,
        position=position,
        chrome=template_id not in templates.FULL_BLEED,
    )


def compose_deck(slides: list[SlideContent], ctx: DeckContext) -> list[SlideComposition]:
    """Compose a whole deck, threading the color rhythm so it reads as one designed sequence."""
    plans = deck_director.plan_deck(slides, editorial=ctx.editorial)
    return [
        compose(sc, ctx, plan=plan, position=i + 1)
        for i, (sc, plan) in enumerate(zip(slides, plans, strict=True))
    ]
