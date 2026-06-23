"""Arrow-key selection menus for the REPL (Claude-Code-style), with a typed-number fallback.

One tiny, testable entry point (:func:`select`) wraps ``questionary.select`` so the REPL can
offer ``up/down + Enter`` menus for ``/model`` and ``/role``. When the terminal cannot enter raw
mode (no TTY — tests, pipes, some embedded terminals) or questionary raises, it falls back to a
plain numbered prompt so the REPL never breaks. The active entry is pre-selected so the current
choice is obvious.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from rich.console import Console


@dataclass(frozen=True)
class Choice:
    """One menu entry: a stable ``value`` plus the ``title`` shown (and an optional ``hint``)."""

    value: str
    title: str
    hint: str = ""


def _label(choice: Choice) -> str:
    """Render a choice as ``title — hint`` (hint omitted when empty)."""
    return f"{choice.title}  —  {choice.hint}" if choice.hint else choice.title


def _interactive_select(
    message: str, choices: list[Choice], active_value: str | None
) -> str | None:
    """Arrow-key menu via questionary; returns the chosen value or ``None`` if cancelled."""
    import questionary

    q_choices = [questionary.Choice(title=_label(c), value=c.value) for c in choices]
    answer = questionary.select(
        message,
        choices=q_choices,
        default=active_value,
        qmark="›",
        instruction="(↑/↓, Enter)",
    ).ask()
    return answer if isinstance(answer, str) else None


def _fallback_select(
    message: str, choices: list[Choice], active_value: str | None, console: Console
) -> str | None:
    """Numbered text prompt used when no interactive TTY is available."""
    console.print(message)
    for index, choice in enumerate(choices, start=1):
        marker = "[bold cyan]●[/bold cyan]" if choice.value == active_value else " "
        console.print(f"  {marker} [bold]{index}[/bold]) {_label(choice)}")
    try:
        raw = input("Auswahl [Zahl, leer = abbrechen]: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not raw.isdigit():
        return None
    pick = int(raw)
    if 1 <= pick <= len(choices):
        return choices[pick - 1].value
    return None


def select(
    message: str,
    choices: list[Choice],
    *,
    active_value: str | None = None,
    console: Console | None = None,
) -> str | None:
    """Show a single-choice menu and return the chosen ``value`` (or ``None`` if cancelled).

    Uses an arrow-key menu when stdin/stdout are an interactive TTY; otherwise (and on any
    questionary failure) falls back to a numbered text prompt. ``active_value`` is pre-selected.
    """
    if not choices:
        return None
    console = console or Console()
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if interactive:
        try:
            return _interactive_select(message, choices, active_value)
        except Exception:  # noqa: BLE001 — any terminal/raw-mode failure must not break the REPL
            pass
    return _fallback_select(message, choices, active_value, console)
