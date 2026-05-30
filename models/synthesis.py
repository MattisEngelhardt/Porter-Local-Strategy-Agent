"""Synthesis-layer Pydantic models: the synthesizer's input bundle and its output.

Used by the reasoning/synthesis layer (Phase 3+). Phase 1 only defines the contracts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from models.research import DocContent, FetchedContent, SourceTier
from models.task import Intent, Language, OutputFormat


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
    prior_findings: str = ""  # retrieved from ChromaDB memory (Phase 5)


class AnalysisOutput(BaseModel):
    """Structured analysis result, format-agnostic. Renderers turn this into PDF/PPTX/Excel."""

    title: str
    language: Language
    bottom_line: str  # executive summary / recommendation up front
    sections: list[Section] = Field(default_factory=list)
    sources: list[SourceRef] = Field(default_factory=list)
    recommended_formats: list[OutputFormat] = Field(default_factory=list)
