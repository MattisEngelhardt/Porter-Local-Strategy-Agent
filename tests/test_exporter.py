"""Tests for output rendering (core/exporter.py): PPTX (live) + PDF (fail-fast without GTK)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import AppConfig
from core.exporter import (
    PdfBuildError,
    brief_template_for,
    build_brief_pdf,
    build_deck,
    build_management_deck,
    build_management_pdf,
    render_brief_html,
)
from models.deck import DeckStructure, SlideContent, SlideType
from models.synthesis import AnalysisOutput, Section, SourceRef
from models.task import Language, TaskType


def _analysis() -> AnalysisOutput:
    return AnalysisOutput(
        title="Q2 Board Update",
        language=Language.EN,
        bottom_line="Runway is 9 months. Approve the bridge round now.",
        sections=[
            Section(
                heading="Cash runway shortens to 9 months", body="Cash fell to 10.8M. Burn 1.2M/mo."
            ),
            Section(heading="Revenue up 35%", body="Revenue rose to 4.2M on industrial pilots."),
        ],
        sources=[SourceRef(url="q2_financials.xlsx", title="Q2 figures")],
    )


def test_build_management_deck_creates_pptx(tmp_path: Path) -> None:
    """A Neura-styled .pptx is created with title + exec-summary + one slide per theme + sources."""
    pptx = pytest.importorskip("pptx")  # python-pptx is a declared dependency
    path = build_management_deck(_analysis(), AppConfig(), tmp_path, Language.EN)
    assert path.exists() and path.suffix == ".pptx"

    prs = pptx.Presentation(str(path))
    # title + executive summary + 2 sections + sources = 5 slides
    assert len(prs.slides) == 5
    title_texts = [shape.text_frame.text for shape in prs.slides[0].shapes if shape.has_text_frame]
    assert any("Q2 Board Update" in text for text in title_texts)
    # a section headline ("so what") appears on a content slide
    all_text = " ".join(
        shape.text_frame.text
        for slide in prs.slides
        for shape in slide.shapes
        if shape.has_text_frame
    )
    assert "Cash runway shortens to 9 months" in all_text


def test_build_management_pdf_failfast_or_renders(tmp_path: Path) -> None:
    """PDF renders when WeasyPrint+GTK are available; otherwise fails fast with fix instructions."""
    try:
        import weasyprint  # noqa: F401

        available = True
    except Exception:  # ImportError or OSError (missing GTK runtime)
        available = False

    if available:
        path = build_management_pdf(_analysis(), AppConfig(), tmp_path, Language.EN)
        assert path.exists() and path.suffix == ".pdf"
    else:
        with pytest.raises(PdfBuildError) as excinfo:
            build_management_pdf(_analysis(), AppConfig(), tmp_path, Language.EN)
        message = str(excinfo.value).lower()
        assert "gtk" in message or "weasyprint" in message


# ----------------------------------------------------------------- brief HTML (pure)
def test_brief_template_routing() -> None:
    """Each task type maps to its SPEC §10 brief template (T-1..T-6)."""
    assert brief_template_for(TaskType.COMPETITOR_ANALYSIS) == "competitor_brief.md.j2"
    assert brief_template_for(TaskType.TARGET_SCREENING) == "decision_brief.md.j2"
    assert brief_template_for(TaskType.MARKET_ANALYSIS) == "market_overview.md.j2"
    assert brief_template_for(TaskType.BOARD_PREP) == "board_update.md.j2"
    assert brief_template_for(TaskType.DOCUMENT_SYNTHESIS) == "document_synthesis.md.j2"
    assert brief_template_for(TaskType.INDUSTRY_NEWS) == "adhoc_brief.md.j2"


def test_render_brief_html_structure_and_bullets() -> None:
    """The HTML leads with the bottom line, renders sections, and converts bullet lines."""
    analysis = AnalysisOutput(
        title="1X — Competitive Brief",
        language=Language.EN,
        bottom_line="1X is well funded; Neura must differentiate on cognition.",
        sections=[
            Section(heading="Three rivals are closing in", body="- 1X: $100M\n- Figure: $675M")
        ],
        sources=[SourceRef(url="https://reuters.com/x", title="round")],
    )
    html = render_brief_html(analysis, AppConfig(), task_type=TaskType.COMPETITOR_ANALYSIS)
    assert "1X — Competitive Brief" in html
    assert "1X is well funded" in html
    assert "Three rivals are closing in" in html
    assert "<li>1X: $100M</li>" in html and "<li>Figure: $675M</li>" in html
    assert "Executive Summary" in html  # T-1 bottom-line label (EN)
    assert "https://reuters.com/x" in html


def test_render_brief_html_is_bilingual() -> None:
    """A German analysis renders German labels; an English one renders English labels."""
    base = dict(title="T", bottom_line="b", sections=[Section(heading="h", body="x")], sources=[])
    de = render_brief_html(
        AnalysisOutput(language=Language.DE, **base),  # type: ignore[arg-type]
        AppConfig(),
        task_type=TaskType.TARGET_SCREENING,
    )
    en = render_brief_html(
        AnalysisOutput(language=Language.EN, **base),  # type: ignore[arg-type]
        AppConfig(),
        task_type=TaskType.TARGET_SCREENING,
    )
    assert "Empfehlung" in de and "Entscheidungsanalyse" in de
    assert "Recommendation" in en and "Decision Analysis" in en


def test_render_brief_html_escapes_markup() -> None:
    """User/LLM text is HTML-escaped (no injection through the analysis)."""
    analysis = AnalysisOutput(
        title="A <script>alert(1)</script>",
        language=Language.EN,
        bottom_line="b & c < d",
        sections=[],
        sources=[],
    )
    html = render_brief_html(analysis, AppConfig(), task_type=TaskType.ADHOC)
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "b &amp; c &lt; d" in html


def test_build_brief_pdf_failfast_or_renders(tmp_path: Path) -> None:
    """build_brief_pdf renders a .pdf when WeasyPrint+GTK are present, else fails fast."""
    try:
        import weasyprint  # noqa: F401

        available = True
    except Exception:  # ImportError or OSError (missing/!broken GTK runtime)
        available = False

    if available:
        path = build_brief_pdf(
            _analysis(), AppConfig(), tmp_path, task_type=TaskType.COMPETITOR_ANALYSIS
        )
        assert path.exists() and path.suffix == ".pdf"
    else:
        with pytest.raises(PdfBuildError):
            build_brief_pdf(_analysis(), AppConfig(), tmp_path, task_type=TaskType.ADHOC)


# ----------------------------------------------------------------- deck (all 10 slide types)
def _full_deck() -> DeckStructure:
    return DeckStructure(
        title="Neura Q2 Board",
        language=Language.EN,
        slides=[
            SlideContent(
                slide_type=SlideType.TITLE, headline="Neura Board Update Q2", body="Board"
            ),
            SlideContent(
                slide_type=SlideType.EXECUTIVE_SUMMARY,
                headline="Runway is 9 months",
                bullets=["Cash 10.8M", "Burn 1.2M/mo"],
            ),
            SlideContent(slide_type=SlideType.MARKET_LANDSCAPE, headline="Rivals closing in"),
            SlideContent(slide_type=SlideType.COMPANY_DEEP_DIVE, headline="Figure scaling"),
            SlideContent(slide_type=SlideType.FINANCIAL_OVERVIEW, headline="Funding up"),
            SlideContent(
                slide_type=SlideType.COMPETITIVE_COMPARISON,
                headline="Neura leads on cognition",
                table=[["Company", "Funding"], ["Neura", "120M"], ["Figure", "675M"]],
            ),
            SlideContent(slide_type=SlideType.STRATEGIC_SIGNALS, headline="Hiring signals push"),
            SlideContent(
                slide_type=SlideType.SWOT,
                headline="Strong tech, thin capital",
                table=[
                    ["Strengths", "Cognitive AI; Bosch"],
                    ["Weaknesses", "Less capital"],
                    ["Opportunities", "EU industrial"],
                    ["Threats", "US scale"],
                ],
            ),
            SlideContent(
                slide_type=SlideType.RECOMMENDATION,
                headline="Approve the bridge round now",
                body="GO — raise €80M bridge",
                bullets=["Extends runway 18mo"],
            ),
            SlideContent(
                slide_type=SlideType.APPENDIX, headline="Sources", bullets=["reuters.com/x"]
            ),
        ],
    )


def test_build_deck_all_slide_types_with_logo(tmp_path: Path) -> None:
    """build_deck renders all 10 slide types, one slide each, with the logo bottom-right."""
    pptx = pytest.importorskip("pptx")
    path = build_deck(_full_deck(), AppConfig(), tmp_path)
    assert path.exists() and path.suffix == ".pptx"

    prs = pptx.Presentation(str(path))
    assert len(prs.slides) == 10
    # Logo (a picture, shape_type == 13) appears on every slide (SPEC §11).
    for slide in prs.slides:
        assert any(shape.shape_type == 13 for shape in slide.shapes)
    # The "so what" recommendation headline and its decision callout are present.
    all_text = " ".join(
        shape.text_frame.text
        for slide in prs.slides
        for shape in slide.shapes
        if shape.has_text_frame
    )
    assert "Approve the bridge round now" in all_text
    assert "GO — raise" in all_text
    # The comparison table cells made it into the deck.
    assert "Cognitive AI" in all_text  # SWOT quadrant content


def test_build_deck_no_logo_when_disabled(tmp_path: Path) -> None:
    """With include_logo off, no picture is added (the bottom-right logo is config-gated)."""
    pptx = pytest.importorskip("pptx")
    config = AppConfig()
    config.output.include_logo = False
    path = build_deck(_full_deck(), config, tmp_path)
    prs = pptx.Presentation(str(path))
    assert all(all(shape.shape_type != 13 for shape in slide.shapes) for slide in prs.slides)
