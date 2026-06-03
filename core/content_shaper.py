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

from core.artifact_framework import ArtifactKind, framework_prompt
from core.exporter import management_deck_structure
from core.json_utils import extract_json_array, extract_json_object
from llm.local_llm_client import LLMError, LocalLLMClient
from models.deck import DeckStructure, SlideContent, SlideType
from models.synthesis import AnalysisOutput
from models.task import Intent, Language, TaskType
from models.visuals import ChartSeries, ChartSpec, ChartType
from models.workbook import (
    BenchmarkData,
    BenchmarkRow,
    BenchmarkSource,
    BusinessCaseData,
    CaseAssumption,
    DecisionMatrixData,
    EntityScores,
    ExcelTemplate,
    ScoringCriterion,
    TrackerData,
    TrackerItem,
)

# Structured Excel content shaped from the analysis (template + its typed data).
WorkbookData = DecisionMatrixData | BenchmarkData | BusinessCaseData | TrackerData

# Cap on shaped slides so a runaway response can't produce a 50-slide deck.
_MAX_SLIDES = 12
_SLIDE_TYPES = ", ".join(t.value for t in SlideType)


def _t(language: Language, de: str, en: str) -> str:
    """Pick the German or English string for the language."""
    return de if language == Language.DE else en


_DECK_SYSTEM = """You are a management-deck designer at Neura Robotics (pre-IPO cognitive humanoid \
robotics, Metzingen). Turn the analysis below into a sequence of board/management slides.

Rules (SPEC §11 + output_playbook + Porter Artifact Framework):
- ONE message per slide. Every headline is the "so what" — a claim/insight, NEVER a topic label.
  BAD: "Competitive Landscape"   GOOD: "Three well-funded rivals are closing the gap".
- Use premium, vivid slide models: evidence anchors, decision callouts, risk/option frames,
  comparison tables, and source appendices. No cheap decoration, clip-art, or generic filler.
- Keep supporting content tight; if a message needs more space, split the slide rather than
  shrinking type.
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

# Folded data-visual instruction (server/ultra via the effort dial — see core.pipeline). The chart
# rides along in the SAME shaping call (no extra LLM round-trip); the candidate is still grounded
# against the analysis/evidence in core.visual_selector before it is ever charted.
_VISUAL_INSTRUCTIONS = (
    "\n\nDATA VISUAL (optional): for a slide whose message is a comparison, a time trend, or "
    'shares of a whole built from numbers ALREADY in the analysis, add a "visual" object to that '
    "slide (omit it otherwise — never invent a number):\n"
    '"visual": {"chart_type": "column|bar|line|donut", "categories": ["label", ...], '
    '"series": [{"name": "metric (unit)", "values": [<one number per category>]}], '
    '"caption": "the so-what", "unit": "m|%|x|..."}\n'
    "- >=2 categories; each series carries exactly one value per category; every value must appear "
    "in the analysis. column/bar = comparison, line = time trend, donut = shares of a whole."
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


def _coerce_chart_type(value: object) -> ChartType:
    """Coerce a raw chart-type value into :class:`ChartType` (defaults to COLUMN)."""
    if isinstance(value, str):
        try:
            return ChartType(value.strip().lower())
        except ValueError:
            return ChartType.COLUMN
    return ChartType.COLUMN


def _coerce_series(value: object) -> list[ChartSeries]:
    """Coerce a raw value into a list of :class:`ChartSeries` (values forced numeric)."""
    series: list[ChartSeries] = []
    for item in _as_list(value):
        if not isinstance(item, dict):
            continue
        values = [_coerce_float(v) for v in _as_list(item.get("values"))]
        series.append(ChartSeries(name=str(item.get("name") or "").strip(), values=values))
    return series


def _coerce_visual(value: object) -> ChartSpec | None:
    """Coerce a folded-LLM ``visual`` object into a :class:`ChartSpec`, or ``None`` (fail-open).

    The :class:`ChartSpec` model *is* the schema: a length-mismatched or otherwise unrenderable
    candidate fails its validator and is dropped here, so only a parse-safe spec reaches the
    grounding gate (:func:`core.visuals.validate_spec`) in ``core.visual_selector``. No number is
    ever fabricated — invented values are caught later by grounding against the analysis/evidence.
    """
    if not isinstance(value, dict):
        return None
    categories = [str(c).strip() for c in _as_list(value.get("categories")) if str(c).strip()]
    series = _coerce_series(value.get("series"))
    if not categories or not series:
        return None
    try:
        return ChartSpec(
            chart_type=_coerce_chart_type(value.get("chart_type")),
            categories=categories,
            series=series,
            caption=str(value.get("caption") or "").strip(),
            unit=str(value.get("unit") or "").strip(),
            source=str(value.get("source") or "").strip(),
        )
    except (ValueError, TypeError):
        return None


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
                visual=_coerce_visual(item.get("visual")),
            )
        )
    return slides


def shape_deck(
    client: LocalLLMClient,
    intent: Intent,
    analysis: AnalysisOutput,
    *,
    use_thinking: bool = True,
    propose_visuals: bool = False,
) -> DeckStructure:
    """Shape a prose analysis into a typed :class:`DeckStructure` via one LLM call (fail-open).

    Produces "so what" headlines and the right slide types (SCR ordering for a business case).
    When ``propose_visuals`` is set (server/ultra via the effort dial — laptop default is off), the
    shaper may also attach a ``visual`` chart spec to data slides *in the same call* (no extra LLM
    round-trip); every candidate is still grounded in :mod:`core.visual_selector` before charting.
    Any LLM/parse failure — or an empty result — falls back to the deterministic
    :func:`~core.exporter.management_deck_structure` so delivery never blocks (SPEC REQ-5).
    """
    fallback = management_deck_structure(analysis, intent.language)
    scr = _SCR_LINE if intent.task_type == TaskType.BUSINESS_CASE else ""
    language = "German" if intent.language == Language.DE else "English"
    system = (
        _DECK_SYSTEM.format(types=_SLIDE_TYPES, scr=scr, max=_MAX_SLIDES)
        + "\n\n"
        + framework_prompt(ArtifactKind.PPTX)
        + (_VISUAL_INSTRUCTIONS if propose_visuals else "")
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


# ============================================================ workbook shaping (E-1..E-4)
# Deterministic task-type → Excel template routing (SPEC §12 / §5.4).
_TEMPLATE_FOR_TASK: dict[TaskType, ExcelTemplate] = {
    TaskType.TARGET_SCREENING: ExcelTemplate.DECISION_MATRIX,
    TaskType.PARTNERSHIP_EVALUATION: ExcelTemplate.DECISION_MATRIX,
    TaskType.OPTION_COMPARISON: ExcelTemplate.DECISION_MATRIX,
    TaskType.STRATEGIC_INITIATIVE: ExcelTemplate.DECISION_MATRIX,
    TaskType.FINANCIAL_BENCHMARK: ExcelTemplate.BENCHMARK_TABLE,
    TaskType.MARKET_ANALYSIS: ExcelTemplate.BENCHMARK_TABLE,
    TaskType.BUSINESS_CASE: ExcelTemplate.BUSINESS_CASE_MODEL,
    TaskType.PIPELINE_TRACKING: ExcelTemplate.TRACKER_DASHBOARD,
}


def workbook_template_for(task_type: TaskType) -> ExcelTemplate:
    """Map a task type to its Excel template (SPEC §12); defaults to the Decision Matrix (E-1)."""
    return _TEMPLATE_FOR_TASK.get(task_type, ExcelTemplate.DECISION_MATRIX)


def _as_list(value: object) -> list[object]:
    """Return ``value`` as a list of objects (empty if it is not a list) — narrows for mypy."""
    return list(value) if isinstance(value, list) else []


def _coerce_float(value: object, default: float = 0.0) -> float:
    """Coerce a raw JSON value (number or numeric string) into a float."""
    if isinstance(value, bool):
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(",", "").replace("%", "").replace("€", "").replace("$", "")
        try:
            return float(cleaned)
        except ValueError:
            return default
    return default


def _shape_json(
    client: LocalLLMClient, system: str, user: str, *, use_thinking: bool
) -> dict[str, object] | None:
    """Run one structured shaping call and return the parsed JSON object (fail-open → None)."""
    try:
        response = client.generate(user, system=system, use_thinking=use_thinking)
    except LLMError:
        return None
    return extract_json_object(response)


# ---------------------------------------------------------------- E-1 Decision Matrix shaping
_MATRIX_SYSTEM = """You build a weighted decision/scoring matrix for Neura Robotics' Corporate \
Development team. From the analysis, extract the entities being compared and the scoring criteria.

Rules:
- Pick 4-6 decision criteria appropriate to the task (e.g. M&A screen: Technology Fit, Market \
Access, Integration Complexity, Valuation Signal, Team Quality — analysis_playbook §13).
- Assign each criterion a weight (relative importance); they need not sum to 100 (normalized later).
- Score each entity 1 (worst) .. 5 (best) on each criterion, in the SAME order as the criteria.
- Only use entities and facts present in the analysis; do NOT invent companies.

Respond with ONLY a JSON object — no prose:
{"criteria": [{"name": "...", "weight": 25, "definition": "how to score 1..5"}],
 "entities": [{"name": "...", "scores": [4,3,5,...], "notes": ["evidence per criterion", ...]}]}"""


def _fallback_matrix(intent: Intent, analysis: AnalysisOutput) -> DecisionMatrixData:
    """Deterministic E-1 data when shaping fails: entities from sources, generic criteria."""
    criteria = [
        ScoringCriterion(name=name, weight=1.0)
        for name in ("Strategic Fit", "Market Access", "Execution Risk", "Financial Signal")
    ]
    seen: list[str] = []
    for source in analysis.sources:
        label = source.title or source.url
        if label and label not in seen:
            seen.append(label)
    entities = [EntityScores(name=name[:60], scores=[3, 3, 3, 3]) for name in seen[:6]] or [
        EntityScores(name=_t(intent.language, "Option A", "Option A"), scores=[3, 3, 3, 3])
    ]
    return DecisionMatrixData(
        title=analysis.title, language=intent.language, criteria=criteria, entities=entities
    )


def _shape_matrix(
    client: LocalLLMClient, intent: Intent, analysis: AnalysisOutput, *, use_thinking: bool
) -> DecisionMatrixData:
    """Shape an E-1 Decision Matrix from the analysis (fail-open to a deterministic matrix)."""
    language = "German" if intent.language == Language.DE else "English"
    data = _shape_json(
        client,
        _MATRIX_SYSTEM + f"\nWrite criterion names/notes in {language}.",
        _analysis_block(analysis),
        use_thinking=use_thinking,
    )
    if not data:
        return _fallback_matrix(intent, analysis)
    criteria: list[ScoringCriterion] = []
    for item in _as_list(data.get("criteria")):
        if isinstance(item, dict) and str(item.get("name", "")).strip():
            criteria.append(
                ScoringCriterion(
                    name=str(item["name"]).strip(),
                    weight=_coerce_float(item.get("weight"), 1.0) or 1.0,
                    definition=str(item.get("definition") or "").strip(),
                )
            )
    entities: list[EntityScores] = []
    for item in _as_list(data.get("entities")):
        if isinstance(item, dict) and str(item.get("name", "")).strip():
            scores = [int(_coerce_float(s, 3)) for s in _as_list(item.get("scores"))]
            notes = [str(x) for x in _as_list(item.get("notes"))]
            entities.append(
                EntityScores(name=str(item["name"]).strip(), scores=scores, notes=notes)
            )
    if not criteria or not entities:
        return _fallback_matrix(intent, analysis)
    return DecisionMatrixData(
        title=analysis.title, language=intent.language, criteria=criteria, entities=entities
    )


# ---------------------------------------------------------------- E-2 Benchmark shaping
_BENCHMARK_SYSTEM = """You build a factual benchmark table (no scoring) for Neura Robotics. From \
the analysis, extract the entities and the metrics to compare them on.

Rules:
- Choose 4-8 relevant metric columns (e.g. Founded, HQ, Total Funding, Last Round, Lead Investor, \
Valuation, Headcount, Core Product). Facts only — no opinions or scores.
- One row per entity, values in the SAME order as the metrics. Use "" for unknowns.
- Only entities/facts present in the analysis.

Respond with ONLY a JSON object — no prose:
{"metrics": ["Founded", "HQ", ...],
 "rows": [{"name": "...", "values": ["2022", "Sunnyvale", ...]}],
 "sources": [{"entity": "...", "metric": "...", "value": "...", "url": "...", "date": "...", \
"confidence": "High|Medium|Estimate"}]}"""


def _fallback_benchmark(intent: Intent, analysis: AnalysisOutput) -> BenchmarkData:
    """Deterministic E-2 data when shaping fails: a generic metric set, rows from sources."""
    metrics = ["Overview", "Source"]
    rows = [
        BenchmarkRow(name=(s.title or s.url)[:60], values=["—", s.url])
        for s in analysis.sources[:8]
    ] or [BenchmarkRow(name="—", values=["—", "—"])]
    return BenchmarkData(title=analysis.title, language=intent.language, metrics=metrics, rows=rows)


def _shape_benchmark(
    client: LocalLLMClient, intent: Intent, analysis: AnalysisOutput, *, use_thinking: bool
) -> BenchmarkData:
    """Shape an E-2 Benchmark Table from the analysis (fail-open to a deterministic table)."""
    language = "German" if intent.language == Language.DE else "English"
    data = _shape_json(
        client,
        _BENCHMARK_SYSTEM + f"\nWrite metric names in {language}.",
        _analysis_block(analysis),
        use_thinking=use_thinking,
    )
    if not data:
        return _fallback_benchmark(intent, analysis)
    metrics = [str(m).strip() for m in _as_list(data.get("metrics")) if str(m).strip()]
    rows: list[BenchmarkRow] = []
    for item in _as_list(data.get("rows")):
        if isinstance(item, dict) and str(item.get("name", "")).strip():
            values = [str(v) for v in _as_list(item.get("values"))]
            rows.append(BenchmarkRow(name=str(item["name"]).strip(), values=values))
    sources: list[BenchmarkSource] = []
    for item in _as_list(data.get("sources")):
        if isinstance(item, dict):
            sources.append(
                BenchmarkSource(
                    entity=str(item.get("entity") or ""),
                    metric=str(item.get("metric") or ""),
                    value=str(item.get("value") or ""),
                    url=str(item.get("url") or ""),
                    date=str(item.get("date") or ""),
                    confidence=str(item.get("confidence") or ""),
                )
            )
    if not metrics or not rows:
        return _fallback_benchmark(intent, analysis)
    return BenchmarkData(
        title=analysis.title, language=intent.language, metrics=metrics, rows=rows, sources=sources
    )


# ---------------------------------------------------------------- E-3 Business Case shaping
_CASE_SYSTEM = """You extract the financial drivers for a business-case model for Neura Robotics. \
From the analysis, estimate the headline assumptions (flag them as estimates — they are inputs the \
user will refine). Use realistic magnitudes consistent with the analysis; never invent precise \
figures the analysis does not support.

Respond with ONLY a JSON object — no prose (all amounts in EUR, rates as decimals e.g. 0.3 = 30%):
{"investment": 2000000, "revenue_year1": 1500000, "revenue_growth": 0.3, "opex_year1": 900000, \
"opex_growth": 0.15, "discount_rate": 0.12, "years": 3,
 "assumptions": [{"name": "Market size", "value": 500000000, "unit": "EUR", "source": "...", \
"confidence": "Estimate"}], "bottom_line": "2-sentence recommendation"}"""


def _shape_business_case(
    client: LocalLLMClient, intent: Intent, analysis: AnalysisOutput, *, use_thinking: bool
) -> BusinessCaseData:
    """Shape an E-3 Business Case model from the analysis (fail-open to neutral defaults)."""
    language = "German" if intent.language == Language.DE else "English"
    base = BusinessCaseData(
        title=analysis.title, language=intent.language, bottom_line=analysis.bottom_line[:300]
    )
    data = _shape_json(
        client,
        _CASE_SYSTEM + f"\nWrite assumption names + bottom_line in {language}.",
        _analysis_block(analysis),
        use_thinking=use_thinking,
    )
    if not data:
        return base
    assumptions: list[CaseAssumption] = []
    for item in _as_list(data.get("assumptions")):
        if isinstance(item, dict) and str(item.get("name", "")).strip():
            assumptions.append(
                CaseAssumption(
                    name=str(item["name"]).strip(),
                    value=_coerce_float(item.get("value")),
                    unit=str(item.get("unit") or ""),
                    source=str(item.get("source") or ""),
                    confidence=str(item.get("confidence") or ""),
                )
            )
    years = int(_coerce_float(data.get("years"), 3)) or 3
    return BusinessCaseData(
        title=analysis.title,
        language=intent.language,
        years=max(1, min(5, years)),
        investment=_coerce_float(data.get("investment")),
        revenue_year1=_coerce_float(data.get("revenue_year1")),
        revenue_growth=_coerce_float(data.get("revenue_growth"), 0.3),
        opex_year1=_coerce_float(data.get("opex_year1")),
        opex_growth=_coerce_float(data.get("opex_growth"), 0.15),
        discount_rate=_coerce_float(data.get("discount_rate"), 0.12),
        assumptions=assumptions,
        bottom_line=str(data.get("bottom_line") or analysis.bottom_line)[:300],
    )


# ---------------------------------------------------------------- E-4 Tracker shaping
_TRACKER_SYSTEM = """You build a pipeline/initiative tracker for Neura Robotics. From the \
analysis, list the items to track (companies/options/initiatives) with a category and a sensible \
starting status/priority.

Respond with ONLY a JSON object — no prose:
{"items": [{"name": "...", "category": "...", "status": "Active|On Hold|Completed|Dropped", \
"priority": "High|Medium|Low", "owner": "", "next_step": "...", "notes": "..."}]}"""


def _fallback_tracker(intent: Intent, analysis: AnalysisOutput) -> TrackerData:
    """Deterministic E-4 data when shaping fails: one item per source/section."""
    names: list[str] = [s.title or s.url for s in analysis.sources if (s.title or s.url)]
    if not names:
        names = [section.heading for section in analysis.sections]
    items = [TrackerItem(name=name[:60]) for name in names[:20]]
    return TrackerData(title=analysis.title, language=intent.language, items=items)


def _shape_tracker(
    client: LocalLLMClient, intent: Intent, analysis: AnalysisOutput, *, use_thinking: bool
) -> TrackerData:
    """Shape an E-4 Tracker from the analysis (fail-open to a deterministic tracker)."""
    language = "German" if intent.language == Language.DE else "English"
    data = _shape_json(
        client,
        _TRACKER_SYSTEM + f"\nWrite item text in {language}.",
        _analysis_block(analysis),
        use_thinking=use_thinking,
    )
    if not data:
        return _fallback_tracker(intent, analysis)
    items: list[TrackerItem] = []
    for item in _as_list(data.get("items")):
        if isinstance(item, dict) and str(item.get("name", "")).strip():
            items.append(
                TrackerItem(
                    name=str(item["name"]).strip(),
                    category=str(item.get("category") or ""),
                    status=str(item.get("status") or "Active"),
                    priority=str(item.get("priority") or "Medium"),
                    owner=str(item.get("owner") or ""),
                    next_step=str(item.get("next_step") or ""),
                    notes=str(item.get("notes") or ""),
                )
            )
    if not items:
        return _fallback_tracker(intent, analysis)
    return TrackerData(title=analysis.title, language=intent.language, items=items)


def shape_workbook(
    client: LocalLLMClient,
    intent: Intent,
    analysis: AnalysisOutput,
    *,
    template: ExcelTemplate | None = None,
    use_thinking: bool = True,
) -> tuple[ExcelTemplate, WorkbookData]:
    """Shape the analysis into typed Excel data for the routed template (one LLM call, fail-open).

    Routes the task type to its Excel template (E-1..E-4, SPEC §12) unless ``template`` is given,
    then extracts the typed structured data via one shaping call. Every path falls back to a
    deterministic builder so a bad LLM/parse never blocks delivery (SPEC REQ-5). Returns the
    resolved template + its data, ready for the matching ``core.excel_builder`` function.
    """
    resolved = template or workbook_template_for(intent.task_type)
    if resolved == ExcelTemplate.BENCHMARK_TABLE:
        return resolved, _shape_benchmark(client, intent, analysis, use_thinking=use_thinking)
    if resolved == ExcelTemplate.BUSINESS_CASE_MODEL:
        return resolved, _shape_business_case(client, intent, analysis, use_thinking=use_thinking)
    if resolved == ExcelTemplate.TRACKER_DASHBOARD:
        return resolved, _shape_tracker(client, intent, analysis, use_thinking=use_thinking)
    return resolved, _shape_matrix(client, intent, analysis, use_thinking=use_thinking)
