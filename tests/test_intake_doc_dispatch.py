"""Tests for the document-reader dispatch in :func:`core.intake.read_document`.

Verifies that .docx and .pptx are routed to the new readers (Dimensions / Phase 6) while
.xlsx and .pdf keep their existing routing. Readers are monkeypatched so the dispatch is
tested in isolation (no real files needed).
"""

from __future__ import annotations

from pathlib import Path

import core.intake as intake
from models.research import DocContent


def _stub(doc_type: str) -> DocContent:
    return DocContent(source_path=Path("stub"), doc_type=doc_type, text="stub")


def test_read_document_routes_docx(monkeypatch) -> None:
    monkeypatch.setattr(intake, "read_docx", lambda path: _stub("docx"))
    assert intake.read_document(Path("candidate.docx")).doc_type == "docx"


def test_read_document_routes_pptx(monkeypatch) -> None:
    monkeypatch.setattr(intake, "read_pptx", lambda path: _stub("pptx"))
    assert intake.read_document(Path("board_deck.pptx")).doc_type == "pptx"


def test_read_document_routes_excel_and_pdf(monkeypatch) -> None:
    monkeypatch.setattr(intake, "read_excel", lambda path: _stub("xlsx"))
    monkeypatch.setattr(intake, "read_pdf", lambda path, llm=None: _stub("pdf"))
    assert intake.read_document(Path("model.xlsx")).doc_type == "xlsx"
    assert intake.read_document(Path("report.pdf")).doc_type == "pdf"


def test_supported_suffixes_include_docx_and_pptx() -> None:
    assert ".docx" in intake._SUPPORTED_SUFFIXES
    assert ".pptx" in intake._SUPPORTED_SUFFIXES
