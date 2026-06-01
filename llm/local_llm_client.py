"""Backend-agnostic, OpenAI-compatible local LLM client.

All parameters come from :class:`core.config.LLMConfig` — model name, base URL, and
``num_ctx`` are never hardcoded (SPEC REQ-3). Switching backend or model is a one-line
``config.yaml`` change.

Provider-aware transport (the key Phase 1 decision, see PROGRESS.md):

* ``provider == "ollama"`` → native ``POST {base_url}/api/chat`` with
  ``options.num_ctx``. Ollama's OpenAI ``/v1`` endpoint **silently ignores** ``num_ctx``
  (verified), which is the exact 4K-context silent-failure mode SPEC §9 N-1 / WORKFLOW
  RULE 10 warn about. The native endpoint honors it reliably.
* ``provider in {"lmstudio", "llamacpp", "openai"}`` → the OpenAI SDK against
  ``{base_url}/v1``, passing ``num_ctx`` via ``extra_body.options`` (best-effort; those
  backends fix context at load time anyway).

``num_ctx`` is included in **every** request on every path (RULE 10).
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator
from typing import TYPE_CHECKING, Any, cast

import httpx

from core.config import LLMConfig

if TYPE_CHECKING:  # pragma: no cover - typing only
    from openai import OpenAI, Stream
    from openai.types.chat import ChatCompletion, ChatCompletionChunk

# Connection/read timeouts. Local LLMs with CPU offload can be slow, so the read
# timeout is generous while the connect timeout fails fast when nothing is listening.
_TIMEOUT = httpx.Timeout(connect=10.0, read=300.0, write=30.0, pool=10.0)

_OLLAMA_PROVIDER = "ollama"


class LLMError(Exception):
    """Base class for LLM client errors."""


class LLMConnectionError(LLMError):
    """Raised when the LLM backend cannot be reached (fail fast, SPEC REQ-5)."""


def _detect_family(model: str) -> str:
    """Detect the model family from its config name (SPEC §9 N-2).

    Returns one of ``"gemma"``, ``"qwen"``, or ``"other"``.
    """
    name = model.lower()
    if "gemma" in name:
        return "gemma"
    if "qwen" in name:
        return "qwen"
    return "other"


class LocalLLMClient:
    """Talks to any OpenAI-compatible local endpoint. All params from ``LLMConfig``."""

    def __init__(self, config: LLMConfig) -> None:
        """Initialize from an :class:`LLMConfig` (never hardcode model/url/num_ctx)."""
        self._provider = config.provider.lower()
        self._base_url = config.base_url.rstrip("/")
        self._model = config.model
        self._embedding_model = config.embedding_model
        self._num_ctx = config.num_ctx
        self._temperature = config.temperature
        self._thinking_default = config.thinking_mode
        self._family = _detect_family(self._model)
        self._http: httpx.Client | None = None
        self._openai: OpenAI | None = None

    # ------------------------------------------------------------------ properties
    @property
    def model_name(self) -> str:
        """The configured model name (never hardcoded)."""
        return self._model

    @property
    def backend_url(self) -> str:
        """The configured backend base URL (never hardcoded)."""
        return self._base_url

    @property
    def provider(self) -> str:
        """The configured provider (selects the transport)."""
        return self._provider

    @property
    def embedding_model(self) -> str:
        """The configured embedding model name (never hardcoded; used by the memory layer)."""
        return self._embedding_model

    def switch_model(self, model_name: str) -> None:
        """Switch the active model at runtime (re-detects the model family)."""
        self._model = model_name
        self._family = _detect_family(model_name)

    # -------------------------------------------------------------------- internals
    def _client(self) -> httpx.Client:
        """Lazily create the shared httpx client."""
        if self._http is None:
            self._http = httpx.Client(timeout=_TIMEOUT)
        return self._http

    def _openai_client(self) -> OpenAI:
        """Lazily create the OpenAI SDK client for non-Ollama backends."""
        if self._openai is None:
            from openai import OpenAI

            self._openai = OpenAI(
                base_url=f"{self._base_url}/v1",
                # Local endpoints ignore the key, but the SDK requires a non-empty value.
                api_key=os.getenv("OPENAI_API_KEY", "not-needed"),
            )
        return self._openai

    def _build_messages(
        self, prompt: str, system: str, use_thinking: bool, images: list[str] | None = None
    ) -> list[dict[str, Any]]:
        """Build the chat messages, applying family-specific thinking-mode markers.

        gemma: prepend ``<|think|>`` to the system prompt. qwen: append ``/think`` (or
        ``/no_think``) to the user prompt (SPEC §9 N-2). When ``images`` is given, the
        base64 images are attached to the user message (Ollama native vision format).
        """
        system_text = system
        user_text = prompt

        if use_thinking:
            if self._family == "gemma":
                system_text = "<|think|>" + (f"\n{system}" if system else "")
            elif self._family == "qwen":
                user_text = f"{prompt} /think"
        elif self._family == "qwen":
            user_text = f"{prompt} /no_think"

        messages: list[dict[str, Any]] = []
        if system_text:
            messages.append({"role": "system", "content": system_text})
        user_message: dict[str, Any] = {"role": "user", "content": user_text}
        if images:
            user_message["images"] = images
        messages.append(user_message)
        return messages

    def _connection_error(self, exc: Exception) -> LLMConnectionError:
        """Build a fail-fast connection error with exact fix instructions."""
        return LLMConnectionError(
            f"Cannot reach LLM backend at {self._base_url} (provider={self._provider}).\n"
            "Fix:\n"
            "  1. Start the backend (Ollama: launch the Ollama app or run 'ollama serve').\n"
            f"  2. Ensure the model is available: 'ollama pull {self._model}'.\n"
            f"  3. Confirm 'llm.base_url' in config.yaml points to your backend "
            f"({self._base_url})."
        )

    def _post_ollama(self, payload: dict[str, Any]) -> dict[str, Any]:
        """POST a non-streaming request to Ollama's native /api/chat and return JSON."""
        url = f"{self._base_url}/api/chat"
        try:
            response = self._client().post(url, json=payload)
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise self._connection_error(exc) from exc
        except httpx.HTTPStatusError as exc:
            raise LLMError(
                f"LLM backend returned HTTP {exc.response.status_code} for {url}: "
                f"{exc.response.text[:300]}"
            ) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request to {url} failed: {exc}") from exc
        data: dict[str, Any] = response.json()
        return data

    # --------------------------------------------------------------------- public API
    def generate(
        self,
        prompt: str,
        system: str = "",
        use_thinking: bool | None = None,
        num_ctx: int | None = None,
        stream: bool = False,
        images: list[str] | None = None,
    ) -> str:
        """Generate a completion and return the full text.

        Args:
            prompt: The user prompt.
            system: Optional system prompt.
            use_thinking: Enable thinking mode. ``None`` uses the config default.
            num_ctx: Context window. ``None`` uses the config default. ALWAYS sent.
            stream: If True, use the streaming transport (text is still returned whole).
            images: Optional base64-encoded images for vision input (Ollama only).

        Returns:
            The model's response text.

        Raises:
            LLMConnectionError: If the backend is unreachable.
            LLMError: For other backend/transport failures, or images on a non-Ollama backend.
        """
        if stream:
            return "".join(self.stream_generate(prompt, system, use_thinking, num_ctx))

        if images and self._provider != _OLLAMA_PROVIDER:
            raise LLMError(
                "Image/vision input is only supported on the Ollama provider in Phase 2 "
                f"(provider={self._provider}). Set llm.provider to 'ollama' for vision."
            )

        resolved_thinking = self._thinking_default if use_thinking is None else use_thinking
        resolved_num_ctx = self._num_ctx if num_ctx is None else num_ctx
        messages = self._build_messages(prompt, system, resolved_thinking, images)

        if self._provider == _OLLAMA_PROVIDER:
            payload: dict[str, Any] = {
                "model": self._model,
                "messages": messages,
                "stream": False,
                "options": {
                    "num_ctx": resolved_num_ctx,  # RULE 10: always present
                    "temperature": self._temperature,
                },
            }
            data = self._post_ollama(payload)
            message = data.get("message") or {}
            content = message.get("content", "")
            return str(content)

        # OpenAI-compatible backends (LM Studio / llama.cpp / generic OpenAI)
        try:
            raw = self._openai_client().chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                temperature=self._temperature,
                stream=False,
                extra_body={"options": {"num_ctx": resolved_num_ctx}},  # best-effort
            )
        except Exception as exc:  # openai SDK raises its own error hierarchy
            raise self._wrap_openai_error(exc) from exc
        completion = cast("ChatCompletion", raw)
        choice = completion.choices[0].message.content
        return choice or ""

    def stream_generate(
        self,
        prompt: str,
        system: str = "",
        use_thinking: bool | None = None,
        num_ctx: int | None = None,
    ) -> Iterator[str]:
        """Yield response text chunks as they arrive (used for live REPL output)."""
        resolved_thinking = self._thinking_default if use_thinking is None else use_thinking
        resolved_num_ctx = self._num_ctx if num_ctx is None else num_ctx
        messages = self._build_messages(prompt, system, resolved_thinking)

        if self._provider == _OLLAMA_PROVIDER:
            yield from self._stream_ollama(messages, resolved_num_ctx)
            return

        try:
            raw_stream = self._openai_client().chat.completions.create(
                model=self._model,
                messages=messages,  # type: ignore[arg-type]
                temperature=self._temperature,
                stream=True,
                extra_body={"options": {"num_ctx": resolved_num_ctx}},
            )
            stream = cast("Stream[ChatCompletionChunk]", raw_stream)
            for chunk in stream:
                delta = chunk.choices[0].delta.content
                if delta:
                    yield delta
        except Exception as exc:
            raise self._wrap_openai_error(exc) from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts with the configured embedding model (provider-aware, local, CPU).

        Used by the ChromaDB memory layer (Phase 5). The embedding model
        (``llm.embedding_model``, default ``nomic-embed-text``) runs on CPU via Ollama so it
        never competes with the chat model for VRAM (SPEC §4.5). All embedding traffic goes
        through this client (RULE 6) — no raw requests in the memory layer.

        Args:
            texts: The strings to embed (one vector returned per string, order preserved).

        Returns:
            One embedding vector per input string.

        Raises:
            LLMConnectionError: If the backend is unreachable (fail fast, SPEC REQ-5).
            LLMError: If the embedding model is not available (with the exact pull fix).
        """
        if not texts:
            return []
        if self._provider == _OLLAMA_PROVIDER:
            return [self._embed_ollama(text) for text in texts]
        return self._embed_openai(texts)

    def _embed_ollama(self, text: str) -> list[float]:
        """Embed one string via Ollama's native /api/embeddings endpoint."""
        url = f"{self._base_url}/api/embeddings"
        payload = {"model": self._embedding_model, "prompt": text}
        try:
            response = self._client().post(url, json=payload)
            response.raise_for_status()
        except httpx.ConnectError as exc:
            raise self._connection_error(exc) from exc
        except httpx.HTTPStatusError as exc:
            # 404 / 400 here almost always means the embedding model is not pulled.
            raise self._embedding_model_error() from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"Embedding request to {url} failed: {exc}") from exc
        data: dict[str, Any] = response.json()
        vector = data.get("embedding")
        if not isinstance(vector, list) or not vector:
            raise self._embedding_model_error()
        return [float(value) for value in vector]

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        """Embed via an OpenAI-compatible /v1/embeddings endpoint (LM Studio / llama.cpp)."""
        try:
            raw = self._openai_client().embeddings.create(model=self._embedding_model, input=texts)
        except Exception as exc:  # openai SDK raises its own error hierarchy
            raise self._wrap_openai_error(exc) from exc
        return [list(item.embedding) for item in raw.data]

    def _embedding_model_error(self) -> LLMError:
        """Build a fail-fast error for a missing embedding model (with the exact pull fix)."""
        return LLMError(
            f"Embedding model '{self._embedding_model}' is not available at {self._base_url}.\n"
            "Fix:\n"
            f"  1. Pull it: 'ollama pull {self._embedding_model}'.\n"
            "  2. Confirm 'llm.embedding_model' in config.yaml matches a pulled model.\n"
            "  (Persistent memory needs embeddings — the agent still runs without it.)"
        )

    def _stream_ollama(self, messages: list[dict[str, Any]], num_ctx: int) -> Iterator[str]:
        """Stream from Ollama's native /api/chat (NDJSON), yielding content chunks."""
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "messages": messages,
            "stream": True,
            "options": {"num_ctx": num_ctx, "temperature": self._temperature},
        }
        try:
            with self._client().stream("POST", url, json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    obj = json.loads(line)
                    chunk = obj.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk
                    if obj.get("done"):
                        break
        except httpx.ConnectError as exc:
            raise self._connection_error(exc) from exc
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM stream request to {url} failed: {exc}") from exc

    def _wrap_openai_error(self, exc: Exception) -> LLMError:
        """Translate an OpenAI-SDK exception into our error hierarchy."""
        name = type(exc).__name__
        if "Connection" in name or "APIConnection" in name:
            return self._connection_error(exc)
        return LLMError(f"LLM backend error ({name}): {exc}")

    def close(self) -> None:
        """Close underlying HTTP resources."""
        if self._http is not None:
            self._http.close()
            self._http = None
