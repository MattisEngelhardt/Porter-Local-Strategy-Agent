"""Output critic + revision (Phase 3.5, SPEC §15.5): the evaluator-optimizer loop.

After synthesis, a *separate* critic agent scores the draft against a rubric drawn from the
playbooks — including deep-research source validation (claims sourced? financials cross-
referenced? recent? assumptions flagged? Neura-Lens per point? bottom-line-first? right
framework? correct language?). If the draft fails (``score < critique_min_score``), the pipeline
asks :func:`revise` for a targeted rewrite that fixes the listed issues, then re-critiques —
bounded by ``effort.revisions``.

This whole layer is **advisory and fail-open**: a critic LLM/parse failure yields a *passing*
critique ("critic unavailable") so it never blocks delivery (SPEC §15.5). Revision reuses the
synthesizer's system prompt + evidence + :func:`~core.synthesizer.parse_analysis`, so the critic
and synthesizer share one structured-output path.
"""

from __future__ import annotations

from core.json_utils import extract_json_object
from core.playbooks import Playbooks
from core.synthesizer import build_system_prompt, build_user_prompt, parse_analysis
from llm.local_llm_client import LLMError, LocalLLMClient
from models.synthesis import AnalysisOutput, CriterionResult, Critique, SynthesisInput
from models.task import Intent, Language

_CRITIC_SYSTEM = (
    "You are a strict editorial critic reviewing a draft strategy analysis for Neura Robotics "
    "BEFORE it reaches the user. Score it 0-100 against the rubric below. Be objective and "
    "specific: name concrete fixes, never vague praise.\n\n"
    "# OUTPUT RULES\n{output}\n\n"
    "# PORTER ARTIFACT FRAMEWORK (PDF/PPTX)\n{artifact_framework}\n\n"
    "# DEEP-RESEARCH / SOURCE VALIDATION\n{deep_research}\n\n"
    "# RUBRIC (judge each criterion pass/fail with a one-line comment)\n"
    "1. bottom_line_first — the recommendation / bottom line leads.\n"
    "2. neura_lens — every point says what it means for Neura specifically (no generic claims).\n"
    "3. sourced — material claims cite a source.\n"
    "4. financials_cross_referenced — valuation/revenue/funding/deal numbers have >=2 independent "
    "sources or are explicitly flagged as estimates.\n"
    "5. recency — sources are recent or explicitly date-flagged.\n"
    "6. assumptions_flagged — unverified / single-source claims and data gaps are called out.\n"
    "7. framework_fit — the analysis framework matching the task type is applied.\n"
    "8. language — the analysis is written in {language}.\n"
    "9. no_filler — no corporate filler; headlines say 'so what', not topic labels.\n"
    "10. artifact_ready — if rendered as PDF/PPTX, it has vivid source-grounded anchors, "
    "decision/risk structure, and no cheap decoration or hallucinated visual claims.\n\n"
    "Respond with ONLY a JSON object — no prose:\n"
    '{{"score": 0, "criteria": [{{"name": "...", "passed": true, "comment": "..."}}], '
    '"issues": ["concrete fix 1", "concrete fix 2"], "summary": "one-sentence verdict"}}'
)


def _language_name(language: Language) -> str:
    """Human language name for prompts."""
    return "German" if language == Language.DE else "English"


def _serialize_analysis(analysis: AnalysisOutput) -> str:
    """Render an :class:`AnalysisOutput` back to compact text for the critic / revision prompt."""
    lines = [f"TITLE: {analysis.title}", f"BOTTOM LINE: {analysis.bottom_line}"]
    for section in analysis.sections:
        lines.append(f"\n## {section.heading}\n{section.body}")
    if analysis.sources:
        cited = "; ".join(s.url for s in analysis.sources if s.url)
        lines.append(f"\nSOURCES CITED: {cited or '(none)'}")
    return "\n".join(lines)


def _clamp_score(value: object) -> int:
    """Coerce a raw score into an int in [0, 100] (default 0 on garbage)."""
    if isinstance(value, bool):  # bool is an int subclass — treat as garbage here
        return 0
    if isinstance(value, (int, float)):
        score = int(value)
    elif isinstance(value, str):
        try:
            score = int(float(value.strip()))  # tolerates "82" / "82.0"
        except ValueError:
            return 0
    else:
        return 0
    return max(0, min(100, score))


def _coerce_criteria(value: object) -> list[CriterionResult]:
    """Parse the JSON ``criteria`` array into :class:`CriterionResult` objects (tolerant)."""
    criteria: list[CriterionResult] = []
    if not isinstance(value, list):
        return criteria
    for item in value:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        comment = item.get("comment")
        criteria.append(
            CriterionResult(
                name=name.strip(),
                passed=bool(item.get("passed", False)),
                comment=comment.strip() if isinstance(comment, str) else "",
            )
        )
    return criteria


def _coerce_str_list(value: object) -> list[str]:
    """Parse a JSON array of strings (drops blanks/non-strings)."""
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _passing_critique(summary: str) -> Critique:
    """A fail-open passing critique (used when the critic is unavailable)."""
    return Critique(passed=True, score=100, issues=[], criteria=[], summary=summary)


def critique(
    client: LocalLLMClient,
    intent: Intent,
    analysis: AnalysisOutput,
    playbooks: Playbooks,
    min_score: int,
) -> Critique:
    """Score a draft analysis against the playbook rubric (fail-open).

    Args:
        client: The LLM client (the critic uses ``use_thinking=True``).
        intent: The parsed intent (drives the expected language/framework).
        analysis: The draft to evaluate.
        playbooks: The loaded playbooks (output + deep-research rules form the rubric).
        min_score: The pass threshold (``config.effort.critique_min_score``).

    Returns:
        A :class:`Critique`. ``passed = score >= min_score``. On any LLM/parse failure it returns
        a *passing* critique ("critic unavailable") so the advisory layer never blocks delivery.
    """
    system = _CRITIC_SYSTEM.format(
        output=playbooks.output,
        artifact_framework=playbooks.artifact_framework,
        deep_research=playbooks.deep_research,
        language=_language_name(intent.language),
    )
    user = (
        f"TASK ({intent.task_type.value}): {intent.summary or '(see draft)'}\n\n"
        f"DRAFT ANALYSIS TO SCORE:\n{_serialize_analysis(analysis)}\n\n"
        "Return the JSON critique now."
    )
    try:
        response = client.generate(user, system=system, use_thinking=True)
    except LLMError as exc:
        return _passing_critique(f"critic unavailable (LLM error: {exc})")

    data = extract_json_object(response)
    if data is None:
        return _passing_critique("critic unavailable (unparseable response)")

    score = _clamp_score(data.get("score"))
    summary = data.get("summary")
    return Critique(
        passed=score >= min_score,
        score=score,
        issues=_coerce_str_list(data.get("issues")),
        criteria=_coerce_criteria(data.get("criteria")),
        summary=summary.strip() if isinstance(summary, str) and summary.strip() else "",
    )


def revise(
    client: LocalLLMClient,
    intent: Intent,
    analysis: AnalysisOutput,
    critique_result: Critique,
    synthesis_input: SynthesisInput,
    playbooks: Playbooks,
) -> AnalysisOutput:
    """Rewrite a draft to fix the critic's issues, reusing the synthesis path.

    Reuses :func:`~core.synthesizer.build_system_prompt` (same standards) + the original evidence
    (:func:`~core.synthesizer.build_user_prompt`) + :func:`~core.synthesizer.parse_analysis`. On an
    LLM error the original draft is returned unchanged (fail-open).
    """
    system = build_system_prompt(intent, synthesis_input.brain_context, playbooks)
    issues = (
        "\n".join(f"- {issue}" for issue in critique_result.issues) or "- improve overall rigor"
    )
    user = (
        f"{build_user_prompt(synthesis_input)}\n\n"
        "--- REVISION TASK ---\n"
        f"Your previous DRAFT was:\n{_serialize_analysis(analysis)}\n\n"
        "A reviewer flagged these issues — fix EACH one while keeping what was strong "
        f"(especially sourcing every material claim):\n{issues}\n\n"
        "Return the improved analysis as the specified JSON now."
    )
    try:
        response = client.generate(user, system=system, use_thinking=True)
    except LLMError:
        return analysis  # fail-open: keep the draft rather than dropping the analysis
    return parse_analysis(response, synthesis_input)
