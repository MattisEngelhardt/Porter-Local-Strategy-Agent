"""Tests for internal document-preparation mode (core/doc_synthesis.py + routing + pipeline).

LLM calls are faked (offline). Covers the research-vs-doc-prep router, the briefing synthesis +
Markdown blueprint, and the pipeline's document-prep branch (no research, no planning).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from core.config import AppConfig
from core.doc_synthesis import (
    propose_doc_questions,
    synthesize_briefing,
    to_management_markdown,
    write_briefing_md,
)
from core.intent_parser import classify_work_mode, route_mode
from core.pipeline import AutoInteraction, _resolve_doc_mode, run_pipeline
from core.playbooks import load_playbooks
from models.research import DocContent
from models.task import Intent, Language, OutputFormat, TaskRequest, TaskType, WorkMode

_BRIEFING_JSON = (
    '{"title": "Q2 Board Update", "bottom_line": "Runway is 9 months; approve the bridge round.", '
    '"sections": [{"heading": "Cash runway shortens to 9 months", "body": "Burn 1.2M/mo (memo.pdf)."}], '  # noqa: E501
    '"sources": [{"url": "memo.pdf", "title": "Q2 financials"}]}'
)


class _Client:
    """Records generate() kwargs and returns a fixed briefing JSON."""

    def __init__(self, response: str = _BRIEFING_JSON) -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    def generate(self, prompt: str, system: str = "", use_thinking: Any = None, **kw: Any) -> str:
        self.calls.append({"prompt": prompt, "system": system, "use_thinking": use_thinking})
        return self.response


def _intent(**kw: Any) -> Intent:
    base: dict[str, Any] = {
        "task_type": TaskType.DOCUMENT_SYNTHESIS,
        "output_formats": [OutputFormat.BRIEF],
        "language": Language.EN,
        "summary": "Consolidate the board pack",
    }
    base.update(kw)
    return Intent(**base)


def _doc(name: str = "memo.pdf") -> DocContent:
    return DocContent(
        source_path=Path(name),
        doc_type="pdf",
        text="Burn rate is 1.2M per month. Cash runway 9 months. Bridge round proposed.",
        extraction_method="pdfplumber",
    )


# ------------------------------------------------------------------ routing
def test_route_mode_documents_default_to_doc_prep() -> None:
    """Attached documents → DOCUMENT_PREP; no documents → RESEARCH."""
    assert route_mode("Summarize this for the board", True, TaskType.DOCUMENT_SYNTHESIS) == (
        WorkMode.DOCUMENT_PREP
    )
    assert route_mode("Analyze Figure AI", False, TaskType.COMPETITOR_ANALYSIS) == (
        WorkMode.RESEARCH
    )


def test_route_mode_explicit_research_overrides_documents() -> None:
    """A task that demands fresh web data routes to RESEARCH even with documents attached."""
    assert (
        route_mode(
            "Compare this memo against the latest market data online",
            True,
            TaskType.DOCUMENT_SYNTHESIS,
        )
        == WorkMode.RESEARCH
    )
    assert route_mode("Recherchiere dazu", True, TaskType.ADHOC) == WorkMode.RESEARCH


def test_classify_work_mode_returns_none_when_unsure() -> None:
    """Ambiguous tasks with documents return None (→ caller asks); clear ones are decided."""
    assert classify_work_mode("market overview of robotics", has_documents=False) == (
        WorkMode.RESEARCH
    )
    assert classify_work_mode("Consolidate these for the board", has_documents=True) == (
        WorkMode.DOCUMENT_PREP
    )
    assert classify_work_mode("Recherchiere die aktuelle Marktdaten", has_documents=True) == (
        WorkMode.RESEARCH
    )
    # Documents attached but no clear instruction → unsure → None (the agent must ask).
    assert classify_work_mode("Here are some files I need handled.", has_documents=True) is None


class _ChoiceInteraction:
    """Records ask_choice questions and returns a preset choice."""

    def __init__(self, choice: str) -> None:
        self.choice = choice
        self.asked: list[str] = []

    def ask_choice(self, question: str, options: list[str]) -> str:
        self.asked.append(question)
        return self.choice

    def ask_text(self, question: str) -> str:
        return ""

    def confirm(self, prompt: str) -> bool:
        return True

    def notify(self, message: str) -> None:
        pass


def test_resolve_doc_mode_asks_only_when_unsure() -> None:
    """A clear task decides without asking; an unclear one asks and honors the user's choice."""
    # Clear doc-prep task → no question asked.
    clear = _ChoiceInteraction("ignored")
    assert _resolve_doc_mode("Consolidate these for the board", clear, Language.EN) == (
        WorkMode.DOCUMENT_PREP
    )
    assert clear.asked == []

    # Unclear task → the agent asks; the user picks research.
    ask_research = _ChoiceInteraction("Research the web")
    assert _resolve_doc_mode("Here are some files.", ask_research, Language.EN) == WorkMode.RESEARCH
    assert len(ask_research.asked) == 1

    # Unclear task → the user picks prepare.
    ask_prep = _ChoiceInteraction("Only prepare for management")
    assert _resolve_doc_mode("Here are some files.", ask_prep, Language.EN) == (
        WorkMode.DOCUMENT_PREP
    )


# ------------------------------------------------------------ clarifying questions
def test_propose_doc_questions_parses_array() -> None:
    """The agent reads the docs and returns up to N targeted questions (no thinking)."""
    client = _Client('["Which theme should lead — runway or the M&A pipeline?", "PDF or deck?"]')
    qs = propose_doc_questions(client, _intent(), [_doc()], max_questions=2)  # type: ignore[arg-type]
    assert qs == ["Which theme should lead — runway or the M&A pipeline?", "PDF or deck?"]
    assert client.calls[0]["use_thinking"] is False


def test_propose_doc_questions_budget_zero_or_failopen() -> None:
    """Zero budget asks nothing; unparseable output fails open to no questions."""
    assert propose_doc_questions(_Client("[]"), _intent(), [_doc()], 0) == []  # type: ignore[arg-type]
    assert propose_doc_questions(_Client("not json"), _intent(), [_doc()], 2) == []  # type: ignore[arg-type]


def test_synthesize_briefing_injects_guidance() -> None:
    """User answers (guidance) are injected into the briefing prompt."""
    client = _Client()
    synthesize_briefing(
        client,  # type: ignore[arg-type]
        _intent(),
        [_doc()],
        "",
        load_playbooks(),
        guidance="Q: Lead with what?\nA: Lead with the runway risk.",
    )
    assert "USER GUIDANCE" in client.calls[0]["prompt"]
    assert "runway risk" in client.calls[0]["prompt"]


# ------------------------------------------------------------ synthesize_briefing
def test_synthesize_briefing_uses_thinking_and_parses() -> None:
    """The briefing reads documents with thinking on and parses into a structured analysis."""
    client = _Client()
    out = synthesize_briefing(client, _intent(), [_doc()], "", load_playbooks())  # type: ignore[arg-type]
    assert out.title == "Q2 Board Update"
    assert "9 months" in out.bottom_line
    assert client.calls[0]["use_thinking"] is True
    # The document text + the zero-hallucination rule reach the model.
    assert "memo.pdf" in client.calls[0]["prompt"]
    assert "ZERO HALLUCINATION" in client.calls[0]["system"]


def test_to_management_markdown_blueprint_structure() -> None:
    """The Markdown blueprint leads with the bottom line and lists the source documents."""
    out = synthesize_briefing(_Client(), _intent(), [_doc()], "", load_playbooks())  # type: ignore[arg-type]
    md = to_management_markdown(out, [_doc()], Language.EN)
    assert md.startswith("# Q2 Board Update")
    assert "## Bottom Line" in md
    assert "Cash runway shortens to 9 months" in md  # the section's "so what" heading
    assert "memo.pdf" in md  # source document listed


def test_write_briefing_md(tmp_path: Path) -> None:
    """The blueprint is written to the output dir with a dated, slugged filename."""
    path = write_briefing_md("# Hi\n\ncontent", tmp_path, "Q2 Board Update")
    assert path.exists()
    assert path.suffix == ".md"
    assert "board_update" in path.name
    assert path.read_text(encoding="utf-8").startswith("# Hi")


# ------------------------------------------------------------ pipeline branch
def test_run_pipeline_routes_to_document_prep(tmp_path: Path) -> None:
    """With documents attached, run_pipeline takes the doc-prep branch (no research, writes .md)."""
    config = AppConfig()
    config.output.output_dir = str(tmp_path)

    # One client answers all three calls, routed by a unique token in each system prompt:
    # classifier → intent; synthesis (carries ZERO HALLUCINATION) → briefing; else → questions.
    class _Routed:
        def generate(
            self, prompt: str, system: str = "", use_thinking: Any = None, **kw: Any
        ) -> str:
            low = system.lower()
            if "intent classifier" in low:
                return (
                    '{"task_type":"document_synthesis","depth":"standard","summary":"board pack"}'
                )
            if "zero hallucination" in low:
                return _BRIEFING_JSON
            return '["Lead with runway or the M&A pipeline?"]'

    interaction = AutoInteraction(text_answers=["Lead with the runway risk."])
    result = run_pipeline(
        _Routed(),  # type: ignore[arg-type]
        config,
        TaskRequest(raw_input="Consolidate this board pack for management"),
        interaction,
        documents=[_doc()],
    )
    assert result.mode == "document_prep"
    assert result.analysis is not None
    assert result.analysis.title == "Q2 Board Update"
    assert result.artifact_path is not None and result.artifact_path.exists()
    assert result.research_report is None  # no research ran
    # The agent asked its targeted question and captured the answer.
    assert interaction.asked_text == ["Lead with runway or the M&A pipeline?"]
    assert result.answered and result.answered[0].answer == "Lead with the runway risk."
