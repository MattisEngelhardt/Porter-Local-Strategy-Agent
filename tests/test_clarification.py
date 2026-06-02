"""Tests for the clarification dialog (core/clarification.py)."""

from __future__ import annotations

from core.clarification import clarify, propose_scoping_questions, question_budget
from llm.local_llm_client import LLMError
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


# ------------------------------------------ situation-specific scoping questions
class _FakeLLM:
    """A minimal scripted LLM client; records calls and replays one canned response (or raises)."""

    def __init__(self, response: str = "[]", *, fail: bool = False) -> None:
        self._response = response
        self._fail = fail
        self.calls: list[tuple[str, str]] = []

    def generate(
        self, prompt: str, system: str = "", use_thinking: object = None, **kw: object
    ) -> str:
        self.calls.append((prompt, system))
        if self._fail:
            raise LLMError("backend down")
        return self._response


def test_propose_scoping_questions_situational_and_capped() -> None:
    """The agent reads the real task and returns task-specific questions, capped at the budget."""
    intent = _intent(TaskType.COMPETITOR_ANALYSIS, [OutputFormat.BRIEF], summary="Assess Figure AI")
    client = _FakeLLM('["Tech moat or commercial traction?", "Which time horizon?", "Third?"]')
    questions = propose_scoping_questions(
        client, intent, TaskRequest(raw_input="Assess Figure AI as a competitor"), "", 2
    )
    assert questions == ["Tech moat or commercial traction?", "Which time horizon?"]  # capped at 2
    # The prompt carried the actual task text, so the model can be situation-specific (not generic).
    assert "Assess Figure AI as a competitor" in client.calls[0][0]


def test_propose_scoping_questions_zero_budget_skips_llm() -> None:
    """A zero budget asks nothing and never calls the LLM (low effort / no room left)."""
    client = _FakeLLM('["x"]')
    questions = propose_scoping_questions(
        client, _intent(TaskType.ADHOC, [OutputFormat.BRIEF]), TaskRequest(raw_input="hi"), "", 0
    )
    assert questions == []
    assert client.calls == []


def test_propose_scoping_questions_fail_open() -> None:
    """An LLM error yields no questions — the run proceeds on routing answers alone."""
    client = _FakeLLM(fail=True)
    questions = propose_scoping_questions(
        client, _intent(TaskType.MARKET_ANALYSIS, [OutputFormat.BRIEF]),
        TaskRequest(raw_input="market"), "", 2,
    )
    assert questions == []


def test_propose_scoping_questions_uses_language_and_brain() -> None:
    """German intent → ask in German; brain.md is injected so it won't re-ask the already-known."""
    intent = _intent(TaskType.MARKET_ANALYSIS, [OutputFormat.BRIEF], language=Language.DE)
    client = _FakeLLM("[]")
    propose_scoping_questions(
        client, intent, TaskRequest(raw_input="Marktanalyse"), "Neura ist pre-IPO.", 2
    )
    prompt, system = client.calls[0]
    assert "German" in system  # asks in the user's language
    assert "Neura ist pre-IPO." in prompt  # persistent context injected to avoid re-asking
