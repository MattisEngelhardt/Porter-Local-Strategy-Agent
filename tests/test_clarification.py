"""Tests for the clarification dialog (core/clarification.py)."""

from __future__ import annotations

from core.clarification import clarify, question_budget
from models.task import Audience, Depth, Intent, Language, OutputFormat, TaskRequest, TaskType


class _Ask:
    """A scripted question asker; records calls and replays canned answers (then first option)."""

    def __init__(self, *answers: str) -> None:
        self._answers = list(answers)
        self.calls: list[tuple[str, list[str]]] = []

    def __call__(self, question: str, options: list[str]) -> str:
        self.calls.append((question, options))
        return self._answers.pop(0) if self._answers else options[0]


def _intent(task_type: TaskType, formats: list[OutputFormat], **kw: object) -> Intent:
    base: dict[str, object] = {
        "task_type": task_type,
        "output_formats": formats,
        "language": Language.EN,
        "depth": Depth.STANDARD,
        "audience": None,
    }
    base.update(kw)
    return Intent(**base)  # type: ignore[arg-type]


# ------------------------------------------------------------------- budget
def test_question_budget_scales_with_complexity() -> None:
    """Complex tasks/multi-format → 3; quick → 1; standard → 2; capped by max_rounds."""
    assert (
        question_budget(_intent(TaskType.BUSINESS_CASE, [OutputFormat.DECK, OutputFormat.EXCEL]), 3)
        == 3
    )
    assert question_budget(_intent(TaskType.INDUSTRY_NEWS, [OutputFormat.BRIEF]), 3) == 1
    assert question_budget(_intent(TaskType.COMPETITOR_ANALYSIS, [OutputFormat.BRIEF]), 3) == 2
    # max_rounds caps the budget
    assert (
        question_budget(_intent(TaskType.BUSINESS_CASE, [OutputFormat.DECK, OutputFormat.EXCEL]), 1)
        == 1
    )


# --------------------------------------------------------- scope (the triple)
def test_scope_question_resolves_format_audience_depth() -> None:
    """Answering the scope triple sets format + audience + depth in one shot."""
    intent = _intent(TaskType.COMPETITOR_ANALYSIS, [OutputFormat.BRIEF])
    ask = _Ask("Management deck")
    out, answered = clarify(intent, TaskRequest(raw_input="Analyze 1X Technologies"), ask, 3)
    assert out.output_formats == [OutputFormat.DECK]
    assert out.audience == Audience.CEO_BOARD
    assert out.depth == Depth.DEEP
    assert len(answered) == 1
    assert len(ask.calls) == 1  # exactly one question asked


def test_scope_uses_language_for_question_text() -> None:
    """A German intent gets the German question + option labels."""
    intent = _intent(TaskType.MARKET_ANALYSIS, [OutputFormat.BRIEF], language=Language.DE)
    ask = _Ask("Strategy Brief")
    out, answered = clarify(intent, TaskRequest(raw_input="Marktanalyse Humanoid Robotics"), ask, 3)
    assert "Strategy Brief fürs Team" in answered[0].question
    assert out.audience == Audience.STRATEGY_TEAM


# -------------------------------------------------- nothing to ask (inference)
def test_no_questions_when_everything_inferred() -> None:
    """Explicit format + known audience → zero questions asked."""
    intent = _intent(
        TaskType.COMPETITOR_ANALYSIS,
        [OutputFormat.DECK],
        depth=Depth.DEEP,
        audience=Audience.CEO_BOARD,
    )
    ask = _Ask()
    out, answered = clarify(
        intent, TaskRequest(raw_input="Make a deck on 1X Technologies for the board"), ask, 3
    )
    assert answered == []
    assert ask.calls == []


# ------------------------------------------------------ excel screening flow
def test_excel_screening_asks_kind_then_audience() -> None:
    """A screening task asks the matrix/benchmark choice, then audience — one at a time."""
    intent = _intent(
        TaskType.TARGET_SCREENING,
        [OutputFormat.EXCEL, OutputFormat.BRIEF],
        language=Language.DE,
    )
    ask = _Ask("Decision Matrix", "Strategy-Team")
    out, answered = clarify(
        intent, TaskRequest(raw_input="Screen diese 5 Startups als Targets"), ask, 3
    )
    assert len(answered) == 2
    assert "Decision Matrix" in answered[0].question
    assert answered[0].answer == "Decision Matrix"
    assert out.audience == Audience.STRATEGY_TEAM
    # excel routing is preserved (the kind question doesn't drop the brief)
    assert out.output_formats == [OutputFormat.EXCEL, OutputFormat.BRIEF]


# --------------------------------------------------------- budget hard cap
def test_max_rounds_caps_questions() -> None:
    """With max_rounds=1, only one question is asked even if more are relevant."""
    intent = _intent(TaskType.TARGET_SCREENING, [OutputFormat.EXCEL, OutputFormat.BRIEF])
    ask = _Ask()
    _out, answered = clarify(
        intent, TaskRequest(raw_input="Screen these 5 startups as targets"), ask, 1
    )
    assert len(answered) == 1
    assert len(ask.calls) == 1


def test_default_to_first_option_on_unmatched_answer() -> None:
    """An unrecognized answer falls back to the first option (never crashes)."""
    intent = _intent(TaskType.COMPETITOR_ANALYSIS, [OutputFormat.BRIEF])
    ask = _Ask("???")
    out, answered = clarify(intent, TaskRequest(raw_input="Analyze Figure AI"), ask, 3)
    # first scope option = Quick Brief → personal/brief/quick
    assert out.output_formats == [OutputFormat.BRIEF]
    assert out.audience == Audience.PERSONAL
    assert len(answered) == 1
