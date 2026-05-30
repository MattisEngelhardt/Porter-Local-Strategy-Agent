"""Tests for the backend-agnostic LocalLLMClient (llm/local_llm_client.py).

Offline unit tests mock the network so they always run. One live test exercises a
real generation and is skipped if Ollama is unreachable.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from core.config import LLMConfig, load_config
from llm.local_llm_client import LocalLLMClient, _detect_family

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config.yaml"


def _ollama_config(**overrides: Any) -> LLMConfig:
    """Build an Ollama LLMConfig with sensible defaults for tests."""
    base = {
        "provider": "ollama",
        "base_url": "http://localhost:11434",
        "model": "gemma4:e4b",
        "num_ctx": 32768,
        "temperature": 0.2,
        "thinking_mode": True,
    }
    base.update(overrides)
    return LLMConfig(**base)


def _capture_post(client: LocalLLMClient, captured: list[dict[str, Any]]) -> None:
    """Monkeypatch the client's Ollama POST to record payloads and return a canned reply."""

    def fake_post(payload: dict[str, Any]) -> dict[str, Any]:
        captured.append(payload)
        return {"message": {"role": "assistant", "content": "ok"}, "done": True}

    client._post_ollama = fake_post  # type: ignore[method-assign]


# --------------------------------------------------------------- num_ctx (RULE 10)
def test_num_ctx_always_sent_default() -> None:
    """Every Ollama call includes num_ctx from config (never the 4096 default)."""
    client = LocalLLMClient(_ollama_config())
    captured: list[dict[str, Any]] = []
    _capture_post(client, captured)

    client.generate("hello")

    assert captured[0]["options"]["num_ctx"] == 32768


def test_num_ctx_override_per_call() -> None:
    """A per-call num_ctx overrides the config default and is still sent."""
    client = LocalLLMClient(_ollama_config())
    captured: list[dict[str, Any]] = []
    _capture_post(client, captured)

    client.generate("hello", num_ctx=8192)

    assert captured[0]["options"]["num_ctx"] == 8192


# ------------------------------------------------------- backend/model agnosticism
def test_backend_url_and_model_from_config() -> None:
    """model_name and backend_url reflect config with no code change."""
    client = LocalLLMClient(_ollama_config(model="gemma4:e4b"))
    assert client.model_name == "gemma4:e4b"
    assert client.backend_url == "http://localhost:11434"

    # A different config -> different backend, zero code changes.
    other = LocalLLMClient(_ollama_config(model="qwen3:8b", base_url="http://localhost:1234"))
    assert other.model_name == "qwen3:8b"
    assert other.backend_url == "http://localhost:1234"


def test_base_url_trailing_slash_normalized() -> None:
    """A trailing slash in base_url is normalized away."""
    client = LocalLLMClient(_ollama_config(base_url="http://localhost:11434/"))
    assert client.backend_url == "http://localhost:11434"


def test_switch_model_updates_family() -> None:
    """switch_model changes the active model and re-detects the family."""
    client = LocalLLMClient(_ollama_config(model="gemma4:e4b"))
    assert client._family == "gemma"
    client.switch_model("qwen3:8b")
    assert client.model_name == "qwen3:8b"
    assert client._family == "qwen"


def test_detect_family() -> None:
    """Family detection works from the model name (SPEC §9 N-2)."""
    assert _detect_family("gemma4:e4b") == "gemma"
    assert _detect_family("qwen3:8b") == "qwen"
    assert _detect_family("amadeus:latest") == "other"


# ---------------------------------------------------------------- thinking mode
def test_gemma_thinking_injects_into_system() -> None:
    """gemma + thinking prepends <|think|> to the system prompt."""
    client = LocalLLMClient(_ollama_config(model="gemma4:e4b"))
    captured: list[dict[str, Any]] = []
    _capture_post(client, captured)

    client.generate("analyze X", system="You are helpful.", use_thinking=True)

    messages = captured[0]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"].startswith("<|think|>")
    assert "You are helpful." in messages[0]["content"]


def test_gemma_no_thinking_has_no_marker() -> None:
    """gemma without thinking does not inject the <|think|> marker."""
    client = LocalLLMClient(_ollama_config(model="gemma4:e4b"))
    captured: list[dict[str, Any]] = []
    _capture_post(client, captured)

    client.generate("analyze X", use_thinking=False)

    # No system message at all when none was provided and thinking is off.
    roles = [m["role"] for m in captured[0]["messages"]]
    assert "system" not in roles
    assert all("<|think|>" not in m["content"] for m in captured[0]["messages"])


def test_qwen_thinking_flag_in_prompt() -> None:
    """qwen + thinking appends /think; without thinking appends /no_think."""
    client = LocalLLMClient(_ollama_config(model="qwen3:8b"))
    captured: list[dict[str, Any]] = []
    _capture_post(client, captured)

    client.generate("analyze X", use_thinking=True)
    assert captured[-1]["messages"][-1]["content"].endswith("/think")

    client.generate("analyze X", use_thinking=False)
    assert captured[-1]["messages"][-1]["content"].endswith("/no_think")


def test_thinking_defaults_to_config() -> None:
    """When use_thinking is None, the config default is used."""
    client = LocalLLMClient(_ollama_config(model="gemma4:e4b", thinking_mode=True))
    captured: list[dict[str, Any]] = []
    _capture_post(client, captured)

    client.generate("analyze X")  # no use_thinking -> config default (True)
    assert captured[0]["messages"][0]["content"].startswith("<|think|>")


# ---------------------------------------------------------------------- vision
def test_images_attached_to_user_message_ollama() -> None:
    """Base64 images are attached to the user message on the Ollama path."""
    client = LocalLLMClient(_ollama_config())
    captured: list[dict[str, Any]] = []
    _capture_post(client, captured)

    client.generate("describe this", images=["B64DATA"], use_thinking=False)

    user_message = captured[0]["messages"][-1]
    assert user_message["role"] == "user"
    assert user_message["images"] == ["B64DATA"]


def test_images_rejected_on_non_ollama_backend() -> None:
    """Passing images to a non-Ollama backend fails fast with a clear error."""
    from llm.local_llm_client import LLMError

    client = LocalLLMClient(_ollama_config(provider="lmstudio", base_url="http://localhost:1234"))
    with pytest.raises(LLMError) as excinfo:
        client.generate("describe", images=["B64DATA"])
    assert "vision" in str(excinfo.value).lower()


# ---------------------------------------------------------------- connection error
def test_connection_error_is_fail_fast() -> None:
    """An unreachable backend raises LLMConnectionError with fix instructions."""
    from llm.local_llm_client import LLMConnectionError

    # Point at a closed port to force a connect error quickly.
    client = LocalLLMClient(_ollama_config(base_url="http://localhost:9"))
    with pytest.raises(LLMConnectionError) as excinfo:
        client.generate("hello")
    assert "Fix:" in str(excinfo.value)


# ---------------------------------------------------------------------- live test
def _ollama_reachable(base_url: str) -> bool:
    try:
        resp = httpx.get(f"{base_url}/api/tags", timeout=2.0)
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def test_live_generate_returns_text() -> None:
    """Live: a real generation against the configured model returns non-empty text."""
    config = load_config(CONFIG_PATH)
    if not _ollama_reachable(config.llm.base_url):
        pytest.skip("Ollama not reachable — skipping live LLM test.")

    client = LocalLLMClient(config.llm)
    result = client.generate("Reply with exactly one word: pong", use_thinking=False)
    assert isinstance(result, str)
    assert result.strip() != ""
