"""Tests for the memory layer (core/memory.py): brain.md inject + ChromaDB session memory.

Layer-2 (ChromaDB) is tested offline with a fake collection + a deterministic stub embedder, plus
one real-ChromaDB roundtrip (importorskip). The LLM is a tiny stub — these never hit the network.
"""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from core.config import MemoryConfig
from core.memory import (
    MemoryLayerError,
    MemoryRecord,
    MemoryStore,
    append_brain_additions,
    build_delta_note,
    build_memory_document,
    extract_entities,
    load_brain,
    make_record,
    open_memory,
    propose_brain_additions,
    recall,
)
from models.synthesis import AnalysisOutput, Section
from models.task import Intent, Language, OutputFormat, TaskType


def _config(path: Path, max_lines: int = 300) -> MemoryConfig:
    return MemoryConfig(brain_path=str(path), max_brain_lines=max_lines)


# ----------------------------------------------------------------- test doubles (Layer 2)
def _vec(text: str, dim: int = 12) -> list[float]:
    """Deterministic embedding from a text's hash (same text → same vector)."""
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return [b / 255.0 for b in digest[:dim]]


def _stub_embed(texts: list[str]) -> list[list[float]]:
    return [_vec(text) for text in texts]


class _FakeCollection:
    """In-memory stand-in for a ChromaDB collection (add + L2 query)."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def add(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        documents: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        for index, rid in enumerate(ids):
            self.records.append(
                {
                    "id": rid,
                    "embedding": embeddings[index],
                    "document": documents[index],
                    "metadata": metadatas[index],
                }
            )

    def query(self, query_embeddings: list[list[float]], n_results: int) -> dict[str, Any]:
        q = query_embeddings[0]

        def dist(emb: list[float]) -> float:
            return sum((a - b) ** 2 for a, b in zip(q, emb, strict=False))

        ranked = sorted(self.records, key=lambda r: dist(r["embedding"]))[:n_results]
        return {
            "ids": [[r["id"] for r in ranked]],
            "documents": [[r["document"] for r in ranked]],
            "metadatas": [[r["metadata"] for r in ranked]],
            "distances": [[dist(r["embedding"]) for r in ranked]],
        }


class _StubClient:
    """Minimal LocalLLMClient stand-in: scripted generate() + deterministic embed()."""

    def __init__(self, responses: list[str] | None = None) -> None:
        self._responses = list(responses or [])
        self.generate_systems: list[str] = []

    def generate(self, prompt: str, system: str = "", use_thinking: Any = None, **kw: Any) -> str:
        self.generate_systems.append(system)
        return self._responses.pop(0) if self._responses else ""

    def embed(self, texts: list[str]) -> list[list[float]]:
        return _stub_embed(texts)


def _intent(summary: str = "Figure AI competitive analysis", **kw: Any) -> Intent:
    base: dict[str, Any] = {
        "task_type": TaskType.COMPETITOR_ANALYSIS,
        "output_formats": [OutputFormat.BRIEF],
        "language": Language.EN,
        "summary": summary,
    }
    base.update(kw)
    return Intent(**base)


def _analysis(title: str = "Figure AI Brief") -> AnalysisOutput:
    return AnalysisOutput(
        title=title,
        language=Language.EN,
        bottom_line="Figure AI raised a large round and is scaling fast.",
        sections=[Section(heading="Funding", body="Raised $675M in 2024.")],
    )


def test_load_brain_strips_scaffolding_keeps_content(tmp_path: Path) -> None:
    """Single-# comments/title are dropped; ## headings and real content are kept."""
    brain = tmp_path / "brain.md"
    brain.write_text(
        "# AGENT BRAIN\n"
        "# ⚠️ GITIGNORED — comment line\n"
        "\n"
        "## NEURA — STRATEGIC CONTEXT\n"
        "# Only facts that change framing.\n"
        "Neura builds cognitive humanoid robots.\n"
        "**Differentiation:** cognitive vs scripted.\n",
        encoding="utf-8",
    )
    result = load_brain(_config(brain))
    assert "## NEURA — STRATEGIC CONTEXT" in result
    assert "Neura builds cognitive humanoid robots." in result
    assert "**Differentiation:** cognitive vs scripted." in result
    # scaffolding removed
    assert "AGENT BRAIN" not in result
    assert "GITIGNORED" not in result
    assert "Only facts that change framing" not in result


def test_load_brain_missing_file_returns_empty(tmp_path: Path) -> None:
    """A missing brain.md yields '' — the agent runs without persistent context."""
    assert load_brain(_config(tmp_path / "nope.md")) == ""


def test_load_brain_comment_only_file_returns_empty(tmp_path: Path) -> None:
    """A file of only scaffolding comments injects nothing."""
    brain = tmp_path / "brain.md"
    brain.write_text("# only\n# comments\n# here\n", encoding="utf-8")
    assert load_brain(_config(brain)) == ""


def test_load_brain_respects_max_lines(tmp_path: Path) -> None:
    """The cap limits how many (kept) lines are injected."""
    brain = tmp_path / "brain.md"
    brain.write_text("\n".join(f"content line {i}" for i in range(50)), encoding="utf-8")
    result = load_brain(_config(brain, max_lines=10))
    assert result.count("\n") == 9  # 10 lines → 9 newlines
    assert "content line 0" in result
    assert "content line 10" not in result


# ============================================================ Layer 2: ChromaDB store
def test_memory_store_write_then_retrieve_roundtrip() -> None:
    """A written record is retrievable, with metadata (entities/timestamp/quality) preserved."""
    store = MemoryStore(_FakeCollection(), _stub_embed, top_k=5)
    record = make_record(
        _intent(), _analysis(), ["Figure AI"], quality_score=88, today="2026-05-11"
    )
    store.write(record)

    out = store.retrieve("Figure AI competitive analysis")
    assert len(out) == 1
    assert out[0].title == "Figure AI Brief"
    assert out[0].entities == ["Figure AI"]
    assert out[0].timestamp == "2026-05-11"
    assert out[0].quality_score == 88
    assert out[0].distance is not None


def test_memory_store_retrieve_orders_by_distance() -> None:
    """Retrieval returns the closest records first (sorted by distance)."""
    store = MemoryStore(_FakeCollection(), _stub_embed, top_k=5)
    store.write(
        make_record(_intent(summary="Boston Dynamics"), _analysis("BD"), ["Boston Dynamics"], 70)
    )
    store.write(make_record(_intent(summary="Figure AI"), _analysis("Figure"), ["Figure AI"], 90))

    out = store.retrieve("Figure AI")
    assert len(out) == 2
    distances = [r.distance for r in out if r.distance is not None]
    assert distances == sorted(distances)


def test_memory_store_empty_query_returns_empty() -> None:
    """A blank query short-circuits to no results (no embedding call needed)."""
    assert MemoryStore(_FakeCollection(), _stub_embed).retrieve("   ") == []


def test_memory_store_embed_failure_is_fail_open() -> None:
    """An embedding failure surfaces as MemoryLayerError (the pipeline then fails open)."""
    from llm.local_llm_client import LLMError

    def _broken_embed(texts: list[str]) -> list[list[float]]:
        raise LLMError("nomic-embed-text not pulled")

    store = MemoryStore(_FakeCollection(), _broken_embed)
    with pytest.raises(MemoryLayerError):
        store.write(make_record(_intent(), _analysis(), ["Figure AI"], 80))


def test_open_memory_disabled_raises() -> None:
    """open_memory on a disabled config raises MemoryLayerError with a fix."""
    config = MemoryConfig(enabled=False)
    with pytest.raises(MemoryLayerError):
        open_memory(config, _StubClient())  # type: ignore[arg-type]


def test_memory_store_real_chroma_roundtrip(tmp_path: Path) -> None:
    """Real ChromaDB (EphemeralClient) write→retrieve works fully offline (explicit embeddings)."""
    chromadb = pytest.importorskip("chromadb")
    client = chromadb.EphemeralClient()
    collection = client.get_or_create_collection(
        "strategy_agent_memory_test", embedding_function=None
    )
    store = MemoryStore(collection, _stub_embed, top_k=3)
    store.write(make_record(_intent(), _analysis(), ["Figure AI"], 91, today="2026-05-11"))

    out = store.retrieve("Figure AI funding")
    assert len(out) == 1
    assert out[0].title == "Figure AI Brief"
    assert out[0].entities == ["Figure AI"]
    assert out[0].quality_score == 91


def test_build_memory_document_caps_length() -> None:
    """The stored digest includes title/bottom-line/sections and respects the char cap."""
    doc = build_memory_document(_intent(), _analysis())
    assert "TITLE: Figure AI Brief" in doc
    assert "Funding" in doc
    long = build_memory_document(_intent(), _analysis(), max_chars=20)
    assert len(long) == 20


# --------------------------------------------------------------------- entity extraction
def test_extract_entities_parses_array() -> None:
    """extract_entities parses the JSON array and dedupes case-insensitively."""
    client = _StubClient(responses=['["Figure AI", "1X Technologies", "figure ai"]'])
    entities = extract_entities(client, _intent(), "Analyze Figure AI vs 1X")  # type: ignore[arg-type]
    assert entities == ["Figure AI", "1X Technologies"]


def test_extract_entities_fails_open_to_empty() -> None:
    """Bad/empty model output yields no entities (never raises)."""
    client = _StubClient(responses=["not json at all"])
    assert extract_entities(client, _intent(), "x") == []  # type: ignore[arg-type]


# ----------------------------------------------------------------------------- recall + delta
def test_recall_same_entity_produces_delta() -> None:
    """A retrieved prior sharing an entity drives a delta naming the entity + prior date."""
    store = MemoryStore(_FakeCollection(), _stub_embed, top_k=5)
    store.write(make_record(_intent(), _analysis(), ["Figure AI"], 85, today="2026-05-11"))

    client = _StubClient(responses=["Funding doubled and a Tier-1 customer signed."])
    result = recall(
        store,
        client,  # type: ignore[arg-type]
        _intent(),
        ["Figure AI"],
        "CURRENT: Figure AI signed BMW and raised again.",
        today=date(2026, 6, 1),
    )
    assert result.delta_note is not None
    assert result.delta_note.startswith("Since our last analysis of Figure AI")
    assert "2026-05-11" in result.delta_note
    assert "weeks ago" in result.delta_note
    assert "Funding doubled" in result.delta_note
    assert result.prior_findings  # prior findings populated for synthesis injection


def test_recall_no_entity_overlap_has_no_delta() -> None:
    """A prior about a different entity yields prior_findings but no delta note."""
    store = MemoryStore(_FakeCollection(), _stub_embed, top_k=5)
    store.write(
        make_record(_intent(summary="Boston Dynamics"), _analysis("BD"), ["Boston Dynamics"], 70)
    )

    result = recall(
        store,
        _StubClient(),  # type: ignore[arg-type]
        _intent(),
        ["Figure AI"],
        "current digest",
        today=date(2026, 6, 1),
    )
    assert result.delta_note is None
    assert result.prior_findings  # still surfaces the prior as context


def test_recall_empty_store_returns_blank() -> None:
    """No priors → empty recall (no delta, no prior findings)."""
    store = MemoryStore(_FakeCollection(), _stub_embed)
    result = recall(store, _StubClient(), _intent(), ["Figure AI"], "d")  # type: ignore[arg-type]
    assert result.delta_note is None
    assert result.prior_findings == ""


def test_build_delta_note_fails_open_to_template() -> None:
    """A model failure still yields the guaranteed header phrase (German) + a template body."""
    record = MemoryRecord(
        record_id="x",
        document="prior",
        title="Figure AI",
        entities=["Figure AI"],
        task_type="competitor_analysis",
        language="de",
        timestamp="2026-05-11",
        quality_score=80,
    )
    note = build_delta_note(
        _StubClient(responses=[""]),  # type: ignore[arg-type]
        _intent(language=Language.DE),
        record,
        "current",
        "Figure AI",
        today=date(2026, 6, 1),
    )
    assert note.startswith("Seit unserer letzten Analyse von Figure AI")
    assert "2026-05-11" in note
    assert "Wochen" in note


# ============================================================= Layer 1: brain-update flow
def test_propose_brain_additions_parses_and_dedupes() -> None:
    """Proposals are parsed; ones already in the brain are dropped."""
    client = _StubClient(responses=['["Board decks: English only", "Already known fact"]'])
    additions = propose_brain_additions(
        client,  # type: ignore[arg-type]
        _intent(),
        _analysis(),
        existing_brain="Some line. already known fact. Another line.",
    )
    assert additions == ["Board decks: English only"]


def test_propose_brain_additions_fails_open() -> None:
    """Bad model output yields no proposals (never raises)."""
    client = _StubClient(responses=["nope"])
    assert propose_brain_additions(client, _intent(), _analysis()) == []  # type: ignore[arg-type]


def test_append_brain_additions_writes_and_is_kept_by_load_brain(tmp_path: Path) -> None:
    """Confirmed additions are appended under one managed heading and survive load_brain."""
    brain = tmp_path / "brain.md"
    brain.write_text("## NEURA\nNeura builds cognitive robots.\n", encoding="utf-8")
    config = _config(brain)

    written = append_brain_additions(config, ["Board decks: English only"], today="2026-06-01")
    assert written == 1
    written2 = append_brain_additions(config, ["CEO prefers 3 bullets max"], today="2026-06-02")
    assert written2 == 1

    text = brain.read_text(encoding="utf-8")
    assert text.count("## AGENT-PROPOSED ADDITIONS") == 1  # header created once, not duplicated
    assert "- [2026-06-01] Board decks: English only" in text
    assert "- [2026-06-02] CEO prefers 3 bullets max" in text

    injected = load_brain(config)
    assert "Board decks: English only" in injected
    assert "CEO prefers 3 bullets max" in injected
    assert "Agent-proposed, user-confirmed" not in injected  # the '#' comment is stripped


def test_append_brain_additions_noop_on_empty(tmp_path: Path) -> None:
    """Empty/whitespace additions write nothing."""
    brain = tmp_path / "brain.md"
    assert append_brain_additions(_config(brain), ["  ", ""]) == 0
    assert not brain.exists()
