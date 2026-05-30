"""Tests for brain.md injection (core/memory.py)."""

from __future__ import annotations

from pathlib import Path

from core.config import MemoryConfig
from core.memory import load_brain


def _config(path: Path, max_lines: int = 300) -> MemoryConfig:
    return MemoryConfig(brain_path=str(path), max_brain_lines=max_lines)


def test_load_brain_strips_scaffolding_keeps_content(tmp_path: Path) -> None:
    """Single-# comments/title are dropped; ## headings and real content are kept."""
    brain = tmp_path / "brain.md"
    brain.write_text(
        "# AGENT BRAIN\n"
        "# ⚠️ GITIGNORED — comment line\n"
        "\n"
        "## NEURA — STRATEGIC CONTEXT\n"
        "# Only facts that change framing.\n"
        "Neura builds cognitive humanoid robots.\n"
        "**Differentiation:** cognitive vs scripted.\n",
        encoding="utf-8",
    )
    result = load_brain(_config(brain))
    assert "## NEURA — STRATEGIC CONTEXT" in result
    assert "Neura builds cognitive humanoid robots." in result
    assert "**Differentiation:** cognitive vs scripted." in result
    # scaffolding removed
    assert "AGENT BRAIN" not in result
    assert "GITIGNORED" not in result
    assert "Only facts that change framing" not in result


def test_load_brain_missing_file_returns_empty(tmp_path: Path) -> None:
    """A missing brain.md yields '' — the agent runs without persistent context."""
    assert load_brain(_config(tmp_path / "nope.md")) == ""


def test_load_brain_comment_only_file_returns_empty(tmp_path: Path) -> None:
    """A file of only scaffolding comments injects nothing."""
    brain = tmp_path / "brain.md"
    brain.write_text("# only\n# comments\n# here\n", encoding="utf-8")
    assert load_brain(_config(brain)) == ""


def test_load_brain_respects_max_lines(tmp_path: Path) -> None:
    """The cap limits how many (kept) lines are injected."""
    brain = tmp_path / "brain.md"
    brain.write_text("\n".join(f"content line {i}" for i in range(50)), encoding="utf-8")
    result = load_brain(_config(brain, max_lines=10))
    assert result.count("\n") == 9  # 10 lines → 9 newlines
    assert "content line 0" in result
    assert "content line 10" not in result
