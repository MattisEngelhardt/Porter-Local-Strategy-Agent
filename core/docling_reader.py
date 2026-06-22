"""Optional high-fidelity document reader via Docling (Dimensions / Phase 6).

**Docling** (IBM, MIT-licensed, fully local/offline, runs on CPU) gives the best open-source
structural fidelity — tables via TableFormer, multi-column layouts, formulas, and built-in OCR —
across PDF / DOCX / PPTX / XLSX / images, exporting to clean Markdown. It is the *preferred*
reader for the Analyst (CV screening) and Builder (finance reporting) dimensions, where exact
tables and word-for-word fidelity change the result.

It is an **optional** dependency and this adapter **fails open**: if ``docling`` is not installed
it raises :class:`DoclingNotInstalledError`, so callers fall back to the lightweight readers
(``core.pdf_reader`` / ``core.docx_reader`` / ``core.pptx_reader`` / ``core.excel_reader``)
with an exact fix hint. Install with ``pip install docling``. Nothing here imports ``docling`` at
module load — the heavy import happens only inside :func:`read_with_docling`.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from models.research import DocContent

# Map file suffix → the DocContent.doc_type label (matches the other readers' conventions).
_DOC_TYPE_BY_SUFFIX: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".xlsm": "xlsx",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".bmp": "image",
    ".tiff": "image",
    ".tif": "image",
    ".webp": "image",
}


class DoclingReadError(Exception):
    """Docling failed to convert a document (fail fast, SPEC REQ-5)."""


class DoclingNotInstalledError(DoclingReadError):
    """The optional ``docling`` package is not installed — callers should fall back."""


def docling_available() -> bool:
    """Return True if the optional ``docling`` package is importable (no heavy import)."""
    return importlib.util.find_spec("docling") is not None


def read_with_docling(path: Path | str) -> DocContent:
    """Read any supported document into :class:`DocContent` as Markdown via Docling.

    Preferred high-fidelity path for the Analyst/Builder dimensions. Callers that want graceful
    degradation should catch :class:`DoclingNotInstalledError` (and :class:`DoclingReadError`)
    and fall back to the lightweight readers.

    Args:
        path: Path to a supported document (PDF / DOCX / PPTX / XLSX / image).

    Returns:
        :class:`DocContent` with ``extraction_method="docling"`` and Markdown ``text``.

    Raises:
        FileNotFoundError: If the path does not exist.
        DoclingNotInstalledError: If ``docling`` is not installed (caller should fall back).
        DoclingReadError: If Docling fails to convert the document.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(
            f"Document not found: {file_path.resolve()}\n"
            "Fix: check the path; it must point to an existing document file."
        )

    try:
        from docling.document_converter import DocumentConverter
    except ImportError as exc:
        raise DoclingNotInstalledError(
            "The optional 'docling' package is not installed.\n"
            "Fix: pip install docling  (high-fidelity local reader for tables/multi-column/OCR; "
            "Porter falls back to the lightweight readers if you skip it)."
        ) from exc

    try:
        converter = DocumentConverter()
        result = converter.convert(str(file_path))
        markdown = result.document.export_to_markdown()
    except Exception as exc:  # Docling raises varied conversion errors
        raise DoclingReadError(
            f"Docling could not convert {file_path.name}: {exc}\n"
            "Fix: try the lightweight reader, or check the file is a valid, supported document."
        ) from exc

    doc_type = _DOC_TYPE_BY_SUFFIX.get(file_path.suffix.lower(), "document")
    return DocContent(
        source_path=file_path,
        doc_type=doc_type,
        text=markdown.strip(),
        page_count=None,
        extraction_method="docling",
    )
