"""Tests for config loading (core/config.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import AppConfig, EffortConfig, LLMConfig, load_config

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def test_config_yaml_loads() -> None:
    """config.yaml parses into an AppConfig."""
    config = load_config(CONFIG_PATH)
    assert isinstance(config, AppConfig)


def test_llm_schema_defaults_match_spec() -> None:
    """The LLMConfig schema defaults match the SPEC §8 reference (Ollama / gemma4:e4b)."""
    defaults = LLMConfig()
    assert defaults.provider == "ollama"
    assert defaults.model == "gemma4:e4b"
    assert defaults.num_ctx == 32768  # CRITICAL: never the 4096 default (N-1)
    assert defaults.base_url == "http://localhost:11434"
    assert defaults.thinking_mode is True


def test_live_config_llm_matches_active_backend() -> None:
    """The active config.yaml is valid for whichever backend is selected (elegant switch, REQ-3).

    The project ships a one-line provider/model switch (switch-llm.ps1) and must stay green on BOTH
    backends — now and on future hardware. Backend-independent invariants are always asserted; each
    backend's contract is checked when it is active (so the Ollama assertions are preserved, not
    removed — they simply apply when Ollama is selected).
    """
    llm = load_config(CONFIG_PATH).llm
    # Invariants that must hold on every backend:
    assert llm.num_ctx == 32768  # CRITICAL: never the 4096 default (N-1)
    assert llm.thinking_mode is True
    assert llm.base_url.startswith("http")
    assert llm.model  # a model name is configured
    # Backend-specific defaults — both kept first-class by the switch:
    expected_base = {"ollama": "http://localhost:11434", "lmstudio": "http://localhost:1234"}
    assert llm.provider in {*expected_base, "llamacpp", "openai"}
    if llm.provider in expected_base:
        assert llm.base_url == expected_base[llm.provider]
    if llm.provider == "ollama":
        assert llm.model == "gemma4:e4b"  # SPEC §8 default model when on Ollama


def test_excel_and_neura_colors_present() -> None:
    """Output color palette includes Neura accent + Excel color coding."""
    config = load_config(CONFIG_PATH)
    colors = config.output.colors
    assert colors.accent_cyan == "#4DACC7"
    assert colors.excel_input_cell == "#FFF2CC"
    assert colors.excel_formula_cell == "#DDEEFF"


def test_brain_path_configured() -> None:
    """brain.md path is configured for synthesis injection."""
    config = load_config(CONFIG_PATH)
    assert config.memory.brain_path == "./brain.md"
    assert config.memory.max_brain_lines == 300


def test_missing_config_raises() -> None:
    """A missing config file fails fast with FileNotFoundError (SPEC REQ-5)."""
    with pytest.raises(FileNotFoundError):
        load_config(PROJECT_ROOT / "does_not_exist.yaml")


def test_num_ctx_must_be_positive() -> None:
    """num_ctx is validated as > 0."""
    with pytest.raises(ValueError):
        LLMConfig(num_ctx=0)


# --- effort master dial (Phase 3.5) ------------------------------------------------------
def test_effort_block_loads_three_levels() -> None:
    """config.yaml defines the low/high/ultra effort levels with the planned values."""
    config = load_config(CONFIG_PATH)
    effort = config.effort
    assert effort.default == "high"
    assert effort.critique_min_score == 75
    assert effort.worker_concurrency >= 1
    assert set(effort.levels) >= {"low", "high", "ultra"}
    assert effort.levels["low"].research_workers == 1
    assert effort.levels["low"].critique is False
    assert effort.levels["ultra"].research_workers == 5
    assert effort.levels["ultra"].max_research_rounds == 3
    assert effort.levels["high"].critique is True


def test_effort_level_for_resolves_and_falls_back() -> None:
    """level_for resolves a known level and falls back to the default for unknown ones."""
    effort = EffortConfig()
    assert effort.level_for("low").research_workers == 1
    assert effort.level_for("ULTRA").research_workers == 5  # case-insensitive
    # Unknown level → falls back to the configured default ("high").
    assert effort.level_for("nonsense").research_workers == effort.levels["high"].research_workers


def test_effort_defaults_are_never_shallow() -> None:
    """An EffortLevelConfig with no fields set mirrors the safe 'high' profile (RULE 9)."""
    from core.config import EffortLevelConfig

    level = EffortLevelConfig()
    assert level.research_workers == 3
    assert level.critique is True
    assert level.thinking is True


def test_v4_palette_and_style_tokens_present() -> None:
    """Editorial v4.0 adds warm + vivid palette tokens and new style knobs (defaults, RULE 4)."""
    from core.config import ColorsConfig, OutputConfig, StyleConfig

    colors = ColorsConfig()
    # Warm extensions + vivid additions all present and valid hex.
    for token in ("terracotta", "ochre", "plum", "deep_blue", "sand", "cream_hi", "knockout_cream"):
        assert getattr(colors, token).startswith("#")
    for token in (
        "baby_blue",
        "vivid_red",
        "vivid_green",
        "vivid_orange",
        "vivid_yellow",
        "violet",
    ):
        assert getattr(colors, token).startswith("#")
    # The warm v3.0 tokens still exist (nothing removed).
    assert colors.paper and colors.coral and colors.artifact_gold and colors.white and colors.black
    # New style knobs default to the bold/clean behavior.
    style = StyleConfig()
    assert style.type_theme == "editorial"
    assert style.telemetry_chips is False  # chips off by default
    assert style.max_diagrams_per_deck == 3
    out = OutputConfig()
    assert out.logo_path_light is None
    assert out.imagery_dir.endswith("imagery")


def test_live_config_yaml_carries_v4_tokens() -> None:
    """The shipped config.yaml exposes the v4 palette + style tokens (not just the schema)."""
    config = load_config(CONFIG_PATH)
    assert config.output.colors.vivid_red.startswith("#")
    assert config.output.style.type_theme in {
        "editorial",
        "kinetic",
        "luxury",
        "modern",
        "brutalist",
    }
