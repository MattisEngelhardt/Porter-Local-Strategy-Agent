"""Tests for the intent parser (core/intent_parser.py).

The LLM classification call is faked so the suite runs fully offline. Routing and language
detection are deterministic and asserted directly.
"""

from __future__ import annotations

from typing import Any

from core.config import AgentConfig, AppConfig
from core.intent_parser import (
    detect_effort,
    detect_explicit_formats,
    detect_language,
    parse_effort_override,
    parse_intent,
    route_outputs,
)
from llm.local_llm_client import LLMError
from models.task import Depth, EffortLevel, Language, OutputFormat, TaskRequest, TaskType


class _FakeClient:
    """Returns a fixed canned response, ignoring the prompt (stands in for LocalLLMClient)."""

    def __init__(self, response: str) -> None:
        self.response = response

    def generate(self, prompt: str, **kwargs: Any) -> str:
        return self.response


class _RaisingClient:
    """Raises LLMError on generate (simulates an unreachable backend)."""

    def generate(self, prompt: str, **kwargs: Any) -> str:
        raise LLMError("backend down")


def _task(text: str) -> TaskRequest:
    return TaskRequest(raw_input=text)


# ------------------------------------------------------------------ language
def test_detect_language_heuristic() -> None:
    """Umlauts / German function words → DE; otherwise EN."""
    assert detect_language("Was macht Neura Robotics für uns?") == Language.DE
    assert detect_language("What is the market size for humanoid robots?") == Language.EN
    assert detect_language("Screen diese 5 Startups als Targets") == Language.DE


def test_detect_language_config_override() -> None:
    """An explicit default_language overrides the heuristic."""
    assert detect_language("humanoid robots", "de") == Language.DE
    assert detect_language("Bereite ein Deck für das Management vor", "en") == Language.EN


# -------------------------------------------------------------------- routing
def test_route_outputs_spec_table() -> None:
    """Defaults follow the SPEC §5.4 task→output map, incl. Business Case dual output (N-6)."""
    assert route_outputs(TaskType.BUSINESS_CASE) == [OutputFormat.DECK, OutputFormat.EXCEL]
    assert route_outputs(TaskType.TARGET_SCREENING) == [OutputFormat.EXCEL, OutputFormat.BRIEF]
    assert route_outputs(TaskType.BOARD_PREP) == [OutputFormat.DECK]
    assert route_outputs(TaskType.PIPELINE_TRACKING) == [OutputFormat.EXCEL]
    assert route_outputs(TaskType.COMPETITOR_ANALYSIS) == [OutputFormat.BRIEF]


def test_route_outputs_explicit_override() -> None:
    """An explicitly requested format overrides the task default."""
    assert route_outputs(TaskType.COMPETITOR_ANALYSIS, [OutputFormat.DECK]) == [OutputFormat.DECK]


def test_detect_explicit_formats() -> None:
    """Format keywords (DE/EN) are detected; plain tasks yield nothing."""
    assert OutputFormat.DECK in detect_explicit_formats("mach mir ein Deck dazu")
    assert OutputFormat.EXCEL in detect_explicit_formats("create an Excel matrix")
    assert detect_explicit_formats("analyze Figure AI funding") == []


# -------------------------------------------------------------- parse_intent
def test_parse_intent_business_case_dual_output() -> None:
    """A business case routes to the dual PPTX + Excel output (N-6)."""
    client = _FakeClient(
        '{"task_type":"business_case","depth":"deep","audience":"ceo_board","summary":"Japan"}'
    )
    intent = parse_intent(
        client,  # type: ignore[arg-type]
        AppConfig(),
        _task("Business case for Japan expansion: market size, investment, ROI"),
    )
    assert intent.task_type == TaskType.BUSINESS_CASE
    assert intent.output_formats == [OutputFormat.DECK, OutputFormat.EXCEL]
    assert intent.language == Language.EN
    assert intent.depth == Depth.DEEP


def test_parse_intent_german_input_stays_german() -> None:
    """Language comes from the heuristic (DE here), independent of the LLM JSON."""
    client = _FakeClient(
        '{"task_type":"target_screening","depth":"standard","audience":null,"summary":"x"}'
    )
    intent = parse_intent(
        client,  # type: ignore[arg-type]
        AppConfig(),
        _task("Screen diese 5 europäischen Robotics Startups als M&A Targets"),
    )
    assert intent.language == Language.DE
    assert intent.task_type == TaskType.TARGET_SCREENING
    assert intent.output_formats == [OutputFormat.EXCEL, OutputFormat.BRIEF]


def test_parse_intent_tolerates_messy_json() -> None:
    """Fenced / prose-wrapped JSON is still parsed (tolerant extraction)."""
    messy = (
        "Sure! Here you go:\n```json\n"
        '{"task_type":"board_prep","depth":"deep","audience":"ceo_board","summary":"deck"}\n'
        "```\nHope that helps."
    )
    intent = parse_intent(
        _FakeClient(messy),  # type: ignore[arg-type]
        AppConfig(),
        _task("Board deck on our competitive position"),
    )
    assert intent.task_type == TaskType.BOARD_PREP
    assert intent.output_formats == [OutputFormat.DECK]


def test_parse_intent_llm_failure_defaults() -> None:
    """An LLM failure yields conservative defaults (ADHOC / standard / brief)."""
    intent = parse_intent(
        _RaisingClient(),  # type: ignore[arg-type]
        AppConfig(),
        _task("hello there"),
    )
    assert intent.task_type == TaskType.ADHOC
    assert intent.depth == Depth.STANDARD
    assert intent.output_formats == [OutputFormat.BRIEF]


def test_parse_intent_config_language_override() -> None:
    """config.agent.default_language forces the output language."""
    client = _FakeClient('{"task_type":"adhoc","depth":"quick","audience":null,"summary":"x"}')
    config = AppConfig(agent=AgentConfig(default_language="de"))
    intent = parse_intent(client, config, _task("quick humanoid robotics news"))  # type: ignore[arg-type]
    assert intent.language == Language.DE


# -------------------------------------------------------------- effort (Phase 3.5)
def test_detect_effort_keyword_wins() -> None:
    """Explicit user words pin the effort (ULTRA beats LOW), over any LLM suggestion."""
    assert detect_effort("Vollständige Analyse von 1X", TaskType.ADHOC, None) == EffortLevel.ULTRA
    assert detect_effort("deep dive on Figure AI", TaskType.ADHOC, EffortLevel.LOW) == (
        EffortLevel.ULTRA
    )
    assert detect_effort("quick overview of the market", TaskType.ADHOC, None) == EffortLevel.LOW
    assert detect_effort("kurzer Überblick bitte", TaskType.ADHOC, None) == EffortLevel.LOW


def test_detect_effort_task_floor_and_default() -> None:
    """Heavy task types floor at HIGH; unsure defaults to HIGH (never shallow)."""
    # Business case with an LLM 'low' suggestion is floored up to HIGH.
    assert detect_effort("build a business case", TaskType.BUSINESS_CASE, EffortLevel.LOW) == (
        EffortLevel.HIGH
    )
    # A light task with no signal and no suggestion → HIGH default.
    assert detect_effort("tell me about Figure AI", TaskType.COMPETITOR_ANALYSIS, None) == (
        EffortLevel.HIGH
    )
    # A valid LLM suggestion is honored when no keyword / floor pushes higher.
    assert detect_effort("latest news", TaskType.INDUSTRY_NEWS, EffortLevel.LOW) == EffortLevel.LOW
    # Floor + higher suggestion → the higher wins.
    assert detect_effort("screen these", TaskType.TARGET_SCREENING, EffortLevel.ULTRA) == (
        EffortLevel.ULTRA
    )


def test_parse_effort_override() -> None:
    """A leading /effort token is stripped and wins; plain text is untouched."""
    level, rest = parse_effort_override("/effort ultra Analyze 1X Technologies")
    assert level == EffortLevel.ULTRA
    assert rest == "Analyze 1X Technologies"

    level2, rest2 = parse_effort_override("/EFFORT low quick market check")
    assert level2 == EffortLevel.LOW
    assert rest2 == "quick market check"

    none, original = parse_effort_override("just a normal task")
    assert none is None
    assert original == "just a normal task"


def test_parse_intent_effort_override_wins() -> None:
    """An explicit effort_override beats both the LLM hint and auto-detection."""
    client = _FakeClient(
        '{"task_type":"competitor_analysis","depth":"standard","effort":"low","audience":null,"summary":"x"}'  # noqa: E501
    )
    intent = parse_intent(
        client,  # type: ignore[arg-type]
        AppConfig(),
        _task("tell me about Figure AI"),
        effort_override=EffortLevel.ULTRA,
    )
    assert intent.effort == EffortLevel.ULTRA


def test_parse_intent_effort_from_llm_hint() -> None:
    """With no override/keyword, the LLM effort hint flows into the intent."""
    client = _FakeClient(
        '{"task_type":"competitor_analysis","depth":"standard","effort":"ultra","audience":null,"summary":"x"}'  # noqa: E501
    )
    intent = parse_intent(
        client,  # type: ignore[arg-type]
        AppConfig(),
        _task("analyze Figure AI"),
    )
    assert intent.effort == EffortLevel.ULTRA
