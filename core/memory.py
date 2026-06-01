"""Memory layer (Phase 3 brain.md inject · Phase 5 ChromaDB session memory + brain-update flow).

Two layers (SPEC §4.5):

* **Layer 1 — brain.md** (always-on, read-only injection): :func:`load_brain` strips human
  scaffolding and returns the persistent Neura context injected into every synthesis call.
  Phase 5 adds the *brain-update flow*: :func:`propose_brain_additions` asks the model for
  high-signal durable additions and :func:`append_brain_additions` writes the user-confirmed
  ones back (the REPL drives the [y/N] confirm).
* **Layer 2 — ChromaDB** (session memory, Phase 5): :class:`MemoryStore` writes each run's
  synthesized analysis (with entities + timestamp + quality rating) as an embedded document and
  retrieves the most similar prior runs before a new one. :func:`recall` turns retrieval into a
  bilingual **delta** ("Since our last analysis of X …") and the ``prior_findings`` injected into
  synthesis (the seam already exists in :class:`models.synthesis.SynthesisInput`).

Embeddings always go through :meth:`LocalLLMClient.embed` (RULE 6 — ``nomic-embed-text`` on CPU,
no VRAM competition). The whole Layer-2 path is **advisory / fail-open**: any failure raises
:class:`MemoryLayerError` (carrying an exact fix) which the pipeline turns into a notice and then
delivers anyway (SPEC REQ-5). Hard chat-model/SearXNG failures keep their own fail-fast policy.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from core.config import MemoryConfig
from core.json_utils import extract_json_array
from llm.local_llm_client import LLMError, LocalLLMClient
from models.synthesis import AnalysisOutput
from models.task import Intent, Language

# A scaffolding line: starts with a single '#' (comment or H1 title) but NOT '##'+ (which are
# real markdown section headings we keep). Matches the brain.md authoring convention.
_SCAFFOLDING_LINE = re.compile(r"^#(?!#)")

# An embedding function: a list of texts -> one vector per text (provided by LocalLLMClient.embed).
EmbedFn = Callable[[list[str]], list[list[float]]]


def _is_scaffolding(line: str) -> bool:
    """True if a line is a single-``#`` comment/title (human scaffolding, not content)."""
    return bool(_SCAFFOLDING_LINE.match(line.lstrip()))


def load_brain(config: MemoryConfig) -> str:
    """Load brain.md as injectable context, stripped of human-facing scaffolding.

    Reads ``config.brain_path`` (UTF-8), drops single-``#`` comment/title lines, and caps the
    result at ``config.max_brain_lines`` lines. A missing or content-empty file yields ``""``
    (the agent runs fine without a brain — it just loses persistent context).

    Args:
        config: The memory configuration (brain path + max line cap).

    Returns:
        The cleaned brain content, or ``""`` if there is nothing to inject.
    """
    path = Path(config.brain_path)
    if not path.is_file():
        return ""

    raw = path.read_text(encoding="utf-8")
    kept = [line for line in raw.splitlines() if not _is_scaffolding(line)]
    capped = kept[: max(0, config.max_brain_lines)]
    return "\n".join(capped).strip()


def _t(language: Language, de: str, en: str) -> str:
    """Pick the German or English string for the language."""
    return de if language == Language.DE else en


# ======================================================================= Layer 2: ChromaDB
class MemoryLayerError(Exception):
    """The ChromaDB memory layer is unavailable. Advisory — the caller fails open and delivers.

    Always carries an exact fix in the message (SPEC REQ-5) so the user can re-enable memory.
    """


@dataclass
class MemoryRecord:
    """One stored research run (or a retrieved prior), with provenance metadata.

    ``document`` is the embedded digest (title + bottom line + sections). ``distance`` is set only
    on retrieval (ChromaDB L2 — lower = more similar).
    """

    record_id: str
    document: str
    title: str
    entities: list[str]
    task_type: str
    language: str
    timestamp: str  # ISO date (YYYY-MM-DD)
    quality_score: int
    distance: float | None = None


def _join_entities(entities: list[str]) -> str:
    """Join entities into a ChromaDB-safe metadata string (scalar only — no lists allowed)."""
    seen: set[str] = set()
    kept: list[str] = []
    for entity in entities:
        name = entity.strip()
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            kept.append(name)
    return " | ".join(kept)


def _parse_entities(value: str) -> list[str]:
    """Parse the ``" | "``-joined entity metadata string back into a list."""
    return [part.strip() for part in value.split("|") if part.strip()]


def _records_from_query(raw: dict[str, Any]) -> list[MemoryRecord]:
    """Turn a ChromaDB ``query`` result (lists-of-lists, one row per query) into MemoryRecords."""
    ids = (raw.get("ids") or [[]])[0]
    docs = (raw.get("documents") or [[]])[0] or []
    metas = (raw.get("metadatas") or [[]])[0] or []
    dists = (raw.get("distances") or [[]])[0] or []
    records: list[MemoryRecord] = []
    for index, rid in enumerate(ids):
        meta = metas[index] if index < len(metas) and metas[index] else {}
        distance = dists[index] if index < len(dists) and dists[index] is not None else None
        records.append(
            MemoryRecord(
                record_id=str(rid),
                document=str(docs[index]) if index < len(docs) else "",
                title=str(meta.get("title", "")),
                entities=_parse_entities(str(meta.get("entities", ""))),
                task_type=str(meta.get("task_type", "")),
                language=str(meta.get("language", "")),
                timestamp=str(meta.get("timestamp", "")),
                quality_score=int(meta.get("quality_score", 0) or 0),
                distance=float(distance) if distance is not None else None,
            )
        )
    return records


class MemoryStore:
    """ChromaDB-backed session memory. Embeds via an injected ``embed_fn`` (RULE 6).

    The collection is duck-typed (any object with ChromaDB's ``add``/``query`` signatures) so the
    store is testable offline with a fake collection and a stub embedder.
    """

    def __init__(self, collection: Any, embed_fn: EmbedFn, *, top_k: int = 5) -> None:
        """Bind the ChromaDB collection, the embedding function, and the retrieval depth."""
        self._collection = collection
        self._embed = embed_fn
        self._top_k = max(1, top_k)

    def write(self, record: MemoryRecord) -> None:
        """Embed the record's document and add it to the collection (fail-open)."""
        vector = self._embed_one(record.document)
        metadata = {
            "title": record.title,
            "entities": _join_entities(record.entities),
            "task_type": record.task_type,
            "language": record.language,
            "timestamp": record.timestamp,
            "quality_score": int(record.quality_score),
        }
        try:
            self._collection.add(
                ids=[record.record_id],
                embeddings=[vector],
                documents=[record.document],
                metadatas=[metadata],
            )
        except Exception as exc:  # chromadb raises its own error hierarchy
            raise MemoryLayerError(
                f"Could not write to the memory store: {exc}\n"
                "Fix: ensure the ChromaDB path is writable, or set memory.enabled=false."
            ) from exc

    def retrieve(self, query_text: str, top_k: int | None = None) -> list[MemoryRecord]:
        """Return prior records most similar to ``query_text`` (closest first)."""
        if not query_text.strip():
            return []
        vector = self._embed_one(query_text)
        try:
            raw = self._collection.query(query_embeddings=[vector], n_results=top_k or self._top_k)
        except Exception as exc:
            raise MemoryLayerError(
                f"Could not query the memory store: {exc}\n"
                "Fix: delete data/chroma_db to reset it, or set memory.enabled=false."
            ) from exc
        records = _records_from_query(raw)
        records.sort(key=lambda r: r.distance if r.distance is not None else float("inf"))
        return records

    def _embed_one(self, text: str) -> list[float]:
        """Embed a single string, translating an embedding failure into a MemoryLayerError."""
        try:
            vectors = self._embed([text])
        except LLMError as exc:
            raise MemoryLayerError(f"Memory needs embeddings but they failed.\n{exc}") from exc
        if not vectors or not vectors[0]:
            raise MemoryLayerError("Embedding returned no vector — memory write/read skipped.")
        return vectors[0]


def open_memory(config: MemoryConfig, client: LocalLLMClient) -> MemoryStore:
    """Open the persistent ChromaDB store under ``config.db_path``.

    Embeddings are provided to ChromaDB directly (``embedding_function=None``) so nothing is ever
    downloaded — all vectors come from the local ``nomic-embed-text`` via the client's ``embed``.

    Raises:
        MemoryLayerError: If memory is disabled, ChromaDB is missing, or the path is not usable
            (advisory — the caller fails open and the agent still delivers).
    """
    if not config.enabled:
        raise MemoryLayerError("Memory is disabled (set memory.enabled=true in config.yaml).")
    try:
        import chromadb
    except ImportError as exc:
        raise MemoryLayerError(
            "ChromaDB is not installed — persistent memory is off.\n"
            "Fix: pip install chromadb  (it is listed in requirements.txt)."
        ) from exc

    db_path = Path(config.db_path)
    try:
        db_path.mkdir(parents=True, exist_ok=True)
        chroma = chromadb.PersistentClient(path=str(db_path))
        collection = chroma.get_or_create_collection(
            config.collection_name, embedding_function=None
        )
    except Exception as exc:
        raise MemoryLayerError(
            f"Could not open the memory store at {db_path}: {exc}\n"
            "Fix: ensure the path is writable, or set memory.enabled=false to run without memory."
        ) from exc
    return MemoryStore(collection, client.embed, top_k=config.top_k_retrieval)


# ---------------------------------------------------------------- entity extraction + records
_ENTITY_SYSTEM = (
    "Extract the named entities (companies, organizations, products, markets, or people) that a "
    "strategy/research task is ABOUT. Return ONLY a JSON array of short canonical names "
    '(e.g. ["Figure AI", "1X Technologies"]). Empty array if none. No prose.'
)


def extract_entities(
    client: LocalLLMClient, intent: Intent, task_text: str, max_entities: int = 6
) -> list[str]:
    """Extract the entities a task is about (fast LLM call; fail-open to ``[]``).

    Used to tag stored runs and to detect "have we researched this entity before?" for the delta.
    """
    probe = f"{intent.summary}\n{task_text}".strip()
    if not probe:
        return []
    try:
        response = client.generate(
            f'Task:\n"""\n{probe}\n"""\n\nReturn the JSON array now.',
            system=_ENTITY_SYSTEM,
            use_thinking=False,
        )
        array = extract_json_array(response)
    except LLMError:
        array = None
    if not array:
        return []
    seen: set[str] = set()
    entities: list[str] = []
    for item in array:
        name = str(item).strip()
        key = name.lower()
        if name and key not in seen:
            seen.add(key)
            entities.append(name)
        if len(entities) >= max_entities:
            break
    return entities


def build_memory_document(intent: Intent, analysis: AnalysisOutput, max_chars: int = 4000) -> str:
    """Build the digest stored + embedded for a run (the synthesized analysis)."""
    parts = [
        f"TITLE: {analysis.title}",
        f"TASK TYPE: {intent.task_type.value}",
        f"BOTTOM LINE: {analysis.bottom_line}",
    ]
    for section in analysis.sections:
        body = section.body.strip()
        if section.heading or body:
            parts.append(f"## {section.heading}\n{body}")
    return "\n\n".join(parts)[:max_chars]


def make_record(
    intent: Intent,
    analysis: AnalysisOutput,
    entities: list[str],
    quality_score: int,
    *,
    today: str | None = None,
) -> MemoryRecord:
    """Assemble a :class:`MemoryRecord` for the just-finished run (id = fresh UUID)."""
    return MemoryRecord(
        record_id=uuid.uuid4().hex,
        document=build_memory_document(intent, analysis),
        title=analysis.title,
        entities=entities,
        task_type=intent.task_type.value,
        language=intent.language.value,
        timestamp=today or date.today().isoformat(),
        quality_score=int(quality_score),
    )


# ----------------------------------------------------------------------------- recall + delta
@dataclass
class Recall:
    """Result of consulting memory before a new run."""

    prior_findings: str = ""  # injected into SynthesisInput.prior_findings
    delta_note: str | None = None  # bilingual "Since our last analysis of X …" (if same entity)
    matched: list[MemoryRecord] = field(default_factory=list)


def _entities_overlap(current: list[str], stored: list[str]) -> str | None:
    """Return the first overlapping entity name (case-insensitive substring match), else None."""
    for cur in current:
        cur_l = cur.strip().lower()
        if not cur_l:
            continue
        for sto in stored:
            sto_l = sto.strip().lower()
            if not sto_l:
                continue
            if cur_l == sto_l or cur_l in sto_l or sto_l in cur_l:
                return sto.strip() or cur.strip()
    return None


def _entity_in_text(entities: list[str], haystack: str) -> str | None:
    """Return the first stored entity (length ≥ 3) that appears in the lowercased haystack."""
    for entity in entities:
        name = entity.strip()
        if len(name) >= 3 and name.lower() in haystack:
            return name
    return None


def _format_prior(records: list[MemoryRecord], max_records: int = 3, max_chars: int = 1500) -> str:
    """Render the most relevant prior runs as a compact PRIOR-FINDINGS block."""
    lines: list[str] = []
    for record in records[:max_records]:
        snippet = " ".join(record.document.split())[:400]
        head = f"[{record.timestamp}] {record.title}" if record.timestamp else record.title
        lines.append(f"- {head}: {snippet}")
    return "\n".join(lines)[:max_chars]


def _age_phrase(timestamp: str, language: Language, today: date | None = None) -> str:
    """Build the ' (vom DATE, vor N Wochen)' / ' (DATE, N weeks ago)' delta-header suffix."""
    try:
        then = date.fromisoformat(timestamp)
    except (ValueError, TypeError):
        return ""
    days = max(0, ((today or date.today()) - then).days)
    weeks = days // 7
    if weeks >= 1:
        age = _t(language, f", vor {weeks} Wochen", f", {weeks} weeks ago")
    elif days >= 1:
        age = _t(language, f", vor {days} Tagen", f", {days} days ago")
    else:
        age = _t(language, ", heute", ", today")
    return _t(language, f" (vom {timestamp}{age})", f" ({timestamp}{age})")


_DELTA_SYSTEM_DE = (
    "Du vergleichst eine FRÜHERE Analyse mit den AKTUELLEN Rechercheergebnissen zur selben "
    "Entität. Schreibe 2-4 Sätze auf Deutsch: Was hat sich seit der früheren Analyse geändert "
    "(neue Fakten, Kehrtwenden, Fortschritt)? Nenne nur Materielles. Kein Vorspann, keine "
    "Wiederholung der Überschrift — nur die Veränderung."
)
_DELTA_SYSTEM_EN = (
    "You compare a PRIOR analysis with the CURRENT research findings about the same entity. Write "
    "2-4 sentences in English: what has changed since the prior analysis (new facts, reversals, "
    "progress)? Only material changes. No preamble or heading — just the delta."
)


def build_delta_note(
    client: LocalLLMClient,
    intent: Intent,
    prior: MemoryRecord,
    current_digest: str,
    entity: str,
    *,
    today: date | None = None,
) -> str:
    """Build the bilingual delta note: a guaranteed header phrase + an LLM 'what changed' body.

    The header (which names the entity + the prior date + age) is built deterministically so the
    SPEC §15 success phrase always appears; the body is LLM-generated and **fail-open** to a
    template, so a model hiccup never loses the delta.
    """
    language = intent.language
    age = _age_phrase(prior.timestamp, language, today=today)
    header = _t(
        language,
        f"Seit unserer letzten Analyse von {entity}{age}:",
        f"Since our last analysis of {entity}{age}:",
    )
    system = _DELTA_SYSTEM_DE if language == Language.DE else _DELTA_SYSTEM_EN
    prompt = (
        f"PRIOR ANALYSIS (from {prior.timestamp}):\n{prior.document[:1800]}\n\n"
        f"CURRENT RESEARCH FINDINGS:\n{current_digest[:1800]}\n\n"
        "Describe what changed now."
    )
    try:
        body = client.generate(prompt, system=system, use_thinking=False).strip()
    except LLMError:
        body = ""
    if not body:
        body = _t(
            language,
            "Diese Analyse aktualisiert die frühere Recherche — vergleiche die neuen Erkenntnisse.",
            "This analysis updates the earlier research — compare the new findings below.",
        )
    return f"{header} {body}"


def recall(
    store: MemoryStore,
    client: LocalLLMClient,
    intent: Intent,
    entities: list[str],
    current_digest: str,
    *,
    today: date | None = None,
) -> Recall:
    """Consult memory before synthesis: retrieve prior runs, build prior_findings + a delta note.

    The query is the task summary (falling back to the current research digest). Retrieved runs
    that share an entity with the current task drive the delta. Raises MemoryLayerError on a store
    failure (the pipeline fails open).
    """
    query = (intent.summary or current_digest).strip()[:1000]
    records = store.retrieve(query)
    if not records:
        return Recall()

    prior_findings = _format_prior(records)
    # Robust same-entity detection: match the current run's extracted entities OR a prior's known
    # entity appearing in what this run is about (summary + findings). The second path means a flaky
    # entity-extraction call never silently loses the delta when the new request names the entity.
    haystack = f"{intent.summary}\n{current_digest}".lower()
    for record in records:
        match = _entities_overlap(entities, record.entities) or _entity_in_text(
            record.entities, haystack
        )
        if match:
            note = build_delta_note(client, intent, record, current_digest, match, today=today)
            return Recall(prior_findings=prior_findings, delta_note=note, matched=[record])
    return Recall(prior_findings=prior_findings, matched=[])


# ============================================================= Layer 1: brain-update flow
_PROPOSE_SYSTEM = (
    "You maintain brain.md, a tiny persistent memory whose CARDINAL RULE is: every line must "
    "change FUTURE agent outputs. Given a finished analysis, propose 0-3 short, DURABLE, "
    "high-signal additions — strategic facts or audience/style preferences that should persist and "
    "reshape future outputs. Exclude ephemeral findings, dated news, and anything generic. Return "
    "ONLY a JSON array of short strings (<=160 chars each); empty array if nothing durable."
)


def _already_in_brain(addition: str, brain_text: str) -> bool:
    """Cheap dedupe: True if a near-identical line already lives in the brain text."""
    needle = " ".join(addition.lower().split())
    haystack = " ".join(brain_text.lower().split())
    return bool(needle) and needle in haystack


def propose_brain_additions(
    client: LocalLLMClient,
    intent: Intent,
    analysis: AnalysisOutput,
    existing_brain: str = "",
    max_items: int = 3,
) -> list[str]:
    """Propose durable, high-signal brain.md additions for this run (fail-open to ``[]``).

    The REPL shows these and asks the user to confirm before :func:`append_brain_additions` writes
    them (never auto-applied — brain.md is confidential, SPEC N-9).
    """
    probe = f"TITLE: {analysis.title}\nBOTTOM LINE: {analysis.bottom_line}\n" + "\n".join(
        f"{section.heading}: {section.body[:200]}" for section in analysis.sections
    )
    try:
        response = client.generate(
            f'Analysis:\n"""\n{probe[:2500]}\n"""\n\nReturn the JSON array now.',
            system=_PROPOSE_SYSTEM,
            use_thinking=False,
        )
        array = extract_json_array(response)
    except LLMError:
        array = None
    if not array:
        return []
    additions: list[str] = []
    for item in array:
        text = str(item).strip()
        if text and not _already_in_brain(text, existing_brain):
            additions.append(text[:200])
        if len(additions) >= max_items:
            break
    return additions


_BRAIN_MARKER = "## AGENT-PROPOSED ADDITIONS"


def append_brain_additions(
    config: MemoryConfig, additions: list[str], *, today: str | None = None
) -> int:
    """Append user-confirmed additions to brain.md under a single managed heading (UTF-8).

    Returns the number of lines written. Idempotent header: the marker section is created once,
    then later confirmations append bullets beneath it (no duplicate headers). brain.md stays
    gitignored (N-9); ``load_brain`` keeps these ``-`` bullets and strips the ``#`` comment line.
    """
    cleaned = [addition.strip() for addition in additions if addition and addition.strip()]
    if not cleaned:
        return 0
    path = Path(config.brain_path)
    stamp = today or date.today().isoformat()
    bullets = "\n".join(f"- [{stamp}] {addition}" for addition in cleaned)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    if _BRAIN_MARKER in existing:
        body = bullets + "\n"
    else:
        body = (
            f"\n{_BRAIN_MARKER}\n"
            "# Agent-proposed, user-confirmed durable context (Phase 5 brain-update flow).\n"
            f"{bullets}\n"
        )
    separator = "" if (not existing or existing.endswith("\n")) else "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(separator + body)
    return len(cleaned)
