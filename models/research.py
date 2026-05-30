"""Research-layer Pydantic models: search queries, results, fetched/extracted content.

Used by the research engine (Phase 2). Phase 1 only defines the contracts.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field

from models.task import ClarificationRound, Language


class SourceTier(StrEnum):
    """Source trust tier (research_playbook, SPEC §13). Tier 1 = highest trust."""

    TIER_1 = "tier_1"  # Bloomberg, TechCrunch, Reuters, FT, official filings
    TIER_2 = "tier_2"  # Crunchbase, LinkedIn, official company pages
    TIER_3 = "tier_3"  # blogs, X, Substack, forums — signals only


class SearchQuery(BaseModel):
    """A single SearXNG query (one of several parallel queries per run)."""

    query: str
    max_results: int = 8
    language: Language | None = None
    sub_question: str | None = None  # the decomposed sub-question this query serves


class SearchResult(BaseModel):
    """A single ranked search hit returned by SearXNG."""

    title: str
    url: str
    snippet: str = ""
    engine: str | None = None
    score: float | None = None


class FetchedContent(BaseModel):
    """Clean text extracted from a web page (trafilatura, Phase 2)."""

    url: str
    title: str | None = None
    text: str
    word_count: int = 0
    fetched_at: datetime = Field(default_factory=datetime.now)


class DocContent(BaseModel):
    """Text/data extracted from a user-provided document (PDF / image / .xlsx / .docx)."""

    source_path: Path
    doc_type: str  # "pdf" | "image" | "xlsx" | "docx"
    text: str
    page_count: int | None = None
    extraction_method: str | None = None  # "pdfplumber" | "ocr" | "vision" | "pandas"


class RankedResult(SearchResult):
    """A :class:`SearchResult` enriched with a source tier and a computed ranking score.

    ``rank_score`` makes the tier dominate (Tier 1 always outranks Tier 2 outranks
    Tier 3) while the original SearXNG ``score`` breaks ties within a tier.
    """

    tier: SourceTier
    rank_score: float


class ResearchBundle(BaseModel):
    """Structured output of one research run (Phase 2 — no synthesis yet).

    Synthesis (Phase 3) and output rendering (Phase 4) consume this contract.
    """

    query: str
    sub_queries: list[str] = Field(default_factory=list)
    results: list[RankedResult] = Field(default_factory=list)
    fetched: list[FetchedContent] = Field(default_factory=list)
    from_cache: bool = False


# --- Phase 3.5: multi-agent deep research contracts --------------------------------------
class Confidence(StrEnum):
    """Confidence in a researched fact (deep_research_playbook, SPEC §15.5)."""

    HIGH = "high"  # cross-referenced in ≥2 independent authoritative sources
    MEDIUM = "medium"  # single authoritative source, or 2 weaker sources
    ESTIMATE = "estimate"  # inferred / single weak source / undated — flag explicitly


class Finding(BaseModel):
    """One researched fact with provenance: source + date + confidence (deep-research rule)."""

    claim: str
    source_url: str = ""
    date: str | None = None  # publication / as-of date of the source (free-form, e.g. "2026-03")
    confidence: Confidence = Confidence.MEDIUM
    recency_flag: str | None = None  # e.g. "stale (>6mo)"; None when fresh / not time-sensitive


class WorkerFindings(BaseModel):
    """Structured output of one research worker for its assigned sub-topic."""

    sub_topic: str
    queries: list[str] = Field(default_factory=list)
    findings: list[Finding] = Field(default_factory=list)
    sources: list[FetchedContent] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)
    confidence: Confidence = Confidence.MEDIUM


class CoverageGap(BaseModel):
    """A coverage gap flagged across the worker findings (advisory; fail-open)."""

    sub_topic: str = ""
    issue: str


class CoverageReport(BaseModel):
    """Advisory coverage assessment of the aggregated findings (never blocks delivery)."""

    covered: bool = True
    gaps: list[CoverageGap] = Field(default_factory=list)


class ResearchReport(BaseModel):
    """Aggregated multi-agent research output (Phase 3.5) — the manager's evidence report.

    Replaces the single-pass :class:`ResearchBundle` path in the advanced loop. ``evidence`` is
    the deduped fetched content fed to synthesis; the worker findings digest + telemetry make the
    self-correcting research visible in the result panel.
    """

    query: str = ""
    sub_topics: list[str] = Field(default_factory=list)
    worker_findings: list[WorkerFindings] = Field(default_factory=list)
    evidence: list[FetchedContent] = Field(default_factory=list)
    rounds_used: int = 0
    workers_used: int = 0
    sources_evaluated: int = 0
    midresearch: list[ClarificationRound] = Field(default_factory=list)
    coverage: CoverageReport | None = None
