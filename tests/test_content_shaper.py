"""Tests for output shaping (core/content_shaper.py): prose analysis -> typed DeckStructure.

The LLM is scripted so shaping runs offline and deterministically; fail-open paths fall back to
the deterministic management deck structure.
"""

from __future__ import annotations

from typing import Any

from core.content_shaper import shape_deck
from llm.local_llm_client import LLMError
from models.deck import SlideType
from models.synthesis import AnalysisOutput, Section, SourceRef
from models.task import Intent, Language, OutputFormat, TaskType


class _Client:
    """Returns a canned response (or raises) and records the system prompts it saw."""

    def __init__(self, response: str = "[]", raise_error: bool = False) -> None:
        self.response = response
        self.raise_error = raise_error
        self.systems: list[str] = []

    def generate(self, prompt: str, system: str = "", use_thinking: Any = None, **kw: Any) -> str:
        self.systems.append(system)
        if self.raise_error:
            raise LLMError("backend down")
        return self.response


def _analysis() -> AnalysisOutput:
    return AnalysisOutput(
        title="1X Technologies — Brief",
        language=Language.EN,
        bottom_line="1X is well funded; Neura must differentiate on cognition.",
        sections=[Section(heading="Funding accelerates", body="1X raised $100M in 2026.")],
        sources=[SourceRef(url="https://reuters.com/x", title="round")],
    )


def _intent(task_type: TaskType = TaskType.COMPETITOR_ANALYSIS) -> Intent:
    return Intent(
        task_type=task_type,
        output_formats=[OutputFormat.DECK],
        language=Language.EN,
        summary="Analyze 1X",
    )


def test_shape_deck_parses_typed_slides() -> None:
    """A valid JSON array becomes a typed DeckStructure (slide types + table coerced)."""
    response = """[
      {"slide_type": "title", "headline": "1X Technologies", "body": "Brief"},
      {"slide_type": "executive_summary", "headline": "1X closing the gap",
       "bullets": ["$100M raised"]},
      {"slide_type": "competitive_comparison", "headline": "Neura leads on cognition",
       "table": [["Company", "Funding"], ["Neura", "120M"], ["1X", "100M"]]},
      {"slide_type": "recommendation", "headline": "Accelerate integration", "body": "WATCH"}
    ]"""
    deck = shape_deck(_Client(response), _intent(), _analysis())
    types = [s.slide_type for s in deck.slides]
    assert types == [
        SlideType.TITLE,
        SlideType.EXECUTIVE_SUMMARY,
        SlideType.COMPETITIVE_COMPARISON,
        SlideType.RECOMMENDATION,
    ]
    assert deck.slides[2].table == [["Company", "Funding"], ["Neura", "120M"], ["1X", "100M"]]
    assert deck.slides[3].body == "WATCH"


def test_shape_deck_inserts_title_if_missing() -> None:
    """If the model omits a leading title slide, one is prepended from the analysis title."""
    response = '[{"slide_type": "executive_summary", "headline": "Bottom line", "bullets": ["x"]}]'
    deck = shape_deck(_Client(response), _intent(), _analysis())
    assert deck.slides[0].slide_type == SlideType.TITLE
    assert deck.slides[0].headline == "1X Technologies — Brief"


def test_shape_deck_business_case_requests_scr() -> None:
    """A business case injects the SCR ordering instruction into the shaping prompt (§13)."""
    client = _Client('[{"slide_type":"title","headline":"BC"}]')
    shape_deck(client, _intent(TaskType.BUSINESS_CASE), _analysis())
    assert "SCR" in client.systems[0] and "Situation" in client.systems[0]


def test_shape_deck_failopen_on_llm_error() -> None:
    """An LLM error falls back to the deterministic management deck structure."""
    deck = shape_deck(_Client(raise_error=True), _intent(), _analysis())
    assert deck.slides[0].slide_type == SlideType.TITLE
    headings = " ".join(s.headline for s in deck.slides)
    assert "Funding accelerates" in headings  # section became a fallback slide


def test_shape_deck_failopen_on_bad_json() -> None:
    """An unparseable response falls back to the deterministic structure (no crash)."""
    deck = shape_deck(_Client("not json at all"), _intent(), _analysis())
    assert deck.slides[0].slide_type == SlideType.TITLE
    assert any(s.slide_type == SlideType.EXECUTIVE_SUMMARY for s in deck.slides)
