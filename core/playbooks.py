"""Playbook loader (Phase 3): the three quality rulebooks injected into synthesis.

The playbooks (``research``/``analysis``/``output``) live in ``playbooks/*.md`` and are
written verbatim from SPEC §13. They are injected into the synthesis system prompt so the
agent reasons with the same source-quality, framework, and output-excellence rules the SPEC
defines (SPEC §4.2 reasoning layer / §5.3 step 7).

Justified addition to the SPEC §7 tree (like ``core/config.py``): the SPEC names the playbook
*files* but not a loader module. This module only reads them — no content decisions (RULE 14).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel

# The playbooks directory is fixed by SPEC §7 and resolved relative to the project root so it
# is independent of the current working directory.
_PLAYBOOKS_DIR = Path(__file__).resolve().parent.parent / "playbooks"

_RESEARCH_FILE = "research_playbook.md"
_ANALYSIS_FILE = "analysis_playbook.md"
_OUTPUT_FILE = "output_playbook.md"


class PlaybooksError(Exception):
    """A required playbook file is missing or empty (fail fast, SPEC REQ-5)."""


class Playbooks(BaseModel):
    """The three synthesis rulebooks, loaded as raw markdown text (SPEC §13)."""

    research: str
    analysis: str
    output: str


def _read_playbook(directory: Path, filename: str) -> str:
    """Read one playbook file as UTF-8 text, failing fast if missing or empty."""
    path = directory / filename
    if not path.is_file():
        raise PlaybooksError(
            f"Playbook not found: {path}\n"
            "Fix: ensure the three playbooks exist in the 'playbooks/' directory "
            "(research_playbook.md, analysis_playbook.md, output_playbook.md)."
        )
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise PlaybooksError(f"Playbook is empty: {path}")
    return text


@lru_cache(maxsize=4)
def _load_cached(directory_str: str) -> Playbooks:
    """Load and cache the playbooks for a given directory (keyed by its string path)."""
    directory = Path(directory_str)
    return Playbooks(
        research=_read_playbook(directory, _RESEARCH_FILE),
        analysis=_read_playbook(directory, _ANALYSIS_FILE),
        output=_read_playbook(directory, _OUTPUT_FILE),
    )


def load_playbooks(playbooks_dir: Path | None = None) -> Playbooks:
    """Load the three playbooks (cached) from ``playbooks_dir`` (default: project ``playbooks/``).

    Args:
        playbooks_dir: Override directory (used in tests). Defaults to the SPEC §7 location.

    Returns:
        A :class:`Playbooks` with the raw markdown of each rulebook.

    Raises:
        PlaybooksError: If any playbook file is missing or empty.
    """
    directory = (playbooks_dir or _PLAYBOOKS_DIR).resolve()
    return _load_cached(str(directory))
