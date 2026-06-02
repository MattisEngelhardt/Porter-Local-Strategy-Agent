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

# One numeric/metric token (currency optional, at least one digit, optional unit suffix).
_NUMBER_TOKEN_RE = re.compile(
    r"(?:[$€£]\s?)?\d[\d.,]*\s?(?:%|x|bn|b|mio|m|k|million|billion|months?|years?|EUR|USD|GBP)?",
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
    """Single font names for python-pptx (PowerPoint substitutes if a font is not installed)."""
    return {
        "display": style.grotesk_font or GROTESK_FALLBACK,
        "body": style.body_font or BODY_FALLBACK,
        "mono": style.mono_font or MONO_FALLBACK,
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
