"""Synthesis layer (Phase 3): reason over research + playbooks + brain → structured analysis.

This is SPEC §5.3 steps 5–8 (extract → synthesize → quality-check). The synthesis system
prompt injects brain.md (persistent Neura context) and all three playbooks (research / analysis
/ output rules), so the model reasons with the same standards the SPEC defines. The user prompt
carries the gathered evidence (web pages + documents), each tagged with its source tier.

Thinking mode follows depth (SPEC §5.3 / N-2): on for standard/deep analysis, off for quick.
The model returns JSON which is parsed into :class:`AnalysisOutput`; a bad/empty parse degrades
gracefully (raw text wrapped in one section) rather than crashing (SPEC REQ-5).

Output rendering to PDF/PPTX/Excel is Phase 4 — this module stops at the structured contract.
"""

from __future__ import annotations

from core.json_utils import extract_json_object
from core.playbooks import Playbooks, load_playbooks
from core.researcher import classify_tier
from llm.local_llm_client import LLMError, LocalLLMClient
from models.research import SourceTier
from models.synthesis import AnalysisOutput, Section, SourceRef, SynthesisInput
from models.task import Depth, Intent, Language

# Per-source / per-document excerpt caps so several sources fit comfortably in num_ctx (32768).
_MAX_SOURCE_CHARS = 1800
_MAX_DOC_CHARS = 2500

_ROLE = (
    "You are a senior strategy analyst supporting the CEO Office and Corporate Development team "
    "at Neura Robotics (pre-IPO cognitive humanoid robotics company, Metzingen, Germany). You "
    "produce structured, decision-ready analysis — bottom line first, no filler."
)

_RESPONSE_FORMAT = (
    "# RESPONSE FORMAT\n"
    "Respond with ONLY a JSON object — no prose, no markdown fences:\n"
    '{"title": "...", '
    '"bottom_line": "the recommendation / bottom line up front (2-4 sentences)", '
    '"sections": [{"heading": "...", "body": "..."}], '
    '"sources": [{"url": "...", "title": "...", "date": "YYYY-MM-DD or null", '
    '"tier": "tier_1|tier_2|tier_3"}]}\n'
    "Lead with the bottom line. Apply the Neura Lens: every point must say what it means for "
    "Neura specifically. Flag unverified or single-source claims explicitly as assumptions/gaps."
)


def build_system_prompt(intent: Intent, brain: str, playbooks: Playbooks) -> str:
    """Assemble the synthesis system prompt: role + language + brain + 3 playbooks + format."""
    language = "German" if intent.language == Language.DE else "English"
    parts = [_ROLE, f"\nWrite ALL output in {language}."]
    if brain.strip():
        parts.append(
            "\n# PERSISTENT CONTEXT (brain.md) — applies to every analysis\n" + brain.strip()
        )
    parts.append("\n# RESEARCH PLAYBOOK\n" + playbooks.research)
    parts.append(
        "\n# ANALYSIS PLAYBOOK — apply the framework matching the task type\n" + playbooks.analysis
    )
    parts.append("\n# OUTPUT PLAYBOOK\n" + playbooks.output)
    parts.append("\n" + _RESPONSE_FORMAT)
    return "\n".join(parts)


def build_user_prompt(synthesis_input: SynthesisInput) -> str:
    """Assemble the user prompt: the task + tiered research evidence + provided documents."""
    intent = synthesis_input.intent
    lines = [f"TASK ({intent.task_type.value}): {intent.summary or '(see evidence below)'}"]

    if synthesis_input.findings_digest.strip():
        lines.append(
            "\nVALIDATED FINDINGS (from the research team — claim · confidence · date · source; "
            "lead with these and respect their confidence levels):\n"
            + synthesis_input.findings_digest.strip()
        )

    if synthesis_input.prior_findings.strip():
        lines.append(
            "\nPRIOR FINDINGS (from earlier analysis):\n" + synthesis_input.prior_findings.strip()
        )

    if synthesis_input.documents:
        lines.append("\nDOCUMENTS PROVIDED:")
        for idx, doc in enumerate(synthesis_input.documents, start=1):
            excerpt = doc.text.strip()[:_MAX_DOC_CHARS]
            lines.append(f"[D{idx}] {doc.source_path.name} ({doc.doc_type}):\n{excerpt}")

    if synthesis_input.research:
        lines.append(f"\nRESEARCH EVIDENCE ({len(synthesis_input.research)} sources):")
        for idx, content in enumerate(synthesis_input.research, start=1):
            tier = classify_tier(content.url).value
            title = f" — {content.title}" if content.title else ""
            excerpt = content.text.strip()[:_MAX_SOURCE_CHARS]
            lines.append(f"[{idx}] {content.url}{title} [{tier}]\n{excerpt}")

    if not synthesis_input.research and not synthesis_input.documents:
        lines.append(
            "\n(No external evidence was gathered — rely on the persistent context and flag the "
            "lack of fresh sources as a data gap.)"
        )

    lines.append("\nProduce the analysis as the specified JSON now.")
    return "\n".join(lines)


# ------------------------------------------------------------------- coercion helpers
def _opt_str(value: object) -> str | None:
    """Return a stripped non-empty string, or ``None``."""
    return value.strip() if isinstance(value, str) and value.strip() else None


def _coerce_tier(value: object) -> SourceTier | None:
    """Coerce a raw tier value into :class:`SourceTier` or ``None``."""
    if isinstance(value, str):
        try:
            return SourceTier(value.strip().lower())
        except ValueError:
            return None
    return None


def _coerce_sections(value: object) -> list[Section]:
    """Parse the JSON ``sections`` array into :class:`Section` objects (tolerant)."""
    sections: list[Section] = []
    if not isinstance(value, list):
        return sections
    for item in value:
        if isinstance(item, dict):
            heading = _opt_str(item.get("heading"))
            body = _opt_str(item.get("body"))
            if heading or body:
                sections.append(Section(heading=heading or "Section", body=body or ""))
        elif isinstance(item, str) and item.strip():
            sections.append(Section(heading="Section", body=item.strip()))
    return sections


def _coerce_sources(value: object) -> list[SourceRef]:
    """Parse the JSON ``sources`` array into :class:`SourceRef` objects (tolerant)."""
    sources: list[SourceRef] = []
    if not isinstance(value, list):
        return sources
    for item in value:
        if isinstance(item, dict):
            url = _opt_str(item.get("url"))
            if url:
                sources.append(
                    SourceRef(
                        url=url,
                        title=_opt_str(item.get("title")),
                        date=_opt_str(item.get("date")),
                        tier=_coerce_tier(item.get("tier")),
                    )
                )
        elif isinstance(item, str) and item.strip().startswith("http"):
            sources.append(SourceRef(url=item.strip(), tier=classify_tier(item.strip())))
    return sources


def _sources_from_research(synthesis_input: SynthesisInput) -> list[SourceRef]:
    """Build source refs from the fetched research (fallback when the LLM cites none)."""
    return [
        SourceRef(url=content.url, title=content.title, tier=classify_tier(content.url))
        for content in synthesis_input.research
        if content.url
    ]


def _default_title(intent: Intent) -> str:
    """A safe fallback title from the intent summary."""
    return (_opt_str(intent.summary) or "Analysis")[:120]


def _build_analysis(data: dict[str, object], synthesis_input: SynthesisInput) -> AnalysisOutput:
    """Assemble :class:`AnalysisOutput` from a parsed JSON response."""
    intent = synthesis_input.intent
    sections = _coerce_sections(data.get("sections"))
    sources = _coerce_sources(data.get("sources")) or _sources_from_research(synthesis_input)
    bottom_line = _opt_str(data.get("bottom_line")) or (sections[0].body[:400] if sections else "")
    return AnalysisOutput(
        title=_opt_str(data.get("title")) or _default_title(intent),
        language=intent.language,
        bottom_line=bottom_line,
        sections=sections,
        sources=sources,
        recommended_formats=intent.output_formats,
    )


def parse_analysis(response: str, synthesis_input: SynthesisInput) -> AnalysisOutput:
    """Parse an LLM response into a structured :class:`AnalysisOutput` (tolerant).

    Shared by :func:`synthesize` and the Phase-3.5 revision loop (``core/critic.revise``) so both
    use one JSON→AnalysisOutput path. A bad/empty parse degrades gracefully — the raw text is
    wrapped in a single section rather than raising (SPEC REQ-5).
    """
    intent = synthesis_input.intent
    data = extract_json_object(response)
    if data is None:
        text = response.strip()
        return AnalysisOutput(
            title=_default_title(intent),
            language=intent.language,
            bottom_line=text[:400],
            sections=[Section(heading="Analysis", body=text)] if text else [],
            sources=_sources_from_research(synthesis_input),
            recommended_formats=intent.output_formats,
        )
    return _build_analysis(data, synthesis_input)


def synthesize(client: LocalLLMClient, synthesis_input: SynthesisInput) -> AnalysisOutput:
    """Reason over the evidence with playbooks + brain and return a structured analysis.

    Args:
        client: The LLM client (thinking mode is enabled for standard/deep depth).
        synthesis_input: Intent + research + documents + injected brain/prior context.

    Returns:
        A structured :class:`AnalysisOutput`. On LLM/parse failure it degrades gracefully
        (error note or raw text wrapped in one section) instead of raising.
    """
    intent = synthesis_input.intent
    playbooks = load_playbooks()
    system = build_system_prompt(intent, synthesis_input.brain_context, playbooks)
    user = build_user_prompt(synthesis_input)
    use_thinking = intent.depth in {Depth.STANDARD, Depth.DEEP}

    try:
        response = client.generate(user, system=system, use_thinking=use_thinking)
    except LLMError as exc:
        return AnalysisOutput(
            title=_default_title(intent),
            language=intent.language,
            bottom_line=f"(Synthesis failed — LLM backend error: {exc})",
            sources=_sources_from_research(synthesis_input),
            recommended_formats=intent.output_formats,
        )

    return parse_analysis(response, synthesis_input)


def quality_check(output: AnalysisOutput) -> list[str]:
    """Deterministic completeness check (SPEC §5.3 step 8); returns a list of issue flags."""
    issues: list[str] = []
    if not output.bottom_line.strip():
        issues.append("missing bottom line")
    if not output.sections:
        issues.append("no analysis sections")
    if not output.sources:
        issues.append("no sources cited")
    return issues
