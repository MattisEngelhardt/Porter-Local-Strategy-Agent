"""Tests for REPL file-path detection + document routing (core/intake.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

import core.intake as intake
from core.intake import detect_file_path, read_document
from models.research import DocContent


def _doc(path: Path, doc_type: str) -> DocContent:
    return DocContent(source_path=path, doc_type=doc_type, text="x", extraction_method="stub")


def test_detect_file_path_recognizes_supported(tmp_path: Path) -> None:
    """A bare (or quoted) path to a supported file is detected."""
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"stub")
    assert detect_file_path(str(pdf)) == pdf
    assert detect_file_path(f'"{pdf}"') == pdf  # quoted (Windows paths with spaces)


def test_detect_file_path_ignores_non_paths(tmp_path: Path) -> None:
    """Questions, missing files, and unsupported types are not treated as docs."""
    assert detect_file_path("What does Neura Robotics build?") is None
    assert detect_file_path(str(tmp_path / "missing.pdf")) is None
    txt = tmp_path / "notes.txt"
    txt.write_text("hi", encoding="utf-8")
    assert detect_file_path(str(txt)) is None


def test_read_document_routes_by_suffix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """.xlsx routes to the Excel reader; .pdf routes to the PDF reader."""
    monkeypatch.setattr(intake, "read_excel", lambda p: _doc(p, "xlsx"))
    monkeypatch.setattr(intake, "read_pdf", lambda p, llm=None: _doc(p, "pdf"))

    xlsx = tmp_path / "data.xlsx"
    xlsx.write_bytes(b"stub")
    pdf = tmp_path / "data.pdf"
    pdf.write_bytes(b"stub")

    assert read_document(xlsx).doc_type == "xlsx"
    assert read_document(pdf, llm=None).doc_type == "pdf"
