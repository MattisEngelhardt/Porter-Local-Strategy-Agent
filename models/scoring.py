"""Pydantic models for the Analyst (Recruiting) dimension: CV scoring & ranking (Phase 6).

Local, DSGVO-safe CV screening contracts. Scores are 0-100 per criterion; the weighted total is
a 0-100 roll-up using the criteria weights. ``evidence`` carries a short verbatim quote from the
CV so every non-zero score is traceable (zero-hallucination rubric — the human recruiter decides).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class JobCriterion(BaseModel):
    """One weighted hiring criterion derived from (or supplied for) a job profile."""

    name: str
    weight: float = Field(default=1.0, ge=0.0)  # relative importance (e.g. 1-5)
    description: str = ""  # what "good" looks like for this criterion


class CriterionScore(BaseModel):
    """A candidate's score on one criterion, with rationale and CV evidence (provenance)."""

    criterion: str
    score: float = 0.0  # 0-100 (clamped on construction by the scorer)
    rationale: str = ""
    evidence: str = ""  # short verbatim quote from the CV; empty = no support found


class CandidateEvaluation(BaseModel):
    """A full evaluation of one candidate against the job criteria."""

    candidate: str
    source_file: str = ""
    criterion_scores: list[CriterionScore] = Field(default_factory=list)
    weighted_score: float = 0.0  # 0-100 weighted roll-up
    summary: str = ""
    strengths: list[str] = Field(default_factory=list)
    gaps: list[str] = Field(default_factory=list)  # requirements not evidenced in the CV
    rank: int = 0  # 1 = best; assigned after ranking


class ScreeningResult(BaseModel):
    """The ranked output of a CV-screening run (Analyst dimension)."""

    job_title: str = ""
    criteria: list[JobCriterion] = Field(default_factory=list)
    candidates: list[CandidateEvaluation] = Field(default_factory=list)  # ranked best-first
    language: str = "en"
