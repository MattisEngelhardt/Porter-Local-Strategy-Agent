"""Tests for the research worker (core/research_agent.py).

The LLM is scripted (keyed on the system prompt) and SearXNG/fetcher are async fakes, so the
deep-research loop runs fully offline and deterministically.
"""

from __future__ import annotations

from typing import Any

from core.config import EffortLevelConfig
from core.playbooks import load_playbooks
from core.research_agent import ResearchWorker
from models.research import Confidence, FetchedContent, SearchResult


class _ScriptedClient:
    """Returns canned query-craft / extraction responses keyed on the system prompt."""

    def __init__(self, *, queries: str, extraction: str) -> None:
        self.queries = queries
        self.extraction = extraction
        self.thinking_calls: list[Any] = []

    def generate(self, prompt: str, system: str = "", use_thinking: Any = None, **kw: Any) -> str:
        self.thinking_calls.append(use_thinking)
        if "craft a small spread" in system.lower():
            return self.queries
        return self.extraction


class _FakeSearx:
    """Async SearXNG stub returning fixed results and recording the queries it saw."""

    def __init__(self, results: list[SearchResult]) -> None:
        self._results = results
        self.seen: list[str] = []

    async def search_many(self, queries: list[Any]) -> list[tuple[str, list[SearchResult]]]:
        self.seen.extend(q.query for q in queries)
        return [(q.query, list(self._results)) for q in queries]


class _FakeFetcher:
    """Async content-fetcher stub returning fixed pages and recording the URLs requested."""

    def __init__(self, pages: list[FetchedContent]) -> None:
        self._pages = pages
        self.requested: list[str] = []

    async def fetch_many(self, urls: list[str]) -> list[FetchedContent]:
        self.requested.extend(urls)
        return list(self._pages)


def _worker(client: Any, searx: Any, fetcher: Any) -> ResearchWorker:
    return ResearchWorker(client, searx, fetcher, load_playbooks())


_RESULTS = [
    SearchResult(title="A", url="https://reuters.com/a", score=9.0),
    SearchResult(title="B", url="https://techcrunch.com/b", score=5.0),
]
_PAGES = [FetchedContent(url="https://reuters.com/a", text="1X raised $100M in 2026.")]
_EXTRACTION = (
    '{"findings": [{"claim": "1X raised $100M", "source_url": "https://reuters.com/a", '
    '"date": "2026-01", "confidence": "high", "recency_flag": null}], '
    '"gaps": [], "confidence": "high", "coverage_thin": false}'
)


async def test_worker_runs_deep_research_loop() -> None:
    """A worker crafts queries, searches+fetches, and extracts dated/sourced findings."""
    client = _ScriptedClient(queries='["1X funding 2026", "1X valuation"]', extraction=_EXTRACTION)
    searx = _FakeSearx(_RESULTS)
    fetcher = _FakeFetcher(_PAGES)
    cfg = EffortLevelConfig(research_workers=1, max_research_rounds=2, max_fetch_per_worker=5)

    findings = await _worker(client, searx, fetcher).run("1X funding", cfg)

    assert findings.sub_topic == "1X funding"
    assert "1X funding 2026" in findings.queries
    assert findings.findings[0].claim == "1X raised $100M"
    assert findings.findings[0].confidence == Confidence.HIGH
    assert findings.findings[0].date == "2026-01"
    assert findings.sources[0].url == "https://reuters.com/a"
    # coverage_thin=false stops it after round one (it does not exhaust both rounds).
    assert searx.seen == ["1X funding 2026", "1X valuation"]


async def test_worker_iterates_when_coverage_thin() -> None:
    """When coverage stays thin, the worker uses all its rounds (refining queries)."""
    thin = (
        '{"findings": [], "gaps": ["valuation unverified"], '
        '"confidence": "estimate", "coverage_thin": true}'
    )
    client = _ScriptedClient(queries='["q1"]', extraction=thin)
    searx = _FakeSearx(_RESULTS)
    cfg = EffortLevelConfig(max_research_rounds=3, max_fetch_per_worker=3)

    findings = await _worker(client, searx, _FakeFetcher(_PAGES)).run("topic", cfg)

    # 3 rounds, one query each = 3 searches (the identical query is deduped in the report).
    assert len(searx.seen) == 3
    assert findings.confidence == Confidence.ESTIMATE
    assert "valuation unverified" in findings.gaps


async def test_worker_thinking_follows_effort() -> None:
    """Extraction uses thinking mode per effort_cfg.thinking; query craft never does."""
    client = _ScriptedClient(queries='["q"]', extraction=_EXTRACTION)
    cfg = EffortLevelConfig(max_research_rounds=1, max_fetch_per_worker=3, thinking=True)
    await _worker(client, _FakeSearx(_RESULTS), _FakeFetcher(_PAGES)).run("t", cfg)
    # First call is query craft (no thinking); second is extraction (thinking=True).
    assert client.thinking_calls[0] is False
    assert client.thinking_calls[1] is True


async def test_worker_fail_open_on_bad_extraction_json() -> None:
    """Unparseable extraction degrades to empty findings + a gap, never raises."""
    client = _ScriptedClient(queries='["q"]', extraction="not json at all")
    cfg = EffortLevelConfig(max_research_rounds=1, max_fetch_per_worker=3)
    findings = await _worker(client, _FakeSearx(_RESULTS), _FakeFetcher(_PAGES)).run("t", cfg)
    assert findings.findings == []
    assert findings.gaps  # a gap was recorded
    assert findings.confidence == Confidence.ESTIMATE


async def test_worker_handles_no_sources() -> None:
    """If nothing is fetched, the worker reports a gap and stays low-confidence (no crash)."""
    client = _ScriptedClient(queries='["q"]', extraction=_EXTRACTION)
    cfg = EffortLevelConfig(max_research_rounds=1, max_fetch_per_worker=3)
    findings = await _worker(client, _FakeSearx([]), _FakeFetcher([])).run("t", cfg)
    assert findings.findings == []
    assert findings.confidence == Confidence.ESTIMATE
