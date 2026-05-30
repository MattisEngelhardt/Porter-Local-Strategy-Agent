"""Multi-agent deep research (Phase 3.5, SPEC §15.5): the research worker.

A :class:`ResearchWorker` is one specialist identity assigned ONE sub-topic. It runs the
deep-research methodology (``deep_research_playbook.md``): craft targeted queries → search +
fetch (Phase-2 ``SearXNGClient``/``ContentFetcher``, reused) → evaluate sources for
recency/authority → extract :class:`Finding`s (each carrying source + date + confidence) →
iterate up to ``max_research_rounds`` while coverage is thin. The manager (``ResearchManager``,
next task) decomposes the task and runs N of these concurrently.

Concurrency model (designed around one local model serializing LLM calls — SPEC §15.5):
web I/O is genuinely parallel via aiohttp; the LLM steps run via ``asyncio.to_thread`` so they
never block the event loop. The *degree* of parallelism is config-gated by the manager.

Failure isolation: any LLM/extraction error inside a worker is **fail-open** — the worker
returns what it has (possibly empty findings) and records a gap, never crashing the run. A
SearXNG total failure (all of the worker's queries fail) propagates so the manager can apply the
Phase-3 fail-fast policy when *every* worker is starved.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Protocol

from core.config import AppConfig, EffortLevelConfig
from core.json_utils import extract_json_array, extract_json_object
from core.playbooks import Playbooks, load_playbooks
from core.researcher import (
    ContentFetcher,
    SearXNGClient,
    SearXNGError,
    dedup_results,
    rank_results,
)
from llm.local_llm_client import LLMError, LocalLLMClient
from models.research import (
    Confidence,
    FetchedContent,
    Finding,
    ResearchReport,
    SearchQuery,
    WorkerFindings,
)
from models.task import ClarificationRound, Intent, Language, ResearchPlan


class _Interaction(Protocol):
    """The slice of the pipeline's Interaction the manager needs (avoids a circular import)."""

    def ask_text(self, question: str) -> str: ...

    def notify(self, message: str) -> None: ...


# Query/extraction excerpt caps so several sources fit comfortably in num_ctx (32768).
_MAX_SOURCE_CHARS = 1500
_MAX_QUERIES_PER_ROUND = 3

_QUERY_SYSTEM = (
    "You are one research worker in a deep-research team, assigned ONE sub-topic. Craft a small "
    "spread of targeted web-search queries for it, following this methodology:\n\n"
    "{methodology}\n\n"
    "Build queries as entity + metric + timeframe (add the year for anything time-sensitive). "
    "Do not repeat one query reworded. Respond with ONLY a JSON array of "
    f"{_MAX_QUERIES_PER_ROUND} short query strings — no prose."
)

_EXTRACT_SYSTEM = (
    "You are one research worker evaluating sources for ONE sub-topic. Apply this methodology "
    "strictly:\n\n{methodology}\n\n"
    "For each source decide its authority and recency, then extract only facts that matter to the "
    "sub-topic. Every fact carries a source_url, a date (the source's publication/as-of date, or "
    "null), a confidence (high = cross-referenced in >=2 independent authoritative sources; "
    "medium = one solid recent source; estimate = single/weak/undated/inferred), and a "
    "recency_flag when the source is older than ~6 months (else null). Financially material claims "
    "need >=2 independent sources for high confidence. Write claims in {language}.\n\n"
    "Respond with ONLY a JSON object — no prose:\n"
    '{{"findings": [{{"claim": "...", "source_url": "...", "date": "YYYY-MM or null", '
    '"confidence": "high|medium|estimate", "recency_flag": "... or null"}}], '
    '"gaps": ["what the sub-topic still needs that you could not verify"], '
    '"confidence": "high|medium|estimate", "coverage_thin": true}}'
)


@dataclass
class _Extraction:
    """Parsed result of one extraction round."""

    findings: list[Finding] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.ESTIMATE
    thin: bool = True


def _coerce_confidence(value: object, default: Confidence = Confidence.MEDIUM) -> Confidence:
    """Coerce a raw confidence value into :class:`Confidence` (or ``default``)."""
    if isinstance(value, str):
        try:
            return Confidence(value.strip().lower())
        except ValueError:
            return default
    return default


def _opt_str(value: object) -> str | None:
    """Return a stripped non-empty string, or ``None``."""
    return value.strip() if isinstance(value, str) and value.strip() else None


class ResearchWorker:
    """One async research-worker identity (deep-research methodology for a single sub-topic)."""

    def __init__(
        self,
        client: LocalLLMClient,
        searx: SearXNGClient,
        fetcher: ContentFetcher,
        playbooks: Playbooks,
        language: Language = Language.EN,
    ) -> None:
        """Wire the LLM client, the (shared) SearXNG client + fetcher, and the playbooks.

        ``searx`` and ``fetcher`` are injected so the manager shares one of each across workers
        (and tests can stub them). ``playbooks.deep_research`` is the injected methodology.
        """
        self._client = client
        self._searx = searx
        self._fetcher = fetcher
        self._playbooks = playbooks
        self._language = language
        self.results_evaluated = 0  # ranked search results seen (telemetry for the manager)
        self.rounds_used = 0  # research rounds actually executed (telemetry for the manager)

    async def run(self, sub_topic: str, effort_cfg: EffortLevelConfig) -> WorkerFindings:
        """Research one sub-topic to depth and return structured :class:`WorkerFindings`.

        Iterates up to ``effort_cfg.max_research_rounds`` while coverage stays thin, refining
        queries with the gaps found so far. Raises :class:`~core.researcher.SearXNGError` only if
        a whole round's searches all fail (the manager turns an all-worker failure into fail-fast).
        """
        rounds = max(1, effort_cfg.max_research_rounds)
        queries_all: list[str] = []
        findings_all: list[Finding] = []
        sources_all: list[FetchedContent] = []
        gaps: list[str] = []
        confidence = Confidence.ESTIMATE

        for round_number in range(1, rounds + 1):
            self.rounds_used = round_number
            queries = await asyncio.to_thread(self._craft_queries, sub_topic, findings_all, gaps)
            queries_all.extend(q for q in queries if q not in queries_all)

            pairs = await self._searx.search_many(
                [SearchQuery(query=q, sub_question=sub_topic) for q in queries]
            )
            results = [result for _, batch in pairs for result in batch]
            ranked = rank_results(dedup_results(results))
            self.results_evaluated += len(ranked)

            urls = [r.url for r in ranked[: max(1, effort_cfg.max_fetch_per_worker)]]
            fetched = await self._fetcher.fetch_many(urls)
            sources_all.extend(fetched)

            extraction = await asyncio.to_thread(
                self._extract, sub_topic, sources_all, effort_cfg.thinking
            )
            findings_all = _dedup_findings(findings_all + extraction.findings)
            gaps = extraction.gaps
            confidence = extraction.confidence
            if not extraction.thin:
                break

        return WorkerFindings(
            sub_topic=sub_topic,
            queries=queries_all,
            findings=findings_all,
            sources=_dedup_sources(sources_all),
            gaps=gaps,
            confidence=confidence if findings_all else Confidence.ESTIMATE,
        )

    # ------------------------------------------------------------------ LLM steps (sync)
    def _craft_queries(
        self, sub_topic: str, prior_findings: list[Finding], gaps: list[str]
    ) -> list[str]:
        """Ask the LLM for targeted queries (fail-open → the sub-topic itself as one query)."""
        system = _QUERY_SYSTEM.format(methodology=self._playbooks.deep_research)
        context = _refine_context(prior_findings, gaps)
        prompt = (
            f'Sub-topic: "{sub_topic}"\n{context}'
            f"Return the JSON array of {_MAX_QUERIES_PER_ROUND} queries now."
        )
        try:
            response = self._client.generate(prompt, system=system, use_thinking=False)
            array = extract_json_array(response)
        except LLMError:
            array = None
        queries = (
            [str(x).strip() for x in array if isinstance(x, str) and str(x).strip()]
            if array
            else []
        )
        return queries[:_MAX_QUERIES_PER_ROUND] or [sub_topic]

    def _extract(
        self, sub_topic: str, sources: list[FetchedContent], use_thinking: bool
    ) -> _Extraction:
        """Ask the LLM to evaluate sources and extract findings (fail-open on error/parse)."""
        if not sources:
            return _Extraction(gaps=[f"no sources fetched for '{sub_topic}'"], thin=True)

        language = "German" if self._language == Language.DE else "English"
        system = _EXTRACT_SYSTEM.format(
            methodology=self._playbooks.deep_research, language=language
        )
        prompt = f'Sub-topic: "{sub_topic}"\n\n{_format_sources(sources)}\n\nReturn the JSON now.'
        try:
            response = self._client.generate(prompt, system=system, use_thinking=use_thinking)
        except LLMError:
            return _Extraction(gaps=[f"extraction failed (LLM) for '{sub_topic}'"], thin=True)

        data = extract_json_object(response)
        if data is None:
            return _Extraction(gaps=[f"extraction unparseable for '{sub_topic}'"], thin=True)
        return _parse_extraction(data)


_DECOMPOSE_SYSTEM = (
    "You are the research MANAGER of a deep-research team. Decompose the task into exactly "
    "{n} distinct, non-overlapping research sub-topics — each a focused angle one specialist can "
    "research independently. Choose angles using the analysis framework that fits the task type:"
    "\n\n{analysis}\n\n"
    "Guidance: a single-company deep-dive → angles like technology moat, commercial traction, "
    "team quality, strategic moves, financials. Screening MULTIPLE entities → one sub-topic per "
    "entity. Market sizing → top-down size, bottom-up demand, key players, trends. Pick the angles "
    "that fit THIS task. Respond with ONLY a JSON array of exactly {n} short sub-topic strings."
)

_MIDRESEARCH_SYSTEM = (
    "You are the research MANAGER reviewing the gaps after a first research pass. If — and ONLY "
    "if — there is a blocking ambiguity that could not be known upfront and that materially "
    "changes what to search next (e.g. the entity name is ambiguous, or the scope / segment / "
    "geography is unclear), produce ONE precise question for the user plus a refined sub-topic to "
    "research once it is answered. If there is no such blocking ambiguity, return an empty "
    "question. Never ask what can reasonably be assumed.\n"
    "Respond with ONLY a JSON object: "
    '{"question": "the precise question, or empty string", "refine_topic": "sub-topic to research '
    'after the answer"}'
)


class ResearchManager:
    """Orchestrator (Phase 3.5): decompose → run N workers concurrently → mid-research → aggregate.

    Replaces Phase-3's single research step. Concurrency is config-gated
    (``config.effort.worker_concurrency``) so the same code runs modestly on the laptop and fans
    out fully on the planned server — zero code change to scale (SPEC §15.5). Worker failures are
    isolated; a SearXNG total failure (every worker starved) re-raises :class:`SearXNGError` so the
    caller keeps the Phase-3 fail-fast policy.
    """

    async def run(
        self,
        client: LocalLLMClient,
        config: AppConfig,
        intent: Intent,
        plan: ResearchPlan,
        interaction: _Interaction,
        effort_cfg: EffortLevelConfig,
        searx: SearXNGClient | None = None,
        fetcher: ContentFetcher | None = None,
    ) -> ResearchReport:
        """Run the full multi-agent research and return an aggregated :class:`ResearchReport`."""
        playbooks = load_playbooks()
        searx = searx or SearXNGClient(config.research)
        fetcher = fetcher or ContentFetcher(
            config.research.model_copy(
                update={"max_fetch_per_run": effort_cfg.max_fetch_per_worker}
            )
        )

        sub_topics = await asyncio.to_thread(
            self._decompose, client, intent, plan, playbooks, effort_cfg.research_workers
        )
        interaction.notify(
            _t(
                intent.language,
                f"Zerlege in {len(sub_topics)} Research-Stränge…",
                f"Decomposing into {len(sub_topics)} research angles…",
            )
        )

        workers = [
            ResearchWorker(client, searx, fetcher, playbooks, intent.language) for _ in sub_topics
        ]
        semaphore = asyncio.Semaphore(max(1, config.effort.worker_concurrency))

        async def _run_one(worker: ResearchWorker, topic: str) -> WorkerFindings:
            async with semaphore:
                interaction.notify(_t(intent.language, f"Worker: {topic}", f"Worker: {topic}"))
                return await worker.run(topic, effort_cfg)

        outcomes = await asyncio.gather(
            *(_run_one(worker, topic) for worker, topic in zip(workers, sub_topics, strict=True)),
            return_exceptions=True,
        )

        worker_findings: list[WorkerFindings] = []
        searx_errors: list[SearXNGError] = []
        for outcome in outcomes:
            if isinstance(outcome, WorkerFindings):
                worker_findings.append(outcome)
            elif isinstance(outcome, SearXNGError):
                searx_errors.append(outcome)
            # Any other exception is a fail-open worker glitch: skip it, keep the run alive.

        # Hard dep: if every worker was starved by SearXNG, fail fast with fix instructions.
        if not worker_findings and searx_errors and len(searx_errors) == len(sub_topics):
            raise searx_errors[0]

        midresearch: list[ClarificationRound] = []
        if effort_cfg.max_midresearch_questions > 0 and worker_findings:
            midresearch = await self._midresearch(
                client,
                config,
                intent,
                interaction,
                searx,
                fetcher,
                playbooks,
                effort_cfg,
                worker_findings,
                workers,
            )

        return _aggregate_report(intent, plan, sub_topics, worker_findings, midresearch, workers)

    # ------------------------------------------------------------------ manager LLM steps
    def _decompose(
        self,
        client: LocalLLMClient,
        intent: Intent,
        plan: ResearchPlan,
        playbooks: Playbooks,
        n: int,
    ) -> list[str]:
        """Ask the LLM for N sub-topics (fail-open → plan sub-queries, then the task summary)."""
        count = max(1, n)
        system = _DECOMPOSE_SYSTEM.format(n=count, analysis=playbooks.analysis)
        prompt = (
            f"TASK ({intent.task_type.value}): {intent.summary or '(see below)'}\n"
            f"Return the JSON array of exactly {count} sub-topics now."
        )
        try:
            response = client.generate(prompt, system=system, use_thinking=False)
            array = extract_json_array(response)
        except LLMError:
            array = None
        topics = (
            [str(x).strip() for x in array if isinstance(x, str) and str(x).strip()]
            if array
            else []
        )
        if not topics:
            topics = [q for q in plan.sub_questions if q.strip()]
        if not topics:
            topics = [intent.summary.strip() or "the task"]
        return topics[:count]

    async def _midresearch(
        self,
        client: LocalLLMClient,
        config: AppConfig,
        intent: Intent,
        interaction: _Interaction,
        searx: SearXNGClient,
        fetcher: ContentFetcher,
        playbooks: Playbooks,
        effort_cfg: EffortLevelConfig,
        worker_findings: list[WorkerFindings],
        workers: list[ResearchWorker],
    ) -> list[ClarificationRound]:
        """Detect blocking ambiguities, ask the user, and feed answers into targeted re-runs."""
        rounds: list[ClarificationRound] = []
        for _ in range(effort_cfg.max_midresearch_questions):
            gaps = [gap for wf in worker_findings for gap in wf.gaps]
            probe = await asyncio.to_thread(self._detect_midresearch, client, intent, gaps)
            question = probe.get("question", "").strip()
            if not question:
                break
            answer = interaction.ask_text(question).strip()
            rounds.append(ClarificationRound(question=question, answer=answer or None))
            if not answer:
                # Empty answer → proceed on assumption (never block delivery).
                interaction.notify(
                    _t(
                        intent.language,
                        "Keine Antwort — fahre mit Annahme fort.",
                        "No answer — proceeding on an assumption.",
                    )
                )
                break
            refine = probe.get("refine_topic", "").strip() or (intent.summary or question)
            sub_topic = f"{refine} — {answer}"
            worker = ResearchWorker(client, searx, fetcher, playbooks, intent.language)
            workers.append(worker)
            interaction.notify(
                _t(
                    intent.language,
                    f"Vertiefe nach Rückfrage: {sub_topic}",
                    f"Following up after your answer: {sub_topic}",
                )
            )
            try:
                worker_findings.append(await worker.run(sub_topic, effort_cfg))
            except SearXNGError:
                pass  # fail-open: a failed follow-up never blocks delivery
        return rounds

    def _detect_midresearch(
        self, client: LocalLLMClient, intent: Intent, gaps: list[str]
    ) -> dict[str, str]:
        """Probe for a blocking ambiguity; return ``{"question", "refine_topic"}`` (fail-open)."""
        gap_text = "; ".join(gaps[:8]) or "(none reported)"
        prompt = (
            f"TASK ({intent.task_type.value}): {intent.summary or '(unknown)'}\n"
            f"Gaps after the first pass: {gap_text}\nReturn the JSON now."
        )
        try:
            response = client.generate(prompt, system=_MIDRESEARCH_SYSTEM, use_thinking=False)
            data = extract_json_object(response)
        except LLMError:
            data = None
        if not isinstance(data, dict):
            return {"question": "", "refine_topic": ""}
        return {
            "question": _opt_str(data.get("question")) or "",
            "refine_topic": _opt_str(data.get("refine_topic")) or "",
        }


# ------------------------------------------------------------------- pure helpers
def _t(language: Language, de: str, en: str) -> str:
    """Pick the German or English string for the language."""
    return de if language == Language.DE else en


def _aggregate_report(
    intent: Intent,
    plan: ResearchPlan,
    sub_topics: list[str],
    worker_findings: list[WorkerFindings],
    midresearch: list[ClarificationRound],
    workers: list[ResearchWorker],
) -> ResearchReport:
    """Aggregate worker outputs + telemetry into a :class:`ResearchReport` (dedup evidence)."""
    evidence = _dedup_sources([src for wf in worker_findings for src in wf.sources])
    return ResearchReport(
        query=intent.summary or (plan.sub_questions[0] if plan.sub_questions else ""),
        sub_topics=sub_topics,
        worker_findings=worker_findings,
        evidence=evidence,
        rounds_used=max((w.rounds_used for w in workers), default=0),
        workers_used=len(worker_findings),
        sources_evaluated=sum(w.results_evaluated for w in workers),
        midresearch=midresearch,
    )


def _refine_context(prior_findings: list[Finding], gaps: list[str]) -> str:
    """Build a short refinement note for the next query round (so it digs, not repeats)."""
    if not prior_findings and not gaps:
        return ""
    parts: list[str] = []
    if prior_findings:
        known = "; ".join(f.claim for f in prior_findings[:5])
        parts.append(f"Already established: {known}.")
    if gaps:
        parts.append(f"Still missing (target these): {'; '.join(gaps[:5])}.")
    return " ".join(parts) + "\n"


def _format_sources(sources: list[FetchedContent]) -> str:
    """Format fetched sources (url + excerpt) for the extraction prompt."""
    lines = [f"SOURCES ({len(sources)}):"]
    for idx, content in enumerate(sources, start=1):
        title = f" — {content.title}" if content.title else ""
        excerpt = content.text.strip()[:_MAX_SOURCE_CHARS]
        lines.append(f"[{idx}] {content.url}{title}\n{excerpt}")
    return "\n".join(lines)


def _parse_extraction(data: dict[str, object]) -> _Extraction:
    """Build an :class:`_Extraction` from a parsed JSON object (tolerant)."""
    findings: list[Finding] = []
    raw_findings = data.get("findings")
    if isinstance(raw_findings, list):
        for item in raw_findings:
            if not isinstance(item, dict):
                continue
            claim = _opt_str(item.get("claim"))
            if not claim:
                continue
            findings.append(
                Finding(
                    claim=claim,
                    source_url=_opt_str(item.get("source_url")) or "",
                    date=_opt_str(item.get("date")),
                    confidence=_coerce_confidence(item.get("confidence")),
                    recency_flag=_opt_str(item.get("recency_flag")),
                )
            )

    gaps_raw = data.get("gaps")
    gaps = (
        [str(g).strip() for g in gaps_raw if isinstance(g, str) and str(g).strip()]
        if isinstance(gaps_raw, list)
        else []
    )
    thin = bool(data.get("coverage_thin", not findings))
    return _Extraction(
        findings=findings,
        gaps=gaps,
        confidence=_coerce_confidence(data.get("confidence")),
        thin=thin,
    )


def _dedup_findings(findings: list[Finding]) -> list[Finding]:
    """Drop duplicate findings by normalized claim text, keeping the first (highest-conf) seen."""
    seen: set[str] = set()
    unique: list[Finding] = []
    for finding in findings:
        key = finding.claim.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(finding)
    return unique


def _dedup_sources(sources: list[FetchedContent]) -> list[FetchedContent]:
    """Drop duplicate fetched sources by URL, keeping the first seen."""
    seen: set[str] = set()
    unique: list[FetchedContent] = []
    for source in sources:
        if source.url in seen:
            continue
        seen.add(source.url)
        unique.append(source)
    return unique
