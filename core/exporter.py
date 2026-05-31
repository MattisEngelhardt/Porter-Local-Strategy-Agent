"""Output rendering (SPEC §7 ``exporter.py``): Neura-styled PDF briefs + PPTX decks.

Turns a structured :class:`~models.synthesis.AnalysisOutput` into delivery files with Neura
styling (colors from ``config.yaml``, logo bottom-right on decks / in the brief header):

* **PDF brief** — Jinja2 HTML templates (``templates/briefs/`` T-1..T-6, SPEC §10) → ``weasyprint``
  (the SPEC §6 PDF tool). :func:`render_brief_html` is pure/testable; :func:`build_brief_pdf` writes
  the PDF. On Windows WeasyPrint needs the GTK runtime — :func:`_ensure_gtk_dll_dir` forces a found
  GTK ``bin`` ahead of any incompatible ``libgobject`` on PATH, and if WeasyPrint still cannot be
  imported the call fails fast with exact install instructions (the renderer is correct and works
  the moment GTK is present — zero code change).
* **PPTX deck** — ``python-pptx``, fully local with zero system libraries
  (:func:`build_management_deck`; generalized to all 10 SPEC §11 slide types in a later task).

The SPEC §4.6 "Markdown → weasyprint" step is resolved to Jinja2→HTML→weasyprint because no
Markdown→HTML library is permitted by SPEC §6 / RULE 3 (documented in PROGRESS).
"""

from __future__ import annotations

import base64
import os
import re
import sys
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup, escape

from core.config import AppConfig
from models.deck import DeckStructure, SlideContent, SlideType
from models.synthesis import AnalysisOutput
from models.task import Audience, Language, TaskType


class ExportError(Exception):
    """Base class for output-rendering failures."""


class DeckBuildError(ExportError):
    """python-pptx is unavailable (fail fast with fix instructions)."""


class PdfBuildError(ExportError):
    """weasyprint (or its GTK system libraries) is unavailable (fail fast with fix instructions)."""


_PPTX_FIX = (
    "Fix: install python-pptx into the venv:\n  .venv\\Scripts\\python -m pip install python-pptx"
)
_PDF_FIX = (
    "PDF rendering needs WeasyPrint + the GTK/Pango runtime (PPTX + Excel work without it).\n"
    "Fix (Windows, one-time) — recommended via MSYS2 (auto-detected at C:\\msys64\\mingw64\\bin):\n"
    "  1. Install MSYS2 from https://www.msys2.org/ (keep the default C:\\msys64).\n"
    "  2. Open the 'MSYS2 MINGW64' terminal and run:\n"
    "       pacman -S mingw-w64-x86_64-pango\n"
    "     (pulls in cairo/glib/harfbuzz — everything WeasyPrint needs).\n"
    "  3. Reopen this terminal, then re-run.\n"
    "Alternative: install the GTK3 runtime (open the repo, then Releases):\n"
    "  https://github.com/tschoonj/GTK-for-Windows-Runtime-Installer  (tick 'set up PATH').\n"
    "If GTK lives elsewhere, set output.gtk_runtime_path in config.yaml to its 'bin' dir.\n"
    "Docs: https://www.gtk.org/docs/installations/windows/ · "
    "https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#troubleshooting"
)


def _slug(text: str) -> str:
    """Make a short, filesystem-safe slug from a title."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (cleaned or "briefing")[:50]


def _sentences(text: str, cap: int = 6) -> list[str]:
    """Split a body into a few short bullet points (by line, then by sentence)."""
    raw = [seg.strip(" -•\t") for seg in re.split(r"\n+", text) if seg.strip()]
    bullets: list[str] = []
    for segment in raw:
        for part in re.split(r"(?<=[.!?])\s+", segment):
            part = part.strip()
            if part:
                bullets.append(part)
    return bullets[:cap] or (["—"] if not text.strip() else [text.strip()[:200]])


# ----------------------------------------------------------------- GTK runtime (WeasyPrint)
def _gtk_candidate_dirs(config: AppConfig) -> list[Path]:
    """Candidate GTK-runtime ``bin`` dirs (config > env > standard Windows locations)."""
    candidates: list[str] = []
    configured = config.output.gtk_runtime_path
    if configured:
        candidates.append(configured)
    env_dir = os.environ.get("WEASYPRINT_DLL_DIRECTORIES")
    if env_dir:
        candidates.extend(env_dir.split(os.pathsep))
    local = os.environ.get("LOCALAPPDATA", "")
    candidates += [
        r"C:\Program Files\GTK3-Runtime Win64\bin",
        os.path.join(local, "Programs", "GTK3-Runtime Win64", "bin") if local else "",
        r"C:\msys64\mingw64\bin",
    ]
    return [Path(c) for c in candidates if c]


def _ensure_gtk_dll_dir(config: AppConfig) -> None:
    """Put a real GTK runtime's ``bin`` first on the Windows DLL search path (idempotent).

    WeasyPrint needs Pango/Cairo/GObject. On Windows the Tesseract folder may ship an
    incompatible ``libgobject`` earlier on PATH, so a found GTK runtime is forced ahead of it
    (both via ``PATH`` and :func:`os.add_dll_directory`). No-op off Windows / when none is found.
    """
    if sys.platform != "win32":
        return
    for path in _gtk_candidate_dirs(config):
        if path.is_dir() and (path / "libgobject-2.0-0.dll").is_file():
            bin_str = str(path)
            current = os.environ.get("PATH", "")
            if not current.lower().startswith(bin_str.lower()):
                os.environ["PATH"] = bin_str + os.pathsep + current
            add_dll = getattr(os, "add_dll_directory", None)
            if callable(add_dll):
                try:
                    add_dll(bin_str)
                except OSError:  # pragma: no cover - defensive
                    pass
            return


# ----------------------------------------------------------------- brief (Jinja2 → HTML → PDF)
# Per-template labels (bottom-line label · type label), bilingual as (DE, EN).
_BRIEF_META: dict[str, dict[str, tuple[str, str]]] = {
    "competitor_brief.md.j2": {
        "bl": ("Kernaussage", "Executive Summary"),
        "type": ("Wettbewerbsanalyse", "Competitive Intelligence"),
    },
    "decision_brief.md.j2": {
        "bl": ("Empfehlung", "Recommendation"),
        "type": ("Entscheidungsanalyse", "Decision Analysis"),
    },
    "market_overview.md.j2": {
        "bl": ("Kernaussage", "Bottom Line"),
        "type": ("Marktanalyse", "Market Intelligence"),
    },
    "board_update.md.j2": {
        "bl": ("Kernaussage", "Bottom Line"),
        "type": ("Management-Briefing", "Management Brief"),
    },
    "document_synthesis.md.j2": {
        "bl": ("Kernaussage", "Bottom Line"),
        "type": ("Dokumentenanalyse", "Document Analysis"),
    },
    "adhoc_brief.md.j2": {
        "bl": ("Kernaussage", "Bottom Line Up Front"),
        "type": ("Kurzanalyse", "Quick Intel"),
    },
}

_DEFAULT_BRIEF_TEMPLATE = "adhoc_brief.md.j2"

# Task type → brief template (SPEC §10 T-1..T-6).
_BRIEF_TEMPLATES: dict[TaskType, str] = {
    TaskType.COMPETITOR_ANALYSIS: "competitor_brief.md.j2",
    TaskType.TARGET_SCREENING: "decision_brief.md.j2",
    TaskType.PARTNERSHIP_EVALUATION: "decision_brief.md.j2",
    TaskType.OPTION_COMPARISON: "decision_brief.md.j2",
    TaskType.STRATEGIC_INITIATIVE: "decision_brief.md.j2",
    TaskType.BUSINESS_CASE: "decision_brief.md.j2",
    TaskType.MARKET_RESEARCH: "market_overview.md.j2",
    TaskType.MARKET_ANALYSIS: "market_overview.md.j2",
    TaskType.FINANCIAL_BENCHMARK: "market_overview.md.j2",
    TaskType.BOARD_PREP: "board_update.md.j2",
    TaskType.MEETING_BRIEFING: "board_update.md.j2",
    TaskType.DOCUMENT_SYNTHESIS: "document_synthesis.md.j2",
    TaskType.INDUSTRY_NEWS: "adhoc_brief.md.j2",
    TaskType.ADHOC: "adhoc_brief.md.j2",
}

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates" / "briefs"
_BULLET_RE = re.compile(r"^\s*[-*•]\s+")


def brief_template_for(task_type: TaskType) -> str:
    """Return the brief template filename for a task type (SPEC §10)."""
    return _BRIEF_TEMPLATES.get(task_type, _DEFAULT_BRIEF_TEMPLATE)


@lru_cache(maxsize=1)
def _brief_env() -> Environment:
    """Build (and cache) the Jinja2 environment for the brief templates."""
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(default=True, default_for_string=True),
        trim_blocks=True,
        lstrip_blocks=True,
    )


def _body_to_html(text: str) -> Markup:
    """Convert a section body (plain text + optional bullet lines) into safe HTML.

    Blank lines separate blocks; lines starting with ``-``/``*``/``•`` become a bullet list,
    other lines a paragraph (single newlines → ``<br>``). Everything is HTML-escaped first.
    """
    blocks = re.split(r"\n\s*\n", text.strip())
    parts: list[str] = []
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if all(_BULLET_RE.match(ln) for ln in lines):
            items = "".join(f"<li>{escape(_BULLET_RE.sub('', ln).strip())}</li>" for ln in lines)
            parts.append(f"<ul>{items}</ul>")
        else:
            joined = Markup("<br>").join(escape(ln.strip()) for ln in lines)
            parts.append(f"<p>{joined}</p>")
    return Markup("".join(parts) or "<p>—</p>")


def _logo_data_uri(config: AppConfig) -> str | None:
    """Return the Neura logo as a base64 PNG data URI for HTML embedding (or ``None``)."""
    logo = Path(config.output.logo_path)
    if not (config.output.include_logo and logo.is_file()):
        return None
    data = base64.b64encode(logo.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{data}"


def _brief_context(
    analysis: AnalysisOutput, config: AppConfig, template_name: str
) -> dict[str, Any]:
    """Assemble the Jinja context for a brief from the analysis (bilingual labels)."""
    is_de = analysis.language == Language.DE
    idx = 0 if is_de else 1
    meta = _BRIEF_META.get(template_name, _BRIEF_META[_DEFAULT_BRIEF_TEMPLATE])
    meta_line = (
        f"{date.today().isoformat()} · {meta['type'][idx]} · {analysis.language.value.upper()}"
    )
    sections = [
        {"heading": s.heading, "body_html": _body_to_html(s.body)} for s in analysis.sections
    ]
    sources = [
        {
            "url": s.url,
            "title": s.title or "",
            "date": s.date or "",
            "tier": s.tier.value if s.tier else "",
        }
        for s in analysis.sources
    ]
    return {
        "c": config.output.colors,
        "title": analysis.title,
        "meta": meta_line,
        "bl_label": meta["bl"][idx],
        "bottom_line": analysis.bottom_line,
        "sections": sections,
        "sources_label": "Quellen" if is_de else "Sources",
        "sources": sources,
        "note": "",
        "footer_note": "NEURA · " + ("Management-Briefing" if is_de else "Management Brief"),
        "logo_data_uri": _logo_data_uri(config),
    }


def render_brief_html(
    analysis: AnalysisOutput,
    config: AppConfig,
    *,
    task_type: TaskType = TaskType.DOCUMENT_SYNTHESIS,
    audience: Audience | None = None,
) -> str:
    """Render the analysis into a Neura-styled HTML brief (pure — no WeasyPrint, testable)."""
    template_name = brief_template_for(task_type)
    template = _brief_env().get_template(template_name)
    return template.render(**_brief_context(analysis, config, template_name))


def build_brief_pdf(
    analysis: AnalysisOutput,
    config: AppConfig,
    output_dir: str | Path,
    *,
    task_type: TaskType = TaskType.DOCUMENT_SYNTHESIS,
    audience: Audience | None = None,
) -> Path:
    """Render the analysis into a Neura-styled PDF brief (Jinja2 → HTML → WeasyPrint).

    The brief template is chosen from the task type (SPEC §10). Raises :class:`PdfBuildError`
    with exact install instructions if WeasyPrint / its GTK runtime is unavailable (the renderer
    is correct and works the moment GTK is present — no code change).
    """
    _ensure_gtk_dll_dir(config)
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        raise PdfBuildError(_PDF_FIX) from exc

    html = render_brief_html(analysis, config, task_type=task_type, audience=audience)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{date.today().isoformat()}_{_slug(analysis.title)}_brief.pdf"
    HTML(string=html).write_pdf(str(path))
    return path


# ----------------------------------------------------------------- PPTX (python-pptx)
_SLIDE_W_IN = 13.333  # 16:9 widescreen
_SLIDE_H_IN = 7.5
# SWOT quadrant fills (Strengths/Opportunities = positive, Weaknesses/Threats = risk).
_SWOT_FILLS = ("excel_positive", "excel_negative", "excel_positive", "excel_negative")


class _DeckRenderer:
    """Render a :class:`~models.deck.DeckStructure` into a Neura-styled python-pptx deck.

    Holds the shared pptx primitives (colors, text, bullets, tables, rounded boxes, the
    bottom-right logo) and dispatches per :class:`~models.deck.SlideType`, so all 10 SPEC §11
    slide types share one implementation (no per-type duplication, SPEC §11 + output_playbook).
    """

    def __init__(self, config: AppConfig) -> None:
        """Build an empty 16:9 presentation and cache the pptx primitives + Neura palette."""
        try:
            from pptx import Presentation
            from pptx.dml.color import RGBColor
            from pptx.enum.shapes import MSO_SHAPE
            from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
            from pptx.util import Inches, Pt
        except ImportError as exc:  # pragma: no cover - python-pptx is a declared dependency
            raise DeckBuildError(f"python-pptx is not installed.\n{_PPTX_FIX}") from exc

        self._RGBColor = RGBColor
        self._MSO_SHAPE = MSO_SHAPE
        self._PP_ALIGN = PP_ALIGN
        self._MSO_ANCHOR = MSO_ANCHOR
        self._Inches = Inches
        self._Pt = Pt
        self.colors = config.output.colors
        self.prs = Presentation()
        self.prs.slide_width = Inches(_SLIDE_W_IN)
        self.prs.slide_height = Inches(_SLIDE_H_IN)
        self._blank = self.prs.slide_layouts[6]
        logo = Path(config.output.logo_path)
        self._show_logo = config.output.include_logo and logo.is_file()
        self._logo = str(logo)

    def rgb(self, hex_color: str) -> Any:
        """A pptx ``RGBColor`` from a ``#rrggbb`` string (config-driven palette)."""
        return self._RGBColor.from_string(hex_color.lstrip("#").upper())  # type: ignore[no-untyped-call]

    def _add_logo(self, slide: Any) -> None:
        """Place the Neura logo bottom-right on a slide (~2.5cm wide), if configured + present."""
        if not self._show_logo:
            return
        inches = self._Inches
        slide.shapes.add_picture(
            self._logo,
            inches(_SLIDE_W_IN) - inches(1.75),
            inches(_SLIDE_H_IN) - inches(0.8),
            height=inches(0.4),
        )

    def _text(
        self,
        slide: Any,
        text: str,
        left: Any,
        top: Any,
        width: Any,
        height: Any,
        size: int,
        color: str,
        *,
        bold: bool = False,
        align: Any = None,
        anchor: Any = None,
    ) -> Any:
        """Add a single-paragraph Arial text box and return it."""
        box = slide.shapes.add_textbox(left, top, width, height)
        frame = box.text_frame
        frame.word_wrap = True
        if anchor is not None:
            frame.vertical_anchor = anchor
        para = frame.paragraphs[0]
        para.text = text
        para.alignment = align if align is not None else self._PP_ALIGN.LEFT
        run = para.runs[0]
        run.font.size = self._Pt(size)
        run.font.bold = bold
        run.font.name = "Arial"
        run.font.color.rgb = self.rgb(color)
        return box

    def _headline(self, slide: Any, text: str) -> None:
        """Render the slide's 'so what' headline bar at the top of a content slide."""
        inches = self._Inches
        self._text(
            slide,
            text,
            inches(0.7),
            inches(0.45),
            inches(11.9),
            inches(1.2),
            26,
            self.colors.charcoal,
            bold=True,
        )

    def _bullets(self, slide: Any, bullets: list[str], *, top: float = 1.8) -> None:
        """Render a vertical list of bullets on a content slide."""
        inches, pt = self._Inches, self._Pt
        box = slide.shapes.add_textbox(
            inches(0.7), inches(top), inches(11.9), inches(_SLIDE_H_IN - top - 0.6)
        )
        frame = box.text_frame
        frame.word_wrap = True
        for idx, line in enumerate(bullets or ["—"]):
            para = frame.paragraphs[0] if idx == 0 else frame.add_paragraph()
            para.text = f"• {line}"
            para.space_after = pt(9)
            run = para.runs[0]
            run.font.size = pt(16)
            run.font.name = "Arial"
            run.font.color.rgb = self.rgb(self.colors.text_dark)

    def _rounded(self, slide: Any, left: Any, top: Any, width: Any, height: Any, fill: str) -> Any:
        """Add a borderless rounded rectangle filled with ``fill`` (clean Neura aesthetic)."""
        shape = slide.shapes.add_shape(self._MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
        shape.fill.solid()
        shape.fill.fore_color.rgb = self.rgb(fill)
        shape.line.fill.background()
        shape.shadow.inherit = False
        return shape

    def _new(self) -> Any:
        """Append a blank slide."""
        return self.prs.slides.add_slide(self._blank)

    # --- per-slide-type renderers --------------------------------------------------------
    def _title_slide(self, sc: SlideContent) -> None:
        inches = self._Inches
        slide = self._new()
        background = slide.background
        background.fill.solid()
        background.fill.fore_color.rgb = self.rgb(self.colors.dark_bg)
        self._text(
            slide,
            sc.headline,
            inches(0.8),
            inches(2.6),
            inches(11.7),
            inches(2.6),
            40,
            self.colors.white,
            bold=True,
        )
        subtitle = sc.body or date.today().isoformat()
        self._text(
            slide,
            subtitle,
            inches(0.8),
            inches(5.2),
            inches(11.7),
            inches(0.8),
            18,
            self.colors.accent_cyan,
        )
        self._add_logo(slide)

    def _table_slide(self, sc: SlideContent) -> None:
        slide = self._new()
        self._headline(slide, sc.headline)
        if sc.table:
            self._draw_table(slide, sc.table)
        else:
            self._bullets(slide, sc.bullets)
        self._add_logo(slide)

    def _draw_table(self, slide: Any, rows: list[list[str]]) -> None:
        """Draw a header-styled table (row 0 = header) with alternating row fills."""
        inches, pt = self._Inches, self._Pt
        n_rows = len(rows)
        n_cols = max((len(r) for r in rows), default=1)
        graphic = slide.shapes.add_table(
            n_rows, n_cols, inches(0.7), inches(1.8), inches(11.9), inches(0.4 * n_rows)
        )
        table = graphic.table
        for r, row in enumerate(rows):
            for c in range(n_cols):
                cell = table.cell(r, c)
                cell.text = str(row[c]) if c < len(row) else ""
                para = cell.text_frame.paragraphs[0]
                run = para.runs[0] if para.runs else para.add_run()
                run.font.name = "Arial"
                run.font.size = pt(12 if r else 13)
                run.font.bold = r == 0
                if r == 0:
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = self.rgb(self.colors.excel_header)
                    run.font.color.rgb = self.rgb(self.colors.white)
                else:
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = self.rgb(
                        self.colors.white if r % 2 else self.colors.light_surface
                    )
                    run.font.color.rgb = self.rgb(self.colors.text_dark)

    def _swot_slide(self, sc: SlideContent) -> None:
        """Render a 2x2 SWOT grid from ``table`` rows ([quadrant, content]) or bullets."""
        inches, pt = self._Inches, self._Pt
        slide = self._new()
        self._headline(slide, sc.headline)
        quadrants = self._swot_quadrants(sc)
        positions = [(0.7, 1.8), (7.05, 1.8), (0.7, 4.45), (7.05, 4.45)]
        for (label, content), (left, top), fill in zip(
            quadrants, positions, _SWOT_FILLS, strict=False
        ):
            box = self._rounded(
                slide,
                inches(left),
                inches(top),
                inches(5.6),
                inches(2.4),
                getattr(self.colors, fill),
            )
            frame = box.text_frame
            frame.word_wrap = True
            frame.margin_left = inches(0.15)
            frame.margin_top = inches(0.1)
            head = frame.paragraphs[0]
            head.text = label
            head_run = head.runs[0]
            head_run.font.bold = True
            head_run.font.size = pt(15)
            head_run.font.name = "Arial"
            head_run.font.color.rgb = self.rgb(self.colors.text_dark)
            for line in content:
                para = frame.add_paragraph()
                para.text = f"• {line}"
                run = para.runs[0]
                run.font.size = pt(12)
                run.font.name = "Arial"
                run.font.color.rgb = self.rgb(self.colors.text_dark)
        self._add_logo(slide)

    def _swot_quadrants(self, sc: SlideContent) -> list[tuple[str, list[str]]]:
        """Resolve 4 (label, lines) quadrants from the slide's table or bullets (fail-safe)."""
        default_labels = ["Strengths", "Weaknesses", "Opportunities", "Threats"]
        if sc.table and len(sc.table) >= 4:
            out: list[tuple[str, list[str]]] = []
            for row in sc.table[:4]:
                label = str(row[0]) if row else ""
                body = str(row[1]) if len(row) > 1 else ""
                out.append(
                    (label, [seg.strip() for seg in re.split(r"[;\n]", body) if seg.strip()])
                )
            return out
        bullets = sc.bullets or []
        return [(default_labels[i], [bullets[i]] if i < len(bullets) else []) for i in range(4)]

    def _recommendation_slide(self, sc: SlideContent) -> None:
        """A clean decision slide: headline + a standalone accent callout (decision-ready)."""
        inches = self._Inches
        slide = self._new()
        self._headline(slide, sc.headline)
        box = self._rounded(
            slide, inches(0.7), inches(1.9), inches(11.9), inches(1.6), self.colors.accent_cyan
        )
        frame = box.text_frame
        frame.word_wrap = True
        frame.vertical_anchor = self._MSO_ANCHOR.MIDDLE
        para = frame.paragraphs[0]
        para.text = sc.body or (sc.bullets[0] if sc.bullets else "—")
        para.alignment = self._PP_ALIGN.CENTER
        run = para.runs[0]
        run.font.size = self._Pt(22)
        run.font.bold = True
        run.font.name = "Arial"
        run.font.color.rgb = self.rgb(self.colors.white)
        supporting = sc.bullets if sc.body else sc.bullets[1:]
        if supporting:
            self._bullets(slide, supporting, top=3.8)
        self._add_logo(slide)

    def _content_slide(self, sc: SlideContent) -> None:
        """Generic 'one message per slide': headline + table (if present) or bullets."""
        slide = self._new()
        self._headline(slide, sc.headline)
        if sc.table:
            self._draw_table(slide, sc.table)
        else:
            self._bullets(slide, sc.bullets)
        self._add_logo(slide)

    def render(self, sc: SlideContent) -> None:
        """Dispatch a single slide to its renderer by :class:`~models.deck.SlideType`."""
        if sc.slide_type == SlideType.TITLE:
            self._title_slide(sc)
        elif sc.slide_type == SlideType.COMPETITIVE_COMPARISON:
            self._table_slide(sc)
        elif sc.slide_type == SlideType.SWOT:
            self._swot_slide(sc)
        elif sc.slide_type == SlideType.RECOMMENDATION:
            self._recommendation_slide(sc)
        else:  # exec summary / market / company / financial / signals / appendix
            self._content_slide(sc)

    def save(self, output_dir: str | Path, title: str) -> Path:
        """Write the deck to ``output_dir`` and return its path."""
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        path = out / f"{date.today().isoformat()}_{_slug(title)}_deck.pptx"
        self.prs.save(str(path))
        return path


def build_deck(deck: DeckStructure, config: AppConfig, output_dir: str | Path) -> Path:
    """Render a :class:`~models.deck.DeckStructure` into a Neura-styled .pptx and return its path.

    Handles all 10 SPEC §11 slide types (Neura colors from ``config.output.colors``, Arial, rounded
    callouts, logo bottom-right on every slide). Raises :class:`DeckBuildError` if python-pptx is
    unavailable.
    """
    renderer = _DeckRenderer(config)
    for slide in deck.slides:
        renderer.render(slide)
    return renderer.save(output_dir, deck.title)


def management_deck_structure(analysis: AnalysisOutput, language: Language) -> DeckStructure:
    """Build a generic management :class:`DeckStructure` from an analysis (doc-prep / fallback).

    Title → executive summary → one 'so what' slide per section → sources. This is the
    deterministic mapping used when no LLM deck shaping is applied.
    """
    is_de = language == Language.DE
    slides = [
        SlideContent(
            slide_type=SlideType.TITLE,
            headline=analysis.title,
            body=("Management-Briefing" if is_de else "Management Briefing")
            + f"  ·  {date.today().isoformat()}",
        ),
        SlideContent(
            slide_type=SlideType.EXECUTIVE_SUMMARY,
            headline="Kernaussage" if is_de else "Executive Summary",
            bullets=_sentences(analysis.bottom_line),
        ),
    ]
    for section in analysis.sections:
        slides.append(
            SlideContent(
                slide_type=SlideType.STRATEGIC_SIGNALS,
                headline=section.heading,
                bullets=_sentences(section.body),
            )
        )
    if analysis.sources:
        slides.append(
            SlideContent(
                slide_type=SlideType.APPENDIX,
                headline="Quellen" if is_de else "Sources",
                bullets=[s.url + (f" — {s.title}" if s.title else "") for s in analysis.sources],
            )
        )
    return DeckStructure(title=analysis.title, language=language, slides=slides)


def build_management_deck(
    analysis: AnalysisOutput, config: AppConfig, output_dir: str | Path, language: Language
) -> Path:
    """Back-compatible management deck — builds a generic structure and renders via build_deck."""
    return build_deck(management_deck_structure(analysis, language), config, output_dir)


# ----------------------------------------------------------------- PDF (back-compat shim)
def build_management_pdf(
    analysis: AnalysisOutput, config: AppConfig, output_dir: str | Path, language: Language
) -> Path:
    """Back-compatible management PDF brief — delegates to :func:`build_brief_pdf` (T-5 layout).

    Kept so the doc-prep path and existing tests keep working; new callers should use
    :func:`build_brief_pdf` directly with the task type.
    """
    return build_brief_pdf(analysis, config, output_dir, task_type=TaskType.DOCUMENT_SYNTHESIS)
