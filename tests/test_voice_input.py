"""Tests for the voice-input layer (core/voice_input.py).

No real microphone, Whisper model, or global hotkey is touched: the record/transcribe/inject/
overlay steps are overridable seams, and the lazy-import helper is exercised via monkeypatching.
"""

from __future__ import annotations

from typing import Any

import pytest

import core.voice_input as voice_input
from core.config import VoiceConfig
from core.voice_input import VoiceError, VoiceInput, build_voice_input


def _config(**kw: Any) -> VoiceConfig:
    base: dict[str, Any] = {"enabled": True, "model": "base", "language": "auto"}
    base.update(kw)
    return VoiceConfig(**base)


# ------------------------------------------------------------------ build / gating
def test_build_voice_input_disabled_returns_none() -> None:
    """Voice off → no VoiceInput (no hotkey thread, no voice libs imported)."""
    assert build_voice_input(VoiceConfig(enabled=False)) is None


def test_build_voice_input_enabled_returns_instance() -> None:
    """Voice on → a VoiceInput is built."""
    assert isinstance(build_voice_input(_config()), VoiceInput)


# ------------------------------------------------------------------ lazy-import fail-fast
def test_require_missing_module_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    """A missing optional dep raises VoiceError carrying the exact pip fix."""

    def _boom(name: str) -> Any:
        raise ImportError(f"no module {name}")

    monkeypatch.setattr(voice_input.importlib, "import_module", _boom)
    with pytest.raises(VoiceError) as excinfo:
        voice_input._require("pyaudio")
    message = str(excinfo.value)
    assert "pyaudio" in message
    assert "Fix:" in message
    assert "pip install" in message


def test_require_present_module_returns_it() -> None:
    """When the module is importable, _require returns it (json stands in for a voice lib)."""
    import json

    assert voice_input._require("json") is json


# ------------------------------------------------------------------ capture pipeline (seams)
class _StubVoice(VoiceInput):
    """VoiceInput with the hardware/model/overlay seams stubbed for offline tests."""

    def __init__(self, transcript: str = "", **kw: Any) -> None:
        super().__init__(_config(**kw))
        self._transcript = transcript
        self.events: list[str] = []
        self.recorded = False

    def _show_overlay(self) -> None:
        self.events.append("show")

    def _hide_overlay(self) -> None:
        self.events.append("hide")

    def _record_frames(self) -> bytes:
        self.recorded = True
        return b"\x00\x01"

    def _transcribe(self, audio: bytes) -> str:
        return self._transcript


def test_capture_once_runs_overlay_record_transcribe() -> None:
    """capture_once shows + hides the overlay around recording and returns the transcript."""
    voice = _StubVoice(transcript="  Analysiere Figure AI  ")
    assert voice.capture_once() == "Analysiere Figure AI"
    assert voice.recorded is True
    assert voice.events == ["show", "hide"]


def test_handle_hotkey_delivers_transcript_to_sink() -> None:
    """A hotkey press records, transcribes, and hands the text to the sink (the REPL injector)."""
    voice = _StubVoice(transcript="business case japan")
    delivered: list[str] = []
    voice._handle_hotkey(delivered.append)
    assert delivered == ["business case japan"]


def test_handle_hotkey_swallows_voice_error() -> None:
    """A capture failure never crashes the REPL — the sink is simply not called."""

    class _BrokenVoice(_StubVoice):
        def _record_frames(self) -> bytes:
            raise VoiceError("mic gone")

    voice = _BrokenVoice()
    delivered: list[str] = []
    voice._handle_hotkey(delivered.append)  # must not raise
    assert delivered == []


def test_handle_hotkey_empty_transcript_not_delivered() -> None:
    """An empty transcript (no speech) is not injected."""
    voice = _StubVoice(transcript="   ")
    delivered: list[str] = []
    voice._handle_hotkey(delivered.append)
    assert delivered == []


def test_transcribe_empty_audio_returns_empty() -> None:
    """Empty PCM short-circuits to '' (no model/numpy needed)."""
    assert VoiceInput(_config())._transcribe(b"") == ""


# ------------------------------------------------------------------ hotkey parsing + start
@pytest.mark.parametrize(
    ("hotkey", "expected"),
    [
        ("ctrl+space", "<ctrl>+<space>"),
        ("ctrl+alt+h", "<ctrl>+<alt>+h"),
        ("control+space", "<ctrl>+<space>"),
        ("", "<ctrl>+<space>"),
    ],
)
def test_to_pynput_hotkey(hotkey: str, expected: str) -> None:
    """Config hotkeys convert to pynput's GlobalHotKeys notation."""
    assert VoiceInput._to_pynput_hotkey(hotkey) == expected


def test_start_registers_global_hotkey(monkeypatch: pytest.MonkeyPatch) -> None:
    """start() registers the configured combo and starts the listener (pynput stubbed)."""
    registered: dict[str, Any] = {}

    class _FakeHotKeys:
        def __init__(self, mapping: dict[str, Any]) -> None:
            registered["mapping"] = mapping
            self.started = False

        def start(self) -> None:
            self.started = True

        def stop(self) -> None:
            self.started = False

    class _FakeKeyboard:
        GlobalHotKeys = _FakeHotKeys

    monkeypatch.setattr(
        voice_input,
        "_require",
        lambda name: _FakeKeyboard if name == "pynput.keyboard" else __import__(name),
    )
    voice = VoiceInput(_config(hotkey="ctrl+space"))
    voice.start(on_transcript=lambda _t: None)
    assert "<ctrl>+<space>" in registered["mapping"]
    assert voice._listener.started is True
    voice.stop()  # idempotent, never raises
    voice.stop()
