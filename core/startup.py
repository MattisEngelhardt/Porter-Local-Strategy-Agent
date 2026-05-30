"""Startup dependency checks — fail fast with exact fix instructions (SPEC REQ-5).

Phase 1 verifies the LLM backend only. SearXNG / Docker checks arrive in Phase 2.
These functions raise :class:`StartupError` (with actionable messages); the caller
(main.py) prints and exits non-zero. No presentation logic lives here.
"""

from __future__ import annotations

from typing import Any

import httpx

from core.config import AppConfig

_OLLAMA_PROVIDER = "ollama"


class StartupError(Exception):
    """A required dependency is missing or unreachable at startup."""


def _model_present(model: str, available: list[str]) -> bool:
    """True if the configured model matches an available model (exact or untagged)."""
    if model in available:
        return True
    base = model.split(":", 1)[0]
    return any(name == model or name.split(":", 1)[0] == base for name in available)


def list_ollama_models(base_url: str, timeout: float = 5.0) -> list[str]:
    """Return the names of models available on an Ollama backend.

    Raises:
        StartupError: If the backend cannot be reached.
    """
    url = f"{base_url.rstrip('/')}/api/tags"
    try:
        response = httpx.get(url, timeout=timeout)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise StartupError(
            f"Ollama is not reachable at {base_url}.\n"
            "Fix:\n"
            "  1. Install Ollama from https://ollama.com/download (if not installed).\n"
            "  2. Start it: launch the Ollama app, or run 'ollama serve'.\n"
            f"  3. Confirm 'llm.base_url' in config.yaml is correct ({base_url})."
        ) from exc

    data: dict[str, Any] = response.json()
    models = data.get("models", [])
    return [str(m.get("name", "")) for m in models if m.get("name")]


def check_llm_backend(config: AppConfig) -> list[str]:
    """Verify the configured LLM backend is reachable and the model is available.

    Returns:
        The list of available model names (empty list for non-Ollama backends that
        do not expose a model list).

    Raises:
        StartupError: If the backend is unreachable or the model is missing.
    """
    llm = config.llm
    provider = llm.provider.lower()

    if provider == _OLLAMA_PROVIDER:
        available = list_ollama_models(llm.base_url)
        if not _model_present(llm.model, available):
            listed = ", ".join(sorted(available)) or "(none)"
            raise StartupError(
                f"Model '{llm.model}' is not available on Ollama.\n"
                f"Available models: {listed}\n"
                "Fix:\n"
                f"  1. Pull it: 'ollama pull {llm.model}'.\n"
                "  2. Or set 'llm.model' in config.yaml to one of the available models."
            )
        return available

    # Non-Ollama OpenAI-compatible backend: verify reachability only (best effort).
    url = f"{llm.base_url.rstrip('/')}/v1/models"
    try:
        response = httpx.get(url, timeout=5.0)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise StartupError(
            f"LLM backend (provider={provider}) is not reachable at {llm.base_url}.\n"
            "Fix:\n"
            "  1. Start your backend (LM Studio server / llama.cpp-server).\n"
            f"  2. Confirm 'llm.base_url' in config.yaml is correct ({llm.base_url})."
        ) from exc
    return []
