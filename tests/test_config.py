"""Tests for config loading (core/config.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import AppConfig, LLMConfig, load_config

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
