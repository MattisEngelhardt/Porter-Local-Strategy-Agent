"""Tests for the Phase 2 Excel reader (core/excel_reader.py).

Builds a small real .xlsx with openpyxl in a tmp dir, then reads it back with
pandas — fully offline, no fixtures on disk.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from openpyxl import Workbook

from core.excel_reader import ExcelReadError, read_excel


def _make_workbook(path: Path) -> None:
    """Write a two-sheet workbook to ``path``."""
    wb = Workbook()
    targets = wb.active
    targets.title = "Targets"
    targets.append(["Company", "Funding_M"])
    targets.append(["Figure AI", 675])
    targets.append(["1X Technologies", 100])

    notes = wb.create_sheet("Notes")
    notes.append(["Field", "Value"])
    notes.append(["Source", "TechCrunch"])
    wb.save(path)


def test_read_excel_extracts_all_sheets(tmp_path: Path) -> None:
    """Both sheets, their columns, and cell values appear in the extracted text."""
    path = tmp_path / "pipeline.xlsx"
    _make_workbook(path)

    doc = read_excel(path)

    assert doc.doc_type == "xlsx"
    assert doc.extraction_method == "pandas"
    assert doc.page_count == 2
    assert "Sheet: Targets" in doc.text
    assert "Sheet: Notes" in doc.text
    assert "Company" in doc.text
    assert "Figure AI" in doc.text
    assert "TechCrunch" in doc.text


def test_read_excel_missing_file_fails_fast() -> None:
    """A missing path raises FileNotFoundError with a fix hint."""
    with pytest.raises(FileNotFoundError):
        read_excel("does/not/exist.xlsx")


def test_read_excel_invalid_file_raises(tmp_path: Path) -> None:
    """A non-xlsx file raises ExcelReadError (not a bare pandas traceback)."""
    bad = tmp_path / "not_really.xlsx"
    bad.write_text("this is not a spreadsheet", encoding="utf-8")
    with pytest.raises(ExcelReadError):
        read_excel(bad)
