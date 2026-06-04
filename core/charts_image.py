"""Themed matplotlib image-charts: a grounded ``ChartSpec`` → a crisp, branded PNG for the deck.

Why images (not native python-pptx charts): full design control — the exact Editorial/Aivazovsky
palette, the deck's OFL fonts, labeled axes + gridlines + value labels, magazine-grade. The
trade-off (not click-to-edit) was accepted with the user. Every number comes from a ``ChartSpec``
already grounded by :func:`core.visuals.validate_spec` (anti-hallucination — nothing is invented).

**Fail-open**: any failure (incl. matplotlib absent) returns ``None``/``False`` so the caller falls
back to the native chart and never loses the slide (REQ-5). matplotlib is imported lazily inside the
render call so importing this module stays cheap and dependency-optional.
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from core.config import ColorsConfig, StyleConfig
from core.design import chart_series_colors, deck_fonts
from models.visuals import ChartSpec, ChartType

_registered_dirs: set[str] = set()


def _register_fonts(fonts_dir: str | Path) -> None:
    """Register the shipped OFL TTFs with matplotlib so charts use the deck's fonts (idempotent)."""
    key = str(fonts_dir)
    if key in _registered_dirs:
        return
    _registered_dirs.add(key)
    try:
        from matplotlib import font_manager

        for ttf in Path(fonts_dir).glob("*.ttf"):
            try:
                font_manager.fontManager.addfont(str(ttf))
            except (OSError, RuntimeError):
                continue
    except ImportError:
        return


def _fmt(value: float, unit: str) -> str:
    """Compact value label, e.g. ``39``, ``39%``, ``120 m``."""
    num = str(int(value)) if value == int(value) else f"{value:.1f}"
    unit = unit.strip()
    return f"{num}%" if unit == "%" else f"{num} {unit}".strip()


def render_chart_png(
    spec: ChartSpec,
    colors: ColorsConfig,
    style: StyleConfig,
    *,
    width_in: float = 11.4,
    height_in: float = 3.5,
    dpi: int = 200,
    on_dark: bool = False,
) -> bytes | None:
    """Render ``spec`` into a transparent, themed PNG (bytes); ``None`` on failure (fail-open)."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        _register_fonts(style.fonts_dir)
        fonts = deck_fonts(style)
        palette = chart_series_colors(colors)
        ink = colors.knockout_cream if on_dark else colors.ink
        axis = colors.light_surface if on_dark else colors.charcoal

        plt.rcParams.update(
            {
                "font.family": [fonts["body"], "DejaVu Sans"],
                "text.color": ink,
                "axes.edgecolor": axis,
                "axes.labelcolor": ink,
                "xtick.color": ink,
                "ytick.color": ink,
            }
        )
        fig, ax = plt.subplots(figsize=(width_in, height_in), dpi=dpi)
        fig.patch.set_alpha(0.0)
        ax.set_facecolor("none")

        if spec.chart_type == ChartType.DONUT:
            _draw_donut(ax, spec, palette, ink)
        elif spec.chart_type in (ChartType.LINE, ChartType.AREA):
            _draw_line(ax, spec, palette, axis, ink, area=spec.chart_type == ChartType.AREA)
        else:
            _draw_bars(ax, spec, palette, axis, ink, horizontal=spec.chart_type == ChartType.BAR)

        if spec.caption:
            fig.text(
                0.5,
                0.005,
                spec.caption,
                ha="center",
                va="bottom",
                fontsize=9,
                color=axis,
                family=[fonts["mono"], "DejaVu Sans Mono"],
            )
        fig.subplots_adjust(left=0.06, right=0.985, top=0.94, bottom=0.16)
        buffer = io.BytesIO()
        fig.savefig(buffer, format="png", dpi=dpi, transparent=True)
        plt.close(fig)
        return buffer.getvalue()
    except Exception:  # noqa: BLE001 — any matplotlib/render issue → caller falls back (REQ-5)
        return None


def _clean_axes(ax: Any, axis: str) -> None:
    """Strip chartjunk: drop the top/right spines, soften the rest (editorial)."""
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(axis)
        ax.spines[side].set_linewidth(0.8)
    ax.tick_params(length=0)


def _draw_bars(
    ax: Any, spec: ChartSpec, palette: list[str], axis: str, ink: str, *, horizontal: bool
) -> None:
    """Grouped column (vertical) or bar (horizontal) chart with value labels."""
    cats = [_short(c, 18) for c in spec.categories]
    n_series = len(spec.series)
    positions = list(range(len(cats)))
    span = min(0.8, 0.28 * n_series + 0.32)  # keep bars from becoming chunky with few categories
    bar = span / max(n_series, 1)
    _clean_axes(ax, axis)
    for si, series in enumerate(spec.series):
        offset = (si - (n_series - 1) / 2) * bar
        shifted = [p + offset for p in positions]
        color = palette[si % len(palette)]
        labels = [_fmt(v, spec.unit) for v in series.values]
        if horizontal:
            bars = ax.barh(shifted, series.values, height=bar * 0.92, color=color)
        else:
            bars = ax.bar(shifted, series.values, width=bar * 0.92, color=color)
        ax.bar_label(bars, labels=labels, padding=3, fontsize=8.5, color=ink)
    if horizontal:
        ax.set_yticks(positions, cats, fontsize=9.5)
        ax.invert_yaxis()
        ax.xaxis.set_visible(False)
        ax.margins(x=0.14)
    else:
        ax.set_xticks(positions, cats, fontsize=9.5)
        ax.yaxis.set_visible(False)
        ax.margins(y=0.18)
    if n_series > 1:
        names = [s.name or " " for s in spec.series]
        ax.legend(names, loc="upper right", frameon=False, fontsize=8.5)


def _draw_line(
    ax: Any, spec: ChartSpec, palette: list[str], axis: str, ink: str, *, area: bool
) -> None:
    """Line / area chart: one polyline per series, markers + value labels + a soft y-grid."""
    cats = [_short(c, 12) for c in spec.categories]
    positions = list(range(len(cats)))
    _clean_axes(ax, axis)
    ax.grid(axis="y", color=axis, alpha=0.18, linewidth=0.7)
    for si, series in enumerate(spec.series):
        color = palette[si % len(palette)]
        ax.plot(
            positions,
            series.values,
            marker="o",
            markersize=5,
            linewidth=2.4,
            color=color,
            label=series.name or " ",
        )
        if area:
            ax.fill_between(positions, series.values, color=color, alpha=0.16)
        for x, value in zip(positions, series.values, strict=True):
            ax.annotate(
                _fmt(value, spec.unit),
                (x, value),
                textcoords="offset points",
                xytext=(0, 7),
                ha="center",
                fontsize=8.5,
                color=ink,
            )
    ax.set_xticks(positions, cats, fontsize=9.5)
    ax.margins(y=0.22)
    if len([s for s in spec.series if s.name]) > 1:
        ax.legend(loc="upper left", frameon=False, fontsize=8.5)


def _draw_donut(ax: Any, spec: ChartSpec, palette: list[str], ink: str) -> None:
    """Donut chart from the first series (shares of a whole) with category + percent labels."""
    values = [max(v, 0.0) for v in spec.series[0].values]
    labels = [_short(c, 18) for c in spec.categories]
    colors = [palette[i % len(palette)] for i in range(len(values))]
    ax.pie(
        values,
        labels=labels,
        colors=colors,
        autopct="%1.0f%%",
        startangle=90,
        counterclock=False,
        wedgeprops={"width": 0.42, "edgecolor": "none"},
        textprops={"fontsize": 9, "color": ink},
        pctdistance=0.78,
    )
    ax.set_aspect("equal")


def _short(text: str, limit: int) -> str:
    """Truncate a label to a fixed slot at a word boundary where possible."""
    cleaned = " ".join(str(text).split())
    if len(cleaned) <= limit:
        return cleaned
    clipped = cleaned[: limit - 1]
    if " " in clipped[limit // 2 :]:
        clipped = clipped.rsplit(" ", 1)[0]
    return clipped.rstrip() + "…"


def add_image_chart(
    slide: Any,
    spec: ChartSpec,
    colors: ColorsConfig,
    style: StyleConfig,
    *,
    left_in: float,
    top_in: float,
    width_in: float,
    height_in: float,
    on_dark: bool = False,
) -> bool:
    """Render ``spec`` to a themed PNG, place it on ``slide``; ``False`` on failure (fail-open)."""
    png = render_chart_png(
        spec, colors, style, width_in=width_in, height_in=height_in, on_dark=on_dark
    )
    if not png:
        return False
    try:
        from pptx.util import Inches

        slide.shapes.add_picture(
            io.BytesIO(png), Inches(left_in), Inches(top_in), width=Inches(width_in)
        )
        return True
    except Exception:  # noqa: BLE001 — any pptx issue → caller falls back (REQ-5)
        return False
