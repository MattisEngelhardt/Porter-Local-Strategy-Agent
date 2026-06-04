"""Tests for the Porter Editorial design tokens (core/design.py).

Pure helpers — no I/O, no LLM, no python-pptx. They lock the palette, the multi-font system with
system-font fallbacks, the two-tone headline split, source-grounded telemetry chips, and the
depth-gradient/SVG helpers used by both renderers.
"""

from __future__ import annotations

from core.config import ColorsConfig, StyleConfig
from core.design import (
    GROTESK_FALLBACK,
    SERIF_FALLBACK,
    chart_series_colors,
    contrast_text,
    darken,
    deck_fonts,
    depth_gradient_stops,
    design_marker,
    hex_to_rgb,
    is_editorial,
    knockout_text,
    lighten,
    linear_gradient_svg,
    luminance,
    mono_stack,
    serif_stack,
    split_for_highlight,
    spot_for_canvas,
    statement_fields,
    strip_inline_markdown,
    strip_label_prefix,
    svg_escape,
    telemetry_chips,
)
from models.research import Confidence, Finding, ResearchReport, WorkerFindings
from models.task import Language


def _report() -> ResearchReport:
    return ResearchReport(
        worker_findings=[
            WorkerFindings(
                sub_topic="funding",
                findings=[
                    Finding(claim="Raised $55M", date="2023-07", confidence=Confidence.HIGH),
                    Finding(claim="Raised $120M", date="2025-01", confidence=Confidence.HIGH),
                    Finding(claim="Valued at $39B", date="2026-03", confidence=Confidence.MEDIUM),
                ],
            )
        ],
        workers_used=3,
        sources_evaluated=22,
    )


# --- palette / color math ----------------------------------------------------------------
def test_chart_series_colors_are_config_driven() -> None:
    colors = ColorsConfig()
    series = chart_series_colors(colors)
    assert series[0] == colors.artifact_blue
    assert colors.coral in series
    assert len(series) == len(set(series)) == 6


def test_hex_and_luminance_and_contrast() -> None:
    assert hex_to_rgb("#FFFFFF") == (255, 255, 255)
    assert hex_to_rgb("#000") == (0, 0, 0)  # shorthand expands
    colors = ColorsConfig()
    assert luminance(colors.canvas_dark) < luminance(colors.paper)
    assert contrast_text(colors.canvas_dark, colors) == colors.white
    assert contrast_text(colors.paper, colors) == colors.ink


# --- fonts -------------------------------------------------------------------------------
def test_font_stacks_include_primary_and_fallback() -> None:
    style = StyleConfig()
    serif = serif_stack(style)
    assert style.serif_font in serif and SERIF_FALLBACK in serif
    assert "Consolas" in mono_stack(style)
    fonts = deck_fonts(style)
    assert fonts["display"] == style.grotesk_font


def test_deck_fonts_resolve_from_theme_and_override() -> None:
    # A blank field now resolves to the active theme's family (editorial default), NOT a bare
    # system fallback — the theme always supplies a real family name (PowerPoint substitutes).
    fonts = deck_fonts(StyleConfig(grotesk_font=""))
    assert fonts["display"] == "Space Grotesk"
    assert fonts["display"] != GROTESK_FALLBACK
    # The deck now exposes serif + an expressive statement face (was PDF-only before).
    assert fonts["serif"] == "Fraunces"
    assert fonts["statement"] == "Archivo Black"
    # An explicit *_font override still wins over the theme (back-compat).
    assert deck_fonts(StyleConfig(grotesk_font="My Grotesk"))["display"] == "My Grotesk"
    # A non-editorial theme swaps the families.
    luxury = deck_fonts(StyleConfig(type_theme="luxury"))
    assert luxury["display"] == "Sora"
    assert luxury["serif"] == "Bodoni Moda"
    # An unknown theme degrades to the editorial default.
    assert deck_fonts(StyleConfig(type_theme="nope"))["serif"] == "Fraunces"


def test_statement_fields_mix_warm_and_vivid() -> None:
    colors = ColorsConfig()
    fields = statement_fields(colors)
    assert len(fields) >= 6
    assert colors.vivid_red in fields and colors.baby_blue in fields  # vivid present
    assert colors.terracotta in fields and colors.plum in fields  # warm present
    assert all(f.startswith("#") and len(f) == 7 for f in fields)  # all valid hex


def test_knockout_and_spot_colors_are_legible() -> None:
    colors = ColorsConfig()
    # cream knockout on a dark/strong field, ink on a light field
    assert knockout_text(colors.vivid_red, colors) == colors.knockout_cream
    assert knockout_text(colors.vivid_yellow, colors) == colors.ink
    # two-tone spot: gold on dark, coral on cream, vivid-yellow pop on a mid field
    assert spot_for_canvas(colors.canvas_dark, colors) == colors.artifact_gold
    assert spot_for_canvas(colors.paper, colors) == colors.coral
    assert spot_for_canvas(colors.vivid_red, colors) == colors.vivid_yellow


def test_darken_and_lighten_move_luminance_and_clamp() -> None:
    base = "#808080"
    assert luminance(darken(base, 40)) < luminance(base)
    assert luminance(lighten(base, 40)) > luminance(base)
    assert darken("#000000", 50) == "#000000"  # clamps at black
    assert lighten("#FFFFFF", 50) == "#FFFFFF"  # clamps at white


# --- two-tone headline -------------------------------------------------------------------
def test_split_highlights_a_number_token() -> None:
    before, token, after = split_for_highlight("Revenue grew 40% last year")
    assert token == "40%"
    assert before.strip() == "Revenue grew"
    assert after.strip() == "last year"


def test_split_falls_back_to_proper_noun() -> None:
    before, token, after = split_for_highlight("Watch Figure AI closely")
    assert token  # a proper noun is highlighted when there is no number
    assert "Figure" in token


def test_split_returns_plain_when_nothing_to_highlight() -> None:
    before, token, after = split_for_highlight("keep moving forward")
    assert token == ""
    assert before == "keep moving forward"


def test_split_keeps_unit_word_intact() -> None:
    # The v3 bug sliced "12 months" into "12 m" + "onths"; the token must stay whole now.
    before, token, after = split_for_highlight("Pursue partnerships within the next 12 months")
    assert token == "12 months"
    assert "onths" not in (before + after)


# --- content hygiene (Block 5.0) ---------------------------------------------------------
def test_strip_inline_markdown_removes_emphasis() -> None:
    assert strip_inline_markdown("**Go:** move fast") == "Go: move fast"
    assert strip_inline_markdown("a `code` and __b__") == "a code and b"
    assert strip_inline_markdown("## Heading") == "Heading"
    assert strip_inline_markdown("- bullet point") == "bullet point"


def test_strip_label_prefix_drops_only_the_redundant_label() -> None:
    assert (
        strip_label_prefix("Recommendation: pursue two partnerships") == "pursue two partnerships"
    )
    assert strip_label_prefix("Focus Area 1: formalize R&D") == "formalize R&D"
    # The decision token and ordinary text are untouched (no over-stripping).
    assert strip_label_prefix("GO — accelerate now") == "GO — accelerate now"
    assert strip_label_prefix("Revenue grew 40%") == "Revenue grew 40%"


# --- telemetry chips (source-grounded) ---------------------------------------------------
def test_telemetry_chips_from_real_report() -> None:
    chips = telemetry_chips(_report(), Language.EN)
    joined = " | ".join(chips)
    assert "SOURCES 22" in joined
    assert "WORKERS 3" in joined
    assert "CONFIDENCE HIGH" in joined  # dominant confidence across findings
    assert "AS OF 2026-03" in joined  # latest finding date


def test_telemetry_chips_none_report_is_empty() -> None:
    assert telemetry_chips(None, Language.EN) == []


def test_telemetry_chips_german_labels() -> None:
    chips = telemetry_chips(_report(), Language.DE)
    assert any(c.startswith("QUELLEN") for c in chips)


# --- gradient + svg helpers --------------------------------------------------------------
def test_depth_gradient_and_linear_gradient_svg() -> None:
    stops = depth_gradient_stops(ColorsConfig())
    assert len(stops) >= 2 and stops[0][0] == 0.0 and stops[-1][0] == 1.0
    svg = linear_gradient_svg("g1", stops)
    assert svg.startswith("<linearGradient") and svg.endswith("</linearGradient>")
    assert svg.count("<stop") == len(stops)


def test_svg_escape_and_marker_and_intensity() -> None:
    assert svg_escape("a & b <x>") == "a &amp; b &lt;x&gt;"
    assert "Porter Editorial" in design_marker()
    assert is_editorial(StyleConfig()) is True
    assert is_editorial(StyleConfig(intensity="restrained")) is False
