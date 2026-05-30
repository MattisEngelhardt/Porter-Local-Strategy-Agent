"""Tests for the Phase 2 PDF/image reader (core/pdf_reader.py).

The backend seams (pdfplumber, render, OCR, vision) are monkeypatched so the
extraction cascade is verified without the real Tesseract binary or a vision model.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

import core.pdf_reader as pdf_reader
from core.pdf_reader import PdfReadError, read_pdf

_LONG = "This is a sufficiently long block of extracted text to clear the threshold."


def _touch(path: Path) -> Path:
    """Create an empty file (content irrelevant — extraction seams are stubbed)."""
    path.write_bytes(b"%PDF-1.4 stub")
    return path


# ------------------------------------------------------------- cascade routing
def test_text_pdf_uses_pdfplumber(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A PDF with real text is read by pdfplumber (no OCR/vision)."""
    pdf = _touch(tmp_path / "report.pdf")
    monkeypatch.setattr(pdf_reader, "_extract_text_pdfplumber", lambda p: (_LONG, 3))

    doc = read_pdf(pdf)
    assert doc.extraction_method == "pdfplumber"
    assert doc.doc_type == "pdf"
    assert doc.page_count == 3
    assert _LONG in doc.text


def test_scanned_pdf_falls_back_to_ocr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When pdfplumber yields nothing, OCR provides the text."""
    pdf = _touch(tmp_path / "scan.pdf")
    monkeypatch.setattr(pdf_reader, "_extract_text_pdfplumber", lambda p: ("", 2))
    monkeypatch.setattr(pdf_reader, "_render_pdf_pages", lambda p: ["page1", "page2"])
    monkeypatch.setattr(pdf_reader, "_ocr_pages", lambda pages: _LONG)

    doc = read_pdf(pdf)
    assert doc.extraction_method == "ocr"
    assert doc.page_count == 2


def test_image_pdf_falls_back_to_vision(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When pdfplumber AND OCR yield nothing, the vision model is used."""
    pdf = _touch(tmp_path / "image_only.pdf")
    monkeypatch.setattr(pdf_reader, "_extract_text_pdfplumber", lambda p: ("", 1))
    monkeypatch.setattr(pdf_reader, "_render_pdf_pages", lambda p: ["page1"])
    monkeypatch.setattr(pdf_reader, "_ocr_pages", lambda pages: "")
    monkeypatch.setattr(pdf_reader, "_vision_pages", lambda pages, llm: "vision transcribed text")

    doc = read_pdf(pdf, llm=object())  # type: ignore[arg-type]
    assert doc.extraction_method == "vision"
    assert "vision transcribed text" in doc.text


def test_no_text_without_llm_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No text + no LLM for vision → PdfReadError naming the missing fallback."""
    pdf = _touch(tmp_path / "blank.pdf")
    monkeypatch.setattr(pdf_reader, "_extract_text_pdfplumber", lambda p: ("", 1))
    monkeypatch.setattr(pdf_reader, "_render_pdf_pages", lambda p: ["page1"])
    monkeypatch.setattr(pdf_reader, "_ocr_pages", lambda pages: "")

    with pytest.raises(PdfReadError) as excinfo:
        read_pdf(pdf, llm=None)
    assert "vision" in str(excinfo.value).lower()


def test_image_file_uses_ocr(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A standalone image is OCR'd into DocContent of type 'image'."""
    img = tmp_path / "chart.png"
    img.write_bytes(b"\x89PNG stub")
    monkeypatch.setattr(pdf_reader, "_open_image", lambda p: "PILIMAGE")
    monkeypatch.setattr(pdf_reader, "_ocr_pages", lambda pages: _LONG)

    doc = read_pdf(img)
    assert doc.doc_type == "image"
    assert doc.extraction_method == "ocr"
    assert doc.page_count == 1


# ------------------------------------------------------------------ edge cases
def test_missing_file_fails_fast() -> None:
    """A non-existent path raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        read_pdf("nope/missing.pdf")


def test_unsupported_type_raises(tmp_path: Path) -> None:
    """An unsupported extension raises PdfReadError."""
    txt = tmp_path / "notes.txt"
    txt.write_text("hi", encoding="utf-8")
    with pytest.raises(PdfReadError):
        read_pdf(txt)


# --------------------------------------------------------------- vision seam
class _FakeImage:
    """Minimal PIL-image stand-in: writes deterministic bytes on .save()."""

    def save(self, buffer: Any, format: str) -> None:  # noqa: A002 - mirrors PIL API
        buffer.write(b"PNGBYTES")


class _FakeLLM:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def generate(self, prompt: str, images: list[str] | None = None, **kwargs: Any) -> str:
        self.calls.append({"prompt": prompt, "images": images})
        return "transcribed"


def test_vision_pages_encodes_images_and_calls_llm() -> None:
    """_vision_pages base64-encodes each page and passes it to llm.generate(images=...)."""
    import base64

    llm = _FakeLLM()
    text = pdf_reader._vision_pages([_FakeImage()], llm)  # type: ignore[arg-type]
    assert text == "transcribed"
    assert llm.calls[0]["images"] == [base64.b64encode(b"PNGBYTES").decode("ascii")]
