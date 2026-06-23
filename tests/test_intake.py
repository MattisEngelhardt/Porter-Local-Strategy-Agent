"""Tests for REPL file-path detection, document routing, and result rendering (core/intake.py)."""

from __future__ import annotations

from io import StringIO
from pathlib import Path

import pytest
from rich.console import Console

import core.intake as intake
import core.profile as profile_mod
from core.config import AppConfig
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
    assert "Routed" in out  # no files attached → routed (not "Generated")
    assert "excel" in out


def test_render_result_shows_generated_files() -> None:
    """When deliverables were rendered, render_result lists the file paths as Generated."""
    console = _capture_console()
    result = PipelineResult(
        intent=_intent(),
        routed_formats=[OutputFormat.BRIEF],
        analysis=AnalysisOutput(
            title="OneX Brief", language=Language.EN, bottom_line="Acquire now."
        ),
        output_files=[Path("output/2026-05-31_onex_brief.pdf")],
    )
    render_result(console, result, "cyan")
    out = console.file.getvalue()  # type: ignore[attr-defined]
    assert "Generated" in out
    assert "onex_brief.pdf" in out


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


def test_render_result_shows_delta_note() -> None:
    """A memory delta note renders as its own panel above the sections."""
    console = _capture_console()
    result = PipelineResult(
        intent=_intent(),
        routed_formats=[OutputFormat.BRIEF],
        analysis=AnalysisOutput(title="T", language=Language.EN, bottom_line="bl"),
        delta_note="Since our last analysis of Figure AI (2026-05-11, 3 weeks ago): up.",
    )
    render_result(console, result, "cyan")
    out = console.file.getvalue()  # type: ignore[attr-defined]
    assert "Since our last analysis of Figure AI" in out
    assert "delta" in out


def _brain_config(tmp_path: Path) -> AppConfig:
    config = AppConfig()
    config.memory.brain_path = str(tmp_path / "brain.md")
    return config


def test_maybe_update_brain_appends_on_confirm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Confirming [y] appends the proposed additions to brain.md."""
    config = _brain_config(tmp_path)
    result = PipelineResult(
        intent=_intent(), proposed_brain_additions=["Board decks: English only"]
    )
    monkeypatch.setattr(intake.Confirm, "ask", lambda *a, **k: True)
    intake._maybe_update_brain(_capture_console(), config, result, "cyan")
    text = Path(config.memory.brain_path).read_text(encoding="utf-8")
    assert "Board decks: English only" in text


def test_maybe_update_brain_skips_on_decline(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Declining [N] leaves brain.md untouched (default is No)."""
    config = _brain_config(tmp_path)
    result = PipelineResult(intent=_intent(), proposed_brain_additions=["X"])
    monkeypatch.setattr(intake.Confirm, "ask", lambda *a, **k: False)
    intake._maybe_update_brain(_capture_console(), config, result, "cyan")
    assert not Path(config.memory.brain_path).exists()


def test_maybe_update_brain_noop_without_proposals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With no proposals, the user is never prompted and nothing is written."""
    asked: list[bool] = []
    monkeypatch.setattr(intake.Confirm, "ask", lambda *a, **k: asked.append(True) or True)
    config = _brain_config(tmp_path)
    intake._maybe_update_brain(_capture_console(), config, PipelineResult(intent=_intent()), "cyan")
    assert asked == []
    assert not Path(config.memory.brain_path).exists()


class _StubVoiceObj:
    """Duck-typed VoiceInput stand-in: returns a canned transcript from capture_once()."""

    def __init__(self, transcript: str) -> None:
        self._transcript = transcript

    def capture_once(self) -> str:
        return self._transcript


def test_capture_voice_disabled_prints_enable_hint() -> None:
    """With voice off, /voice prints how to enable it and returns None."""
    console = _capture_console()
    assert intake._capture_voice(console, None, "cyan") is None
    out = console.file.getvalue()  # type: ignore[attr-defined]
    assert "voice.enabled" in out


def test_capture_voice_returns_transcript() -> None:
    """/voice returns the spoken transcript when capture succeeds."""
    console = _capture_console()
    result = intake._capture_voice(console, _StubVoiceObj("analyze figure ai"), "cyan")  # type: ignore[arg-type]
    assert result == "analyze figure ai"


def test_capture_voice_empty_returns_none() -> None:
    """An empty transcript (no speech) returns None (no task is run)."""
    console = _capture_console()
    assert intake._capture_voice(console, _StubVoiceObj("   "), "cyan") is None  # type: ignore[arg-type]


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


# --- /role dimension switch (Slice 1) -------------------------------------------------


def _role_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, initial: str | None = None
) -> Path:
    """Point core.profile at a tmp .porter_profile and clear the env override."""
    pfile = tmp_path / ".porter_profile"
    if initial is not None:
        pfile.write_text(initial + "\n", encoding="utf-8")
    monkeypatch.setattr(profile_mod, "_PROFILE_FILE", pfile)
    monkeypatch.delenv("PORTER_PROFILE", raising=False)
    return pfile


def test_role_switch_menu_persists_choice(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """/role opens the picker; the chosen role is written to .porter_profile."""
    pfile = _role_file(monkeypatch, tmp_path, initial="all")
    monkeypatch.setattr(intake, "select_choice", lambda *a, **k: "analyst")
    intake._handle_role_switch(_capture_console(), "cyan", "/role")
    assert pfile.read_text(encoding="utf-8").strip() == "analyst"


def test_role_switch_direct_arg_skips_menu(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """/role <name> switches directly, without opening the menu."""
    pfile = _role_file(monkeypatch, tmp_path, initial="all")

    def _no_menu(*a: object, **k: object) -> str:
        pytest.fail("menu must not open when a role name is given")

    monkeypatch.setattr(intake, "select_choice", _no_menu)
    intake._handle_role_switch(_capture_console(), "cyan", "/role Builder")
    assert pfile.read_text(encoding="utf-8").strip() == "builder"


def test_role_switch_cancel_keeps_current(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Cancelling the picker (None) leaves the active role unchanged."""
    pfile = _role_file(monkeypatch, tmp_path, initial="research")
    monkeypatch.setattr(intake, "select_choice", lambda *a, **k: None)
    intake._handle_role_switch(_capture_console(), "cyan", "/role")
    assert pfile.read_text(encoding="utf-8").strip() == "research"


def test_role_switch_unknown_arg_is_handled(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """/role <bogus> reports the error and leaves the role unchanged."""
    pfile = _role_file(monkeypatch, tmp_path, initial="all")
    console = _capture_console()
    intake._handle_role_switch(console, "cyan", "/role bogus")
    assert pfile.read_text(encoding="utf-8").strip() == "all"
    assert "unknown role" in console.file.getvalue()  # type: ignore[attr-defined]
