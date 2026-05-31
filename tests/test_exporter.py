"""Tests for output rendering (core/exporter.py): PPTX (live) + PDF (fail-fast without GTK)."""

from __future__ import annotations

from pathlib import Path

import pytest

from core.config import AppConfig
from core.exporter import PdfBuildError, build_management_deck, build_management_pdf
from models.synthesis import AnalysisOutput, Section, SourceRef
from models.task import Language


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
