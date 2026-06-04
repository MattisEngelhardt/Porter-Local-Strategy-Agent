"""Tests for curated cover-imagery selection (core/imagery.py)."""

from __future__ import annotations

from pathlib import Path

from core import imagery


def _make(dir_path: Path, name: str) -> Path:
    path = dir_path / name
    path.write_bytes(b"\x89PNG\r\n\x1a\n")  # a token PNG header is enough for selection
    return path


def test_list_images_excludes_screenshots_and_subdirs(tmp_path: Path) -> None:
    """Screenshots and non-image files are filtered; only top-level brand images are eligible."""
    _make(tmp_path, "NEURA_4NE1.png")
    _make(tmp_path, "Screenshot 2026-06-04 122002.png")
    (tmp_path / "README.md").write_text("notes")
    reference = tmp_path / "reference"
    reference.mkdir()
    _make(reference, "design_ref.png")  # design references live here, never selected

    images = imagery.list_images(tmp_path)
    names = [p.name for p in images]
    assert names == ["NEURA_4NE1.png"]


def test_cover_image_picks_a_brand_image_and_is_deterministic(tmp_path: Path) -> None:
    """A real brand image is chosen (never a screenshot), stably for the same seed."""
    _make(tmp_path, "NEURA_Quadruped.png")
    _make(tmp_path, "Screenshot 2026-06-04.png")

    first = imagery.cover_image(tmp_path, seed="Threat assessment")
    assert first is not None and "Screenshot" not in first.name
    assert first == imagery.cover_image(tmp_path, seed="Threat assessment")


def test_cover_image_none_when_empty(tmp_path: Path) -> None:
    """An empty/absent library returns None so the caller falls back to the gradient cover."""
    assert imagery.cover_image(tmp_path / "missing") is None
    assert imagery.cover_image(tmp_path) is None
