"""Porter Editorial design system v3.0 — the deterministic 'art-director skill' baked into Porter.

Medium-agnostic design tokens + small pure helpers shared by both renderers (the PPTX deck in
``core/exporter.py`` and the PDF brief templates) and the data-chart engine (``core/visuals.py``).
Everything here is config-driven (RULE 4) and pure/testable: palette resolution, the multi-font
system with system-font fallbacks, two-tone headline splitting, source-grounded telemetry chips,
the luminous depth-gradient used for cover/divider moments, and tiny SVG helpers. No file I/O, no
LLM, no python-pptx — just tokens.
"""

from __future__ import annotations

import re
from collections import Counter
from xml.sax.saxutils import escape as _xml_escape

from core import typography
from core.config import ColorsConfig, StyleConfig
from models.research import Confidence, ResearchReport
from models.task import Language

DESIGN_SYSTEM = "Porter Editorial"
DESIGN_VERSION = "3.0"

# System-font fallbacks so output is never broken when the shipped OFL fonts are absent.
SERIF_FALLBACK = "Georgia"
GROTESK_FALLBACK = "Aptos"
BODY_FALLBACK = "Aptos"
MONO_FALLBACK = "Consolas"

# One numeric/metric token (currency optional, at least one digit, optional unit suffix). Units are
# ordered longest-first and the alphabetic ones require a trailing word boundary, so "12 months" can
# never be sliced into "12 m" + "onths" (the v3 bug — alternation took the shorter "m" first).
_NUMBER_TOKEN_RE = re.compile(
    r"(?:[$€£]\s?)?\d[\d.,]*"
    r"(?:\s?(?:%|x|(?:million|billion|months?|years?|mio|bn|EUR|USD|GBP|k|m|b)\b))?",
    re.IGNORECASE,
)
# A short proper-noun phrase (company/person), used as the two-tone fallback highlight.
_PROPER_NOUN_RE = re.compile(r"[A-Z][A-Za-z0-9&.\-]{2,}(?:\s[A-Z][A-Za-z0-9&.\-]{2,})?")
_YEAR_RE = re.compile(r"\d{4}(?:-\d{2})?")


def _t(language: Language, de: str, en: str) -> str:
    """Pick the German or English string for the language."""
    return de if language == Language.DE else en


def design_marker() -> str:
    """Short label embedded in rendered artifacts."""
    return f"{DESIGN_SYSTEM} v{DESIGN_VERSION}"


def is_editorial(style: StyleConfig) -> bool:
    """Whether the expressive 'editorial' intensity (depth + gradients) is active."""
    return str(style.intensity).strip().lower() != "restrained"


# ---------------------------------------------------------------- palette / color math
def chart_series_colors(colors: ColorsConfig) -> list[str]:
    """Ordered categorical chart palette (deep blue → teal → cyan → gold → coral → charcoal)."""
    return [
        colors.artifact_blue,
        colors.artifact_teal,
        colors.accent_cyan,
        colors.artifact_gold,
        colors.coral,
        colors.charcoal,
    ]


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Parse ``#rgb`` / ``#rrggbb`` into an (r, g, b) tuple."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def luminance(hex_color: str) -> float:
    """Relative perceived luminance (0..1) for contrast decisions."""
    r, g, b = hex_to_rgb(hex_color)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255.0


def contrast_text(bg_hex: str, colors: ColorsConfig) -> str:
    """Return a legible text color for ``bg_hex`` (white on dark, ink on light)."""
    return colors.white if luminance(bg_hex) < 0.55 else colors.ink


def statement_fields(colors: ColorsConfig) -> list[str]:
    """Ordered saturated statement-field colors for full-bleed / color-block slides (v4).

    A deliberate warm+vivid mix (RULE 4, config-driven): the design-director rotates through this
    list so consecutive statement/divider slides never repeat a field — vivid but composed, never a
    random color box. ``black``/``white``/``cream_hi`` are mixed in by the renderer as card accents.
    """
    return [
        colors.vivid_red,
        colors.baby_blue,
        colors.vivid_yellow,
        colors.vivid_green,
        colors.terracotta,
        colors.violet,
        colors.vivid_orange,
        colors.ochre,
        colors.plum,
    ]


def knockout_text(field_hex: str, colors: ColorsConfig) -> str:
    """Legible knockout text color on a saturated/strong field (warm cream on dark, ink on light).

    Uses a slightly higher luminance threshold than :func:`contrast_text` so mid-bright saturated
    fields (green, orange) keep the warm cream knockout, while light fields (yellow, baby blue,
    cream, sand) take ink.
    """
    return colors.knockout_cream if luminance(field_hex) < 0.62 else colors.ink


def spot_for_canvas(canvas_hex: str, colors: ColorsConfig) -> str:
    """A legible two-tone 'spot' accent for one headline token on ``canvas_hex`` (generalizes the
    old cream/dark rule): warm gold on a deep dark canvas, coral on a light cream/sand canvas, and a
    bright knockout-yellow pop on a mid saturated field (yellow token on a red slide).
    """
    lum = luminance(canvas_hex)
    if lum < 0.30:
        return colors.artifact_gold
    if lum > 0.70:
        return colors.coral
    return colors.vivid_yellow


def _clamp_channel(value: int) -> int:
    """Clamp an int color channel to the valid 0..255 range."""
    return max(0, min(255, value))


def _to_hex(r: int, g: int, b: int) -> str:
    """Build a ``#rrggbb`` string from clamped (r, g, b) channels."""
    return f"#{_clamp_channel(r):02X}{_clamp_channel(g):02X}{_clamp_channel(b):02X}"


def darken(hex_color: str, pct: float) -> str:
    """Darken ``hex_color`` toward black by ``pct`` percent (0..100); pure, clamped."""
    factor = 1.0 - max(0.0, min(100.0, pct)) / 100.0
    r, g, b = hex_to_rgb(hex_color)
    return _to_hex(int(r * factor), int(g * factor), int(b * factor))


def lighten(hex_color: str, pct: float) -> str:
    """Lighten ``hex_color`` toward white by ``pct`` percent (0..100); pure, clamped."""
    factor = max(0.0, min(100.0, pct)) / 100.0
    r, g, b = hex_to_rgb(hex_color)
    return _to_hex(
        int(r + (255 - r) * factor), int(g + (255 - g) * factor), int(b + (255 - b) * factor)
    )


# ---------------------------------------------------------------- fonts (multi-font system)
def serif_stack(style: StyleConfig) -> str:
    """CSS font stack for PDF display serif headlines (OFL primary → system fallback)."""
    return f'"{style.serif_font}", "{SERIF_FALLBACK}", "Times New Roman", serif'


def grotesk_stack(style: StyleConfig) -> str:
    """CSS font stack for bold grotesk display (used for deck-flavored brief accents)."""
    return f'"{style.grotesk_font}", "{GROTESK_FALLBACK}", "Segoe UI", Arial, sans-serif'


def body_stack(style: StyleConfig) -> str:
    """CSS font stack for body text."""
    return f'"{style.body_font}", "{BODY_FALLBACK}", "Segoe UI", Arial, sans-serif'


def mono_stack(style: StyleConfig) -> str:
    """CSS font stack for tracked micro-labels / telemetry."""
    return f'"{style.mono_font}", "{MONO_FALLBACK}", "Courier New", monospace'


def deck_fonts(style: StyleConfig) -> dict[str, str]:
    """Font family names per role for python-pptx, resolved from the active type-theme.

    Roles: ``display`` (grotesk headlines), ``body``, ``mono``, ``serif`` (display serif for the
    two-tone accent token / editorial-split / quote) and ``statement`` (the expressive display face
    for full-bleed statement slides). The legacy ``output.style.*_font`` fields still win as an
    explicit override when set away from their v3.0 default, so existing configs keep their fonts.
    PowerPoint substitutes by family name when a font is not installed (REQ-1/2).
    """
    theme = typography.resolve_theme(style.type_theme)

    def _role(theme_role: str, field_value: str, v3_default: str, fallback: str) -> str:
        if field_value and field_value != v3_default:
            return field_value  # explicit user override wins over the theme
        return theme.get(theme_role) or field_value or fallback

    return {
        "display": _role("grotesk", style.grotesk_font, "Space Grotesk", GROTESK_FALLBACK),
        "body": _role("body", style.body_font, "Inter", BODY_FALLBACK),
        "mono": _role("mono", style.mono_font, "Space Mono", MONO_FALLBACK),
        "serif": _role("serif", style.serif_font, "Fraunces", SERIF_FALLBACK),
        "statement": theme.get("display") or GROTESK_FALLBACK,
    }


# ---------------------------------------------------------------- two-tone headline
def split_for_highlight(text: str) -> tuple[str, str, str]:
    """Split a headline into ``(before, highlight, after)`` for the two-tone treatment.

    The highlight is one key token — a numeric/metric token if present, else the first proper-noun
    phrase. Returns ``(text, "", "")`` when nothing suitable is found (renderer shows it plain).
    Never changes the wording; it only marks one span for accent coloring (DNA 7).
    """
    cleaned = " ".join(text.split())
    for pattern in (_NUMBER_TOKEN_RE, _PROPER_NOUN_RE):
        match = pattern.search(cleaned)
        if not match:
            continue
        token = match.group(0).strip()
        start, end = match.span()
        if token and token != cleaned:
            return cleaned[:start], cleaned[start:end].strip(), cleaned[end:]
    return cleaned, "", ""


# ---------------------------------------------------------------- content hygiene (Block 5.0)
# A leading generic label the slide frame already shows — strip it so the claim leads (never the
# decision token GO/NO-GO/WATCH, which is meaningful).
_LABEL_PREFIX_RE = re.compile(
    r"^\s*(?:recommendation|empfehlung|decision|entscheidung|bottom\s*line|kernaussage|"
    r"executive\s+summary|summary|zusammenfassung|fazit|"
    r"focus\s*area\s*\d*|fokus(?:bereich)?\s*\d*|option\s*\d*)\s*[:\-–—]\s+",
    re.IGNORECASE,
)


def strip_inline_markdown(text: str) -> str:
    """Strip leaked inline Markdown so ``**Go:**`` renders as ``Go:`` (the words are kept).

    Removes emphasis (``*`` / ``**`` / ``__``), inline-code backticks, and a single leading ATX
    heading / blockquote / list marker. Never alters the actual words; pure and idempotent.
    """
    s = re.sub(r"^\s{0,3}(?:#{1,6}\s+|>\s+|[-*+]\s+)", "", str(text))
    s = re.sub(r"\*{1,3}|_{2,}|`+", "", s)
    return " ".join(s.split())


def strip_label_prefix(text: str) -> str:
    """Drop a single leading generic label (``Recommendation:``, ``Decision:``, ``Focus Area 1:``).

    The slide frame already shows the section label, so the prefix is redundant (the v3 output read
    "Recommendation: …" under a "RECOMMENDATION" frame). Only the leading label is removed; the
    decision token (GO/NO-GO/WATCH) and all mid-sentence text are untouched. Falls back to the
    original text if stripping would empty the string.
    """
    stripped = _LABEL_PREFIX_RE.sub("", str(text), count=1).strip()
    return stripped or str(text).strip()


# ---------------------------------------------------------------- telemetry chips (source-grounded)
def _dominant_confidence(report: ResearchReport) -> Confidence | None:
    """Most common confidence across all worker findings, or ``None`` when there are none."""
    counts: Counter[Confidence] = Counter()
    for worker in report.worker_findings:
        for finding in worker.findings:
            counts[finding.confidence] += 1
    if not counts:
        return None
    return counts.most_common(1)[0][0]


def _latest_finding_date(report: ResearchReport) -> str:
    """Latest YYYY[-MM] date seen across findings (lexicographic max), or ``""``."""
    dates: list[str] = []
    for worker in report.worker_findings:
        for finding in worker.findings:
            if finding.date and _YEAR_RE.match(finding.date.strip()):
                dates.append(finding.date.strip()[:7])
    return max(dates) if dates else ""


def telemetry_chips(report: ResearchReport | None, language: Language) -> list[str]:
    """Source-grounded mono metric chips for the HUD footer (only real numbers, never invented)."""
    if report is None:
        return []
    chips: list[str] = []
    if report.sources_evaluated:
        chips.append(f"{_t(language, 'QUELLEN', 'SOURCES')} {report.sources_evaluated}")
    if report.workers_used:
        chips.append(f"{_t(language, 'AGENTEN', 'WORKERS')} {report.workers_used}")
    conf = _dominant_confidence(report)
    if conf is not None:
        chips.append(f"{_t(language, 'KONFIDENZ', 'CONFIDENCE')} {conf.value.upper()}")
    asof = _latest_finding_date(report)
    if asof:
        chips.append(f"{_t(language, 'STAND', 'AS OF')} {asof}")
    return chips


# ---------------------------------------------------------------- depth gradient + SVG helpers
def depth_gradient_stops(colors: ColorsConfig) -> list[tuple[float, str]]:
    """Luminous warm→cool depth-gradient stops for cover/divider moments (Aivazovsky-inspired)."""
    return [
        (0.0, colors.canvas_dark),
        (0.5, colors.artifact_blue),
        (1.0, colors.artifact_teal),
    ]


def glow_color(colors: ColorsConfig) -> str:
    """The single warm focal-glow color layered over a dark cover (DNA 5)."""
    return colors.artifact_gold


def svg_escape(text: str) -> str:
    """Escape text for safe inclusion in SVG/XML."""
    return _xml_escape(str(text))


def linear_gradient_svg(
    gid: str,
    stops: list[tuple[float, str]],
    *,
    x1: float = 0.0,
    y1: float = 0.0,
    x2: float = 1.0,
    y2: float = 1.0,
) -> str:
    """Build a reusable ``<linearGradient>`` def from (offset, hex) stops."""
    parts = [f'<linearGradient id="{svg_escape(gid)}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">']
    for offset, hex_color in stops:
        parts.append(f'<stop offset="{offset}" stop-color="{svg_escape(hex_color)}"/>')
    parts.append("</linearGradient>")
    return "".join(parts)
