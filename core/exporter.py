"""Output rendering (Phase 3.5 slice of SPEC §7 ``exporter.py``): management PDF + PPTX.

Turns a structured :class:`~models.synthesis.AnalysisOutput` (e.g. the CEO-office document
briefing) into delivery files with Neura styling (colors from ``config.yaml``, logo bottom-right):

* **PPTX** via ``python-pptx`` — fully local, zero system libraries. Works now.
* **PDF** via ``weasyprint`` (the SPEC §6 PDF tool). On Windows weasyprint needs the GTK runtime;
  if it cannot be imported, :func:`build_management_pdf` fails fast with exact install instructions
  (the renderer itself is correct and works the moment GTK is present — zero code change).

Headlines are the analysis's "so what" section headings; the deck is one message per slide. This
is the focused doc-prep renderer; Phase 4 extends it to all brief/deck/Excel templates.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from typing import Any

from core.config import AppConfig
from models.synthesis import AnalysisOutput
from models.task import Language


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


# ----------------------------------------------------------------- PDF (weasyprint)
def _briefing_html(analysis: AnalysisOutput, language: Language, config: AppConfig) -> str:
    """Build clean, Neura-styled HTML for the management PDF brief."""
    c = config.output.colors
    is_de = language == Language.DE

    def esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    sections = "".join(f"<h2>{esc(s.heading)}</h2><p>{esc(s.body)}</p>" for s in analysis.sections)
    sources = "".join(
        f"<li>{esc(s.url)}{(' — ' + esc(s.title)) if s.title else ''}</li>"
        for s in analysis.sources
    )
    sources_block = (
        f"<h2>{'Quellen' if is_de else 'Sources'}</h2><ul>{sources}</ul>" if sources else ""
    )
    label = "Management-Briefing" if is_de else "Management Briefing"
    bl_label = "Kernaussage" if is_de else "Bottom Line"
    meta = f"{label} · {date.today().isoformat()} · {analysis.language.value}"
    return f"""<!doctype html><html><head><meta charset="utf-8"><style>
      @page {{ size: A4; margin: 1.8cm; }}
      body {{ font-family: Arial, sans-serif; color: {c.text_dark};
              font-size: 11pt; line-height: 1.45; }}
      h1 {{ font-size: 20pt; color: {c.text_dark}; margin: 0 0 2pt 0; }}
      .meta {{ color: {c.charcoal}; font-size: 9pt; margin-bottom: 14pt; }}
      .bl {{ background: {c.light_surface}; border-left: 4px solid {c.accent_cyan};
             padding: 10pt 12pt; margin-bottom: 14pt; font-size: 12pt; }}
      h2 {{ font-size: 13pt; color: {c.accent_cyan}; margin: 14pt 0 4pt 0; }}
      p {{ margin: 0 0 8pt 0; }} ul {{ margin: 0; padding-left: 16pt; }}
      li {{ margin-bottom: 3pt; }}
    </style></head><body>
      <h1>{esc(analysis.title)}</h1>
      <div class="meta">{meta}</div>
      <div class="bl"><b>{bl_label}:</b> {esc(analysis.bottom_line)}</div>
      {sections}{sources_block}
    </body></html>"""


def build_management_pdf(
    analysis: AnalysisOutput, config: AppConfig, output_dir: str | Path, language: Language
) -> Path:
    """Render the analysis into a Neura-styled PDF brief and return its path.

    Raises :class:`PdfBuildError` with exact install instructions if WeasyPrint / its GTK runtime
    is unavailable (the renderer is correct and works once GTK is installed — no code change).
    """
    try:
        from weasyprint import HTML
    except (ImportError, OSError) as exc:
        raise PdfBuildError(_PDF_FIX) from exc

    html = _briefing_html(analysis, language, config)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{date.today().isoformat()}_{_slug(analysis.title)}_brief.pdf"
    HTML(string=html).write_pdf(str(path))
    return path
