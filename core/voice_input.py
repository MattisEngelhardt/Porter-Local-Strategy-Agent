"""Voice-input layer (Phase 5, SPEC §4.7) — fully local, additive, fail-fast.

Flow: **Ctrl+Space** (pynput global hotkey) → a small **Tkinter** overlay → **pyaudio** captures
audio → **faster-whisper** transcribes it locally (DE/EN auto-detect) → the transcript is injected
into the REPL **as if typed** (pynput keyboard). Zero API calls, zero cloud.

This module is a justified addition to the SPEC §7 tree (like ``config.py`` / ``startup.py``):
SPEC §4.7 names ``voice_input.py`` but §7 omits it from the file list. It is strictly **additive** —
``voice.enabled`` defaults False, the heavy libs (faster-whisper / pyaudio / pynput / numpy) are
imported lazily, and every failure raises :class:`VoiceError` carrying an exact fix, so the text
REPL is never broken (SPEC REQ-5). The record/transcribe/inject steps are overridable seams, so the
logic is unit-testable without a real microphone, model, or global hotkey.
"""

from __future__ import annotations

import importlib
import threading
from collections.abc import Callable
from typing import Any

from core.config import VoiceConfig


class VoiceError(Exception):
    """Voice capture/transcription is unavailable — carries an exact fix (SPEC REQ-5)."""


# Exact install fixes per optional dependency (surfaced in VoiceError messages).
_PIP_HINT = {
    "pyaudio": (
        "pip install pyaudio  (Windows: ships PortAudio; if the build fails, try "
        "'pip install pipwin' then 'pipwin install pyaudio')"
    ),
    "faster_whisper": "pip install faster-whisper",
    "pynput": "pip install pynput",
    "pynput.keyboard": "pip install pynput",
    "numpy": "pip install numpy",
}


def _require(module: str) -> Any:
    """Import an optional voice dependency, or fail fast with its exact pip fix."""
    try:
        return importlib.import_module(module)
    except ImportError as exc:
        hint = _PIP_HINT.get(module, f"pip install {module}")
        raise VoiceError(
            f"Voice needs the '{module}' package, which is not installed.\n"
            f"Fix: {hint}\n"
            "(Voice is optional — the text REPL works without it.)"
        ) from exc


class VoiceInput:
    """Local push-to-talk voice input: hotkey → overlay → record → transcribe → inject."""

    def __init__(self, config: VoiceConfig) -> None:
        """Configure from :class:`VoiceConfig` (all knobs config-driven, RULE 4)."""
        self._model_size = config.model
        self._language = (config.language or "auto").lower()
        self._hotkey = config.hotkey
        self._sample_rate = config.sample_rate
        self._max_seconds = config.max_record_seconds
        self._compute_type = config.compute_type
        self._device_index = config.device_index
        self._model_obj: Any = None
        self._listener: Any = None
        self._overlay: Any = None
        self._busy = threading.Lock()

    # ------------------------------------------------------------------- public API
    def capture_once(self) -> str:
        """Record one utterance and return the transcript (the synchronous ``/voice`` path)."""
        self._show_overlay()
        try:
            audio = self._record_frames()
        finally:
            self._hide_overlay()
        return self._transcribe(audio).strip()

    def start(self, on_transcript: Callable[[str], None] | None = None) -> None:
        """Register the Ctrl+Space global hotkey (background). Raises VoiceError on failure.

        On each press the agent records + transcribes and hands the transcript to ``on_transcript``
        (default: type it into the focused window — the REPL — as if typed).
        """
        keyboard = _require("pynput.keyboard")
        sink = on_transcript or self._inject
        combo = self._to_pynput_hotkey(self._hotkey)

        def _trigger() -> None:
            # Capture off the hotkey thread so the handler returns immediately.
            threading.Thread(target=self._handle_hotkey, args=(sink,), daemon=True).start()

        try:
            self._listener = keyboard.GlobalHotKeys({combo: _trigger})
            self._listener.start()
        except Exception as exc:
            raise VoiceError(
                f"Could not register the voice hotkey '{self._hotkey}'.\n"
                "Fix: ensure no other app owns it, or change voice.hotkey in config.yaml."
            ) from exc

    def stop(self) -> None:
        """Stop the hotkey listener (idempotent; never raises)."""
        listener = self._listener
        self._listener = None
        if listener is not None:
            try:
                listener.stop()
            except Exception:
                pass

    # --------------------------------------------------------- seams (overridable in tests)
    def _handle_hotkey(self, sink: Callable[[str], None]) -> None:
        """Capture + transcribe on a hotkey press, then hand the transcript to ``sink``.

        Never raises — a voice failure must never crash the REPL (additive layer). Re-triggers
        while a capture is in flight are ignored.
        """
        if not self._busy.acquire(blocking=False):
            return
        try:
            text = self.capture_once()
            if text:
                sink(text)
        except VoiceError:
            pass
        finally:
            self._busy.release()

    def _record_frames(self) -> bytes:
        """Capture up to ``max_record_seconds`` of 16 kHz mono PCM via pyaudio."""
        pyaudio = _require("pyaudio")
        audio = pyaudio.PyAudio()
        chunk = 1024
        try:
            stream = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self._sample_rate,
                input=True,
                frames_per_buffer=chunk,
                input_device_index=self._device_index,
            )
        except Exception as exc:
            audio.terminate()
            raise VoiceError(
                "Could not open the microphone.\n"
                "Fix: connect a mic and allow microphone access for your terminal "
                "(Windows: Settings → Privacy & security → Microphone), or set "
                "voice.device_index in config.yaml."
            ) from exc
        frames: list[bytes] = []
        total_chunks = max(1, int(self._sample_rate / chunk * self._max_seconds))
        try:
            for _ in range(total_chunks):
                frames.append(stream.read(chunk, exception_on_overflow=False))
        finally:
            stream.stop_stream()
            stream.close()
            audio.terminate()
        return b"".join(frames)

    def _transcribe(self, audio: bytes) -> str:
        """Transcribe PCM bytes locally with faster-whisper (DE/EN auto-detect)."""
        if not audio:
            return ""
        numpy = _require("numpy")
        model = self._load_model()
        samples = numpy.frombuffer(audio, dtype=numpy.int16).astype("float32") / 32768.0
        language = None if self._language == "auto" else self._language
        try:
            segments, _info = model.transcribe(samples, language=language)
            return " ".join(segment.text for segment in segments).strip()
        except Exception as exc:
            raise VoiceError(f"Transcription failed: {exc}") from exc

    def _inject(self, text: str) -> None:
        """Type the transcript into the focused window (the REPL) as if typed."""
        keyboard = _require("pynput.keyboard")
        try:
            keyboard.Controller().type(text)
        except Exception as exc:
            raise VoiceError(f"Could not inject the transcript: {exc}") from exc

    def _load_model(self) -> Any:
        """Lazily load + cache the faster-whisper model (downloads once on first use)."""
        if self._model_obj is None:
            module = _require("faster_whisper")
            try:
                self._model_obj = module.WhisperModel(
                    self._model_size, device="cpu", compute_type=self._compute_type
                )
            except Exception as exc:
                raise VoiceError(
                    f"Could not load the faster-whisper model '{self._model_size}'.\n"
                    "Fix: be online for the one-time local model download, or set voice.model "
                    "in config.yaml to a smaller size (e.g. 'tiny')."
                ) from exc
        return self._model_obj

    def _show_overlay(self) -> None:
        """Best-effort Tkinter 'listening' overlay (purely cosmetic — never raises)."""
        try:
            import tkinter as tk

            root = tk.Tk()
            root.overrideredirect(True)
            root.attributes("-topmost", True)
            tk.Label(
                root,
                text="  🎙  Listening…  ",
                font=("Segoe UI", 14),
                fg="#FFFFFF",
                bg="#111111",
            ).pack(ipadx=12, ipady=8)
            root.update_idletasks()
            screen_width = root.winfo_screenwidth()
            width = root.winfo_width()
            root.geometry(f"+{(screen_width - width) // 2}+48")
            root.update()
            self._overlay = root
        except Exception:
            self._overlay = None

    def _hide_overlay(self) -> None:
        """Destroy the overlay if present (never raises)."""
        overlay = self._overlay
        self._overlay = None
        if overlay is not None:
            try:
                overlay.destroy()
            except Exception:
                pass

    @staticmethod
    def _to_pynput_hotkey(hotkey: str) -> str:
        """Convert a config hotkey ('ctrl+space') to pynput's form ('<ctrl>+<space>')."""
        named = {
            "ctrl",
            "alt",
            "shift",
            "cmd",
            "super",
            "space",
            "enter",
            "tab",
            "esc",
            "escape",
            "backspace",
            "delete",
        }
        tokens: list[str] = []
        for part in (segment.strip().lower() for segment in hotkey.split("+")):
            if not part:
                continue
            key = "ctrl" if part == "control" else part
            tokens.append(f"<{key}>" if (key in named or len(key) > 1) else key)
        return "+".join(tokens) or "<ctrl>+<space>"


def build_voice_input(config: VoiceConfig) -> VoiceInput | None:
    """Return a :class:`VoiceInput` when voice is enabled, else ``None``.

    ``None`` means no hotkey thread is started and the voice libs are never imported — the text
    REPL keeps zero hard dependency on them (SPEC §4.7 / kickoff: default off, additive).
    """
    if not config.enabled:
        return None
    return VoiceInput(config)
