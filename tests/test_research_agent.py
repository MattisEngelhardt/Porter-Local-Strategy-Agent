"""Tests for the research worker (core/research_agent.py).

The LLM is scripted (keyed on the system prompt) and SearXNG/fetcher are async fakes, so the
deep-research loop runs fully offline and deterministically.
"""

from __future__ import annotations

from typing import Any

import pytest

from core.config import AppConfig, EffortLevelConfig
from core.pipeline import AutoInteraction
from core.playbooks import load_playbooks
from core.research_agent import ResearchManager, ResearchWorker
from core.researcher import SearXNGError
from models.research import Confidence, FetchedContent, SearchResult
from models.task import Intent, Language, OutputFormat, ResearchPlan, TaskType


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


# ===================================================================== ResearchManager
class _MgrClient:
    """Scripted client for the manager: routes by system-prompt keyword to a canned response."""

    def __init__(
        self,
        *,
        decompose: str,
        queries: str = '["q"]',
        extraction: str = _EXTRACTION,
        midresearch: str = '{"question": "", "refine_topic": ""}',
    ) -> None:
        self.decompose = decompose
        self.queries = queries
        self.extraction = extraction
        self.midresearch = midresearch

    def generate(self, prompt: str, system: str = "", use_thinking: Any = None, **kw: Any) -> str:
        s = system.lower()
        if "decompose the task" in s:
            return self.decompose
        if "craft a small spread" in s:
            return self.queries
        if "blocking ambiguity" in s:
            return self.midresearch
        return self.extraction


class _RaisingSearx:
    """Async SearXNG stub that always fails (simulates SearXNG being down)."""

    async def search_many(self, queries: list[Any]) -> list[tuple[str, list[SearchResult]]]:
        raise SearXNGError("all queries failed")


def _intent() -> Intent:
    return Intent(
        task_type=TaskType.COMPETITOR_ANALYSIS,
        output_formats=[OutputFormat.BRIEF],
        language=Language.EN,
        summary="Analyze 1X Technologies",
    )


def _plan() -> ResearchPlan:
    return ResearchPlan(sub_questions=["1X funding", "1X tech"], summary="Go?")


async def test_manager_decomposes_and_aggregates() -> None:
    """The manager decomposes into N sub-topics, runs workers, and aggregates telemetry."""
    client = _MgrClient(decompose='["funding", "technology", "team"]')
    cfg = EffortLevelConfig(
        research_workers=3,
        max_research_rounds=1,
        max_fetch_per_worker=3,
        max_midresearch_questions=0,
    )
    report = await ResearchManager().run(
        client,  # type: ignore[arg-type]
        AppConfig(),
        _intent(),
        _plan(),
        AutoInteraction(),
        cfg,
        searx=_FakeSearx(_RESULTS),  # type: ignore[arg-type]
        fetcher=_FakeFetcher(_PAGES),  # type: ignore[arg-type]
    )
    assert report.sub_topics == ["funding", "technology", "team"]
    assert report.workers_used == 3
    assert len(report.evidence) == 1  # deduped by URL across the 3 workers
    assert report.sources_evaluated > 0
    assert report.rounds_used == 1
    assert report.worker_findings[0].findings[0].claim == "1X raised $100M"


async def test_manager_decompose_fallback_to_plan() -> None:
    """If decomposition returns nothing usable, it falls back to the plan's sub-queries."""
    client = _MgrClient(decompose="not a json array")
    cfg = EffortLevelConfig(research_workers=2, max_research_rounds=1, max_midresearch_questions=0)
    report = await ResearchManager().run(
        client,  # type: ignore[arg-type]
        AppConfig(),
        _intent(),
        _plan(),
        AutoInteraction(),
        cfg,
        searx=_FakeSearx(_RESULTS),  # type: ignore[arg-type]
        fetcher=_FakeFetcher(_PAGES),  # type: ignore[arg-type]
    )
    assert report.sub_topics == ["1X funding", "1X tech"]  # from the plan


async def test_manager_midresearch_feeds_answer_into_followup() -> None:
    """A blocking-ambiguity question is asked, and the answer drives a targeted follow-up worker."""
    client = _MgrClient(
        decompose='["overview"]',
        midresearch='{"question": "Robotics or payments?", "refine_topic": "1X robotics"}',
    )
    cfg = EffortLevelConfig(
        research_workers=1,
        max_research_rounds=1,
        max_fetch_per_worker=3,
        max_midresearch_questions=1,
    )
    interaction = AutoInteraction(text_answers=["robotics"])
    report = await ResearchManager().run(
        client,  # type: ignore[arg-type]
        AppConfig(),
        _intent(),
        _plan(),
        interaction,
        cfg,
        searx=_FakeSearx(_RESULTS),  # type: ignore[arg-type]
        fetcher=_FakeFetcher(_PAGES),  # type: ignore[arg-type]
    )
    assert len(report.midresearch) == 1
    assert report.midresearch[0].answer == "robotics"
    assert interaction.asked_text == ["Robotics or payments?"]
    # The answer flowed into a follow-up worker (extra findings → workers_used grew past 1).
    assert report.workers_used == 2
    assert any("robotics" in note for note in interaction.notes)


async def test_manager_midresearch_empty_answer_assumes() -> None:
    """An empty mid-research answer is recorded and the manager proceeds (no follow-up worker)."""
    client = _MgrClient(
        decompose='["overview"]',
        midresearch='{"question": "Which segment?", "refine_topic": "segment"}',
    )
    cfg = EffortLevelConfig(research_workers=1, max_research_rounds=1, max_midresearch_questions=1)
    interaction = AutoInteraction(text_answers=[])  # no answer → assume + proceed
    report = await ResearchManager().run(
        client,  # type: ignore[arg-type]
        AppConfig(),
        _intent(),
        _plan(),
        interaction,
        cfg,
        searx=_FakeSearx(_RESULTS),  # type: ignore[arg-type]
        fetcher=_FakeFetcher(_PAGES),  # type: ignore[arg-type]
    )
    assert report.midresearch[0].answer is None
    assert report.workers_used == 1  # no follow-up worker launched


async def test_manager_all_searx_fail_is_fail_fast() -> None:
    """If every worker is starved by SearXNG, the manager re-raises SearXNGError (fail-fast)."""
    client = _MgrClient(decompose='["a", "b"]')
    cfg = EffortLevelConfig(research_workers=2, max_research_rounds=1, max_midresearch_questions=0)
    with pytest.raises(SearXNGError):
        await ResearchManager().run(
            client,  # type: ignore[arg-type]
            AppConfig(),
            _intent(),
            _plan(),
            AutoInteraction(),
            cfg,
            searx=_RaisingSearx(),  # type: ignore[arg-type]
            fetcher=_FakeFetcher(_PAGES),  # type: ignore[arg-type]
        )
