"""PDF / image reader (Phase 2): extract text from user documents.

Extraction cascade (SPEC §4.4), stopping at the first method that yields real text:
  1. pdfplumber — native text PDFs.
  2. pytesseract OCR — scanned PDFs / images (renders pages, then OCRs).
  3. gemma4 vision via :class:`LocalLLMClient` — image-only docs where OCR fails.

Extraction only — no synthesis (that is Phase 3). All LLM access goes through
LocalLLMClient (RULE 6). Each backend step is a small seam so tests can stub it
without the real Tesseract binary or a vision model.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path
from typing import TYPE_CHECKING, Any

from models.research import DocContent

if TYPE_CHECKING:  # pragma: no cover - typing only
    from llm.local_llm_client import LocalLLMClient

# Below this many characters, treat extraction as "no real text" and fall back.
_MIN_TEXT_CHARS = 50
_IMAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"})
_VISION_PROMPT = (
    "Transcribe all text visible in this image. Output only the transcribed text, "
    "preserving structure (headings, bullet points, tables) as plain text."
)


class PdfReadError(Exception):
    """A document could not be read by any available method (fail fast, SPEC REQ-5)."""


class TesseractNotInstalledError(PdfReadError):
    """The Tesseract OCR binary is required for this document but is not installed."""


# --------------------------------------------------------------- backend seams
def _extract_text_pdfplumber(path: Path) -> tuple[str, int]:
    """Return (joined page text, page count) from a text PDF via pdfplumber."""
    import pdfplumber

    parts: list[str] = []
    with pdfplumber.open(path) as pdf:
        page_count = len(pdf.pages)
        for page in pdf.pages:
            parts.append(page.extract_text() or "")
    return "\n".join(parts).strip(), page_count


def _render_pdf_pages(path: Path, resolution: int = 200) -> list[Any]:
    """Render each PDF page to a PIL image (for OCR / vision)."""
    import pdfplumber

    images: list[Any] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            images.append(page.to_image(resolution=resolution).original)
    return images


def _open_image(path: Path) -> Any:
    """Open a standalone image file as a PIL image."""
    from PIL import Image

    return Image.open(path)


def _ocr_pages(pages: list[Any]) -> str:
    """OCR a list of PIL images into joined text. Raises if Tesseract is absent."""
    import pytesseract

    parts: list[str] = []
    try:
        for image in pages:
            parts.append(pytesseract.image_to_string(image))
    except pytesseract.TesseractNotFoundError as exc:
        raise TesseractNotInstalledError(
            "Tesseract OCR is required to read this scanned document but is not installed.\n"
            "Fix (Windows): install from https://github.com/UB-Mannheim/tesseract/wiki, "
            "then ensure 'tesseract.exe' is on your PATH."
        ) from exc
    return "\n".join(parts).strip()


def _vision_pages(pages: list[Any], llm: LocalLLMClient) -> str:
    """Transcribe a list of PIL images via the vision-capable LLM (Ollama)."""
    parts: list[str] = []
    for image in pages:
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        parts.append(llm.generate(_VISION_PROMPT, images=[encoded], use_thinking=False))
    return "\n".join(parts).strip()


# --------------------------------------------------------------------- public API
def read_pdf(path: Path | str, llm: LocalLLMClient | None = None) -> DocContent:
    """Read a PDF or image into :class:`DocContent` via the extraction cascade.

    Args:
        path: Path to a ``.pdf`` or image file.
        llm: Optional vision-capable client for the final image fallback. Without
            it, image-only documents that also fail OCR raise :class:`PdfReadError`.

    Returns:
        :class:`DocContent` with ``extraction_method`` recording which step succeeded.

    Raises:
        FileNotFoundError: If the path does not exist.
        TesseractNotInstalledError: If OCR is needed but Tesseract is missing.
        PdfReadError: If no method yields text, or the type is unsupported.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(
            f"Document not found: {file_path.resolve()}\n"
            "Fix: check the path; it must point to an existing .pdf or image file."
        )

    suffix = file_path.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        return _read_image_file(file_path, llm)
    if suffix == ".pdf":
        return _read_pdf_file(file_path, llm)
    raise PdfReadError(
        f"Unsupported document type '{suffix}' for {file_path.name}. "
        "Supported: .pdf and image files (.png/.jpg/.jpeg/.bmp/.tiff/.webp)."
    )


def _read_pdf_file(path: Path, llm: LocalLLMClient | None) -> DocContent:
    """Apply the cascade to a PDF: pdfplumber → OCR → vision."""
    text, page_count = _extract_text_pdfplumber(path)
    if len(text) >= _MIN_TEXT_CHARS:
        return DocContent(
            source_path=path,
            doc_type="pdf",
            text=text,
            page_count=page_count,
            extraction_method="pdfplumber",
        )

    pages = _render_pdf_pages(path)
    ocr_text = _ocr_pages(pages)
    if len(ocr_text) >= _MIN_TEXT_CHARS:
        return DocContent(
            source_path=path,
            doc_type="pdf",
            text=ocr_text,
            page_count=page_count or len(pages),
            extraction_method="ocr",
        )

    if llm is not None:
        vision_text = _vision_pages(pages, llm)
        if vision_text.strip():
            return DocContent(
                source_path=path,
                doc_type="pdf",
                text=vision_text,
                page_count=page_count or len(pages),
                extraction_method="vision",
            )

    raise PdfReadError(_no_text_message(path, llm))


def _read_image_file(path: Path, llm: LocalLLMClient | None) -> DocContent:
    """Apply OCR → vision to a standalone image file."""
    image = _open_image(path)
    ocr_text = _ocr_pages([image])
    if len(ocr_text) >= _MIN_TEXT_CHARS:
        return DocContent(
            source_path=path,
            doc_type="image",
            text=ocr_text,
            page_count=1,
            extraction_method="ocr",
        )

    if llm is not None:
        vision_text = _vision_pages([image], llm)
        if vision_text.strip():
            return DocContent(
                source_path=path,
                doc_type="image",
                text=vision_text,
                page_count=1,
                extraction_method="vision",
            )

    raise PdfReadError(_no_text_message(path, llm))


def _no_text_message(path: Path, llm: LocalLLMClient | None) -> str:
    """Build the fail-fast message when no extraction method produced text."""
    tail = (
        " and no LLM was provided for the vision fallback"
        if llm is None
        else " (including the vision model)"
    )
    return (
        f"No extractable text found in {path.name}: pdfplumber and OCR returned nothing"
        f"{tail}. Fix: install Tesseract OCR for scanned PDFs, or pass a vision-capable "
        "model for image-only documents."
    )
