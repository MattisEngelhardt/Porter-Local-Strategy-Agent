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

from core.config import EffortLevelConfig
from core.json_utils import extract_json_array, extract_json_object
from core.playbooks import Playbooks
from core.researcher import ContentFetcher, SearXNGClient, dedup_results, rank_results
from llm.local_llm_client import LLMError, LocalLLMClient
from models.research import Confidence, FetchedContent, Finding, SearchQuery, WorkerFindings
from models.task import Language

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

        for _round in range(rounds):
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


# ------------------------------------------------------------------- pure helpers
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
