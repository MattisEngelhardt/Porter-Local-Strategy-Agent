"""Porter deck templates (Block 2.4): ~14 declarative presets over the block library.

A *template* is a deterministic builder that turns a sanitized slide's content (the :class:`Build`
context) into an ordered list of :class:`PlacedBlock` placed into a :mod:`core.layout` scaffold. The
composer (2.3) chooses a template per slide from the slide-type coverage matrix, supplies the canvas
+ accent from the deck-wide color rhythm, and the renderer (2.5) paints the result.

Pure + model-agnostic (the architecture test forbids importing ``llm``): templates only arrange
content the model already wrote — never invent. Each is **visibly distinct**: the adaptive serif
**photo cover** with a text-safe band, the split **color-field + robot** cover, the metric hero, the
editorial split, the image profile, the data chart, the comparison table, the process **flow**
(never a block grid), the SWOT **2×2**, the statement/divider, the restrained Neura **black/white
decision** slide, the paginated bibliography, and the calm card fallback.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from core import design, layout
from core.config import ColorsConfig
from core.layout import Region
from models.deck import SlideType
from models.task import Language
from models.visuals import ChartSpec


@dataclass(frozen=True)
class PlacedBlock:
    """One block (kind + region + params) the renderer will paint via :func:`core.blocks.render`."""

    kind: str
    region: Region
    params: dict[str, Any]


@dataclass(frozen=True)
class CanvasSpec:
    """How a slide's background is painted (resolved by the composer from the color rhythm)."""

    role: str  # cream | sand | cream_hi | dark | field | image | white
    fill: str
    on_dark: bool
    field_hex: str | None = None
    image_path: str | None = None
    glow: bool = True


@dataclass(frozen=True)
class Build:
    """The per-slide build context handed to a template builder (sanitized content + tokens)."""

    slide_type: SlideType
    headline: str
    bullets: list[str]
    body: str | None
    table: list[list[str]] | None
    visual: ChartSpec | None
    colors: ColorsConfig
    language: Language
    canvas: CanvasSpec
    accent: str
    accent_index: int
    position: int
    image_path: str | None = None
    diagram_nodes: list[str] = field(default_factory=list)

    @property
    def fields(self) -> list[str]:
        return design.statement_fields(self.colors)


Builder = Callable[[Build], list[PlacedBlock]]


# ----------------------------------------------------------------- helpers
def _metrics(bullets: list[str]) -> list[tuple[str, str]]:
    """(token, line) pairs for bullets that carry a number — drives the metric hero."""
    out: list[tuple[str, str]] = []
    for line in bullets:
        token = design.split_for_highlight(line)[1]
        if token and any(ch.isdigit() for ch in token):
            out.append((token.strip()[:12], line))
    return out


_DECISION_VERDICTS: list[tuple[str, tuple[str, ...]]] = [
    ("NO-GO", ("no-go", "no go", "nogo", "do not", "reject", "abandon", "exit")),
    ("CONDITIONAL", ("conditional", "watch", "monitor", "hold", "wait", "revisit", "if ")),
    ("GO", ("go", "accelerate", "proceed", "invest", "pursue", "secure", "advance", "yes")),
]


def _decision_label(b: Build) -> str:
    """Derive a Go / No-Go / Conditional verdict from the content (never invents a new decision)."""
    haystack = " ".join([b.headline, b.body or "", *b.bullets]).lower()
    for label, cues in _DECISION_VERDICTS:
        if any(cue in haystack for cue in cues):
            return label
    return "DECISION"


def _swot_nodes(b: Build) -> list[dict[str, str]]:
    """Four (label, detail) quadrants from a table or bullets (fail-safe defaults)."""
    labels = ["Strengths", "Weaknesses", "Opportunities", "Threats"]
    if b.table and len(b.table) >= 4:
        nodes: list[dict[str, str]] = []
        for row in b.table[:4]:
            label = str(row[0]) if row else ""
            detail = "; ".join(str(c) for c in row[1:4] if str(c).strip())
            nodes.append({"label": label, "detail": detail})
        return nodes
    return [
        {"label": labels[i], "detail": b.bullets[i] if i < len(b.bullets) else ""} for i in range(4)
    ]


def _kicker_text(b: Build) -> str:
    """A short mono section ticker for the cover / statement (language-aware, no invented data)."""
    return "STRATEGIC BRIEFING" if b.language != Language.DE else "STRATEGISCHES BRIEFING"


# ----------------------------------------------------------------- content templates
def _content_cards(b: Build) -> list[PlacedBlock]:
    """The calm, board-safe fallback: headline + (callout) + system cards or a clean bullet list."""
    s = layout.scaffold("content_stack")
    out = [PlacedBlock("headline", s["headline"], {"text": b.headline, "accent": b.accent})]
    body_region = s["body"]
    if b.body:
        callout, rest = body_region.slice_top(1.18, gap=0.22)
        out.append(PlacedBlock("callout", callout, {"text": b.body, "fill": b.accent}))
        body_region = rest
    if b.table:
        out.append(PlacedBlock("table", body_region, {"rows": b.table, "style": "editorial"}))
    elif 2 <= len(b.bullets) <= 4:
        out.append(
            PlacedBlock(
                "cards",
                body_region,
                {"items": b.bullets, "style": "system", "accent_start": b.accent_index},
            )
        )
    else:
        out.append(PlacedBlock("bullets", body_region, {"items": b.bullets}))
    return out


def _color_cards(b: Build) -> list[PlacedBlock]:
    """Saturated 'Selected Work' color cards — reimagined + un-numbered-feel, used sparingly."""
    s = layout.scaffold("content_stack")
    out = [PlacedBlock("headline", s["headline"], {"text": b.headline, "accent": b.accent})]
    region = s["body"]
    if b.body:
        callout, rest = region.slice_top(1.18, gap=0.22)
        out.append(PlacedBlock("callout", callout, {"text": b.body, "fill": b.accent}))
        region = rest
    items = [x for x in b.bullets if str(x).strip()][:4]
    if items:
        out.append(
            PlacedBlock(
                "cards", region, {"items": items, "style": "color", "accent_start": b.accent_index}
            )
        )
    else:
        out.append(PlacedBlock("bullets", region, {"items": b.bullets}))
    return out


def _metric_hero(b: Build) -> list[PlacedBlock]:
    """One–three giant grounded numerals over a supporting clause (executive summary / metrics)."""
    metrics = _metrics(b.bullets)[:3]
    if not metrics:
        return _content_cards(b)
    s = layout.scaffold("big_number_hero", n=len(metrics))
    out = [PlacedBlock("headline", s["headline"], {"text": b.headline, "accent": b.accent})]
    for i, (token, line) in enumerate(metrics):
        region = s.get(f"hero{i}")
        if region is None:
            continue
        out.append(PlacedBlock("metric", region, {"token": token, "label": line}))
    return out


def _editorial_split(b: Build) -> list[PlacedBlock]:
    """Big serif headline left, supporting body/bullets right (entity profile / narrative)."""
    s = layout.scaffold("editorial_split")
    out = [
        PlacedBlock(
            "headline",
            s["headline"],
            {
                "text": b.headline,
                "variant": "editorial",
                "serif_token": True,
                "size": 40,
                "accent": b.accent,
                "bar": False,
            },
        ),
        PlacedBlock("panel", s["divider"], {"fill": b.colors.charcoal}),
    ]
    right = s["body"]
    if b.body:
        body_region, rest = right.slice_top(1.9, gap=0.2)
        out.append(PlacedBlock("body", body_region, {"text": b.body, "size": 14}))
        right = rest
    if b.bullets:
        out.append(PlacedBlock("bullets", right, {"items": b.bullets[:4], "treatment": "dash"}))
    return out


def _image_profile(b: Build) -> list[PlacedBlock]:
    """A full-height brand image left + headline/body right (company deep-dive with imagery)."""
    if not b.image_path:
        return _editorial_split(b)
    s = layout.scaffold("image_text_split")
    out = [
        PlacedBlock("image", s["image"], {"path": b.image_path, "cover": True, "scrim_alpha": 28}),
        PlacedBlock(
            "headline",
            s["headline"],
            {
                "text": b.headline,
                "variant": "editorial",
                "serif_token": True,
                "size": 34,
                "accent": b.accent,
                "bar": False,
            },
        ),
    ]
    body_region = s["body"]
    if b.body:
        top, rest = body_region.slice_top(1.7, gap=0.2)
        out.append(PlacedBlock("body", top, {"text": b.body, "size": 14}))
        body_region = rest
    if b.bullets:
        out.append(PlacedBlock("bullets", body_region, {"items": b.bullets[:4]}))
    return out


def _data_chart(b: Build) -> list[PlacedBlock]:
    """Headline (+ optional callout) over a grounded image-chart (market / financial)."""
    if b.visual is None:
        return _comparison_table(b) if b.table else _content_cards(b)
    s = layout.scaffold("data_band")
    out = [PlacedBlock("headline", s["headline"], {"text": b.headline, "accent": b.accent})]
    band = s["band"]
    if b.body:
        out.append(PlacedBlock("callout", s["callout"], {"text": b.body, "fill": b.accent}))
        band = s["band_below_callout"]
    out.append(PlacedBlock("chart", band, {"spec": b.visual}))
    return out


def _comparison_table(b: Build) -> list[PlacedBlock]:
    """A styled comparison table (bold row-label column + accent header) — the always-safe form."""
    if not b.table:
        return _data_chart(b) if b.visual else _content_cards(b)
    s = layout.scaffold("data_band")
    out = [PlacedBlock("headline", s["headline"], {"text": b.headline, "accent": b.accent})]
    band = s["band"]
    if b.body:
        out.append(PlacedBlock("callout", s["callout"], {"text": b.body, "fill": b.accent}))
        band = s["band_below_callout"]
    out.append(
        PlacedBlock("table", band, {"rows": b.table, "style": "compare", "accent": b.accent})
    )
    return out


def _process_flow(b: Build) -> list[PlacedBlock]:
    """An ordered process flow of connected step cards (strategic signals → never a block grid)."""
    nodes = b.diagram_nodes or [str(x) for x in b.bullets if str(x).strip()]
    nodes = nodes[:5]
    if len(nodes) < 2:
        return _content_cards(b)
    s = layout.scaffold("process_band")
    return [
        PlacedBlock("headline", s["headline"], {"text": b.headline, "accent": b.accent}),
        PlacedBlock("flow", s["band"], {"nodes": nodes}),
    ]


def _swot_matrix(b: Build) -> list[PlacedBlock]:
    """A saturated 2×2 matrix of knockout quadrants (SWOT / positioning)."""
    s = layout.scaffold("quadrant")
    return [
        PlacedBlock("headline", s["headline"], {"text": b.headline, "accent": b.accent}),
        PlacedBlock("matrix", s["band"], {"nodes": _swot_nodes(b)}),
    ]


def _bibliography(b: Build) -> list[PlacedBlock]:
    """A paginated two-column numbered reference list (consistent across every Sources page)."""
    s = layout.scaffold("appendix_list")
    items = b.bullets
    if b.table:
        items = [" - ".join(str(c) for c in row if str(c).strip()) for row in b.table]
    return [
        PlacedBlock("headline", s["headline"], {"text": b.headline, "accent": b.accent}),
        PlacedBlock("source_list", s["list"], {"items": items}),
    ]


# ----------------------------------------------------------------- full-bleed templates
def _statement(b: Build) -> list[PlacedBlock]:
    """A full-bleed manifesto / divider: kicker, oversized serif-accent headline, big numeral."""
    s = layout.scaffold("statement")
    out = [
        PlacedBlock("kicker", s["kicker"], {"text": b.headline[:42], "rule": False}),
        PlacedBlock(
            "headline",
            s["headline"],
            {
                "text": b.headline,
                "variant": "display",
                "serif_token": True,
                "size": 54,
                "accent": b.accent,
                "bar": False,
            },
        ),
        PlacedBlock("accent_number", s["accent_number"], {"text": f"{b.position:02d}"}),
    ]
    if b.body:
        out.append(PlacedBlock("body", s["body"], {"text": b.body, "size": 18, "max_chars": 140}))
    return out


def _quote(b: Build) -> list[PlacedBlock]:
    """An oversized serif pull-statement (a daring single message on a dark/field canvas)."""
    s = layout.scaffold("quote")
    text = b.body or b.headline
    out = [PlacedBlock("pull_quote", s["quote"], {"text": text, "size": 40})]
    if b.body and b.headline:
        out.append(
            PlacedBlock("kicker", s["attribution"], {"text": b.headline[:48], "rule": False})
        )
    return out


def _decision(b: Build) -> list[PlacedBlock]:
    """The CEO decision slide — restrained Neura black/white: verdict · decision · actions · ask."""
    s = layout.scaffold("decision")
    actions = [x for x in b.bullets if str(x).strip()][:3]
    ask = b.body or (b.bullets[-1] if b.bullets else "")
    out = [
        PlacedBlock("kicker", s["kicker"], {"text": _kicker_text(b)}),
        PlacedBlock(
            "headline",
            s["verdict"],
            {
                "text": b.headline,
                "variant": "standard",
                "size": 32,
                "accent": b.accent,
                "bar": False,
            },
        ),
        PlacedBlock(
            "decision_chip", s["decision_chip"], {"label": _decision_label(b), "fill": b.accent}
        ),
        PlacedBlock("panel", s["rule"], {"fill": b.colors.ink}),
    ]
    if actions:
        out.append(PlacedBlock("decision_actions", s["actions"], {"items": actions}))
    if ask:
        out.append(PlacedBlock("body", s["ask"], {"text": ask, "size": 16, "max_chars": 180}))
    return out


def _cover_photo(b: Build) -> list[PlacedBlock]:
    """The adaptive serif photo cover: a woven serif title over a guaranteed text-safe band."""
    s = layout.scaffold("full_bleed_hero")
    safe = Region(0.0, 2.1, layout.SLIDE_W, 3.7)  # the calm zone the title sits in
    out = [
        PlacedBlock("scrim_band", safe, {"alpha": 46}),
        PlacedBlock(
            "kicker", s["kicker"], {"text": _kicker_text(b), "color": b.colors.accent_cyan}
        ),
        PlacedBlock(
            "headline",
            s["headline"],
            {
                "text": b.headline,
                "variant": "editorial",
                "serif_token": True,
                "size": 44,
                "accent": b.colors.artifact_gold,
                "bar": False,
            },
        ),
        PlacedBlock(
            "accent_number",
            s["date"],
            {"text": _today_iso(), "size": 11, "align": "right", "color": b.colors.light_surface},
        ),
    ]
    subtitle = b.body or _today_iso()
    out.append(
        PlacedBlock(
            "body",
            s["subtitle"],
            {"text": subtitle, "size": 18, "color": b.colors.accent_cyan, "max_chars": 120},
        )
    )
    return out


def _cover_split(b: Build) -> list[PlacedBlock]:
    """The split cover: a saturated color-field / robot panel left, the title on the dark right."""
    if not b.image_path:
        return _cover_photo(b)
    left = Region(0.0, 0.0, 5.7, layout.SLIDE_H)
    right_head = Region(6.2, 2.45, 6.6, 2.6)
    right_kick = Region(6.2, 1.5, 6.0, 0.32)
    right_sub = Region(6.22, 5.2, 6.4, 0.9)
    out = [
        PlacedBlock("image", left, {"path": b.image_path, "cover": True}),
        PlacedBlock("kicker", right_kick, {"text": _kicker_text(b), "color": b.colors.accent_cyan}),
        PlacedBlock(
            "headline",
            right_head,
            {
                "text": b.headline,
                "variant": "editorial",
                "serif_token": True,
                "size": 38,
                "accent": b.colors.artifact_gold,
                "bar": False,
            },
        ),
    ]
    subtitle = b.body or _today_iso()
    out.append(
        PlacedBlock(
            "body",
            right_sub,
            {"text": subtitle, "size": 16, "color": b.colors.accent_cyan, "max_chars": 110},
        )
    )
    return out


def _today_iso() -> str:
    """Today's date (ISO) — the only dynamic token a cover injects (no hallucinated dates)."""
    from datetime import date

    return date.today().isoformat()


# ----------------------------------------------------------------- registry
TEMPLATES: dict[str, Builder] = {
    "content_cards": _content_cards,
    "color_cards": _color_cards,
    "metric_hero": _metric_hero,
    "editorial_split": _editorial_split,
    "image_profile": _image_profile,
    "data_chart": _data_chart,
    "comparison_table": _comparison_table,
    "process_flow": _process_flow,
    "swot_matrix": _swot_matrix,
    "bibliography": _bibliography,
    "statement": _statement,
    "quote": _quote,
    "decision": _decision,
    "cover_photo": _cover_photo,
    "cover_split": _cover_split,
}

# Templates that paint a full-bleed canvas (no standard editorial chrome / spine / page rail).
FULL_BLEED = frozenset({"statement", "quote", "decision", "cover_photo", "cover_split"})

TEMPLATE_IDS = frozenset(TEMPLATES)


def template_names() -> list[str]:
    """All registered template ids (stable order)."""
    return list(TEMPLATES.keys())


def build(template_id: str, b: Build) -> list[PlacedBlock]:
    """Build a template's placed blocks; an unknown id falls back to the calm card layout."""
    builder = TEMPLATES.get(template_id, _content_cards)
    return builder(b)
