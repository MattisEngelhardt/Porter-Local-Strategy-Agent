"""Tests for the playbook loader (core/playbooks.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.playbooks import Playbooks, PlaybooksError, load_playbooks


def test_load_playbooks_reads_all_three() -> None:
    """The real project playbooks load and carry their SPEC §13 signature content."""
    playbooks = load_playbooks()
    assert isinstance(playbooks, Playbooks)
    # research_playbook: source hierarchy
    assert "Tier 1" in playbooks.research
    assert "Job Posting Intelligence" in playbooks.research
    # analysis_playbook: frameworks + the Neura Lens
    assert "Framework Selection by Task Type" in playbooks.analysis
    assert "The Neura Lens" in playbooks.analysis
    # output_playbook: the 'so what' headline rule
    assert "so what" in playbooks.output
    assert "Excel Rules" in playbooks.output


def test_load_playbooks_is_cached() -> None:
    """Repeated loads of the same directory return the cached instance."""
    assert load_playbooks() is load_playbooks()


def test_missing_playbook_fails_fast(tmp_path: Path) -> None:
    """A directory without the playbook files raises PlaybooksError with a fix."""
    with pytest.raises(PlaybooksError) as excinfo:
        load_playbooks(tmp_path)
    assert "Fix:" in str(excinfo.value)


def test_empty_playbook_fails_fast(tmp_path: Path) -> None:
    """An empty playbook file is rejected (must have content to inject)."""
    for name in ("research_playbook.md", "analysis_playbook.md", "output_playbook.md"):
        (tmp_path / name).write_text("   \n", encoding="utf-8")
    with pytest.raises(PlaybooksError):
        load_playbooks(tmp_path)
