"""Tests for the optional Docling adapter (Dimensions / Phase 6).

Docling is an optional dependency; the adapter must fail open. These tests verify the
availability probe and the not-installed fallback path without requiring docling to be present.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from core.docling_reader import (
    DoclingNotInstalledError,
    docling_available,
    read_with_docling,
)

_DOCLING_INSTALLED = importlib.util.find_spec("docling") is not None


def test_docling_available_matches_import_spec() -> None:
    assert docling_available() is _DOCLING_INSTALLED


def test_read_with_docling_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_with_docling(tmp_path / "missing.pdf")


@pytest.mark.skipif(
    _DOCLING_INSTALLED, reason="docling is installed; the not-installed path does not apply"
)
def test_read_with_docling_not_installed_raises(tmp_path: Path) -> None:
    dummy = tmp_path / "x.pdf"
    dummy.write_bytes(b"%PDF-1.4 dummy")
    with pytest.raises(DoclingNotInstalledError):
        read_with_docling(dummy)
