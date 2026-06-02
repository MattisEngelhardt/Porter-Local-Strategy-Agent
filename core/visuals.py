"""Porter visual engine: source-grounded data charts for PDF (SVG) and PPTX (native charts).

Three responsibilities, all deterministic + fail-open (SPEC REQ-5):

* **Validation** (:func:`validate_spec`) — gate a :class:`~models.visuals.ChartSpec` so only
  chartable, **evidence-grounded** specs reach a renderer (anti-hallucination: every value must be
  traceable to the analysis/evidence text; thin/invented specs are dropped, never raised).
* **Extraction** (:func:`timeline_from_findings`, :func:`numbers_from_text`) — build specs
  deterministically from data Porter already has (dated findings, numeric lines). No LLM.
* **Rendering** — :func:`render_chart_svg` (pure SVG string for WeasyPrint/PDF) and
  :func:`add_native_chart` (native, editable python-pptx chart; fail-open → caller falls back).

The structured-chart-spec approach (vs. generated plot code) is what makes this reliable on a small
local model; the palette/fonts come from :mod:`core.design` (config-driven, RULE 4).
"""

from __future__ import annotations

import math
import re
from typing import Any

from core.config import ColorsConfig, StyleConfig
from core.design import (
    body_stack,
    chart_series_colors,
    mono_stack,
    svg_escape,
)
from models.research import ResearchReport
from models.task import Language
from models.visuals import ChartSeries, ChartSpec, ChartType

# ---- number parsing ------------------------------------------------------------------------
_NUM_RE = re.compile(r"(?:[$€£]\s?)?(\d[\d.,]*)\s?([%a-zA-Z]+)?")
_CURRENCY_RE = re.compile(r"[$€£]\s?(\d[\d.,]*)\s?([a-zA-Z]+)?")  # prefer an explicit money amount
_DATE_RE = re.compile(r"\b(\d{4}(?:-\d{2})?)\b")
_MAGNITUDE = {"bn": 1000.0, "b": 1000.0, "billion": 1000.0, "mrd": 1000.0, "k": 0.001}
_MAGNITUDE_ONE = {"m": 1.0, "mio": 1.0, "million": 1.0, "mn": 1.0}


def _parse_amount(token_value: str, suffix: str | None) -> tuple[float, bool] | None:
    """Parse a numeric token into ``(value, had_magnitude)`` normalized to millions on B/M/k.

    ``had_magnitude`` is True when a scale suffix (bn/m/k) was present, so a timeline can refuse to
    mix scaled and unscaled figures. Returns ``None`` when no number can be parsed.
    """
    cleaned = token_value.replace(",", "").rstrip(".")
    if not cleaned or not any(c.isdigit() for c in cleaned):
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    suf = (suffix or "").strip().lower()
    if suf in _MAGNITUDE:
        return value * _MAGNITUDE[suf], True
    if suf in _MAGNITUDE_ONE:
        return value, True
    return value, False


def _first_amount(text: str) -> tuple[float, bool] | None:
    """First parseable amount in a piece of text (value normalized to millions if scaled).

    Prefers an explicit money amount (``$55M``) over a bare number so a leading token like ``1X``
    in a company name is not mistaken for the figure.
    """
    money = _CURRENCY_RE.search(text or "")
    if money:
        amount = _parse_amount(money.group(1), money.group(2))
        if amount is not None:
            return amount
    match = _NUM_RE.search(text or "")
    if not match:
        return None
    return _parse_amount(match.group(1), match.group(2))


def numbers_in_text(text: str) -> set[str]:
    """Normalized numeric tokens in ``text`` (digits only, thousands separators stripped)."""
    out: set[str] = set()
    for raw in re.findall(r"\d[\d.,]*", text or ""):
        norm = raw.replace(",", "").rstrip(".")
        if not norm:
            continue
        out.add(norm)
        if "." in norm:
            out.add(norm.split(".")[0])
    return out


def _value_forms(value: float) -> set[str]:
    """Candidate string forms of a chart value for grounding against the evidence."""
    forms = {f"{value:g}"}
    if value == int(value):
        forms.add(str(int(value)))
    forms.add(str(abs(int(value))))
    # scaled-down form (e.g. 55.0 from 55_000_000 in millions) handled by callers using millions
    return {f for f in forms if f}


# ---- validation (anti-hallucination) -------------------------------------------------------
def validate_spec(
    spec: ChartSpec | None,
    evidence_text: str = "",
    *,
    min_points: int = 2,
    ground_ratio: float = 0.5,
) -> ChartSpec | None:
    """Return ``spec`` only if it is chartable and grounded; otherwise ``None`` (fail-open).

    Gates: at least ``min_points`` categories, at least one series, not every value identical
    (a flat chart says nothing), and — when ``evidence_text`` is supplied — at least
    ``ground_ratio`` of the values must be findable in the evidence (no invented numbers). The
    deterministic extractors pass grounding by construction (they read the same text).
    """
    if spec is None:
        return None
    if len(spec.categories) < min_points or not spec.series:
        return None
    all_values = [v for s in spec.series for v in s.values]
    if not all_values or len({round(v, 6) for v in all_values}) < 2:
        return None
    evidence = evidence_text.strip()
    if evidence:
        present = numbers_in_text(evidence)
        grounded = sum(1 for v in all_values if _value_forms(v) & present)
        if grounded < math.ceil(ground_ratio * len(all_values)):
            return None
    return spec


# ---- deterministic extraction --------------------------------------------------------------
def timeline_from_findings(
    report: ResearchReport | None,
    language: Language,
    *,
    max_points: int = 8,
) -> ChartSpec | None:
    """Build a LINE timeline from dated, numeric findings (e.g. funding history; SPEC §11 slide 5).

    Only fires when ≥2 distinct dates carry a number on a *consistent* scale (all scaled or all
    raw — never mixing ``$55M`` with ``$1.2B`` silently). Returns ``None`` otherwise (fail-open).
    """
    if report is None:
        return None
    points: dict[str, tuple[float, bool]] = {}
    for worker in report.worker_findings:
        for finding in worker.findings:
            date_match = _DATE_RE.search(finding.date or "") or _DATE_RE.search(finding.claim)
            if not date_match:
                continue
            amount = _first_amount(finding.claim)
            if amount is None:
                continue
            points.setdefault(date_match.group(1)[:7], amount)
    if len(points) < 2:
        return None
    magnitudes = {scaled for _, scaled in points.values()}
    if len(magnitudes) > 1:  # mixed scales → not a trustworthy single axis
        return None
    ordered = sorted(points.items())[:max_points]
    categories = [d for d, _ in ordered]
    values = [v for _, (v, _) in ordered]
    unit = "m" if magnitudes == {True} else ""
    caption = "Entwicklung über die Zeit" if language == Language.DE else "Development over time"
    try:
        return ChartSpec(
            chart_type=ChartType.LINE,
            categories=categories,
            series=[ChartSeries(name=caption, values=values)],
            caption=caption,
            unit=unit,
        )
    except ValueError:
        return None


def _segment_amount(seg: str) -> tuple[re.Match[str], float] | None:
    """Find the most meaningful amount in a segment (prefer money), with its match span."""
    for regex in (_CURRENCY_RE, _NUM_RE):
        match = regex.search(seg)
        if not match:
            continue
        amount = _parse_amount(match.group(1), match.group(2))
        if amount is not None:
            return match, amount[0]
    return None


def numbers_from_text(text: str, *, max_points: int = 8) -> list[tuple[str, float]]:
    """Extract ``(label, value)`` pairs from numeric lines/bullets (deterministic fallback).

    Looks at line/segment level: a segment with a leading label and exactly one strong number
    yields a pair. Used to feed a column/bar chart when no richer structured source exists.
    """
    pairs: list[tuple[str, float]] = []
    seen: set[str] = set()
    segments = re.split(r"[\n;]+", text or "")
    for segment in segments:
        seg = segment.strip(" -•\t")
        found = _segment_amount(seg)
        if found is None:
            continue
        match, amount = found
        label = (seg[: match.start()] or seg[match.end() :]).strip(" :–—-·.")
        label = " ".join(label.split())[:28]
        if not label or label.lower() in seen:
            continue
        seen.add(label.lower())
        pairs.append((label, amount))
        if len(pairs) >= max_points:
            break
    return pairs


def chart_from_pairs(
    pairs: list[tuple[str, float]],
    chart_type: ChartType = ChartType.COLUMN,
    *,
    caption: str = "",
    unit: str = "",
    source: str = "",
    series_name: str = "",
) -> ChartSpec | None:
    """Build a single-series :class:`ChartSpec` from ``(label, value)`` pairs (fail-open → None)."""
    if len(pairs) < 2:
        return None
    try:
        return ChartSpec(
            chart_type=chart_type,
            categories=[label for label, _ in pairs],
            series=[ChartSeries(name=series_name, values=[value for _, value in pairs])],
            caption=caption,
            unit=unit,
            source=source,
        )
    except ValueError:
        return None


# ---- formatting ----------------------------------------------------------------------------
def _fmt_value(value: float, unit: str) -> str:
    """Compact value label, e.g. ``39``, ``39%``, ``120 m``."""
    if value == int(value):
        num = str(int(value))
    else:
        num = f"{value:.1f}"
    unit = unit.strip()
    if unit == "%":
        return f"{num}%"
    return f"{num} {unit}".strip()


# ---- SVG rendering (PDF) -------------------------------------------------------------------
def render_chart_svg(
    spec: ChartSpec,
    colors: ColorsConfig,
    style: StyleConfig,
    *,
    width: int = 560,
    height: int = 300,
    on_dark: bool = False,
) -> str:
    """Render a :class:`ChartSpec` into a themed, self-contained ``<svg>`` string (pure)."""
    palette = chart_series_colors(colors)
    text_color = colors.white if on_dark else colors.ink
    axis_color = colors.light_surface if on_dark else colors.charcoal
    fonts = {"body": body_stack(style), "mono": mono_stack(style)}
    if spec.chart_type == ChartType.DONUT:
        body = _svg_donut(spec, palette, text_color, fonts, width, height)
    elif spec.chart_type in (ChartType.LINE, ChartType.AREA):
        body = _svg_lines(spec, palette, text_color, axis_color, fonts, width, height)
    else:
        body = _svg_bars(spec, palette, text_color, axis_color, fonts, width, height)
    header = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" '
        f'width="100%" role="img">'
    )
    caption = ""
    if spec.caption:
        caption = (
            f'<text x="{width / 2}" y="{height - 6}" text-anchor="middle" '
            f'font-family={_q(fonts["mono"])} font-size="10" fill="{axis_color}">'
            f"{svg_escape(spec.caption)}</text>"
        )
    return f"{header}{body}{caption}</svg>"


def _q(value: str) -> str:
    """Quote a font-family stack for an SVG attribute."""
    return '"' + value.replace('"', "'") + '"'


def _svg_bars(
    spec: ChartSpec,
    palette: list[str],
    text_color: str,
    axis_color: str,
    fonts: dict[str, str],
    width: int,
    height: int,
) -> str:
    """Grouped column/bar chart. BAR = horizontal; COLUMN = vertical."""
    horizontal = spec.chart_type == ChartType.BAR
    left, right, top, bottom = 8, 12, 16, 46
    plot_w = width - left - right
    plot_h = height - top - bottom
    cats = spec.categories
    series = spec.series
    max_val = max((v for s in series for v in s.values), default=1.0) or 1.0
    parts: list[str] = []
    n_groups = len(cats)
    n_series = len(series)
    parts.append(
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" '
        f'stroke="{axis_color}" stroke-width="1"/>'
    )
    if horizontal:
        row_h = plot_h / n_groups
        bar_h = row_h / (n_series + 0.6)
        for gi, cat in enumerate(cats):
            for si, s in enumerate(series):
                val = s.values[gi]
                bw = (val / max_val) * (plot_w - 70)
                y = top + gi * row_h + si * bar_h
                parts.append(
                    f'<rect x="{left + 64}" y="{y:.1f}" width="{max(bw, 1):.1f}" '
                    f'height="{bar_h * 0.8:.1f}" fill="{palette[si % len(palette)]}" rx="2"/>'
                )
                parts.append(
                    f'<text x="{left + 70 + bw:.1f}" y="{y + bar_h * 0.6:.1f}" font-size="10" '
                    f'font-family={_q(fonts["mono"])} fill="{text_color}">'
                    f"{svg_escape(_fmt_value(val, spec.unit))}</text>"
                )
            parts.append(
                f'<text x="{left}" y="{top + gi * row_h + row_h / 2:.1f}" font-size="10" '
                f'font-family={_q(fonts["body"])} fill="{text_color}">'
                f"{svg_escape(_short(cat, 14))}</text>"
            )
    else:
        group_w = plot_w / n_groups
        bar_w = group_w / (n_series + 0.6)
        for gi, cat in enumerate(cats):
            for si, s in enumerate(series):
                val = s.values[gi]
                bh = (val / max_val) * plot_h
                x = left + gi * group_w + si * bar_w + bar_w * 0.3
                y = top + plot_h - bh
                parts.append(
                    f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w * 0.8:.1f}" '
                    f'height="{max(bh, 1):.1f}" fill="{palette[si % len(palette)]}" rx="2"/>'
                )
                parts.append(
                    f'<text x="{x + bar_w * 0.4:.1f}" y="{y - 4:.1f}" text-anchor="middle" '
                    f'font-size="10" font-family={_q(fonts["mono"])} fill="{text_color}">'
                    f"{svg_escape(_fmt_value(val, spec.unit))}</text>"
                )
            parts.append(
                f'<text x="{left + gi * group_w + group_w / 2:.1f}" y="{top + plot_h + 14}" '
                f'text-anchor="middle" font-size="10" font-family={_q(fonts["body"])} '
                f'fill="{text_color}">{svg_escape(_short(cat, 12))}</text>'
            )
    parts.append(_svg_legend(series, palette, text_color, fonts, width, top))
    return "".join(parts)


def _svg_lines(
    spec: ChartSpec,
    palette: list[str],
    text_color: str,
    axis_color: str,
    fonts: dict[str, str],
    width: int,
    height: int,
) -> str:
    """Line / area chart (one polyline per series, markers + value labels)."""
    left, right, top, bottom = 36, 16, 20, 46
    plot_w = width - left - right
    plot_h = height - top - bottom
    cats = spec.categories
    max_val = max((v for s in spec.series for v in s.values), default=1.0) or 1.0
    n = len(cats)
    step = plot_w / max(n - 1, 1)
    parts: list[str] = [
        f'<line x1="{left}" y1="{top + plot_h}" x2="{left + plot_w}" y2="{top + plot_h}" '
        f'stroke="{axis_color}" stroke-width="1"/>'
    ]
    for si, s in enumerate(spec.series):
        color = palette[si % len(palette)]
        pts = [
            (left + i * step, top + plot_h - (v / max_val) * plot_h) for i, v in enumerate(s.values)
        ]
        if spec.chart_type == ChartType.AREA:
            area = (
                f"M {pts[0][0]:.1f} {top + plot_h:.1f} "
                + " ".join(f"L {x:.1f} {y:.1f}" for x, y in pts)
                + f" L {pts[-1][0]:.1f} {top + plot_h:.1f} Z"
            )
            parts.append(f'<path d="{area}" fill="{color}" fill-opacity="0.18"/>')
        line = " ".join(
            (f"M {x:.1f} {y:.1f}" if i == 0 else f"L {x:.1f} {y:.1f}")
            for i, (x, y) in enumerate(pts)
        )
        parts.append(f'<path d="{line}" fill="none" stroke="{color}" stroke-width="2.4"/>')
        for i, (x, y) in enumerate(pts):
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3.2" fill="{color}"/>')
            parts.append(
                f'<text x="{x:.1f}" y="{y - 7:.1f}" text-anchor="middle" font-size="9.5" '
                f'font-family={_q(fonts["mono"])} fill="{text_color}">'
                f"{svg_escape(_fmt_value(s.values[i], spec.unit))}</text>"
            )
    for i, cat in enumerate(cats):
        parts.append(
            f'<text x="{left + i * step:.1f}" y="{top + plot_h + 14}" text-anchor="middle" '
            f'font-size="10" font-family={_q(fonts["body"])} fill="{text_color}">'
            f"{svg_escape(_short(cat, 10))}</text>"
        )
    parts.append(_svg_legend(spec.series, palette, text_color, fonts, width, 4))
    return "".join(parts)


def _svg_donut(
    spec: ChartSpec,
    palette: list[str],
    text_color: str,
    fonts: dict[str, str],
    width: int,
    height: int,
) -> str:
    """Donut chart from the first series' values (shares of a whole)."""
    values = [max(v, 0.0) for v in spec.series[0].values]
    total = sum(values) or 1.0
    cx, cy = height / 2 + 6, height / 2
    r_out, r_in = height / 2 - 24, (height / 2 - 24) * 0.58
    parts: list[str] = []
    angle = -90.0
    for i, val in enumerate(values):
        frac = val / total
        sweep = frac * 360.0
        parts.append(
            _donut_slice(cx, cy, r_out, r_in, angle, angle + sweep, palette[i % len(palette)])
        )
        angle += sweep
    # legend on the right
    lx = height + 8
    ly = 18
    for i, (cat, val) in enumerate(zip(spec.categories, values, strict=False)):
        pct = round(val / total * 100)
        parts.append(
            f'<rect x="{lx}" y="{ly - 9}" width="10" height="10" rx="2" '
            f'fill="{palette[i % len(palette)]}"/>'
        )
        parts.append(
            f'<text x="{lx + 16}" y="{ly}" font-size="10.5" font-family={_q(fonts["body"])} '
            f'fill="{text_color}">{svg_escape(_short(cat, 22))} · {pct}%</text>'
        )
        ly += 20
    return "".join(parts)


def _donut_slice(
    cx: float, cy: float, r_out: float, r_in: float, a0: float, a1: float, color: str
) -> str:
    """One donut slice as an SVG path (outer arc forward, inner arc back)."""
    large = 1 if (a1 - a0) > 180 else 0
    ox0, oy0 = _polar(cx, cy, r_out, a0)
    ox1, oy1 = _polar(cx, cy, r_out, a1)
    ix1, iy1 = _polar(cx, cy, r_in, a1)
    ix0, iy0 = _polar(cx, cy, r_in, a0)
    d = (
        f"M {ox0:.2f} {oy0:.2f} A {r_out:.2f} {r_out:.2f} 0 {large} 1 {ox1:.2f} {oy1:.2f} "
        f"L {ix1:.2f} {iy1:.2f} A {r_in:.2f} {r_in:.2f} 0 {large} 0 {ix0:.2f} {iy0:.2f} Z"
    )
    return f'<path d="{d}" fill="{color}"/>'


def _polar(cx: float, cy: float, r: float, angle_deg: float) -> tuple[float, float]:
    """Cartesian point on a circle at ``angle_deg`` (0° = 3 o'clock, clockwise)."""
    rad = math.radians(angle_deg)
    return cx + r * math.cos(rad), cy + r * math.sin(rad)


def _svg_legend(
    series: list[ChartSeries],
    palette: list[str],
    text_color: str,
    fonts: dict[str, str],
    width: int,
    top: float,
) -> str:
    """A compact top-right legend, only when there is more than one named series."""
    named = [s for s in series if s.name]
    if len(series) < 2 or not named:
        return ""
    parts: list[str] = []
    x = width - 12
    for s in reversed(named):
        idx = series.index(s)
        label = _short(s.name, 16)
        x -= 14 + 7 * len(label)
        parts.append(
            f'<rect x="{x:.1f}" y="{top}" width="9" height="9" rx="2" '
            f'fill="{palette[idx % len(palette)]}"/>'
        )
        parts.append(
            f'<text x="{x + 13:.1f}" y="{top + 9}" font-size="9.5" '
            f'font-family={_q(fonts["mono"])} fill="{text_color}">{svg_escape(label)}</text>'
        )
    return "".join(parts)


def _short(text: str, limit: int) -> str:
    """Truncate a label to fit a fixed slot."""
    cleaned = " ".join(str(text).split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1].rstrip() + "…"


# ---- native PPTX chart --------------------------------------------------------------------
def add_native_chart(
    slide: Any,
    spec: ChartSpec,
    colors: ColorsConfig,
    *,
    left_in: float,
    top_in: float,
    width_in: float,
    height_in: float,
) -> bool:
    """Add a native, editable python-pptx chart for ``spec``. False on any failure (fail-open).

    Native charts (not images) stay fully editable in PowerPoint — the user can retweak before a
    board meeting. Series colors come from the Editorial palette; data labels are on, gridlines and
    the chart title are off (the slide headline carries the message).
    """
    try:
        from pptx.chart.data import CategoryChartData
        from pptx.dml.color import RGBColor
        from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
        from pptx.util import Inches, Pt

        kind = {
            ChartType.COLUMN: XL_CHART_TYPE.COLUMN_CLUSTERED,
            ChartType.BAR: XL_CHART_TYPE.BAR_CLUSTERED,
            ChartType.LINE: XL_CHART_TYPE.LINE_MARKERS,
            ChartType.AREA: XL_CHART_TYPE.AREA,
            ChartType.DONUT: XL_CHART_TYPE.DOUGHNUT,
        }[spec.chart_type]

        data = CategoryChartData()  # type: ignore[no-untyped-call]
        data.categories = spec.categories
        for series in spec.series:
            values = tuple(series.values)
            data.add_series(series.name or " ", values)  # type: ignore[no-untyped-call]

        frame = slide.shapes.add_chart(
            kind, Inches(left_in), Inches(top_in), Inches(width_in), Inches(height_in), data
        )
        chart = frame.chart
        chart.has_title = False
        palette = chart_series_colors(colors)

        if spec.chart_type == ChartType.DONUT:
            chart.has_legend = True
            chart.legend.position = XL_LEGEND_POSITION.RIGHT
            chart.legend.include_in_layout = False
            points = chart.plots[0].series[0].points
            for i, point in enumerate(points):
                point.format.fill.solid()
                point.format.fill.fore_color.rgb = RGBColor.from_string(  # type: ignore[no-untyped-call]
                    palette[i % len(palette)].lstrip("#").upper()
                )
        else:
            chart.has_legend = len(spec.series) > 1
            if chart.has_legend:
                chart.legend.position = XL_LEGEND_POSITION.BOTTOM
                chart.legend.include_in_layout = False
            for i, plot_series in enumerate(chart.series):
                color = RGBColor.from_string(  # type: ignore[no-untyped-call]
                    palette[i % len(palette)].lstrip("#").upper()
                )
                fmt = plot_series.format
                if spec.chart_type in (ChartType.LINE,):
                    fmt.line.color.rgb = color
                else:
                    fmt.fill.solid()
                    fmt.fill.fore_color.rgb = color

        plot = chart.plots[0]
        plot.has_data_labels = True
        plot.data_labels.number_format = "General"
        plot.data_labels.number_format_is_linked = False
        plot.data_labels.font.size = Pt(9)
        return True
    except Exception:  # noqa: BLE001 — fail-open: any pptx/chart issue → caller falls back
        return False
