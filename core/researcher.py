"""Research engine (Phase 2): SearXNG search + content fetch + ranking + cache.

Single responsibility — research only. No LLM reasoning (Phase 3), no output
rendering (Phase 4). Every parameter comes from ``config.research`` (SPEC §8).
Web I/O is async via aiohttp (SPEC §6); HTML → clean text via trafilatura.

Source tiers follow research_playbook (SPEC §13): Tier 1 = highest trust. The
``rank_score`` lets the tier dominate while the raw SearXNG score breaks ties.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import aiohttp
import trafilatura

from core.config import ResearchConfig
from core.searxng_health import searxng_engine_outage_message
from models.research import (
    FetchedContent,
    RankedResult,
    ResearchBundle,
    SearchQuery,
    SearchResult,
    SourceTier,
)

# Tier domains from research_playbook (SPEC §13). Anything unlisted → Tier 3
# (signals only), which is the conservative default.
_TIER_1_DOMAINS = frozenset(
    {
        "bloomberg.com",
        "techcrunch.com",
        "reuters.com",
        "ft.com",
        "wsj.com",
        "sec.gov",
        "bafin.de",
    }
)
_TIER_2_DOMAINS = frozenset(
    {
        "crunchbase.com",
        "linkedin.com",
        "pitchbook.com",
    }
)
_TIER_WEIGHT: dict[SourceTier, float] = {
    SourceTier.TIER_1: 3.0,
    SourceTier.TIER_2: 2.0,
    SourceTier.TIER_3: 1.0,
}

_USER_AGENT = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) StrategyAgent/0.2 "
        "(local research agent; +https://localhost)"
    )
}

_DEFAULT_CACHE_DIR = Path("./data/cache")


class SearXNGError(Exception):
    """SearXNG is unreachable or returned no usable JSON (fail fast, SPEC REQ-5)."""


# ------------------------------------------------------------------ pure helpers
def _host(url: str) -> str:
    """Return the lowercased host without a leading ``www.`` (empty if unparsable)."""
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


def classify_tier(url: str) -> SourceTier:
    """Map a URL's domain to a :class:`SourceTier` (research_playbook hierarchy)."""
    host = _host(url)
    if not host:
        return SourceTier.TIER_3
    if any(host == d or host.endswith(f".{d}") for d in _TIER_1_DOMAINS):
        return SourceTier.TIER_1
    if any(host == d or host.endswith(f".{d}") for d in _TIER_2_DOMAINS):
        return SourceTier.TIER_2
    return SourceTier.TIER_3


def _normalize_url(url: str) -> str:
    """Normalize a URL for dedup: host (no www) + path (no trailing slash), no query."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    return f"{host}{path}"


def dedup_results(results: list[SearchResult]) -> list[SearchResult]:
    """Drop empty-URL and duplicate hits (by normalized URL), keeping first seen."""
    seen: set[str] = set()
    unique: list[SearchResult] = []
    for result in results:
        if not result.url:
            continue
        key = _normalize_url(result.url)
        if key in seen:
            continue
        seen.add(key)
        unique.append(result)
    return unique


def rank_results(results: list[SearchResult]) -> list[RankedResult]:
    """Attach tier + ``rank_score`` and sort highest-first (tier dominates)."""
    ranked: list[RankedResult] = []
    for result in results:
        tier = classify_tier(result.url)
        tie_break = min(max(result.score or 0.0, 0.0), 10.0) / 10.0
        ranked.append(
            RankedResult(
                **result.model_dump(),
                tier=tier,
                rank_score=_TIER_WEIGHT[tier] + tie_break,
            )
        )
    ranked.sort(key=lambda r: r.rank_score, reverse=True)
    return ranked


# ----------------------------------------------------------------- SearXNG client
class SearXNGClient:
    """Async SearXNG JSON client. All params from :class:`ResearchConfig`."""

    def __init__(self, config: ResearchConfig) -> None:
        """Initialize from research config (URL, result/parallel limits)."""
        self._base_url = config.searxng_url.rstrip("/")
        self._max_results = config.max_results_per_query
        self._parallel = max(1, config.parallel_queries)
        self._timeout = aiohttp.ClientTimeout(total=20.0)

    @property
    def base_url(self) -> str:
        """The configured SearXNG base URL (never hardcoded)."""
        return self._base_url

    async def _search_one(
        self, query: SearchQuery, session: aiohttp.ClientSession
    ) -> list[SearchResult]:
        """Run one SearXNG JSON query and parse it into :class:`SearchResult`s."""
        params: dict[str, str] = {"q": query.query, "format": "json"}
        if query.language is not None:
            params["language"] = query.language.value
        async with session.get(f"{self._base_url}/search", params=params) as resp:
            resp.raise_for_status()
            data: dict[str, Any] = await resp.json(content_type=None)

        limit = query.max_results or self._max_results
        hits = data.get("results") or []
        outage = searxng_engine_outage_message(self._base_url, data)
        if not hits and outage:
            raise SearXNGError(outage)
        return [
            SearchResult(
                title=str(item.get("title", "")),
                url=str(item.get("url", "")),
                snippet=str(item.get("content") or ""),
                engine=item.get("engine"),
                score=item.get("score"),
            )
            for item in hits[:limit]
        ]

    async def search_many(self, queries: list[SearchQuery]) -> list[tuple[str, list[SearchResult]]]:
        """Run queries in parallel (bounded by ``parallel_queries``).

        Returns ``(query_text, results)`` pairs. Per-query failures yield an empty
        list so one bad engine never kills the run; if *every* query fails, raises
        :class:`SearXNGError` with fix instructions.
        """
        if not queries:
            return []

        semaphore = asyncio.Semaphore(self._parallel)

        async def _bounded(
            query: SearchQuery, session: aiohttp.ClientSession
        ) -> list[SearchResult]:
            async with semaphore:
                return await self._search_one(query, session)

        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            gathered = await asyncio.gather(
                *(_bounded(q, session) for q in queries), return_exceptions=True
            )

        pairs: list[tuple[str, list[SearchResult]]] = []
        errors: list[BaseException] = []
        for query, outcome in zip(queries, gathered, strict=True):
            if isinstance(outcome, BaseException):
                errors.append(outcome)
                pairs.append((query.query, []))
            else:
                pairs.append((query.query, outcome))

        if errors and len(errors) == len(queries):
            if isinstance(errors[0], SearXNGError):
                raise SearXNGError(str(errors[0])) from errors[0]
            raise SearXNGError(
                f"All {len(queries)} SearXNG queries failed against {self._base_url}.\n"
                "Fix:\n"
                "  1. Start Docker Desktop and wait until the Docker daemon is running.\n"
                "  2. Start SearXNG: 'docker compose up -d searxng' in the project root.\n"
                f"  3. Keep 'research.searxng_url' aligned with the configured host port "
                f"({self._base_url}).\n"
                "     With docker-compose.yml set to '8888:8080', localhost:8888 is intentional.\n"
                "  4. Enable JSON output in searxng-data/settings.yml: "
                "'search: {formats: [html, json]}'.\n"
                f'  5. Verify: curl "{self._base_url}/search?q=test&format=json".\n'
                f"First error: {errors[0]!r}"
            ) from errors[0]
        return pairs


# --------------------------------------------------------------- content fetcher
class ContentFetcher:
    """Fetches web pages in parallel and extracts clean text via trafilatura."""

    def __init__(self, config: ResearchConfig) -> None:
        """Initialize from research config (max pages to fetch per run)."""
        self._max_fetch = config.max_fetch_per_run
        self._timeout = aiohttp.ClientTimeout(total=30.0)

    async def _fetch_one(self, url: str, session: aiohttp.ClientSession) -> FetchedContent | None:
        """Fetch one URL and extract clean text; return ``None`` on any failure."""
        try:
            async with session.get(url, headers=_USER_AGENT) as resp:
                resp.raise_for_status()
                html = await resp.text()
        except (TimeoutError, aiohttp.ClientError, UnicodeDecodeError):
            return None

        text = await asyncio.to_thread(
            trafilatura.extract, html, include_comments=False, include_tables=True
        )
        if not text or not text.strip():
            return None
        return FetchedContent(url=url, text=text, word_count=len(text.split()))

    async def fetch_many(self, urls: list[str]) -> list[FetchedContent]:
        """Fetch up to ``max_fetch_per_run`` URLs in parallel; drop failures."""
        targets = urls[: self._max_fetch]
        if not targets:
            return []
        async with aiohttp.ClientSession(timeout=self._timeout) as session:
            gathered = await asyncio.gather(
                *(self._fetch_one(url, session) for url in targets),
                return_exceptions=True,
            )
        return [item for item in gathered if isinstance(item, FetchedContent)]


# ------------------------------------------------------------------- search cache
class SearchCache:
    """24h diskcache layer for SearXNG results (SPEC §4.4). Keyed on normalized query."""

    def __init__(self, config: ResearchConfig, cache_dir: Path | None = None) -> None:
        """Open (creating if needed) the SQLite-backed cache under ``data/cache``."""
        from diskcache import Cache

        self._dir = cache_dir or _DEFAULT_CACHE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)
        self._cache = Cache(str(self._dir))
        self._ttl = max(1, config.cache_ttl_hours) * 3600

    @staticmethod
    def _key(query: str) -> str:
        return f"search::{query.strip().lower()}"

    def get(self, query: str) -> list[SearchResult] | None:
        """Return cached results for ``query`` (or ``None`` on miss/expiry)."""
        raw = self._cache.get(self._key(query))
        if not isinstance(raw, list):
            return None
        return [SearchResult.model_validate(item) for item in raw]

    def set(self, query: str, results: list[SearchResult]) -> None:
        """Store ``results`` for ``query`` with the configured TTL."""
        payload = [r.model_dump(mode="json") for r in results]
        self._cache.set(self._key(query), payload, expire=self._ttl)

    def close(self) -> None:
        """Close the underlying cache handle."""
        self._cache.close()


# --------------------------------------------------------------- research engine
class ResearchEngine:
    """Orchestrates one research run: search → dedup → rank → fetch top-N.

    Produces a :class:`ResearchBundle`. No synthesis (that is Phase 3).
    """

    def __init__(self, config: ResearchConfig, cache: SearchCache | None = None) -> None:
        """Wire the SearXNG client, content fetcher, and (optional) result cache."""
        self._config = config
        self._searx = SearXNGClient(config)
        self._fetcher = ContentFetcher(config)
        self._cache = cache

    async def run(
        self,
        query: str,
        sub_queries: list[str] | None = None,
        max_fetch: int | None = None,
    ) -> ResearchBundle:
        """Search (cache-aware), rank deduped hits, and fetch the top pages.

        Args:
            query: The primary research query (also the bundle label).
            sub_queries: Optional decomposed queries to run in parallel. Defaults
                to ``[query]`` (Phase 3 supplies real decomposition).
            max_fetch: Override the number of pages to deep-read this run.

        Returns:
            A :class:`ResearchBundle` with ranked results and fetched content.
        """
        query_texts = sub_queries or [query]

        cached_by_query: dict[str, list[SearchResult]] = {}
        to_search: list[SearchQuery] = []
        for text in query_texts:
            hit = self._cache.get(text) if self._cache is not None else None
            if hit is not None:
                cached_by_query[text] = hit
            else:
                to_search.append(
                    SearchQuery(query=text, max_results=self._config.max_results_per_query)
                )

        searched = await self._searx.search_many(to_search)
        for text, results in searched:
            if self._cache is not None:
                self._cache.set(text, results)
            cached_by_query[text] = results

        merged: list[SearchResult] = []
        for text in query_texts:
            merged.extend(cached_by_query.get(text, []))

        ranked = rank_results(dedup_results(merged))

        fetch_limit = self._config.max_fetch_per_run if max_fetch is None else max_fetch
        fetched = await self._fetcher.fetch_many([r.url for r in ranked[:fetch_limit]])

        return ResearchBundle(
            query=query,
            sub_queries=sub_queries or [],
            results=ranked,
            fetched=fetched,
            from_cache=len(to_search) == 0 and len(query_texts) > 0,
        )
