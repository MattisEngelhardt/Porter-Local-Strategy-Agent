"""Synthesis-layer Pydantic models: the synthesizer's input bundle and its output.

Used by the reasoning/synthesis layer (Phase 3+). Phase 1 only defines the contracts.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from models.research import DocContent, FetchedContent, ResearchReport, SourceTier
from models.task import ClarificationRound, EffortLevel, Intent, Language, OutputFormat


class Section(BaseModel):
    """A titled section of a structured analysis."""

    heading: str
    body: str


class SourceRef(BaseModel):
    """A cited source with provenance metadata."""

    url: str
    title: str | None = None
    date: str | None = None
    tier: SourceTier | None = None


class SynthesisInput(BaseModel):
    """Everything the synthesizer needs to produce an analysis."""

    intent: Intent
    research: list[FetchedContent] = Field(default_factory=list)
    documents: list[DocContent] = Field(default_factory=list)
    brain_context: str = ""  # injected from brain.md (SPEC §4.5)
    findings_digest: str = ""  # validated multi-agent findings digest (Phase 3.5)
    prior_findings: str = ""  # retrieved from ChromaDB memory (Phase 5)


class AnalysisOutput(BaseModel):
    """Structured analysis result, format-agnostic. Renderers turn this into PDF/PPTX/Excel."""

    title: str
    language: Language
    bottom_line: str  # executive summary / recommendation up front
    sections: list[Section] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    recommended_formats: list[OutputFormat] = Field(default_factory=list)


class CriterionResult(BaseModel):
    """One rubric criterion's verdict from the output critic (Phase 3.5)."""

    name: str
    passed: bool
    comment: str = ""


class Critique(BaseModel):
    """The output critic's verdict on a draft analysis (evaluator-optimizer, Phase 3.5).

    Scored against the playbook rubric incl. deep-research source validation. Fail-open: a bad
    parse / LLM error yields ``passed=True`` with a "critic unavailable" summary so the advisory
    layer never blocks delivery (SPEC §15.5).
    """

    passed: bool
    score: int = 0  # 0-100; compared against config.effort.critique_min_score
    issues: list[str] = Field(default_factory=list)
    criteria: list[CriterionResult] = Field(default_factory=list)
    summary: str = ""


class PipelineResult(BaseModel):
    """Outcome of one full agent run. No files are rendered yet (Phase 4).

    Either ``analysis`` (full research run) is present, or ``declined`` is True with a
    ``quick_answer`` (the user declined the research plan and got a brain-based short answer).
    The Phase-3.5 fields (``effort``/``critique``/``revisions``/``research_report``) carry the
    self-correction telemetry; their defaults keep all Phase-3 construction valid.
    """

    intent: Intent
    routed_formats: list[OutputFormat] = Field(default_factory=list)
    answered: list[ClarificationRound] = Field(default_factory=list)
    analysis: AnalysisOutput | None = None
    declined: bool = False
    quick_answer: str | None = None
    effort: EffortLevel = EffortLevel.HIGH
    critique: Critique | None = None
    revisions: int = 0
    research_report: ResearchReport | None = None
    mode: str = "research"  # "research" | "document_prep" (Phase 3.5)
    artifact_path: Path | None = None  # the written .md blueprint (document-prep mode)
    output_files: list[Path] = Field(default_factory=list)  # rendered deliverables (.pptx/.pdf)
