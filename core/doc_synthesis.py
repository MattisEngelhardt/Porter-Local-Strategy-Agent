"""Internal document-preparation mode (Phase 3.5): consolidate documents for the CEO Office.

The CEO-office counterpart to web research. Many tasks need NO research — the material is already
in hand (board packs, memos, financial models, reports). This module reads the provided documents
*deeply* and consolidates them into ONE management-ready briefing, then writes a structured
Markdown **blueprint** (the "Spickzettel") to ``./output/`` — the ordered sketch the final PDF/PPTX
(Phase 4) renders from. No web research, no planning step.

Two hard rules drive the prompts (``doc_prep_playbook.md``): **zero hallucination** (every fact
comes from the documents, gaps flagged) and **management-grade structure** (bottom line first, the
few numbers that matter, "so what" sections). LLM/parse failures degrade gracefully.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from core.artifact_framework import framework_prompt
from core.json_utils import extract_json_array
from core.playbooks import Playbooks
from core.synthesizer import parse_analysis
from llm.local_llm_client import LLMError, LocalLLMClient
from models.research import DocContent
from models.synthesis import AnalysisOutput, SynthesisInput
from models.task import Intent, Language

# Per-document excerpt cap so several documents fit in num_ctx (32768) while reading thoroughly.
_MAX_DOC_CHARS = 4500

_ROLE = (
    "You are a CEO-office analyst at Neura Robotics (pre-IPO cognitive humanoid robotics company, "
    "Metzingen). You prepare INTERNAL documents for top management: you read everything carefully "
    "and consolidate it into ONE flawless, decision-ready briefing — bottom line first, no filler."
)

_NO_HALLUCINATION = (
    "# ABSOLUTE RULE — ZERO HALLUCINATION\n"
    "Every fact, number, name, and date MUST come from the provided documents. If it is not in "
    "them, do NOT include it. Quote numbers exactly (with unit + period). If documents disagree or "
    "a value is unclear, say so and cite both. Mark anything the documents do not answer as an "
    "explicit gap. Never invent or 'round' figures. Attribute key claims to their source document."
)

_RESPONSE_FORMAT = (
    "# RESPONSE FORMAT\n"
    "Respond with ONLY a JSON object — no prose, no markdown fences:\n"
    '{"title": "...", '
    '"bottom_line": "decision-first summary (2-3 sentences) management can act on", '
    '"sections": [{"heading": "a \'so what\' heading, not a topic label", "body": "tight, '
    'management-relevant content with figures + their source document"}], '
    '"sources": [{"url": "<source document file name>", "title": "what it provided"}]}\n'
    "Order sections by importance. Lead with the bottom line. Flag gaps explicitly."
)


def build_briefing_system(intent: Intent, brain: str, playbooks: Playbooks) -> str:
    """Assemble the doc-prep system prompt: role + language + brain + playbooks + no-halluc rule."""
    language = "German" if intent.language == Language.DE else "English"
    parts = [_ROLE, f"\nWrite ALL output in {language}."]
    if brain.strip():
        parts.append("\n# PERSISTENT CONTEXT (brain.md)\n" + brain.strip())
    parts.append("\n# DOCUMENT-PREPARATION PLAYBOOK\n" + playbooks.doc_prep)
    parts.append("\n# OUTPUT PLAYBOOK\n" + playbooks.output)
    parts.append("\n# PDF/PPTX ARTIFACT FRAMEWORK\n" + playbooks.artifact_framework)
    parts.append("\n" + framework_prompt())
    parts.append("\n" + _NO_HALLUCINATION)
    parts.append("\n" + _RESPONSE_FORMAT)
    return "\n".join(parts)


def _documents_block(documents: list[DocContent]) -> str:
    """Render the provided documents (name + type + capped full text) for a prompt."""
    lines = [f"INTERNAL DOCUMENTS PROVIDED ({len(documents)}):"]
    for idx, doc in enumerate(documents, start=1):
        excerpt = doc.text.strip()[:_MAX_DOC_CHARS]
        truncated = " … (truncated)" if len(doc.text.strip()) > _MAX_DOC_CHARS else ""
        lines.append(f"\n[D{idx}] {doc.source_path.name} ({doc.doc_type}):\n{excerpt}{truncated}")
    return "\n".join(lines)


def build_briefing_user(intent: Intent, documents: list[DocContent], guidance: str = "") -> str:
    """Assemble the user prompt: task + each document + any user guidance from clarifications."""
    lines = [f"TASK: {intent.summary or 'Consolidate the documents below for top management.'}"]
    lines.append("\n" + _documents_block(documents))
    if guidance.strip():
        lines.append(
            "\nUSER GUIDANCE (answers to your clarifying questions — follow these on emphasis, "
            "audience, format, and style):\n" + guidance.strip()
        )
    lines.append("\nProduce the consolidated management briefing as the specified JSON now.")
    return "\n".join(lines)


_QUESTION_SYSTEM = (
    "You are a CEO-office analyst who has just read the internal documents below. First understand "
    "the key themes, then ask up to {n} PRECISE, high-value clarifying questions so the management "
    "briefing comes out exactly right. Good questions are specific to what you actually read — "
    "which theme to emphasize, the audience and target format (PDF brief vs. board deck), the "
    "tone/level of detail, and anything in the documents that is ambiguous or where figures look "
    "conflicting or uncertain. Ask ONLY what genuinely changes the briefing; never ask what the "
    "documents already make clear. Respond with ONLY a JSON array of question strings (or [] if "
    "nothing material is unclear) — no prose."
)


def propose_doc_questions(
    client: LocalLLMClient,
    intent: Intent,
    documents: list[DocContent],
    max_questions: int,
) -> list[str]:
    """Read the documents and propose up to ``max_questions`` targeted clarifying questions.

    Fail-open: an LLM/parse error yields no questions (the briefing proceeds without them).
    """
    if max_questions <= 0 or not documents:
        return []
    language = "German" if intent.language == Language.DE else "English"
    system = _QUESTION_SYSTEM.format(n=max_questions) + f" Ask in {language}."
    user = (
        f"TASK: {intent.summary or '(prepare a management briefing)'}\n\n"
        f"{_documents_block(documents)}\n\nReturn the JSON array of questions now."
    )
    try:
        response = client.generate(user, system=system, use_thinking=False)
        array = extract_json_array(response)
    except LLMError:
        return []
    if not array:
        return []
    questions = [str(q).strip() for q in array if isinstance(q, str) and str(q).strip()]
    return questions[:max_questions]


def synthesize_briefing(
    client: LocalLLMClient,
    intent: Intent,
    documents: list[DocContent],
    brain: str,
    playbooks: Playbooks,
    guidance: str = "",
) -> AnalysisOutput:
    """Read the documents deeply and consolidate them into a structured management briefing.

    ``guidance`` carries the user's answers to the agent's clarifying questions (emphasis,
    audience, format, style). Uses thinking mode (careful reading). On LLM failure degrades to an
    error briefing; the JSON is parsed via the shared :func:`~core.synthesizer.parse_analysis` path.
    """
    si = SynthesisInput(intent=intent, documents=documents, brain_context=brain)
    system = build_briefing_system(intent, brain, playbooks)
    user = build_briefing_user(intent, documents, guidance)
    try:
        response = client.generate(user, system=system, use_thinking=True)
    except LLMError as exc:
        return AnalysisOutput(
            title=(intent.summary or "Document Briefing")[:120],
            language=intent.language,
            bottom_line=f"(Document preparation failed — LLM backend error: {exc})",
            recommended_formats=intent.output_formats,
        )
    return parse_analysis(response, si)


def to_management_markdown(
    analysis: AnalysisOutput, documents: list[DocContent], language: Language
) -> str:
    """Render the briefing into the Markdown blueprint (the Spickzettel for the final PDF/PPTX)."""
    is_de = language == Language.DE
    files = ", ".join(doc.source_path.name for doc in documents) or "—"
    lines = [
        f"# {analysis.title}",
        "",
        f"_{date.today().isoformat()} · "
        + ("Quelldokumente" if is_de else "Source documents")
        + f": {files} · {analysis.language.value}_",
        "",
        "## " + ("Kernaussage" if is_de else "Bottom Line"),
        "",
        analysis.bottom_line.strip() or "—",
        "",
    ]
    for section in analysis.sections:
        lines.append(f"## {section.heading}")
        lines.append("")
        lines.append(section.body.strip() or "—")
        lines.append("")
    lines.append("## " + ("Quelldokumente" if is_de else "Source Documents"))
    lines.append("")
    if analysis.sources:
        for src in analysis.sources:
            note = f" — {src.title}" if src.title else ""
            lines.append(f"- {src.url}{note}")
    else:
        for doc in documents:
            lines.append(f"- {doc.source_path.name} ({doc.doc_type})")
    note = (
        "_Blueprint (Spickzettel) für das finale PDF/PPTX (Phase 4)._"
        if is_de
        else "_Blueprint (cheat-sheet) for the final PDF/PPTX (Phase 4)._"
    )
    lines += ["", "---", note, ""]
    return "\n".join(lines)


def _slug(text: str) -> str:
    """Make a short, filesystem-safe slug from a title."""
    cleaned = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return (cleaned or "briefing")[:50]


def write_briefing_md(markdown: str, output_dir: str | Path, title: str) -> Path:
    """Write the Markdown blueprint to ``output_dir`` and return its path (created if needed)."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{date.today().isoformat()}_{_slug(title)}_briefing.md"
    path.write_text(markdown, encoding="utf-8")
    return path
