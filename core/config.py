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

    searxng_url: str = "http://localhost:8888"
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


class EffortLevelConfig(BaseModel):
    """Per-level intensity parameters for the effort master dial (Phase 3.5).

    Every knob the advanced loop reads — worker count, research rounds, fetch depth,
    clarification/mid-research budgets, revision count, and the critique/thinking switches —
    lives here, one set per effort level. Defaults mirror ``high`` so a missing field is never
    silently shallow.
    """

    research_workers: int = Field(default=3, ge=1)
    max_research_rounds: int = Field(default=2, ge=1)
    max_fetch_per_worker: int = Field(default=5, ge=1)
    max_clarifications: int = Field(default=2, ge=0)
    max_midresearch_questions: int = Field(default=1, ge=0)
    revisions: int = Field(default=1, ge=0)
    critique: bool = True
    thinking: bool = True


def _default_effort_levels() -> dict[str, EffortLevelConfig]:
    """The three built-in effort levels (used when ``config.yaml`` omits the block)."""
    return {
        "low": EffortLevelConfig(
            research_workers=1,
            max_research_rounds=1,
            max_fetch_per_worker=3,
            max_clarifications=1,
            max_midresearch_questions=0,
            revisions=0,
            critique=False,
            thinking=False,
        ),
        "high": EffortLevelConfig(
            research_workers=3,
            max_research_rounds=2,
            max_fetch_per_worker=5,
            max_clarifications=2,
            max_midresearch_questions=1,
            revisions=1,
            critique=True,
            thinking=True,
        ),
        "ultra": EffortLevelConfig(
            research_workers=5,
            max_research_rounds=3,
            max_fetch_per_worker=8,
            max_clarifications=3,
            max_midresearch_questions=2,
            revisions=2,
            critique=True,
            thinking=True,
        ),
    }


class EffortConfig(BaseModel):
    """The effort master dial (Phase 3.5): one knob controlling the whole loop's intensity.

    ``levels`` maps ``"low"``/``"high"``/``"ultra"`` to their :class:`EffortLevelConfig`.
    ``level_for`` resolves a level name (or an ``EffortLevel`` StrEnum, which equals its value)
    to its config, falling back to ``default`` then to safe defaults so an unknown/typo'd level
    never silently runs shallow. Post-hardware-upgrade the user just edits these numbers +
    ``worker_concurrency`` — zero code change to scale (SPEC §15.5).
    """

    default: str = "high"  # used when auto-detect is unsure (never silently shallow)
    critique_min_score: int = Field(default=75, ge=0, le=100)
    worker_concurrency: int = Field(default=2, ge=1)  # workers truly running at once
    levels: dict[str, EffortLevelConfig] = Field(default_factory=_default_effort_levels)

    def level_for(self, level: str) -> EffortLevelConfig:
        """Resolve a level name to its config (falls back to ``default`` then safe defaults)."""
        key = str(level).strip().lower()
        if key in self.levels:
            return self.levels[key]
        if self.default in self.levels:
            return self.levels[self.default]
        return EffortLevelConfig()


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
    artifact_blue: str = "#1F4E79"
    artifact_teal: str = "#157A6E"
    artifact_gold: str = "#C99700"
    artifact_risk: str = "#B42318"
    artifact_mist: str = "#EEF6F8"


class OutputConfig(BaseModel):
    """Output-layer parameters (used from Phase 4)."""

    default_format: str = "brief"  # "brief" | "deck" | "excel"
    output_dir: str = "./output"
    include_logo: bool = True
    logo_path: str = "./assets/neura_logo.png"
    # Optional explicit GTK3-runtime bin dir for WeasyPrint on Windows (None = auto-detect
    # standard locations). Forced ahead of any incompatible libgobject on PATH (e.g. Tesseract).
    gtk_runtime_path: str | None = None
    colors: ColorsConfig = Field(default_factory=ColorsConfig)


class VoiceConfig(BaseModel):
    """Voice-input parameters (Phase 5). All local: faster-whisper + pyaudio + pynput.

    ``enabled`` defaults False so the text REPL has zero hard dependency on the voice libs and
    starts no hotkey thread unless the user opts in.
    """

    enabled: bool = False
    model: str = "base"  # faster-whisper model size: tiny | base | small | medium | large-v3
    language: str = "auto"  # "auto" | "de" | "en"
    hotkey: str = "ctrl+space"
    sample_rate: int = Field(default=16000, gt=0)  # 16 kHz mono — what Whisper expects
    max_record_seconds: int = Field(default=12, gt=0)  # fixed-duration capture per press
    compute_type: str = "int8"  # CPU-friendly quantization for faster-whisper
    device_index: int | None = None  # input device (None = system default microphone)


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
    effort: EffortConfig = Field(default_factory=EffortConfig)
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
