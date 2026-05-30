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


def test_llm_defaults_match_spec() -> None:
    """Key LLM fields match the SPEC §8 schema."""
    config = load_config(CONFIG_PATH)
    assert config.llm.provider == "ollama"
    assert config.llm.model == "gemma4:e4b"
    assert config.llm.num_ctx == 32768  # CRITICAL: never the 4096 default
    assert config.llm.base_url == "http://localhost:11434"
    assert config.llm.thinking_mode is True


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
