"""Porter composable block library (Block 2.2): parameterized ``render`` primitives.

A *block* is a small, parameterized renderer that fills one :class:`~core.layout.Region` — a
headline, a bullet cluster, a stat strip, a chart, a styled table (N columns / emphasis column), a
flow or 2×2 diagram, a pull-quote, a brand image, a source list, an accent. The composer (2.3) picks
blocks and places them into a scaffold; the templates (2.4) are curated presets over this library.

Design boundary (the architecture test enforces it): **this module never imports the LLM client**.
It also never imports the exporter — instead it paints through a small structural :class:`Surface`
protocol that the exporter's ``_DeckRenderer`` satisfies, so there is no import cycle and blocks
stay unit-testable against a fake surface. Every block is **fail-open**: the :func:`render`
dispatcher swallows a block-level error so one bad block never loses the slide (REQ-5). All
colors/fonts are config-driven (RULE 4); chart/diagram labels are grounded upstream (RULE 14).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from core import charts_image, design, visuals
from core.config import ColorsConfig, StyleConfig
from core.layout import Region
from models.task import Language
from models.visuals import ChartSpec


@dataclass(frozen=True)
class Run:
    """One styled text run inside a multi-run line (mixes face / weight / italic / color)."""

    text: str
    font: str
    size: float
    color: str
    bold: bool = False
    italic: bool = False


@dataclass(frozen=True)
class BlockTheme:
    """Canvas-derived styling handed to every block on a slide (resolved by the renderer).

    ``fg`` is the legible text color for the current canvas, ``spot`` the two-tone highlight color,
    ``muted`` the secondary/label color, ``accent`` the slide's semantic accent. ``fonts`` maps the
    five roles (display/body/mono/serif/statement) to family names.
    """

    colors: ColorsConfig
    fonts: dict[str, str]
    editorial: bool
    fg: str
    on_dark: bool
    spot: str
    muted: str
    accent: str

    def font(self, role: str) -> str:
        """Family name for a type role (falls back to the body font for an unknown role)."""
        return self.fonts.get(role, self.fonts.get("body", "Inter"))


class Surface(Protocol):
    """The painting surface a block draws on — structurally satisfied by ``_DeckRenderer``.

    Inch-based, color-as-hex, alignment-as-string: blocks never touch python-pptx enums, so this
    module has no pptx/LLM dependency. Methods return the created shape/box (``Any``) where useful.
    """

    colors: ColorsConfig
    style: StyleConfig
    fonts: dict[str, str]
    editorial: bool
    language: Language

    def fill_region(
        self,
        slide: Any,
        region: Region,
        fill: str,
        *,
        rounded: bool = False,
        line: str | None = None,
        shadow: bool = False,
    ) -> Any: ...

    def text_region(
        self,
        slide: Any,
        region: Region,
        text: str,
        *,
        size: float,
        color: str,
        font: str | None = None,
        bold: bool = False,
        italic: bool = False,
        align: str = "left",
        anchor: str | None = None,
        autofit: bool = False,
        wrap: bool = True,
    ) -> Any: ...

    def runs_region(
        self,
        slide: Any,
        region: Region,
        runs: Sequence[Run],
        *,
        align: str = "left",
        anchor: str | None = None,
        wrap: bool = True,
    ) -> Any: ...

    def image_region(
        self,
        slide: Any,
        region: Region,
        path: str,
        *,
        cover: bool = True,
        scrim_alpha: int | None = None,
    ) -> bool: ...

    def gradient(self, shape: Any, stops: list[tuple[float, str]]) -> None: ...
    def set_alpha(self, shape: Any, pct: int) -> None: ...
    def soft_shadow(self, shape: Any) -> None: ...

    def card_system(
        self,
        slide: Any,
        line: str,
        *,
        left: float,
        y: float,
        width: float,
        height: float,
        accent: str,
        index: int,
    ) -> None: ...

    def card_color(
        self,
        slide: Any,
        line: str,
        *,
        left: float,
        y: float,
        width: float,
        height: float,
        field: str,
        index: int,
    ) -> None: ...

    def big_number(
        self,
        slide: Any,
        token: str,
        label: str,
        *,
        left: float,
        top: float,
        width: float,
        color: str,
    ) -> None: ...

    def short(self, text: str, limit: int = 165) -> str: ...
    def metric_token(self, text: str) -> str | None: ...


# ----------------------------------------------------------------- headline / type blocks
_HEAD_BASE_FONT = {
    "standard": "display",
    "editorial": "serif",
    "display": "statement",
    "serif": "serif",
}


def _headline(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """Multi-run headline: serif/grotesk base + a recolored (optionally serif-italic) special word.

    Generalizes the two-tone headline into the richer Forma-style treatment — type contrast inside
    one line plus an optional kicker-with-rule above it. The special word is chosen
    deterministically (the metric, else proper noun) by ``design.split_for_highlight`` — not random.
    """
    text = " ".join(str(params.get("text", "")).split())
    if not text:
        return
    variant = str(params.get("variant", "standard"))
    accent = str(params.get("accent", theme.accent))
    size = float(params.get("size", 25))
    align = str(params.get("align", "left"))
    serif_token = bool(params.get("serif_token", variant in ("editorial", "display")))
    base_font = theme.font(_HEAD_BASE_FONT.get(variant, "display"))
    token_font = theme.font("serif") if serif_token else base_font

    head = region
    kicker = params.get("kicker")
    if kicker:
        rule = Region(region.left, region.top + 0.05, 0.34, 0.035)
        surface.fill_region(slide, rule, accent)
        krow = Region(region.left + 0.46, region.top - 0.07, region.width - 0.46, 0.3)
        surface.text_region(
            slide,
            krow,
            str(kicker).upper(),
            size=11,
            color=theme.muted,
            font=theme.font("mono"),
            bold=True,
        )
        head = Region(region.left, region.top + 0.38, region.width, max(0.4, region.height - 0.38))

    if params.get("bar", variant == "standard"):
        bar = Region(head.left - 0.22, head.top + 0.05, 0.08, min(0.72, head.height - 0.06))
        surface.fill_region(slide, bar, accent)

    before, token, after = design.split_for_highlight(text)
    runs: list[Run] = []
    if token:
        if before:
            runs.append(Run(before, base_font, size, theme.fg, bold=True))
        runs.append(Run(token, token_font, size, theme.spot, bold=True, italic=serif_token))
        if after:
            runs.append(Run(after, base_font, size, theme.fg, bold=True))
    else:
        runs.append(Run(text, base_font, size, theme.fg, bold=True))
    surface.runs_region(slide, head, runs, align=align, anchor="top")


def _kicker(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """A standalone tracked mono label with an optional leading rule (section / ticker line)."""
    text = str(params.get("text", "")).strip()
    if not text:
        return
    color = str(params.get("color", theme.muted))
    x = region.left
    if params.get("rule", True):
        surface.fill_region(slide, Region(region.left, region.cy - 0.015, 0.34, 0.03), color)
        x = region.left + 0.46
    row = Region(x, region.top, region.right - x, region.height)
    surface.text_region(
        slide,
        row,
        text.upper(),
        size=float(params.get("size", 11)),
        color=color,
        font=theme.font("mono"),
        bold=True,
        anchor="middle",
    )


def _body(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """A plain body paragraph (sentence/word-boundary trimmed, never a mid-word fragment)."""
    text = surface.short(str(params.get("text", "")), int(params.get("max_chars", 320)))
    if not text:
        return
    surface.text_region(
        slide,
        region,
        text,
        size=float(params.get("size", 14)),
        color=str(params.get("color", theme.fg)),
        font=theme.font("body"),
        anchor="top",
    )


def _callout(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """A high-contrast one-message callout band (one claim, knockout text)."""
    text = surface.short(str(params.get("text", "")), 190)
    if not text:
        return
    fill = str(params.get("fill", theme.colors.canvas_dark))
    surface.fill_region(slide, region, fill, rounded=True, shadow=True)
    fg = design.contrast_text(fill, theme.colors)
    surface.text_region(
        slide,
        region.pad(0.25, 0.06),
        text,
        size=float(params.get("size", 19)),
        color=fg,
        font=theme.font("display"),
        bold=True,
        align="center",
        anchor="middle",
    )


# ----------------------------------------------------------------- list / card blocks
_BULLET_MARKERS = {"dash": "—  ", "plain": "", "check": "✓  ", "arrow": "›  ", "dot": "•  "}


def _bullets(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """A clean stacked bullet cluster (no rounded cards) — the calm, legible default."""
    items = [surface.short(str(b), 170) for b in params.get("items", []) if str(b).strip()][:6]
    if not items:
        return
    marker = _BULLET_MARKERS.get(str(params.get("treatment", "dash")), "—  ")
    size = float(params.get("size", 15))
    gap = 0.16
    n = len(items)
    row_h = max(0.4, (region.height - gap * (n - 1)) / n)
    for i, item in enumerate(items):
        row = Region(region.left, region.top + i * (row_h + gap), region.width, row_h)
        surface.text_region(
            slide,
            row,
            marker + item,
            size=size,
            color=theme.fg,
            font=theme.font("body"),
            anchor="top",
        )


def _cards(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """A small grid of cards — ``color`` (saturated knockout) or ``system`` (white, accent spine).

    Color cards are the reimagined, un-numbered-feel 'Selected Work' look used sparingly; system
    cards are the calm board-safe default. Layout adapts 1/2 columns to the item count.
    """
    items = [str(b) for b in params.get("items", []) if str(b).strip()][:4]
    if not items:
        return
    style = str(params.get("style", "system"))
    start = int(params.get("accent_start", 0))
    fields = design.statement_fields(theme.colors)
    palette = design.chart_series_colors(theme.colors)
    count = len(items)
    cols = 1 if count == 1 else 2
    rows = (count + cols - 1) // cols
    gap = 0.3
    card_w = region.width if cols == 1 else (region.width - gap) / 2
    card_h = min(2.3, (region.height - gap * (rows - 1)) / rows)
    for idx, line in enumerate(items):
        row, col = divmod(idx, cols)
        left = region.left + col * (card_w + gap)
        y = region.top + row * (card_h + gap)
        if style == "color":
            surface.card_color(
                slide,
                line,
                left=left,
                y=y,
                width=card_w,
                height=card_h,
                field=fields[(start + idx) % len(fields)],
                index=idx + 1,
            )
        else:
            surface.card_system(
                slide,
                line,
                left=left,
                y=y,
                width=card_w,
                height=card_h,
                accent=palette[idx % len(palette)],
                index=idx + 1,
            )


def _stat_tiles(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """A KPI strip of 2–5 saturated tiles, each a big grounded value over a small label."""
    tiles = list(params.get("tiles", []))[:5]
    tiles = [(str(v), str(label)) for v, label in tiles if str(v).strip()]
    if not tiles:
        return
    fields = design.statement_fields(theme.colors)
    n = len(tiles)
    cols = region.columns(n, gap=0.3)
    height = min(region.height, 2.4)
    for i, (value, label) in enumerate(tiles):
        cell = cols[i].with_(height=height)
        field = fields[i % len(fields)]
        knock = design.knockout_text(field, theme.colors)
        surface.fill_region(slide, cell, field, rounded=True, shadow=True)
        surface.text_region(
            slide,
            cell.pad(0.15, 0.24, 0.15, 0.0).with_(height=1.0),
            surface.short(value, 10),
            size=38,
            color=knock,
            font=theme.font("display"),
            bold=True,
            align="center",
            anchor="middle",
        )
        surface.text_region(
            slide,
            Region(cell.left + 0.15, cell.top + 1.32, cell.width - 0.3, 0.7),
            surface.short(label, 26),
            size=12,
            color=knock,
            font=theme.font("body"),
            align="center",
        )


# ----------------------------------------------------------------- diagram blocks
def _flow(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """An ordered process flow — connected step cards left→right (steps → flow, never a grid).

    Rebuilds the old process diagram so node text **wraps + auto-fits** inside its card instead of
    being hard-truncated to seven words (the Block-1 deferred fix). An arrow joins the steps.
    """
    nodes = [str(n) for n in params.get("nodes", []) if str(n).strip()][:5]
    if len(nodes) < 2:
        return
    fields = design.statement_fields(theme.colors)
    n = len(nodes)
    gap = 0.34
    card_w = (region.width - gap * (n - 1)) / n
    height = min(region.height, 2.3)
    for i, label in enumerate(nodes):
        left = region.left + i * (card_w + gap)
        cell = Region(left, region.top, card_w, height)
        field = fields[i % len(fields)]
        knock = design.knockout_text(field, theme.colors)
        surface.fill_region(slide, cell, field, rounded=True, shadow=True)
        surface.text_region(
            slide,
            Region(left + 0.22, cell.top + 0.16, card_w - 0.44, 0.4),
            f"{i + 1:02d}",
            size=15,
            color=knock,
            font=theme.font("mono"),
            bold=True,
        )
        surface.text_region(
            slide,
            Region(left + 0.22, cell.top + 0.66, card_w - 0.44, height - 0.82),
            surface.short(label, 120),
            size=13,
            color=knock,
            font=theme.font("body"),
            anchor="top",
            autofit=True,
        )
        if i < n - 1:
            surface.text_region(
                slide,
                Region(left + card_w - 0.04, cell.cy - 0.2, gap + 0.08, 0.4),
                "→",
                size=20,
                color=theme.fg,
                bold=True,
                align="center",
                anchor="middle",
            )


def _matrix(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """A 2×2 matrix of saturated knockout quadrants (SWOT / positioning map)."""
    nodes = list(params.get("nodes", []))[:4]
    if len(nodes) != 4:
        return
    fields = params.get("fields") or design.statement_fields(theme.colors)
    cells = region.grid(2, 2, gap=0.3)
    for i, node in enumerate(nodes):
        label = str(node.get("label", "")) if isinstance(node, Mapping) else str(node)
        detail = str(node.get("detail", "")) if isinstance(node, Mapping) else ""
        cell = cells[i]
        field = fields[i % len(fields)]
        knock = design.knockout_text(field, theme.colors)
        surface.fill_region(slide, cell, field, rounded=True, shadow=True)
        surface.text_region(
            slide,
            cell.pad(0.25, 0.16, 0.25, 0.0).with_(height=0.5),
            label,
            size=16,
            color=knock,
            font=theme.font("display"),
            bold=True,
        )
        if detail:
            surface.text_region(
                slide,
                Region(cell.left + 0.25, cell.top + 0.72, cell.width - 0.5, cell.height - 0.9),
                surface.short(detail, 130),
                size=12,
                color=knock,
                font=theme.font("body"),
                anchor="top",
            )


# ----------------------------------------------------------------- data blocks
def _chart(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> bool:
    """Render a grounded ``ChartSpec`` as a themed image-chart; fail-open to a native chart.

    Returns whether a chart was placed so the composer's fallback (a table/cards block) can run.
    """
    spec = params.get("spec")
    if not isinstance(spec, ChartSpec) or not surface.style.charts_enabled:
        return False
    ok = charts_image.add_image_chart(
        slide,
        spec,
        surface.colors,
        surface.style,
        left_in=region.left,
        top_in=region.top,
        width_in=region.width,
        height_in=min(region.height, 3.9),
        on_dark=theme.on_dark,
    )
    if not ok:
        ok = visuals.add_native_chart(
            slide,
            spec,
            surface.colors,
            left_in=region.left,
            top_in=region.top,
            width_in=region.width,
            height_in=min(region.height, 3.9),
        )
    return ok


_TABLE_HEADER_SIZE = 12
_TABLE_BODY_SIZE = 12


def _table(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """A styled comparison table (multiple styles · N columns · optional emphasis column).

    Styles: ``editorial`` (dark header + zebra rows), ``minimal`` (flat, an accent rule under the
    header), ``emphasis`` (one column tinted + bold), ``compare`` (bold row-label column + accent
    header). All read on the cream canvas; cells are sentence/word trimmed.
    """
    rows = [list(r) for r in params.get("rows", []) if r]
    if len(rows) < 1:
        return
    n_cols = max(len(r) for r in rows)
    n_rows = len(rows)
    style = str(params.get("style", "editorial"))
    emphasis = params.get("emphasis_col")
    accent = str(params.get("accent", theme.accent))
    colors = theme.colors
    height = min(region.height, max(0.6, 0.5 * n_rows))
    graphic = _add_table_shape(slide, region, n_rows, n_cols, height)
    tbl = graphic.table
    header_fill = colors.excel_header if style in ("editorial",) else accent
    for r, row in enumerate(rows):
        for c in range(n_cols):
            cell = tbl.cell(r, c)
            cell.text = surface.short(str(row[c]) if c < len(row) else "", 90)
            para = cell.text_frame.paragraphs[0]
            run = para.runs[0] if para.runs else para.add_run()
            run.font.name = theme.font("body")
            run.font.size = _pt(_TABLE_HEADER_SIZE if r == 0 else _TABLE_BODY_SIZE)
            is_header = r == 0
            is_emph = emphasis is not None and c == int(emphasis)
            run.font.bold = is_header or is_emph or (style == "compare" and c == 0)
            _style_cell(
                cell,
                run,
                style=style,
                is_header=is_header,
                is_emph=is_emph,
                row=r,
                header_fill=header_fill,
                accent=accent,
                colors=colors,
            )
    if style in ("minimal", "compare") and n_rows >= 1:
        rule_y = region.top + height / n_rows
        surface.fill_region(slide, Region(region.left, rule_y, region.width, 0.022), accent)


def _add_table_shape(slide: Any, region: Region, n_rows: int, n_cols: int, height: float) -> Any:
    """Add a pptx table shape sized to the region (kept out of ``_table`` for readability)."""
    from pptx.util import Inches

    return slide.shapes.add_table(
        n_rows,
        n_cols,
        Inches(region.left),
        Inches(region.top),
        Inches(region.width),
        Inches(height),
    )


def _pt(size: float) -> Any:
    """A pptx ``Pt`` value (imported lazily so blocks keep no hard pptx import at module scope)."""
    from pptx.util import Pt

    return Pt(size)


def _style_cell(
    cell: Any,
    run: Any,
    *,
    style: str,
    is_header: bool,
    is_emph: bool,
    row: int,
    header_fill: str,
    accent: str,
    colors: ColorsConfig,
) -> None:
    """Apply one table style's fill + text color to a single cell (no border XML — flat styles)."""
    rgb = run.font.color
    if is_header:
        if style == "minimal":
            cell.fill.background()
            rgb.rgb = _rgb(colors.ink)
        else:
            cell.fill.solid()
            cell.fill.fore_color.rgb = _rgb(header_fill)
            rgb.rgb = _rgb(design.contrast_text(header_fill, colors))
        return
    if is_emph:
        cell.fill.solid()
        cell.fill.fore_color.rgb = _rgb(design.lighten(accent, 82))
        rgb.rgb = _rgb(colors.ink)
        return
    if style == "editorial":
        cell.fill.solid()
        cell.fill.fore_color.rgb = _rgb(colors.white if row % 2 else colors.light_surface)
        rgb.rgb = _rgb(colors.text_dark)
    else:  # minimal / compare — flat, ink on the page
        cell.fill.background()
        rgb.rgb = _rgb(colors.ink)


def _rgb(hex_color: str) -> Any:
    """A pptx ``RGBColor`` from a hex string (lazy import; blocks stay pptx-free at import time)."""
    from pptx.dml.color import RGBColor

    return RGBColor.from_string(hex_color.lstrip("#").upper())  # type: ignore[no-untyped-call]


# ----------------------------------------------------------------- quote / image / sources
def _pull_quote(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """An oversized serif pull-statement with a quote glyph and an optional attribution line."""
    text = surface.short(str(params.get("text", "")), 180)
    if not text:
        return
    glyph = Region(region.left - 0.65, region.top - 1.7, 3.0, 2.4)
    surface.text_region(
        slide,
        glyph,
        "“",
        size=130,
        color=theme.spot,
        font=theme.font("serif"),
        bold=True,
    )
    surface.text_region(
        slide,
        region,
        text,
        size=float(params.get("size", 38)),
        color=theme.fg,
        font=theme.font("serif"),
        anchor="top",
    )
    attribution = str(params.get("attribution", "")).strip()
    if attribution:
        attr = Region(region.left, region.bottom + 0.05, region.width, 0.5)
        surface.text_region(
            slide,
            attr,
            surface.short(attribution, 60),
            size=13,
            color=theme.fg,
            font=theme.font("mono"),
        )


def _image(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """Place a brand image into the region (cover-fit crop), optionally under a dark scrim."""
    path = params.get("path")
    if not path:
        return
    surface.image_region(
        slide,
        region,
        str(path),
        cover=bool(params.get("cover", True)),
        scrim_alpha=params.get("scrim_alpha"),
    )


def _metric(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """One giant grounded numeral with a supporting label beneath it (metric hero)."""
    token = str(params.get("token", "")).strip()
    if not token:
        return
    surface.big_number(
        slide,
        token,
        str(params.get("label", "")),
        left=region.left,
        top=region.top,
        width=region.width,
        color=str(params.get("color", theme.spot)),
    )


def _panel(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """A solid (or gradient) color field panel — a daring single-color block / split field."""
    fill = str(params.get("fill", theme.colors.canvas_dark))
    shape = surface.fill_region(slide, region, fill, rounded=bool(params.get("rounded", False)))
    stops = params.get("gradient")
    if stops:
        surface.gradient(shape, list(stops))


def _scrim_band(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """A translucent dark band behind cover text — the guaranteed text-safe zone over a photo."""
    fill = str(params.get("fill", theme.colors.canvas_dark))
    shape = surface.fill_region(slide, region, fill)
    surface.set_alpha(shape, int(params.get("alpha", 55)))


def _source_list(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """A dense two-column mono reference list (pre-numbered items in one consistent style)."""
    items = [surface.short(str(it), 116) for it in params.get("items", []) if str(it).strip()][:18]
    if not items:
        return
    gap_x = 0.35
    col_w = (region.width - gap_x) / 2
    row_h = 0.52
    for idx, line in enumerate(items):
        col = idx % 2
        row = idx // 2
        cell = Region(region.left + col * (col_w + gap_x), region.top + row * row_h, col_w, 0.46)
        surface.text_region(
            slide,
            cell,
            line,
            size=9,
            color=theme.colors.charcoal,
            font=theme.font("mono"),
            anchor="top",
        )


def _accent_number(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """A single oversized accent numeral (slide index / hero figure) — a quiet editorial mark."""
    text = str(params.get("text", "")).strip()
    if not text:
        return
    surface.text_region(
        slide,
        region,
        text,
        size=float(params.get("size", 80)),
        color=str(params.get("color", theme.spot)),
        bold=True,
        align=str(params.get("align", "right")),
        font=theme.font("statement"),
    )


# ----------------------------------------------------------------- decision (Neura b/w) blocks
def _decision_chip(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """The restrained Go / No-Go / Conditional chip for the CEO decision slide (Neura b/w)."""
    label = str(params.get("label", "")).strip()
    if not label:
        return
    fill = str(params.get("fill", theme.accent))
    surface.fill_region(slide, region, fill, rounded=True)
    surface.text_region(
        slide,
        region,
        label.upper(),
        size=float(params.get("size", 18)),
        color=design.contrast_text(fill, theme.colors),
        font=theme.font("display"),
        bold=True,
        align="center",
        anchor="middle",
    )


def _decision_actions(
    surface: Surface, slide: Any, region: Region, params: Mapping[str, Any], theme: BlockTheme
) -> None:
    """Numbered concrete actions for the decision slide (owner/horizon kept if present)."""
    actions = [surface.short(str(a), 140) for a in params.get("items", []) if str(a).strip()][:3]
    if not actions:
        return
    n = len(actions)
    gap = 0.22
    row_h = max(0.5, (region.height - gap * (n - 1)) / n)
    for i, action in enumerate(actions):
        y = region.top + i * (row_h + gap)
        surface.text_region(
            slide,
            Region(region.left, y, 0.7, row_h),
            f"{i + 1:02d}",
            size=20,
            color=theme.accent,
            font=theme.font("mono"),
            bold=True,
            anchor="top",
        )
        surface.text_region(
            slide,
            Region(region.left + 0.8, y, region.width - 0.8, row_h),
            action,
            size=16,
            color=theme.fg,
            font=theme.font("body"),
            anchor="top",
        )


# ----------------------------------------------------------------- dispatch
_BLOCKS: dict[str, Any] = {
    "headline": _headline,
    "kicker": _kicker,
    "body": _body,
    "callout": _callout,
    "bullets": _bullets,
    "cards": _cards,
    "stat_tiles": _stat_tiles,
    "flow": _flow,
    "matrix": _matrix,
    "chart": _chart,
    "table": _table,
    "pull_quote": _pull_quote,
    "image": _image,
    "metric": _metric,
    "panel": _panel,
    "scrim_band": _scrim_band,
    "source_list": _source_list,
    "accent_number": _accent_number,
    "decision_chip": _decision_chip,
    "decision_actions": _decision_actions,
}

BLOCK_KINDS = frozenset(_BLOCKS)


def render(
    kind: str,
    surface: Surface,
    slide: Any,
    region: Region,
    params: Mapping[str, Any],
    theme: BlockTheme,
) -> None:
    """Render one block into ``region``; unknown kinds and block errors are no-ops (fail-open).

    A single block raising never loses the slide — the composer's per-type fallback and the
    renderer's archetype fallback are the higher-level safety nets (REQ-5).
    """
    fn = _BLOCKS.get(kind)
    if fn is None:
        return
    try:
        fn(surface, slide, region, params, theme)
    except Exception:  # noqa: BLE001 — a block is decorative; never break the deck (REQ-5)
        return
