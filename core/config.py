"""Configuration models and loader for the Strategy Agent.

All tunable parameters live in ``config.yaml`` (SPEC §8). This module parses that
file into typed Pydantic v2 models so the rest of the codebase never touches raw
dicts. ``LLMConfig`` is the object handed to :class:`llm.local_llm_client.LocalLLMClient`.

This file is a justified addition to the SPEC §7 tree: config loading is essential
and the SPEC names the schema but not a loader module (documented in PROGRESS.md).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class LLMCapabilities(BaseModel):
    """Declared capabilities of the configured model (informational)."""

    vision: bool = False
    context_window: int = 131072
    practical_context: int = 32768


class LLMConfig(BaseModel):
    """LLM backend configuration — consumed by ``LocalLLMClient``.

    ``provider`` selects the transport (see ``LocalLLMClient``). ``num_ctx`` is
    ALWAYS sent to the backend on every call (SPEC §9 N-1 / WORKFLOW RULE 10).
    """

    provider: str = "ollama"
    base_url: str = "http://localhost:11434"
    model: str = "gemma4:e4b"
    num_ctx: int = Field(default=32768, gt=0)
    temperature: float = Field(default=0.2, ge=0.0)
    thinking_mode: bool = True
    capabilities: LLMCapabilities = Field(default_factory=LLMCapabilities)
    embedding_model: str = "nomic-embed-text"


class ResearchConfig(BaseModel):
    """SearXNG / research-layer parameters (used from Phase 2)."""

    searxng_url: str = "http://localhost:8080"
    max_results_per_query: int = 8
    max_fetch_per_run: int = 5
    cache_ttl_hours: int = 24
    parallel_queries: int = 3


class MemoryConfig(BaseModel):
    """brain.md + ChromaDB memory parameters (brain inject Phase 3, RAG Phase 5)."""

    enabled: bool = True
    db_path: str = "./data/chroma_db"
    collection_name: str = "strategy_agent_memory"
    top_k_retrieval: int = 5
    brain_path: str = "./brain.md"
    max_brain_lines: int = 300


class AgentConfig(BaseModel):
    """Agent dialog behavior (used from Phase 3)."""

    default_language: str = "auto"  # "auto" | "de" | "en"
    max_clarification_rounds: int = 2
    show_research_plan: bool = True


class ColorsConfig(BaseModel):
    """Neura color palette + Excel color coding (used from Phase 4)."""

    black: str = "#000000"
    white: str = "#FFFFFF"
    accent_cyan: str = "#4DACC7"
    dark_bg: str = "#111111"
    charcoal: str = "#2D2D2D"
    light_surface: str = "#F5F5F5"
    text_dark: str = "#111111"
    text_light: str = "#FFFFFF"
    excel_input_cell: str = "#FFF2CC"
    excel_formula_cell: str = "#DDEEFF"
    excel_positive: str = "#E2EFDA"
    excel_negative: str = "#FFDDC1"
    excel_header: str = "#2D2D2D"


class OutputConfig(BaseModel):
    """Output-layer parameters (used from Phase 4)."""

    default_format: str = "brief"  # "brief" | "deck" | "excel"
    output_dir: str = "./output"
    include_logo: bool = True
    logo_path: str = "./assets/neura_logo.png"
    colors: ColorsConfig = Field(default_factory=ColorsConfig)


class VoiceConfig(BaseModel):
    """Voice-input parameters (enabled in Phase 5)."""

    enabled: bool = False
    model: str = "base"
    language: str = "auto"
    hotkey: str = "ctrl+space"


class LoggingConfig(BaseModel):
    """Logging parameters."""

    level: str = "INFO"
    log_file: str = "./logs/agent.log"


class AppConfig(BaseModel):
    """Top-level application configuration parsed from ``config.yaml``."""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    research: ResearchConfig = Field(default_factory=ResearchConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    voice: VoiceConfig = Field(default_factory=VoiceConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


DEFAULT_CONFIG_PATH = Path("config.yaml")


def load_config(path: Path | str = DEFAULT_CONFIG_PATH) -> AppConfig:
    """Load and validate ``config.yaml`` into an :class:`AppConfig`.

    Args:
        path: Path to the YAML config file.

    Returns:
        A fully validated :class:`AppConfig`.

    Raises:
        FileNotFoundError: If the config file does not exist (fail fast, SPEC REQ-5).
        ValueError: If the YAML is malformed or fails schema validation.
    """
    config_path = Path(path)
    if not config_path.is_file():
        raise FileNotFoundError(
            f"Config file not found: {config_path.resolve()}\n"
            "Fix: ensure config.yaml exists in the project root "
            "(copy the schema from strategy_agent_SPEC.md §8)."
        )

    try:
        with config_path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse {config_path}: {exc}") from exc

    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError(
            f"Config root must be a mapping, got {type(raw).__name__} in {config_path}."
        )

    return AppConfig.model_validate(raw)
