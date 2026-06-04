"""Curated Neura brand imagery for the deck cover (Editorial v4.0).

Deterministic, fail-open selection from a local image library (``output.imagery_dir`` — robots, the
logo, product shots; supplied by the user). The cover archetype lays one full-bleed under a dark
scrim with the title knocked out over it (the warm, photographic 'Cofounder' feel). When the
directory is empty or missing, the cover degrades to the luminous gradient — no network, no image
generation, no hallucination (REQ-5).
"""

from __future__ import annotations

from pathlib import Path

_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
_COVER_HINTS = ("cover", "hero", "title")
# Name fragments that mark a non-brand image (UI/design reference screenshots) — never a cover.
# Design references live in ``assets/imagery/reference/`` (a subdir already skipped by iterdir);
# this is a belt-and-suspenders guard so a stray "Screenshot ….png" is never chosen.
_EXCLUDE_SUBSTRINGS = ("screenshot", "screen shot", "untitled")


def list_images(imagery_dir: str | Path) -> list[Path]:
    """Brand-approved cover images in ``imagery_dir`` (sorted, stable); empty list if absent.

    Only top-level image files are eligible (so ``reference/`` design screenshots are excluded) and
    screenshot-named files are filtered out — selection is *meaningful*, never a random UI grab.
    """
    directory = Path(imagery_dir)
    if not directory.is_dir():
        return []
    return sorted(
        p
        for p in directory.iterdir()
        if p.is_file()
        and p.suffix.lower() in _IMAGE_EXTS
        and not any(token in p.stem.lower() for token in _EXCLUDE_SUBSTRINGS)
    )


def cover_image(imagery_dir: str | Path, *, seed: str = "") -> Path | None:
    """Pick a stable cover image (a ``cover``/``hero``/``title`` file wins, else a seeded pick).

    Returns ``None`` when the library is empty so the caller falls back to the gradient cover.
    """
    images = list_images(imagery_dir)
    if not images:
        return None
    for image in images:
        if any(hint in image.stem.lower() for hint in _COVER_HINTS):
            return image
    index = (sum(ord(c) for c in seed) % len(images)) if seed else 0
    return images[index]
