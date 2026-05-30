"""Excel reader (Phase 2): read user-provided .xlsx files as research input.

Input mode only (SPEC §9 N-5): pandas reads the workbook into a structured text
summary for later synthesis. Creating .xlsx *outputs* is ``excel_builder.py``
(Phase 4) — deliberately a separate module so the two modes never conflate.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from models.research import DocContent

# How many leading rows per sheet to include in the text preview.
_MAX_PREVIEW_ROWS = 10


class ExcelReadError(Exception):
    """An .xlsx file exists but could not be parsed (fail fast, SPEC REQ-5)."""


def read_excel(path: Path | str) -> DocContent:
    """Read every sheet of an .xlsx into a structured text summary.

    Args:
        path: Path to the .xlsx file.

    Returns:
        :class:`DocContent` with a readable summary per sheet (name, shape,
        columns, and a CSV preview of the first rows).

    Raises:
        FileNotFoundError: If the file does not exist.
        ExcelReadError: If the workbook cannot be parsed.
    """
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(
            f"Excel file not found: {file_path.resolve()}\n"
            "Fix: check the path; it must point to an existing .xlsx file."
        )

    try:
        sheets = pd.read_excel(file_path, sheet_name=None)
    except Exception as exc:  # pandas/openpyxl raise a variety of error types
        raise ExcelReadError(
            f"Could not read Excel file {file_path}: {exc}\n"
            "Fix: ensure it is a valid .xlsx and is not open in another program."
        ) from exc

    blocks: list[str] = []
    for name, frame in sheets.items():
        rows, cols = frame.shape
        columns = ", ".join(str(col) for col in frame.columns)
        preview = frame.head(_MAX_PREVIEW_ROWS).to_csv(index=False).strip()
        blocks.append(
            f"## Sheet: {name} ({rows} rows x {cols} cols)\n"
            f"Columns: {columns}\n"
            f"Preview (first {_MAX_PREVIEW_ROWS} rows, CSV):\n{preview}"
        )

    return DocContent(
        source_path=file_path,
        doc_type="xlsx",
        text="\n\n".join(blocks).strip(),
        page_count=len(sheets),
        extraction_method="pandas",
    )
