"""Porter's internal artifact framework for PDF briefs and PPTX decks.

The framework is a first-class layer, not a loose prompt snippet. Synthesis and shaping prompts
inject its rules, and the export path applies deterministic pre-render guards so every PDF/PPTX
gets the same source-grounded, attention-first structure before a file is written.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from core.design import strip_inline_markdown, strip_label_prefix
from models.deck import DeckStructure, SlideContent, SlideType
from models.synthesis import AnalysisOutput, Section, SourceRef
from models.task import Audience, Language, TaskType

FRAMEWORK_NAME = "Porter Artifact Framework"
FRAMEWORK_VERSION = "2.0"

_MAX_BULLETS = 4
_MAX_BULLET_WORDS = 16
_MAX_BODY_WORDS = 24
_MAX_ANCHORS = 3
_MAX_DECK_ANCHORS = 4
_NUMBER_RE = re.compile(
    r"(?:[$EURUSD€]\s*)?\b\d[\d.,]*(?:\s?(?:%|x|m|bn|b|million|billion|months?|"
    r"mo|years?|employees?|customers?|pilots?|rounds?))?",
    re.IGNORECASE,
)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_GENERIC_HEADLINES = {
    "analysis",
    "appendix",
    "background",
    "company deep dive",
    "competitive comparison",
    "competitive landscape",
    "executive summary",
    "financial overview",
    "funding",
    "key findings",
    "market landscape",
    "market overview",
    "recommendation",
    "sources",
    "strategic signals",
    "summary",
    "swot",
}


class ArtifactKind(StrEnum):
    """The artifact types governed by the framework."""

    PDF = "pdf"
    PPTX = "pptx"


@dataclass(frozen=True)
class EvidenceAnchor:
    """A visible, source-grounded proof point used by the artifact frame."""

    text: str
    source: str = ""


def framework_marker() -> str:
    """Short label embedded in rendered artifacts."""
    return f"{FRAMEWORK_NAME} v{FRAMEWORK_VERSION}"


def framework_prompt(kind: ArtifactKind | None = None) -> str:
    """Prompt block injected into reasoning/shaping calls that produce PDF/PPTX artifacts."""
    target = "PDF briefs and PPTX decks" if kind is None else kind.value.upper()
    return (
        f"# {framework_marker()} - mandatory artifact operating system\n"
        f"Apply this before producing content for {target}. This is internal Porter behavior, "
        "not an optional style skill.\n"
        "- Make the artifact vivid and attention-first: lead with the decision tension, not a "
        "generic topic.\n"
        "- Use only facts, numbers, names, dates, and sources present in the evidence, documents, "
        "or prior validated analysis. Never invent a visual fact.\n"
        "- Turn dense prose into visible structure: bottom-line block, evidence anchors, "
        "comparison/risk/option frames, source notes, and explicit gaps.\n"
        "- Every heading must be a 'so what' claim. Generic labels are allowed only for source "
        "appendices.\n"
        "- Avoid default-report layouts. Use cards, proof points, contrast, decision callouts, "
        "tables, and visual hierarchy when the evidence supports them.\n"
        "- If evidence is weak or missing, state the gap in the artifact instead of hiding it."
    )


def _t(language: Language, de: str, en: str) -> str:
    """Pick the German or English string for the language."""
    return de if language == Language.DE else en


def _clean(text: str) -> str:
    """Collapse whitespace, strip leaked inline Markdown, and trim common bullet markers."""
    return " ".join(strip_inline_markdown(text).strip(" -*\t\r\n").split())


def _trim_words(text: str, max_words: int) -> str:
    """Trim text to a word budget without changing the underlying claim."""
    words = _clean(text).split()
    if len(words) <= max_words:
        return " ".join(words)
    return " ".join(words[:max_words]).rstrip(" ,;:") + "..."


def _sentences(text: str) -> list[str]:
    """Split text into compact sentences/lines."""
    return [_clean(part) for part in _SENTENCE_RE.split(text) if _clean(part)]


def _source_label(source: SourceRef) -> str:
    """Human-readable source label without inventing any provenance."""
    label = source.title or source.url
    return _trim_words(label, 9)


def _unique_anchor(anchors: list[EvidenceAnchor], candidate: EvidenceAnchor) -> None:
    """Append ``candidate`` if its text is not already present."""
    seen = {anchor.text.lower() for anchor in anchors}
    if candidate.text.lower() not in seen:
        anchors.append(candidate)


def evidence_anchors(analysis: AnalysisOutput, limit: int = _MAX_ANCHORS) -> list[EvidenceAnchor]:
    """Extract compact visual proof points from existing analysis text and sources only."""
    anchors: list[EvidenceAnchor] = []
    blocks = [analysis.bottom_line] + [section.body for section in analysis.sections]
    for block in blocks:
        for sentence in _sentences(block):
            if _NUMBER_RE.search(sentence):
                _unique_anchor(anchors, EvidenceAnchor(text=_trim_words(sentence, 18)))
                if len(anchors) >= limit:
                    return anchors

    for source in analysis.sources:
        _unique_anchor(anchors, EvidenceAnchor(text=_source_label(source), source=source.url))
        if len(anchors) >= limit:
            return anchors
    return anchors


def brief_frame_context(
    analysis: AnalysisOutput,
    *,
    task_type: TaskType,
    audience: Audience | None = None,
) -> dict[str, Any]:
    """Jinja context additions for the PDF brief frame."""
    is_de = analysis.language == Language.DE
    audience_label = audience.value if audience is not None else "management"
    anchors = evidence_anchors(analysis)
    source_count = len(analysis.sources)
    gap_note = ""
    if not analysis.sources:
        gap_note = _t(
            analysis.language,
            "Keine Quellenliste im Analyseobjekt: ungestuetzte Aussagen als Luecke behandeln.",
            "No source list in the analysis object: treat unsupported claims as a gap.",
        )
    source_status = _t(
        analysis.language,
        "belegt" if source_count else "Luecke",
        "sourced" if source_count else "gap",
    )
    return {
        "artifact_label": (
            f"{framework_marker()} | "
            + _t(analysis.language, "beleggestuetztes PDF", "source-grounded PDF")
        ),
        "artifact_type": task_type.value,
        "artifact_audience": audience_label,
        "artifact_focus_label": _t(analysis.language, "Fokus", "Focus"),
        "artifact_focus": _trim_words(
            (_sentences(analysis.bottom_line) or [_gap_text(analysis.language)])[0], 22
        ),
        "evidence_label": "Beleganker" if is_de else "Evidence anchors",
        "evidence_anchors": [{"text": anchor.text, "source": anchor.source} for anchor in anchors],
        "proof_stat_label": _t(analysis.language, "Belege", "Proof"),
        "proof_stat": str(len(anchors)),
        "source_stat_label": _t(analysis.language, "Quellen", "Sources"),
        "source_stat": str(source_count),
        "gap_stat_label": _t(analysis.language, "Status", "Status"),
        "gap_stat": source_status,
        "gap_note": gap_note,
    }


def _gap_text(language: Language) -> str:
    """Deck-safe evidence-gap text."""
    return _t(
        language,
        "Evidenzluecke: keine belastbare Stuetzung im Analyseobjekt.",
        "Evidence gap: no sourced support in the analysis object.",
    )


def _section_claim_heading(section: Section, analysis: AnalysisOutput) -> str:
    """Return a claim-style section heading without inventing content."""
    heading = _trim_words(section.heading, 14)
    if _clean(heading).lower() not in _GENERIC_HEADLINES and heading.lower() != "section":
        return heading
    body_sentences = _sentences(section.body)
    if body_sentences:
        return _trim_words(body_sentences[0], 14)
    if analysis.bottom_line:
        return _trim_words(_sentences(analysis.bottom_line)[0], 14)
    return _t(analysis.language, "Evidenzluecke sichtbar machen", "Make the evidence gap visible")


def prepare_brief_for_render(analysis: AnalysisOutput) -> AnalysisOutput:
    """Apply the mandatory PDF frame before HTML/PDF rendering.

    This is the deterministic half of the artifact framework. It never creates new facts; it
    turns generic headings into claim headings from the existing body, guarantees a visible bottom
    line/gap, and keeps the renderer from producing a blank or generic report shell.
    """
    bottom_line = analysis.bottom_line.strip() or _gap_text(analysis.language)
    sections = [
        section.model_copy(update={"heading": _section_claim_heading(section, analysis)})
        for section in analysis.sections
    ]
    if not sections:
        sections = [
            Section(
                heading=_t(
                    analysis.language,
                    "Keine belastbaren Detailbelege vorhanden",
                    "No detailed supporting evidence is available",
                ),
                body=_gap_text(analysis.language),
            )
        ]
    return analysis.model_copy(update={"bottom_line": bottom_line, "sections": sections})


def _bottom_line_bullets(analysis: AnalysisOutput | None, language: Language) -> list[str]:
    """Build executive-summary bullets from the existing bottom line only."""
    if analysis is None or not analysis.bottom_line.strip():
        return [_gap_text(language)]
    bullets = [
        _trim_words(sentence, _MAX_BULLET_WORDS) for sentence in _sentences(analysis.bottom_line)
    ]
    return bullets[:3] or [_gap_text(language)]


def _is_generic_headline(headline: str, slide_type: SlideType) -> bool:
    """Return True when the headline is a topic label instead of a claim."""
    if slide_type == SlideType.APPENDIX:
        return False
    return _clean(headline).lower() in _GENERIC_HEADLINES


def _claim_headline(
    slide: SlideContent,
    analysis: AnalysisOutput | None,
    content_index: int,
) -> str:
    """Replace generic headings with existing claim text from the analysis or slide body."""
    if not _is_generic_headline(slide.headline, slide.slide_type):
        return _trim_words(slide.headline, 14)
    if analysis is not None and content_index < len(analysis.sections):
        return _trim_words(analysis.sections[content_index].heading, 14)
    if slide.body:
        return _trim_words(slide.body, 14)
    if analysis is not None and analysis.bottom_line:
        return _trim_words(_sentences(analysis.bottom_line)[0], 14)
    return _trim_words(slide.headline, 14)


def _normalize_bullets(slide: SlideContent, language: Language) -> list[str]:
    """Keep slide support tight while preserving the original facts."""
    bullets = [
        _trim_words(strip_label_prefix(bullet), _MAX_BULLET_WORDS)
        for bullet in slide.bullets
        if _clean(bullet)
    ]
    if slide.slide_type == SlideType.TITLE:
        return bullets[:_MAX_BULLETS]
    if not bullets and not slide.table and not (slide.body and _clean(slide.body)):
        bullets = [_gap_text(language)]
    return bullets[:_MAX_BULLETS]


def _normalize_slide(
    slide: SlideContent,
    analysis: AnalysisOutput | None,
    language: Language,
    content_index: int,
) -> SlideContent:
    """Apply the deterministic deck guardrails to one slide."""
    body = _trim_words(strip_label_prefix(slide.body), _MAX_BODY_WORDS) if slide.body else None
    return slide.model_copy(
        update={
            "headline": strip_label_prefix(_claim_headline(slide, analysis, content_index)),
            "bullets": _normalize_bullets(slide, language),
            "body": body,
        }
    )


def _has_title(slides: list[SlideContent]) -> bool:
    """Whether the deck already starts with a title slide."""
    return bool(slides and slides[0].slide_type == SlideType.TITLE)


def _has_exec_summary(slides: list[SlideContent]) -> bool:
    """Whether the deck already has an executive-summary slide."""
    return any(slide.slide_type == SlideType.EXECUTIVE_SUMMARY for slide in slides)


def _has_sources_appendix(slides: list[SlideContent]) -> bool:
    """Whether an appendix/source slide already exists."""
    for slide in slides:
        if slide.slide_type != SlideType.APPENDIX:
            continue
        text = " ".join([slide.headline, slide.body or "", *slide.bullets]).lower()
        if any(marker in text for marker in ("source", "sources", "quelle", "quellen", "http")):
            return True
    return False


def _has_evidence_slide(slides: list[SlideContent]) -> bool:
    """Whether the deck already has a visible proof/evidence slide."""
    markers = ("evidence", "proof", "source base", "beleg", "quellenbasis")
    for slide in slides:
        if slide.slide_type in {
            SlideType.TITLE,
            SlideType.EXECUTIVE_SUMMARY,
            SlideType.APPENDIX,
        }:
            continue
        text = " ".join([slide.headline, slide.body or "", *slide.bullets]).lower()
        if any(marker in text for marker in markers):
            return True
    return False


def _has_recommendation(slides: list[SlideContent]) -> bool:
    """Whether the deck already contains a decision/recommendation moment."""
    return any(slide.slide_type == SlideType.RECOMMENDATION for slide in slides)


_SOURCES_PER_APPENDIX = 18  # two columns x nine rows fit the appendix content area


def _sources_slides(analysis: AnalysisOutput, language: Language) -> list[SlideContent]:
    """Build the bibliography from the FULL cited-source list, paginated across appendix slides.

    Uses every source the synthesizer compiled (``analysis.sources`` == ``compile_cited_sources``),
    never just the two an LLM happened to echo into its own appendix (the v3 '2 sources' bug). Adds
    no provenance — it only lists what was already cited.
    """
    head = "Quellen" if language == Language.DE else "Sources"
    if not analysis.sources:
        return [
            SlideContent(
                slide_type=SlideType.APPENDIX, headline=head, bullets=[_gap_text(language)]
            )
        ]
    bullets = [
        _trim_words(source.url + (f" - {source.title}" if source.title else ""), 18)
        for source in analysis.sources
    ]
    pages = [
        bullets[i : i + _SOURCES_PER_APPENDIX]
        for i in range(0, len(bullets), _SOURCES_PER_APPENDIX)
    ]
    total = len(pages)
    return [
        SlideContent(
            slide_type=SlideType.APPENDIX,
            headline=head if total == 1 else f"{head} ({idx + 1}/{total})",
            bullets=page,
        )
        for idx, page in enumerate(pages)
    ]


def _evidence_slide(analysis: AnalysisOutput, language: Language) -> SlideContent:
    """Build a compact evidence-anchor slide from existing facts/sources only."""
    anchors = evidence_anchors(analysis, limit=_MAX_DECK_ANCHORS)
    if anchors:
        bullets = [
            anchor.text + (f" ({_trim_words(anchor.source, 8)})" if anchor.source else "")
            for anchor in anchors
        ]
        headline = _t(
            language,
            f"Die Quellenbasis zeigt {len(anchors)} konkrete Beleganker",
            f"The source base shows {len(anchors)} concrete evidence anchors",
        )
        body = _t(language, "Nur validierte Fakten sichtbar machen", "Only surface validated facts")
    else:
        bullets = [_gap_text(language)]
        headline = _t(
            language,
            "Die Quellenbasis reicht fuer starke Visualisierung nicht aus",
            "The source base is too thin for strong visualization",
        )
        body = _t(language, "Luecke sichtbar statt dekorativ kaschieren", "Show the gap plainly")
    return SlideContent(
        slide_type=SlideType.STRATEGIC_SIGNALS,
        headline=headline,
        body=body,
        bullets=bullets,
    )


def _recommendation_from_bottom_line(analysis: AnalysisOutput, language: Language) -> SlideContent:
    """Create a decision slide from the existing bottom line."""
    sentences = _sentences(analysis.bottom_line)
    decision = _trim_words(sentences[0], 18) if sentences else _gap_text(language)
    support = [_trim_words(sentence, _MAX_BULLET_WORDS) for sentence in sentences[1:4]]
    if not support:
        support = [_gap_text(language)] if not analysis.sources else []
    return SlideContent(
        slide_type=SlideType.RECOMMENDATION,
        headline=_t(
            language,
            "Naechster Management-Schritt folgt aus der Kernaussage",
            "The next management move follows from the bottom line",
        ),
        body=decision,
        bullets=support,
    )


def _insert_before_appendix(slides: list[SlideContent], slide: SlideContent) -> None:
    """Insert ``slide`` before the first appendix, or append if there is no appendix."""
    for idx, existing in enumerate(slides):
        if existing.slide_type == SlideType.APPENDIX:
            slides.insert(idx, slide)
            return
    slides.append(slide)


def prepare_deck_for_render(
    deck: DeckStructure,
    analysis: AnalysisOutput | None = None,
) -> DeckStructure:
    """Apply Porter's artifact framework before a PPTX is rendered.

    The function is deliberately conservative: it trims and structures existing content, inserts
    required frame slides when missing, and adds a source appendix from the analysis. It never adds
    new facts.
    """
    language = deck.language
    slides = list(deck.slides)
    if not _has_title(slides):
        slides.insert(
            0,
            SlideContent(
                slide_type=SlideType.TITLE,
                headline=analysis.title if analysis is not None else deck.title,
                body=framework_marker(),
            ),
        )

    normalized: list[SlideContent] = []
    content_index = 0
    for slide in slides:
        normalized_slide = _normalize_slide(slide, analysis, language, content_index)
        normalized.append(normalized_slide)
        if normalized_slide.slide_type not in {SlideType.TITLE, SlideType.APPENDIX}:
            content_index += 1

    if not _has_exec_summary(normalized):
        normalized.insert(
            1,
            SlideContent(
                slide_type=SlideType.EXECUTIVE_SUMMARY,
                headline="Kernaussage" if language == Language.DE else "Executive Summary",
                bullets=_bottom_line_bullets(analysis, language),
            ),
        )

    if analysis is not None and not _has_evidence_slide(normalized):
        normalized.insert(min(2, len(normalized)), _evidence_slide(analysis, language))

    if analysis is not None and not _has_recommendation(normalized):
        _insert_before_appendix(normalized, _recommendation_from_bottom_line(analysis, language))

    if analysis is not None:
        # Always (re)build the bibliography from the FULL cited-source list, paginated — never the
        # two sources the LLM happened to echo into its own appendix (the v3 '2 sources' bug).
        normalized = [s for s in normalized if s.slide_type != SlideType.APPENDIX]
        normalized.extend(_sources_slides(analysis, language))

    return deck.model_copy(update={"slides": normalized})


def deck_frame_label(language: Language, slide_type: SlideType) -> str:
    """Small slide-type marker for the rendered deck shell."""
    labels = {
        SlideType.TITLE: ("Titel", "Title"),
        SlideType.EXECUTIVE_SUMMARY: ("Kernaussage", "Executive summary"),
        SlideType.MARKET_LANDSCAPE: ("Marktbild", "Market landscape"),
        SlideType.COMPANY_DEEP_DIVE: ("Unternehmen", "Company deep dive"),
        SlideType.FINANCIAL_OVERVIEW: ("Finanzen", "Financial overview"),
        SlideType.COMPETITIVE_COMPARISON: ("Vergleich", "Comparison"),
        SlideType.STRATEGIC_SIGNALS: ("Signale", "Strategic signals"),
        SlideType.SWOT: ("SWOT", "SWOT"),
        SlideType.RECOMMENDATION: ("Empfehlung", "Recommendation"),
        SlideType.APPENDIX: ("Anhang", "Appendix"),
    }
    de, en = labels[slide_type]
    return _t(language, de, en)
