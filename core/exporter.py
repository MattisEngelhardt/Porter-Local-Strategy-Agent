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
    "PDF rendering needs WeasyPrint + the GTK runtime.\n"
    "Fix (Windows, one-time):\n"
    "  1. .venv\\Scripts\\python -m pip install weasyprint\n"
    "  2. Install the GTK3 runtime (provides libgobject/pango/cairo):\n"
    "     https://github.com/tschoonj/GTK-for-Windows-Runtime-Installer/releases\n"
    "  3. Reopen the terminal, then re-run.\n"
    "Details: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#troubleshooting"
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
def build_management_deck(
    analysis: AnalysisOutput, config: AppConfig, output_dir: str | Path, language: Language
) -> Path:
    """Render the analysis into a Neura-styled .pptx management deck and return its path."""
    try:
        from pptx import Presentation
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN
        from pptx.util import Inches, Pt
    except ImportError as exc:  # pragma: no cover - python-pptx is a declared dependency
        raise DeckBuildError(f"python-pptx is not installed.\n{_PPTX_FIX}") from exc

    colors = config.output.colors

    def rgb(hex_color: str) -> Any:
        return RGBColor.from_string(hex_color.lstrip("#").upper())  # type: ignore[no-untyped-call]

    slide_w = Inches(13.333)
    slide_h = Inches(7.5)
    prs = Presentation()
    prs.slide_width = slide_w
    prs.slide_height = slide_h
    blank = prs.slide_layouts[6]
    logo = Path(config.output.logo_path)
    show_logo = config.output.include_logo and logo.is_file()

    def add_logo(slide: Any) -> None:
        if show_logo:
            slide.shapes.add_picture(
                str(logo), slide_w - Inches(1.6), slide_h - Inches(0.9), height=Inches(0.5)
            )

    def text_box(
        slide: Any,
        text: str,
        left: Any,
        top: Any,
        w: Any,
        h: Any,
        size: int,
        color: str,
        bold: bool = False,
    ) -> None:
        box = slide.shapes.add_textbox(left, top, w, h)
        tf = box.text_frame
        tf.word_wrap = True
        para = tf.paragraphs[0]
        para.text = text
        para.alignment = PP_ALIGN.LEFT
        run = para.runs[0]
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.name = "Arial"
        run.font.color.rgb = rgb(color)

    def bullets_box(slide: Any, bullets: list[str]) -> None:
        box = slide.shapes.add_textbox(Inches(0.7), Inches(1.7), Inches(12), Inches(5.2))
        tf = box.text_frame
        tf.word_wrap = True
        for idx, line in enumerate(bullets):
            para = tf.paragraphs[0] if idx == 0 else tf.add_paragraph()
            para.text = f"• {line}"
            para.space_after = Pt(8)
            run = para.runs[0]
            run.font.size = Pt(16)
            run.font.name = "Arial"
            run.font.color.rgb = rgb(colors.text_dark)

    def content_slide(heading: str, bullets: list[str]) -> None:
        slide = prs.slides.add_slide(blank)
        text_box(
            slide, heading, Inches(0.7), Inches(0.5), Inches(12), Inches(1.1), 26, "#2D2D2D", True
        )
        bullets_box(slide, bullets)
        add_logo(slide)

    # 1. Title slide (dark background)
    title_slide = prs.slides.add_slide(blank)
    bg = title_slide.background
    bg.fill.solid()
    bg.fill.fore_color.rgb = rgb(colors.dark_bg)
    text_box(
        title_slide,
        analysis.title,
        Inches(0.8),
        Inches(2.7),
        Inches(11.7),
        Inches(2.4),
        40,
        colors.white,
        True,
    )
    subtitle = (
        "Management-Briefing" if language == Language.DE else "Management Briefing"
    ) + f"  ·  {date.today().isoformat()}"
    text_box(
        title_slide,
        subtitle,
        Inches(0.8),
        Inches(5.1),
        Inches(11.7),
        Inches(0.8),
        18,
        colors.accent_cyan,
    )
    add_logo(title_slide)

    # 2. Executive summary
    content_slide(
        "Kernaussage" if language == Language.DE else "Executive Summary",
        _sentences(analysis.bottom_line),
    )
    # 3. One slide per theme ("so what" heading)
    for section in analysis.sections:
        content_slide(section.heading, _sentences(section.body))
    # 4. Sources
    if analysis.sources:
        content_slide(
            "Quellen" if language == Language.DE else "Sources",
            [s.url + (f" — {s.title}" if s.title else "") for s in analysis.sources],
        )

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{date.today().isoformat()}_{_slug(analysis.title)}_deck.pptx"
    prs.save(str(path))
    return path


# ----------------------------------------------------------------- PDF (back-compat shim)
def build_management_pdf(
    analysis: AnalysisOutput, config: AppConfig, output_dir: str | Path, language: Language
) -> Path:
    """Back-compatible management PDF brief — delegates to :func:`build_brief_pdf` (T-5 layout).

    Kept so the doc-prep path and existing tests keep working; new callers should use
    :func:`build_brief_pdf` directly with the task type.
    """
    return build_brief_pdf(analysis, config, output_dir, task_type=TaskType.DOCUMENT_SYNTHESIS)
