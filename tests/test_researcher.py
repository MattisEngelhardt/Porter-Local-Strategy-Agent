"""Tests for the Phase 2 research engine (core/researcher.py).

All web I/O is mocked so the suite runs fully offline. One live test exercises a
real SearXNG search and is skipped when SearXNG is not reachable on :8888.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx
import pytest

from core.config import ResearchConfig
from core.researcher import (
    ContentFetcher,
    ResearchEngine,
    SearchCache,
    SearXNGClient,
    SearXNGError,
    classify_tier,
    dedup_results,
    rank_results,
)
from models.research import SearchQuery, SearchResult, SourceTier

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _config(**overrides: Any) -> ResearchConfig:
    base: dict[str, Any] = {
        "searxng_url": "http://localhost:8888",
        "max_results_per_query": 8,
        "max_fetch_per_run": 5,
        "cache_ttl_hours": 24,
        "parallel_queries": 3,
    }
    base.update(overrides)
    return ResearchConfig(**base)


# ---------------------------------------------------------------- tier classify
def test_classify_tier_known_domains() -> None:
    """Known domains map to their playbook tier; www and subdomains included."""
    assert classify_tier("https://www.bloomberg.com/news/x") == SourceTier.TIER_1
    assert classify_tier("https://techcrunch.com/2026/01/01/y") == SourceTier.TIER_1
    assert classify_tier("https://www.crunchbase.com/org/neura") == SourceTier.TIER_2
    assert classify_tier("https://blog.example.com/post") == SourceTier.TIER_3
    assert classify_tier("not-a-url") == SourceTier.TIER_3


# ----------------------------------------------------------------------- dedup
def test_dedup_drops_duplicates_and_empty_urls() -> None:
    """Duplicate (normalized) URLs and empty URLs are removed, first kept."""
    results = [
        SearchResult(title="a", url="https://x.com/page/"),
        SearchResult(title="a-dup", url="https://www.x.com/page"),  # same after normalize
        SearchResult(title="b", url="https://y.com/other"),
        SearchResult(title="empty", url=""),
    ]
    deduped = dedup_results(results)
    assert [r.title for r in deduped] == ["a", "b"]


# ------------------------------------------------------------------------ rank
def test_rank_orders_by_tier_then_score() -> None:
    """Tier dominates ranking; raw SearXNG score breaks ties within a tier."""
    results = [
        SearchResult(title="t3", url="https://blog.example.com/a", score=9.0),
        SearchResult(title="t1", url="https://reuters.com/a", score=0.1),
        SearchResult(title="t2-low", url="https://crunchbase.com/a", score=0.0),
        SearchResult(title="t2-high", url="https://linkedin.com/a", score=5.0),
    ]
    ranked = rank_results(results)
    assert [r.title for r in ranked] == ["t1", "t2-high", "t2-low", "t3"]
    assert ranked[0].tier == SourceTier.TIER_1
    assert ranked[0].rank_score > ranked[1].rank_score


# ------------------------------------------------------------- SearXNG parsing
class _FakeResp:
    def __init__(self, *, json_payload: Any = None, text_payload: str = "") -> None:
        self._json = json_payload
        self._text = text_payload

    async def __aenter__(self) -> _FakeResp:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    def raise_for_status(self) -> None:
        return None

    async def json(self, content_type: str | None = None) -> Any:
        return self._json

    async def text(self) -> str:
        return self._text


class _FakeSession:
    def __init__(self, resp: _FakeResp) -> None:
        self._resp = resp

    def get(self, url: str, params: Any = None, headers: Any = None) -> _FakeResp:
        return self._resp


async def test_searxng_parses_and_limits_results() -> None:
    """SearXNG JSON is parsed into SearchResult and capped at max_results."""
    payload = {
        "results": [
            {"title": f"r{i}", "url": f"https://s{i}.com", "content": "snip", "score": i}
            for i in range(10)
        ]
    }
    client = SearXNGClient(_config())
    session = _FakeSession(_FakeResp(json_payload=payload))
    # The query carries its own result cap (set from config by ResearchEngine.run).
    results = await client._search_one(SearchQuery(query="x", max_results=3), session)  # type: ignore[arg-type]
    assert len(results) == 3
    assert results[0].title == "r0"
    assert results[0].snippet == "snip"


async def test_search_many_tolerates_partial_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """One failing query yields [] for it but the run still returns the others."""
    client = SearXNGClient(_config())

    async def fake_search_one(query: SearchQuery, session: Any) -> list[SearchResult]:
        if query.query == "bad":
            raise RuntimeError("engine down")
        return [SearchResult(title=query.query, url=f"https://{query.query}.com")]

    monkeypatch.setattr(client, "_search_one", fake_search_one)
    pairs = await client.search_many([SearchQuery(query="good"), SearchQuery(query="bad")])
    by_query = dict(pairs)
    assert len(by_query["good"]) == 1
    assert by_query["bad"] == []


async def test_search_many_all_fail_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    """When every query fails, SearXNGError is raised with fix instructions."""
    client = SearXNGClient(_config())

    async def always_fail(query: SearchQuery, session: Any) -> list[SearchResult]:
        raise RuntimeError("down")

    monkeypatch.setattr(client, "_search_one", always_fail)
    with pytest.raises(SearXNGError) as excinfo:
        await client.search_many([SearchQuery(query="a"), SearchQuery(query="b")])
    assert "Fix:" in str(excinfo.value)


# --------------------------------------------------------------- content fetch
async def test_fetch_one_extracts_clean_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fetched page is run through trafilatura into FetchedContent."""
    fetcher = ContentFetcher(_config())
    session = _FakeSession(_FakeResp(text_payload="<html><body>x</body></html>"))

    monkeypatch.setattr("core.researcher.trafilatura.extract", lambda *a, **k: "hello clean world")
    content = await fetcher._fetch_one("https://x.com", session)  # type: ignore[arg-type]
    assert content is not None
    assert content.word_count == 3
    assert content.url == "https://x.com"


async def test_fetch_one_returns_none_on_empty_extract(monkeypatch: pytest.MonkeyPatch) -> None:
    """If trafilatura extracts nothing, the page is dropped (returns None)."""
    fetcher = ContentFetcher(_config())
    session = _FakeSession(_FakeResp(text_payload="<html></html>"))
    monkeypatch.setattr("core.researcher.trafilatura.extract", lambda *a, **k: None)
    assert await fetcher._fetch_one("https://x.com", session) is None  # type: ignore[arg-type]


# ----------------------------------------------------------------------- cache
def test_cache_roundtrip_and_miss(tmp_path: Path) -> None:
    """Cache stores and returns results by query; unseen query is a miss."""
    cache = SearchCache(_config(), cache_dir=tmp_path / "cache")
    try:
        assert cache.get("neura") is None
        cache.set("neura", [SearchResult(title="t", url="https://x.com", score=1.0)])
        hit = cache.get("NEURA ")  # normalized (case + whitespace)
        assert hit is not None
        assert hit[0].title == "t"
    finally:
        cache.close()


# --------------------------------------------------------------- engine wiring
async def test_engine_run_ranks_and_reports_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """ResearchEngine.run dedups + ranks search hits and fetches the top pages."""
    engine = ResearchEngine(_config())

    async def fake_search_many(
        queries: list[SearchQuery],
    ) -> list[tuple[str, list[SearchResult]]]:
        return [
            (
                queries[0].query,
                [
                    SearchResult(title="blog", url="https://blog.example.com/a", score=9.0),
                    SearchResult(title="reuters", url="https://reuters.com/a", score=0.1),
                ],
            )
        ]

    fetched_urls: list[str] = []

    async def fake_fetch_many(urls: list[str]) -> list[Any]:
        fetched_urls.extend(urls)
        return []

    monkeypatch.setattr(engine._searx, "search_many", fake_search_many)
    monkeypatch.setattr(engine._fetcher, "fetch_many", fake_fetch_many)

    bundle = await engine.run("humanoid robotics")
    assert bundle.results[0].title == "reuters"  # Tier 1 ranked first
    assert bundle.from_cache is False
    assert fetched_urls[0] == "https://reuters.com/a"  # top-ranked fetched first


# ------------------------------------------------------------------- live test
def _searxng_reachable(url: str) -> bool:
    try:
        resp = httpx.get(
            f"{url.rstrip('/')}/search", params={"q": "t", "format": "json"}, timeout=2.0
        )
        resp.raise_for_status()
        resp.json()
        return True
    except (httpx.HTTPError, ValueError):
        return False


async def test_live_research_returns_results() -> None:
    """Live: a real SearXNG search returns ranked results (skipped if :8888 down)."""
    config = _config()
    if not _searxng_reachable(config.searxng_url):
        pytest.skip("SearXNG not reachable on :8888 — skipping live research test.")
    engine = ResearchEngine(config)
    bundle = await engine.run("Neura Robotics", max_fetch=1)
    assert isinstance(bundle.results, list)
