"""Tests for REPL file-path detection, document routing, and result rendering (core/intake.py)."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

import core.intake as intake
from core.intake import ReplInteraction, detect_file_path, read_document, render_result
from models.research import DocContent, FetchedContent, ResearchReport, SourceTier
from models.synthesis import AnalysisOutput, Critique, PipelineResult, Section, SourceRef
from models.task import EffortLevel, Intent, Language, OutputFormat, TaskType


def _doc(path: Path, doc_type: str) -> DocContent:
    return DocContent(source_path=path, doc_type=doc_type, text="x", extraction_method="stub")


def test_detect_file_path_recognizes_supported(tmp_path: Path) -> None:
    """A bare (or quoted) path to a supported file is detected."""
    pdf = tmp_path / "report.pdf"
    pdf.write_bytes(b"stub")
    assert detect_file_path(str(pdf)) == pdf
    assert detect_file_path(f'"{pdf}"') == pdf  # quoted (Windows paths with spaces)


def test_detect_file_path_ignores_non_paths(tmp_path: Path) -> None:
    """Questions, missing files, and unsupported types are not treated as docs."""
    assert detect_file_path("What does Neura Robotics build?") is None
    assert detect_file_path(str(tmp_path / "missing.pdf")) is None
    txt = tmp_path / "notes.txt"
    txt.write_text("hi", encoding="utf-8")
    assert detect_file_path(str(txt)) is None


def test_read_document_routes_by_suffix(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """.xlsx routes to the Excel reader; .pdf routes to the PDF reader."""
    monkeypatch.setattr(intake, "read_excel", lambda p: _doc(p, "xlsx"))
    monkeypatch.setattr(intake, "read_pdf", lambda p, llm=None: _doc(p, "pdf"))

    xlsx = tmp_path / "data.xlsx"
    xlsx.write_bytes(b"stub")
    pdf = tmp_path / "data.pdf"
    pdf.write_bytes(b"stub")

    assert read_document(xlsx).doc_type == "xlsx"
    assert read_document(pdf, llm=None).doc_type == "pdf"


def _intent() -> Intent:
    return Intent(
        task_type=TaskType.TARGET_SCREENING,
        output_formats=[OutputFormat.EXCEL, OutputFormat.BRIEF],
        language=Language.EN,
    )


def _capture_console() -> Console:
    return Console(file=StringIO(), width=120, force_terminal=False)


def test_render_result_shows_analysis_structure() -> None:
    """An analysis result renders bottom line, sections, sources, and the output plan."""
    console = _capture_console()
    result = PipelineResult(
        intent=_intent(),
        routed_formats=[OutputFormat.EXCEL, OutputFormat.BRIEF],
        analysis=AnalysisOutput(
            title="OneX Brief",
            language=Language.EN,
            bottom_line="Acquire OneX now.",
            sections=[Section(heading="Technology", body="Strong moat here.")],
            sources=[SourceRef(url="https://reuters.com/a", tier=SourceTier.TIER_1)],
        ),
    )
    render_result(console, result, "cyan")
    out = console.file.getvalue()  # type: ignore[attr-defined]
    assert "OneX Brief" in out
    assert "Acquire OneX now." in out
    assert "Technology" in out
    assert "reuters.com" in out
    assert "Would generate" in out
    assert "excel" in out


def test_render_result_shows_effort_telemetry() -> None:
    """The result panel surfaces the effort + self-correction telemetry (Phase 3.5)."""
    # Wide console so the single telemetry line is not wrapped mid-token.
    console = Console(file=StringIO(), width=240, force_terminal=False)
    result = PipelineResult(
        intent=_intent(),
        routed_formats=[OutputFormat.BRIEF],
        effort=EffortLevel.ULTRA,
        revisions=2,
        critique=Critique(passed=True, score=82),
        research_report=ResearchReport(
            workers_used=5,
            rounds_used=3,
            sources_evaluated=24,
            evidence=[FetchedContent(url="https://reuters.com/a", text="t")],
        ),
        analysis=AnalysisOutput(
            title="X", language=Language.EN, bottom_line="bl", sections=[], sources=[]
        ),
    )
    render_result(console, result, "cyan")
    out = console.file.getvalue()  # type: ignore[attr-defined]
    assert "ultra" in out
    assert "5 workers" in out
    assert "24 sources evaluated" in out
    assert "82/100" in out
    assert "2 revision" in out


def test_render_result_declined_shows_quick_answer() -> None:
    """A declined result shows the brain-based quick answer, not an analysis."""
    console = _capture_console()
    result = PipelineResult(
        intent=_intent(), routed_formats=[], declined=True, quick_answer="Short take here."
    )
    render_result(console, result, "cyan")
    out = console.file.getvalue()  # type: ignore[attr-defined]
    assert "Short take here." in out
    assert "quick answer" in out


def test_repl_interaction_ask_choice(monkeypatch: pytest.MonkeyPatch) -> None:
    """ask_choice prints the numbered options and returns the user's answer."""
    console = _capture_console()
    monkeypatch.setattr(intake.Prompt, "ask", lambda *a, **k: "2")
    interaction = ReplInteraction(console, "cyan")
    assert interaction.ask_choice("Pick one?", ["alpha", "beta"]) == "2"
    out = console.file.getvalue()  # type: ignore[attr-defined]
    assert "Pick one?" in out
    assert "alpha" in out


def test_repl_interaction_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    """confirm delegates to rich Confirm and returns its boolean."""
    monkeypatch.setattr(intake.Confirm, "ask", lambda *a, **k: False)
    assert ReplInteraction(_capture_console(), "cyan").confirm("Go?") is False


def test_repl_interaction_ask_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """ask_text shows the mid-research question and returns the user's free-form answer."""
    console = _capture_console()
    monkeypatch.setattr(intake.Prompt, "ask", lambda *a, **k: "  industrial segment  ")
    interaction = ReplInteraction(console, "cyan")
    assert interaction.ask_text("Which 1X do you mean — robotics or payments?") == (
        "industrial segment"
    )
    out = console.file.getvalue()  # type: ignore[attr-defined]
    assert "mid-research" in out
    assert "Which 1X" in out
