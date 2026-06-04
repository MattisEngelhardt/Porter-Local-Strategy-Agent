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


def list_images(imagery_dir: str | Path) -> list[Path]:
    """All usable image files in ``imagery_dir`` (sorted, stable); empty list if absent."""
    directory = Path(imagery_dir)
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.iterdir() if p.is_file() and p.suffix.lower() in _IMAGE_EXTS)


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
