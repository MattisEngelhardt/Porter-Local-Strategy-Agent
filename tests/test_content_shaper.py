"""Tests for output shaping (core/content_shaper.py): prose analysis -> typed DeckStructure.

The LLM is scripted so shaping runs offline and deterministically; fail-open paths fall back to
the deterministic management deck structure.
"""

from __future__ import annotations

from typing import Any

from core.content_shaper import shape_deck, shape_workbook, workbook_template_for
from llm.local_llm_client import LLMError
from models.deck import SlideType
from models.synthesis import AnalysisOutput, Section, SourceRef
from models.task import Intent, Language, OutputFormat, TaskType
from models.workbook import (
    BenchmarkData,
    BusinessCaseData,
    DecisionMatrixData,
    ExcelTemplate,
    TrackerData,
)


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


# ----------------------------------------------------------------- shape_workbook (E-1..E-4)
def test_workbook_template_routing() -> None:
    """Task types route to the right Excel template (SPEC §12)."""
    assert workbook_template_for(TaskType.TARGET_SCREENING) == ExcelTemplate.DECISION_MATRIX
    assert workbook_template_for(TaskType.FINANCIAL_BENCHMARK) == ExcelTemplate.BENCHMARK_TABLE
    assert workbook_template_for(TaskType.BUSINESS_CASE) == ExcelTemplate.BUSINESS_CASE_MODEL
    assert workbook_template_for(TaskType.PIPELINE_TRACKING) == ExcelTemplate.TRACKER_DASHBOARD
    assert workbook_template_for(TaskType.ADHOC) == ExcelTemplate.DECISION_MATRIX  # default


def test_shape_workbook_decision_matrix() -> None:
    """A screening task shapes a DecisionMatrixData with parsed criteria + entity scores."""
    response = """{
      "criteria": [{"name": "Technology Fit", "weight": 30, "definition": "complementary"},
                   {"name": "Market Access", "weight": 25}],
      "entities": [{"name": "Dexory", "scores": [4, 5], "notes": ["patents", "UK"]},
                   {"name": "Exotec", "scores": [3, 4]}]
    }"""
    template, data = shape_workbook(
        _Client(response), _intent(TaskType.TARGET_SCREENING), _analysis()
    )
    assert template == ExcelTemplate.DECISION_MATRIX
    assert isinstance(data, DecisionMatrixData)
    assert [c.name for c in data.criteria] == ["Technology Fit", "Market Access"]
    assert data.entities[0].name == "Dexory" and data.entities[0].scores == [4, 5]


def test_shape_workbook_business_case_parses_numbers() -> None:
    """A business case shapes BusinessCaseData with numeric drivers coerced from JSON."""
    response = """{"investment": 2000000, "revenue_year1": 1500000, "revenue_growth": 0.4,
      "opex_year1": 900000, "opex_growth": 0.15, "discount_rate": 0.12, "years": 3,
      "assumptions": [{"name": "Market size", "value": 500000000, "unit": "EUR",
                       "confidence": "Estimate"}], "bottom_line": "Phased entry."}"""
    template, data = shape_workbook(_Client(response), _intent(TaskType.BUSINESS_CASE), _analysis())
    assert template == ExcelTemplate.BUSINESS_CASE_MODEL
    assert isinstance(data, BusinessCaseData)
    assert data.investment == 2_000_000 and data.revenue_growth == 0.4
    assert data.years == 3 and data.assumptions[0].name == "Market size"


def test_shape_workbook_benchmark_and_tracker() -> None:
    """Benchmark + tracker tasks shape their respective typed data."""
    bench_resp = (
        '{"metrics": ["Founded", "HQ"], "rows": [{"name": "Figure", "values": ["2022", "US"]}]}'
    )
    template, data = shape_workbook(
        _Client(bench_resp), _intent(TaskType.FINANCIAL_BENCHMARK), _analysis()
    )
    assert template == ExcelTemplate.BENCHMARK_TABLE
    assert isinstance(data, BenchmarkData) and data.metrics == ["Founded", "HQ"]

    track_resp = '{"items": [{"name": "Dexory", "category": "Warehouse", "status": "Active"}]}'
    template2, data2 = shape_workbook(
        _Client(track_resp), _intent(TaskType.PIPELINE_TRACKING), _analysis()
    )
    assert template2 == ExcelTemplate.TRACKER_DASHBOARD
    assert isinstance(data2, TrackerData) and data2.items[0].name == "Dexory"


def test_shape_workbook_failopen_to_deterministic_matrix() -> None:
    """An LLM error falls back to a deterministic matrix built from the analysis (never blocks)."""
    template, data = shape_workbook(
        _Client(raise_error=True), _intent(TaskType.TARGET_SCREENING), _analysis()
    )
    assert template == ExcelTemplate.DECISION_MATRIX
    assert isinstance(data, DecisionMatrixData)
    assert data.criteria and data.entities  # non-empty fallback (criteria + ≥1 entity)


def test_shape_workbook_explicit_template_overrides_routing() -> None:
    """An explicit template argument wins over the task-type routing."""
    template, data = shape_workbook(
        _Client("not json"),
        _intent(TaskType.TARGET_SCREENING),
        _analysis(),
        template=ExcelTemplate.TRACKER_DASHBOARD,
    )
    assert template == ExcelTemplate.TRACKER_DASHBOARD
    assert isinstance(data, TrackerData)
