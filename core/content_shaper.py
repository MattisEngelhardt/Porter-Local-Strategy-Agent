"""Output shaping (Phase 4): turn a prose AnalysisOutput into typed deck/workbook structures.

The synthesizer produces a format-agnostic :class:`~models.synthesis.AnalysisOutput`
(title / bottom_line / sections / sources). The renderers need *typed, structured* content —
deck slides with a type + "so what" headline + bullets/table (``exporter.build_deck``), and Excel
matrices with per-entity numeric scores (``excel_builder``). This module runs **one structured LLM
call per deliverable** to shape that content, with deterministic, **fail-open** fallbacks so a bad
LLM/parse never blocks delivery (SPEC REQ-5). No content decisions live here (RULE 14): the prompts
restate the SPEC §11/§13 structure rules; the facts come from the analysis.
"""

from __future__ import annotations

from core.exporter import management_deck_structure
from core.json_utils import extract_json_array
from llm.local_llm_client import LLMError, LocalLLMClient
from models.deck import DeckStructure, SlideContent, SlideType
from models.synthesis import AnalysisOutput
from models.task import Intent, Language, TaskType

# Cap on shaped slides so a runaway response can't produce a 50-slide deck.
_MAX_SLIDES = 12
_SLIDE_TYPES = ", ".join(t.value for t in SlideType)

_DECK_SYSTEM = """You are a management-deck designer at Neura Robotics (pre-IPO cognitive humanoid \
robotics, Metzingen). Turn the analysis below into a sequence of board/management slides.

Rules (SPEC §11 + output_playbook):
- ONE message per slide. Every headline is the "so what" — a claim/insight, NEVER a topic label.
  BAD: "Competitive Landscape"   GOOD: "Three well-funded rivals are closing the gap".
- Keep supporting content tight (max ~25 words per slide); short bullets.
- Begin with a `title` slide, then an `executive_summary` slide that leads with the bottom line.
- Pick each slide's type from: {types}.
- Use `competitive_comparison` (with a `table`) to compare entities; `swot` for a 2x2 grid
  (table rows = [["Strengths","a; b"],["Weaknesses",...],["Opportunities",...],["Threats",...]]);
  `recommendation` for the decision (Go / No-Go / Watch) so it can stand alone.
{scr}- End with an `appendix` slide listing the sources.

Respond with ONLY a JSON array of 5-{max} slides — no prose. Each slide:
{{"slide_type": "<one of the allowed types>", "headline": "the so-what claim", \
"bullets": ["short point", ...], "body": "optional one-liner (title subtitle / decision text)", \
"table": [["header", ...], ["row", ...]] or null}}"""

_SCR_LINE = (
    "- This is a BUSINESS CASE: order the middle slides as Situation -> Complication -> Options "
    "(>=3) -> Financial Case -> Recommendation (the SCR framework, analysis_playbook §13).\n"
)


def _analysis_block(analysis: AnalysisOutput) -> str:
    """Render the analysis (title, bottom line, sections, sources) for the shaping prompt."""
    lines = [f"TITLE: {analysis.title}", f"BOTTOM LINE: {analysis.bottom_line}", "", "SECTIONS:"]
    for section in analysis.sections:
        lines.append(f"## {section.heading}\n{section.body}")
    if analysis.sources:
        lines.append("\nSOURCES:")
        lines.extend(f"- {s.url}{(' — ' + s.title) if s.title else ''}" for s in analysis.sources)
    lines.append("\nReturn the JSON array of slides now.")
    return "\n".join(lines)


def _coerce_slide_type(value: object) -> SlideType | None:
    """Coerce a raw slide-type value into :class:`SlideType` or ``None``."""
    if isinstance(value, str):
        try:
            return SlideType(value.strip().lower())
        except ValueError:
            return None
    return None


def _coerce_str_list(value: object) -> list[str]:
    """Coerce a raw value into a list of non-empty strings."""
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _coerce_table(value: object) -> list[list[str]] | None:
    """Coerce a raw value into a row-major table of strings, or ``None``."""
    if not isinstance(value, list) or not value:
        return None
    rows: list[list[str]] = []
    for row in value:
        if isinstance(row, list):
            rows.append([str(cell) for cell in row])
        elif row is not None:
            rows.append([str(row)])
    return rows or None


def _coerce_slides(array: list[object] | None, analysis: AnalysisOutput) -> list[SlideContent]:
    """Coerce the LLM's JSON array into validated :class:`SlideContent` objects (tolerant)."""
    if not array:
        return []
    slides: list[SlideContent] = []
    for item in array[:_MAX_SLIDES]:
        if not isinstance(item, dict):
            continue
        slide_type = _coerce_slide_type(item.get("slide_type"))
        headline = str(item.get("headline") or "").strip()
        if slide_type is None or not headline:
            continue
        body = item.get("body")
        slides.append(
            SlideContent(
                slide_type=slide_type,
                headline=headline,
                bullets=_coerce_str_list(item.get("bullets")),
                body=str(body).strip() if isinstance(body, str) and body.strip() else None,
                table=_coerce_table(item.get("table")),
            )
        )
    return slides


def shape_deck(
    client: LocalLLMClient,
    intent: Intent,
    analysis: AnalysisOutput,
    *,
    use_thinking: bool = True,
) -> DeckStructure:
    """Shape a prose analysis into a typed :class:`DeckStructure` via one LLM call (fail-open).

    Produces "so what" headlines and the right slide types (SCR ordering for a business case).
    Any LLM/parse failure — or an empty result — falls back to the deterministic
    :func:`~core.exporter.management_deck_structure` so delivery never blocks (SPEC REQ-5).
    """
    fallback = management_deck_structure(analysis, intent.language)
    scr = _SCR_LINE if intent.task_type == TaskType.BUSINESS_CASE else ""
    language = "German" if intent.language == Language.DE else "English"
    system = (
        _DECK_SYSTEM.format(types=_SLIDE_TYPES, scr=scr, max=_MAX_SLIDES)
        + f"\nWrite ALL slide text in {language}."
    )
    try:
        response = client.generate(
            _analysis_block(analysis), system=system, use_thinking=use_thinking
        )
        array = extract_json_array(response)
    except LLMError:
        return fallback

    slides = _coerce_slides(array, analysis)
    if not slides:
        return fallback
    if slides[0].slide_type != SlideType.TITLE:
        slides.insert(
            0, SlideContent(slide_type=SlideType.TITLE, headline=analysis.title, body=None)
        )
    return DeckStructure(title=analysis.title, language=intent.language, slides=slides)
