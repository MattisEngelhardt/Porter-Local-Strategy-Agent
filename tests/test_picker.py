"""Tests for the REPL choice picker (core/picker.py).

The arrow-key path needs an interactive TTY, so the tests exercise the numbered fallback (which is
also what runs under pytest / pipes) directly and through the public ``select`` entry point.
"""

from __future__ import annotations

import io

import pytest
from rich.console import Console

from core.picker import Choice, _fallback_select, select


def _console() -> Console:
    return Console(file=io.StringIO(), width=100, force_terminal=False)


def _choices() -> list[Choice]:
    return [
        Choice(value="all", title="Allrounder", hint="everything"),
        Choice(value="research", title="Research / Strategy"),
        Choice(value="analyst", title="Analyst", hint="evaluate docs"),
    ]


def test_select_empty_returns_none() -> None:
    assert select("pick", [], console=_console()) is None


def test_fallback_returns_value_for_valid_number(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda *a, **k: "3")
    assert _fallback_select("pick", _choices(), "all", _console()) == "analyst"


def test_fallback_marks_active_in_output(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda *a, **k: "1")
    console = _console()
    assert _fallback_select("pick", _choices(), "research", console) == "all"
    out = console.file.getvalue()  # type: ignore[attr-defined]
    assert "Allrounder" in out and "Analyst" in out  # the menu was rendered


@pytest.mark.parametrize("raw", ["", "0", "9", "abc", "  "])
def test_fallback_none_for_invalid(raw: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("builtins.input", lambda *a, **k: raw)
    assert _fallback_select("pick", _choices(), None, _console()) is None


def test_fallback_eof_returns_none(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*a: object, **k: object) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", _raise)
    assert _fallback_select("pick", _choices(), None, _console()) is None


def test_select_uses_fallback_without_tty(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no interactive TTY, the public select() routes to the numbered fallback."""

    class _NoTTY(io.StringIO):
        def isatty(self) -> bool:
            return False

    monkeypatch.setattr("sys.stdin", _NoTTY())
    monkeypatch.setattr("sys.stdout", _NoTTY())
    monkeypatch.setattr("builtins.input", lambda *a, **k: "2")
    assert select("pick", _choices(), active_value="all", console=_console()) == "research"
