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
from models.research import FetchedContent, ResearchReport, SourceTier
from models.synthesis import AnalysisOutput, Section, SourceRef, SynthesisInput
from models.task import Depth, Intent, Language

# Per-source / per-document excerpt caps so several sources fit comfortably in num_ctx (32768).
_MAX_SOURCE_CHARS = 1800
_MAX_DOC_CHARS = 2500

# Context-budget guardrails. An ultra run reads dozens of pages; dumping all of them plus the
# brain + 4 playbooks into one synthesis call pushed the prompt to ~41k tokens against a 32k
# window — the exact `n_keep > n_ctx` 400 the board run hit. We therefore size the *raw* research
# evidence (the bulk, already distilled into the findings digest) to whatever budget is left after
# the fixed parts, and reserve room for the model's own answer.
#   * _CHARS_PER_TOKEN is deliberately LOW so chars→tokens OVER-counts (trims earlier) on the
#     URL-dense, mixed DE/EN evidence Gemma tokenizes less efficiently than plain English.
#   * _OUTPUT_RESERVE_TOKENS keeps headroom for the JSON analysis (+ thinking) the model emits.
_CHARS_PER_TOKEN = 3.2
_OUTPUT_RESERVE_TOKENS = 5000
_MIN_EVIDENCE_CHARS = 2000  # always show at least the top source(s), even on a tight window
_MAX_FINDINGS_DIGEST_CHARS = 14000  # the distilled signal is kept, but never unbounded
# Hard cap on raw sources handed to the synthesis call. The workers already distilled every source
# into the findings digest, so a small local model reasons BETTER over the ~12 best raw pages than
# over 35+ — fewer tokens, higher signal-to-noise, less "lost in the middle". The full source set
# still reaches the deck's bibliography via compile_cited_sources (unaffected by this cap).
_MAX_EVIDENCE_SOURCES = 12

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
    """Assemble the synthesis system prompt: role + language + brain + 3 playbooks + format.

    The PDF/PPTX artifact framework is deliberately **not** injected here: synthesis only produces
    the structured analysis (bottom line + sections + sources), and the artifact rules apply later —
    enforced by the output critic (``core.critic`` criterion 10) and applied by the content shaper /
    design system. Keeping ~3–4k tokens of layout rules out of the reasoning call sharpens a small
    local model and leaves more of the context window for evidence (it was instruction overload).
    """
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


def build_user_prompt(
    synthesis_input: SynthesisInput, evidence_budget_chars: int | None = None
) -> str:
    """Assemble the user prompt: the task + tiered research evidence + provided documents.

    ``evidence_budget_chars`` caps the total characters of *raw* research excerpts so the assembled
    prompt fits the model's context window (see :func:`synthesize`). ``None`` keeps every source
    (the historical behavior). Sources are added highest-tier-first until the budget is spent; any
    left out are summarized as a one-line omission note (their distilled claims still reach the
    model via the findings digest and the deterministic bibliography, so nothing is silently lost).
    """
    intent = synthesis_input.intent
    lines = [f"TASK ({intent.task_type.value}): {intent.summary or '(see evidence below)'}"]

    if synthesis_input.guidance.strip():
        lines.append(
            "\nUSER GUIDANCE (the user's own answers to the agent's scoping questions — honor "
            "these in the scope, emphasis, and framing of the analysis):\n"
            + synthesis_input.guidance.strip()
        )

    if synthesis_input.findings_digest.strip():
        lines.append(
            "\nVALIDATED FINDINGS (from the research team — claim · confidence · date · source; "
            "lead with these and respect their confidence levels):\n"
            + synthesis_input.findings_digest.strip()[:_MAX_FINDINGS_DIGEST_CHARS]
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
        lines.append(_render_evidence(synthesis_input.research, evidence_budget_chars))

    if not synthesis_input.research and not synthesis_input.documents:
        lines.append(
            "\n(No external evidence was gathered — rely on the persistent context and flag the "
            "lack of fresh sources as a data gap.)"
        )

    lines.append("\nProduce the analysis as the specified JSON now.")
    return "\n".join(lines)


def _render_evidence(research: list[FetchedContent], budget_chars: int | None) -> str:
    """Render the RESEARCH EVIDENCE block, honoring a total character budget (tier-1 sources first).

    ``research`` is the list of fetched pages (``FetchedContent``). When ``budget_chars`` is set,
    sources are taken in tier order until adding the next would exceed it; the rest are noted as
    omitted so the model knows the evidence set was trimmed (not absent).
    """
    ordered = sorted(
        range(len(research)), key=lambda i: classify_tier(research[i].url).value
    )
    total = len(research)
    blocks: list[str] = []
    used = 0
    shown = 0
    for rank, src_idx in enumerate(ordered, start=1):
        content = research[src_idx]
        excerpt = content.text.strip()[:_MAX_SOURCE_CHARS]
        if budget_chars is not None and shown >= 1 and (
            shown >= _MAX_EVIDENCE_SOURCES
            or used + len(excerpt) > max(budget_chars, _MIN_EVIDENCE_CHARS)
        ):
            break
        tier = classify_tier(content.url).value
        title = f" — {content.title}" if content.title else ""
        blocks.append(f"[{rank}] {content.url}{title} [{tier}]\n{excerpt}")
        used += len(excerpt)
        shown += 1
    header = f"\nRESEARCH EVIDENCE ({total} sources"
    header += f", top {shown} shown to fit the context window):" if shown < total else "):"
    omitted = (
        f"\n[+{total - shown} further sources omitted for length — their claims are in the "
        "validated findings and the bibliography.]"
        if shown < total
        else ""
    )
    return header + "\n" + "\n".join(blocks) + omitted


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


def _norm_url(url: str) -> str:
    """Normalize a URL for dedup: trimmed, lowercased, no trailing slash."""
    return url.strip().rstrip("/").lower()


def _tier_order(ref: SourceRef) -> tuple[str, str]:
    """Sort key: tier_1 → tier_3 (untiered last), then URL — a stable, readable bibliography."""
    return (ref.tier.value if ref.tier else "tier_9", ref.url.lower())


def compile_cited_sources(report: ResearchReport) -> list[SourceRef]:
    """Compile the deterministic *belegt* bibliography from the workers' provenance.

    The perfect middle between the LLM's sparse JSON pick and every scanned hit: the union of every
    source a worker pulled a finding from — each ``Finding.source_url`` (with its publication
    ``date``) plus each worker's read set (``WorkerFindings.sources``, with titles). Deduped by
    normalized URL (title from the fetched page, date from the finding), tier-ordered. Excludes the
    hundreds merely scanned (``report.sources_evaluated``).
    """
    by_url: dict[str, SourceRef] = {}

    def _upsert(url: str, *, title: str | None = None, date: str | None = None) -> None:
        url = url.strip()
        if not url:
            return
        key = _norm_url(url)
        existing = by_url.get(key)
        if existing is None:
            by_url[key] = SourceRef(
                url=url, title=title, date=date, tier=classify_tier(url)
            )
            return
        # Merge metadata across the two provenance sources without overwriting good values.
        if title and not existing.title:
            existing.title = title
        if date and not existing.date:
            existing.date = date

    for wf in report.worker_findings:
        for finding in wf.findings:
            if finding.source_url:
                _upsert(finding.source_url, date=finding.date)
        for content in wf.sources:
            if content.url:
                _upsert(content.url, title=content.title)

    return sorted(by_url.values(), key=_tier_order)


def _merge_sources(primary: list[SourceRef], extra: list[SourceRef]) -> list[SourceRef]:
    """Union ``primary`` (belegt ground truth, kept in order) with any new-URL ``extra`` (LLM) refs.

    Guarantees every belegt source appears; appends LLM-only sources the workers didn't carry, and
    backfills a primary entry's missing title/date from a matching LLM ref. Dedup by normalized URL.
    """
    merged = list(primary)
    index = {_norm_url(ref.url): ref for ref in merged}
    for ref in extra:
        key = _norm_url(ref.url)
        existing = index.get(key)
        if existing is None:
            merged.append(ref)
            index[key] = ref
        else:
            if ref.title and not existing.title:
                existing.title = ref.title
            if ref.date and not existing.date:
                existing.date = ref.date
    return merged


def _default_title(intent: Intent) -> str:
    """A safe fallback title from the intent summary."""
    return (_opt_str(intent.summary) or "Analysis")[:120]


def _build_analysis(data: dict[str, object], synthesis_input: SynthesisInput) -> AnalysisOutput:
    """Assemble :class:`AnalysisOutput` from a parsed JSON response."""
    intent = synthesis_input.intent
    sections = _coerce_sections(data.get("sections"))
    # Always merge the deterministic belegt bibliography with whatever the LLM cited — the research
    # set is the ground truth, not just a fallback for when the model emits zero sources.
    deterministic = synthesis_input.cited_sources or _sources_from_research(synthesis_input)
    sources = _merge_sources(deterministic, _coerce_sources(data.get("sources")))
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
            sources=synthesis_input.cited_sources or _sources_from_research(synthesis_input),
            recommended_formats=intent.output_formats,
        )
    return _build_analysis(data, synthesis_input)


def build_budgeted_user_prompt(
    client: LocalLLMClient,
    synthesis_input: SynthesisInput,
    system: str,
    extra_chars: int = 0,
) -> str:
    """Build the user prompt sized so ``system + user`` fits the model's context window.

    Reserves room for the model's own answer, charges the fixed prompt parts (task, guidance,
    validated findings, documents) — plus any ``extra_chars`` the caller appends downstream (the
    revision loop adds the prior draft + the reviewer's issues) — and hands whatever character
    budget is left to the raw research excerpts. This is what keeps an ultra run, which reads dozens
    of pages, from blowing past ``num_ctx`` (the ``n_keep > n_ctx`` 400 the board deck failed on).

    Shared by :func:`synthesize` and ``core.critic.revise`` so both honor one context budget.
    """
    max_prompt_chars = int((client.num_ctx - _OUTPUT_RESERVE_TOKENS) * _CHARS_PER_TOKEN)
    # Cost of everything except the raw evidence (build it with a zero evidence budget to measure).
    fixed = build_user_prompt(synthesis_input, evidence_budget_chars=0)
    evidence_budget = max(
        _MIN_EVIDENCE_CHARS, max_prompt_chars - len(system) - len(fixed) - max(0, extra_chars)
    )
    return build_user_prompt(synthesis_input, evidence_budget_chars=evidence_budget)


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
    user = build_budgeted_user_prompt(client, synthesis_input, system)
    use_thinking = intent.depth in {Depth.STANDARD, Depth.DEEP}

    try:
        response = client.generate(user, system=system, use_thinking=use_thinking)
    except LLMError as exc:
        return AnalysisOutput(
            title=_default_title(intent),
            language=intent.language,
            bottom_line=f"(Synthesis failed — LLM backend error: {exc})",
            sources=synthesis_input.cited_sources or _sources_from_research(synthesis_input),
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
