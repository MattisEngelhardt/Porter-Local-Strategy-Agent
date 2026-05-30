"""Memory layer (Phase 3: brain.md injection — read only).

``brain.md`` (SPEC §4.5) is a gitignored, local-only file holding the persistent Neura context
and the user's output preferences. The agent injects it into every synthesis call so it never
re-explains Neura's products, differentiation, or the user's formatting rules.

Phase 3 scope = **read only**. The ChromaDB vector store and the post-run "propose additions"
flow are Phase 5 (SPEC §15) and deliberately not implemented here.

The brain.md file mixes real context with human-facing scaffolding: its own convention uses
single ``#`` lines for comments/instructions and ``##``/``###`` for real section headings
(see the file's cardinal rule). ``load_brain`` strips the single-``#`` scaffolding so only
output-changing content reaches the model.
"""

from __future__ import annotations

import re
from pathlib import Path

from core.config import MemoryConfig

# A scaffolding line: starts with a single '#' (comment or H1 title) but NOT '##'+ (which are
# real markdown section headings we keep). Matches the brain.md authoring convention.
_SCAFFOLDING_LINE = re.compile(r"^#(?!#)")


def _is_scaffolding(line: str) -> bool:
    """True if a line is a single-``#`` comment/title (human scaffolding, not content)."""
    return bool(_SCAFFOLDING_LINE.match(line.lstrip()))


def load_brain(config: MemoryConfig) -> str:
    """Load brain.md as injectable context, stripped of human-facing scaffolding.

    Reads ``config.brain_path`` (UTF-8), drops single-``#`` comment/title lines, and caps the
    result at ``config.max_brain_lines`` lines. A missing or content-empty file yields ``""``
    (the agent runs fine without a brain — it just loses persistent context).

    Args:
        config: The memory configuration (brain path + max line cap).

    Returns:
        The cleaned brain content, or ``""`` if there is nothing to inject.
    """
    path = Path(config.brain_path)
    if not path.is_file():
        return ""

    raw = path.read_text(encoding="utf-8")
    kept = [line for line in raw.splitlines() if not _is_scaffolding(line)]
    capped = kept[: max(0, config.max_brain_lines)]
    return "\n".join(capped).strip()
