"""Excel output builder (SPEC §7 ``excel_builder.py``, §12): the four .xlsx templates via openpyxl.

Creates professional, **formula-driven** workbooks (N-10): every derived value is a real Excel
formula (``SUMPRODUCT``/``RANK``/``NPV``/…), never a hardcoded intermediate, so changing a yellow
input cell recalculates everything downstream when the file is opened in Microsoft Excel. Color
coding (yellow=input, blue=formula, green=positive, red=risk, dark=header) comes from
``config.output.colors`` (RULE 4). Fully local — openpyxl writes .xlsx with zero network (N-4).

Templates (SPEC §12): E-1 Decision/Scoring Matrix (this task), E-2 Benchmark, E-3 Business Case
model, E-4 Tracker. Structured content is shaped by :mod:`core.content_shaper`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import ColorScaleRule, FormulaRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from core.config import AppConfig
from models.task import Language
from models.workbook import DecisionMatrixData


class ExcelBuildError(Exception):
    """An Excel workbook could not be built (fail fast with context)."""


def _slug(text: str) -> str:
    """Make a short, filesystem-safe slug from a title (shared with exporter naming)."""
    import re

    cleaned = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (cleaned or "workbook")[:50]


def _t(language: Language, de: str, en: str) -> str:
    """Pick the German or English string for the language."""
    return de if language == Language.DE else en


def _argb(hex_color: str) -> str:
    """Normalize a ``#rrggbb`` / ``rrggbb`` color to openpyxl 8-digit ARGB."""
    value = hex_color.lstrip("#").upper()
    return value if len(value) == 8 else "FF" + value


class _Style:
    """Reusable openpyxl fills/fonts derived from the configured Neura palette (config-driven)."""

    def __init__(self, config: AppConfig) -> None:
        """Build the fills/fonts once from ``config.output.colors``."""
        c = config.output.colors
        self.input_fill = PatternFill("solid", fgColor=_argb(c.excel_input_cell))
        self.formula_fill = PatternFill("solid", fgColor=_argb(c.excel_formula_cell))
        self.positive_fill = PatternFill("solid", fgColor=_argb(c.excel_positive))
        self.negative_fill = PatternFill("solid", fgColor=_argb(c.excel_negative))
        self.header_fill = PatternFill("solid", fgColor=_argb(c.excel_header))
        self.surface_fill = PatternFill("solid", fgColor=_argb(c.light_surface))
        self.header_font = Font(name="Arial", bold=True, color=_argb(c.white), size=11)
        self.title_font = Font(name="Arial", bold=True, size=14, color=_argb(c.text_dark))
        self.bold = Font(name="Arial", bold=True, color=_argb(c.text_dark))
        self.normal = Font(name="Arial", color=_argb(c.text_dark))
        self.muted = Font(name="Arial", italic=True, size=9, color=_argb(c.charcoal))
        # 3-colour scale (low→high) for weighted scores, all from config.
        self.scale_low = _argb(c.excel_negative)
        self.scale_mid = _argb(c.excel_input_cell)
        self.scale_high = _argb(c.excel_positive)


_LEFT = Alignment(horizontal="left", vertical="center", wrap_text=True)
_CENTER = Alignment(horizontal="center", vertical="center", wrap_text=True)


def _title_block(ws: Worksheet, style: _Style, title: str, instructions: str) -> None:
    """Write the universal A1 title / A2 last-updated / A3 instructions block (output_playbook)."""
    ws["A1"] = title
    ws["A1"].font = style.title_font
    ws["A2"] = f"{date.today().isoformat()}"
    ws["A2"].font = style.muted
    ws["A3"] = instructions
    ws["A3"].font = style.muted


# --------------------------------------------------------------- E-1 Decision / Scoring Matrix
_HEADER_ROW = 5
_WEIGHTS_ROW = 6
_FIRST_ENTITY_ROW = 7


def _normalized_weights(data: DecisionMatrixData) -> list[float]:
    """Return criterion weights normalized to sum to 1 (equal weights if none/zero)."""
    weights = [max(0.0, c.weight) for c in data.criteria]
    total = sum(weights)
    n = len(weights)
    if total <= 0 and n:
        return [1.0 / n] * n
    return [w / total for w in weights] if total else []


def _matrix_sheet(ws: Worksheet, style: _Style, data: DecisionMatrixData) -> None:
    """Write the Summary_Matrix tab: weights row (yellow) + SUMPRODUCT scores + RANK."""
    language = data.language
    n = len(data.criteria)
    last_crit_col = get_column_letter(1 + n)
    ws_col = 2 + n
    rank_col = 3 + n
    ws_letter = get_column_letter(ws_col)
    rank_letter = get_column_letter(rank_col)
    last_entity_row = _FIRST_ENTITY_ROW + len(data.entities) - 1

    _title_block(
        ws,
        style,
        data.title,
        _t(
            language,
            f"Gelbe Zellen sind Eingaben: Gewichte (Zeile {_WEIGHTS_ROW}) und Scores 1–5 "
            "anpassen — Gewichteter Score und Rang rechnen automatisch neu.",
            f"Yellow cells are inputs: change the weights (row {_WEIGHTS_ROW}) and the 1–5 "
            "scores — the Weighted Score and Rank recalculate automatically.",
        ),
    )

    # Header row.
    headers = [_t(language, "Unternehmen / Option", "Company / Option")]
    headers += [c.name for c in data.criteria]
    headers += [
        _t(language, "Gewichteter Score", "Weighted Score"),
        _t(language, "Rang", "Rank"),
    ]
    for col, text in enumerate(headers, start=1):
        cell = ws.cell(row=_HEADER_ROW, column=col, value=text)
        cell.fill = style.header_fill
        cell.font = style.header_font
        cell.alignment = _CENTER

    # Weights row (yellow inputs) + auto-summing weight total.
    ws.cell(
        row=_WEIGHTS_ROW, column=1, value=_t(language, "Gewichtung", "Weight")
    ).font = style.bold
    for idx, weight in enumerate(_normalized_weights(data)):
        cell = ws.cell(row=_WEIGHTS_ROW, column=2 + idx, value=round(weight, 4))
        cell.fill = style.input_fill
        cell.number_format = "0%"
        cell.alignment = _CENTER
    total_cell = ws.cell(
        row=_WEIGHTS_ROW,
        column=ws_col,
        value=f"=SUM(B{_WEIGHTS_ROW}:{last_crit_col}{_WEIGHTS_ROW})",
    )
    total_cell.number_format = "0%"
    total_cell.font = style.bold
    total_cell.alignment = _CENTER

    # Entity rows: name + 1–5 scores + SUMPRODUCT weighted score + RANK.
    for offset, entity in enumerate(data.entities):
        row = _FIRST_ENTITY_ROW + offset
        ws.cell(row=row, column=1, value=entity.name).font = style.bold
        for idx in range(n):
            score = entity.scores[idx] if idx < len(entity.scores) else 3
            cell = ws.cell(row=row, column=2 + idx, value=max(1, min(5, int(score))))
            cell.fill = style.input_fill
            cell.alignment = _CENTER
        weighted = ws.cell(
            row=row,
            column=ws_col,
            value=(
                f"=SUMPRODUCT(B{row}:{last_crit_col}{row},"
                f"$B${_WEIGHTS_ROW}:${last_crit_col}${_WEIGHTS_ROW})"
            ),
        )
        weighted.fill = style.formula_fill
        weighted.number_format = "0.00"
        weighted.font = style.bold
        weighted.alignment = _CENTER
        rank = ws.cell(
            row=row,
            column=rank_col,
            value=(
                f"=RANK({ws_letter}{row},"
                f"${ws_letter}${_FIRST_ENTITY_ROW}:${ws_letter}${last_entity_row},0)"
            ),
        )
        rank.fill = style.formula_fill
        rank.alignment = _CENTER

    # Column widths + freeze (header + weights rows + entity-name column stay visible).
    ws.column_dimensions["A"].width = 26
    for idx in range(n):
        ws.column_dimensions[get_column_letter(2 + idx)].width = 13
    ws.column_dimensions[ws_letter].width = 16
    ws.column_dimensions[rank_letter].width = 8
    ws.freeze_panes = f"B{_FIRST_ENTITY_ROW}"

    if data.entities:
        score_range = f"{ws_letter}{_FIRST_ENTITY_ROW}:{ws_letter}{last_entity_row}"
        ws.conditional_formatting.add(
            score_range,
            ColorScaleRule(
                start_type="num",
                start_value=1,
                start_color=style.scale_low,
                mid_type="num",
                mid_value=3,
                mid_color=style.scale_mid,
                end_type="num",
                end_value=5,
                end_color=style.scale_high,
            ),
        )
        # Highlight the top-ranked entity's whole row (rank == 1).
        ws.conditional_formatting.add(
            f"A{_FIRST_ENTITY_ROW}:{rank_letter}{last_entity_row}",
            FormulaRule(formula=[f"${rank_letter}{_FIRST_ENTITY_ROW}=1"], fill=style.positive_fill),
        )


def _criteria_guide_sheet(ws: Worksheet, style: _Style, data: DecisionMatrixData) -> None:
    """Write the Criteria_Guide tab: each criterion's weight + 1..5 scoring definition."""
    language = data.language
    _title_block(
        ws,
        style,
        _t(language, "Kriterien & Bewertung", "Criteria & Scoring Guide"),
        _t(
            language,
            "Definition pro Kriterium (1 = schwach … 5 = stark).",
            "Definition per criterion (1 = weak … 5 = strong).",
        ),
    )
    headers = [
        _t(language, "Kriterium", "Criterion"),
        _t(language, "Gewicht", "Weight"),
        _t(language, "Bewertung 1 (schlecht) … 5 (gut)", "How to score 1 (worst) … 5 (best)"),
    ]
    for col, text in enumerate(headers, start=1):
        cell = ws.cell(row=_HEADER_ROW, column=col, value=text)
        cell.fill = style.header_fill
        cell.font = style.header_font
        cell.alignment = _CENTER
    weights = _normalized_weights(data)
    for offset, criterion in enumerate(data.criteria):
        row = _HEADER_ROW + 1 + offset
        ws.cell(row=row, column=1, value=criterion.name).font = style.bold
        wcell = ws.cell(
            row=row, column=2, value=round(weights[offset], 4) if offset < len(weights) else None
        )
        wcell.number_format = "0%"
        ws.cell(row=row, column=3, value=criterion.definition or "—").alignment = _LEFT
    ws.column_dimensions["A"].width = 26
    ws.column_dimensions["B"].width = 10
    ws.column_dimensions["C"].width = 70
    ws.freeze_panes = f"A{_HEADER_ROW + 1}"


def _research_notes_sheet(ws: Worksheet, style: _Style, data: DecisionMatrixData) -> None:
    """Write the Research_Notes tab: the evidence behind each entity × criterion score."""
    language = data.language
    _title_block(
        ws,
        style,
        _t(language, "Recherche-Notizen", "Research Notes"),
        _t(language, "Belege/Quellen hinter jedem Score.", "Evidence/sources behind each score."),
    )
    headers = [
        _t(language, "Unternehmen / Option", "Company / Option"),
        _t(language, "Kriterium", "Criterion"),
        _t(language, "Score", "Score"),
        _t(language, "Beleg / Quelle", "Evidence / Source"),
    ]
    for col, text in enumerate(headers, start=1):
        cell = ws.cell(row=_HEADER_ROW, column=col, value=text)
        cell.fill = style.header_fill
        cell.font = style.header_font
        cell.alignment = _CENTER
    row = _HEADER_ROW + 1
    for entity in data.entities:
        for idx, criterion in enumerate(data.criteria):
            ws.cell(row=row, column=1, value=entity.name)
            ws.cell(row=row, column=2, value=criterion.name)
            ws.cell(
                row=row, column=3, value=entity.scores[idx] if idx < len(entity.scores) else None
            )
            note = entity.notes[idx] if idx < len(entity.notes) else ""
            ws.cell(row=row, column=4, value=note or "—").alignment = _LEFT
            row += 1
    for col_letter, width in (("A", 24), ("B", 22), ("C", 8), ("D", 70)):
        ws.column_dimensions[col_letter].width = width
    ws.freeze_panes = f"A{_HEADER_ROW + 1}"


def build_decision_matrix(
    data: DecisionMatrixData, config: AppConfig, output_dir: str | Path
) -> Path:
    """Build the E-1 Decision/Scoring Matrix workbook and return its path (SPEC §12).

    Weighted scores use ``SUMPRODUCT`` over the yellow weights row; ranks use ``RANK`` — changing
    a weight or a score in Excel recalculates everything (N-10). Three tabs: Summary_Matrix,
    Criteria_Guide, Research_Notes.
    """
    if not data.criteria:
        raise ExcelBuildError("Decision matrix needs at least one scoring criterion.")
    style = _Style(config)
    wb = Workbook()
    matrix = wb.active
    matrix.title = "Summary_Matrix"
    _matrix_sheet(matrix, style, data)
    _criteria_guide_sheet(wb.create_sheet("Criteria_Guide"), style, data)
    _research_notes_sheet(wb.create_sheet("Research_Notes"), style, data)

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{date.today().isoformat()}_{_slug(data.title)}_matrix.xlsx"
    wb.save(str(path))
    return path
