"""Persisted RAG index (precedent_chunks, 018): indexer + retrieve fast path.

The fake embedder projects texts onto keyword axes, so similarity is
deterministic and semantic-ish: a query about "confidencialidad" must rank an
NDA-like text above a board-minutes text even when the latter is NEWER —
exactly the case the degraded (weight×recency) ranking gets wrong.
"""
from __future__ import annotations

from typing import Any

import pytest

from models.schema import PrecedentSource, PrecedentVersionStatus
from services import db as dbmod
from services import indexer, providers, rag
from tests.conftest import DOC_TYPE, seed_precedent

_AXES = ["confidencialidad", "consejo", "capital", "arrendamiento"]
_DIM = indexer.EXPECTED_DIM


def _fake_vector(text: str) -> list[float]:
    lowered = text.lower()
    axes = [float(lowered.count(keyword)) for keyword in _AXES]
    if not any(axes):
        axes = [0.001] * len(_AXES)  # avoid zero-norm vectors
    return axes + [0.0] * (_DIM - len(_AXES))


class _FakeEmbedder:
    name = "fake"

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def is_configured(self, settings: Any) -> bool:
        return True

    def embed(self, texts: list[str], config: Any) -> list[list[float]]:
        self.calls.append(list(texts))
        return [_fake_vector(t) for t in texts]


@pytest.fixture()
def fake_embeddings(monkeypatch: pytest.MonkeyPatch) -> _FakeEmbedder:
    fake = _FakeEmbedder()
    monkeypatch.setattr(providers, "get_embedding", lambda _name: fake)
    return fake


# ---------------------------------------------------------------------------
# Indexer
# ---------------------------------------------------------------------------

def test_reindex_creates_chunks_with_vectors(db: dbmod.DevStore, fake_embeddings: _FakeEmbedder) -> None:
    gestora = db.insert("gestoras", {"name": "G"})
    precedent, version = seed_precedent(
        db, gestora_id=gestora["id"], text="Acuerdo de confidencialidad entre las partes."
    )
    rag.reindex_gestora(gestora["id"], precedent["id"])

    chunks = db.select("precedent_chunks", precedent_version_id=version["id"])
    assert chunks, "expected chunk rows after reindex"
    row = chunks[0]
    assert row["gestora_id"] == gestora["id"]
    assert row["doc_type"] == DOC_TYPE
    assert row["source"] == "manual_upload"
    assert row["version_status"] == "active"
    assert row["is_docx"] is True
    assert row["embed_model"] == "bge-m3"  # conftest default: ollama provider
    assert len(row["embedding"]) == _DIM


def test_reindex_is_idempotent(db: dbmod.DevStore, fake_embeddings: _FakeEmbedder) -> None:
    gestora = db.insert("gestoras", {"name": "G"})
    precedent, version = seed_precedent(db, gestora_id=gestora["id"], text="Texto confidencialidad")
    rag.reindex_gestora(gestora["id"], precedent["id"])
    first = len(db.select("precedent_chunks", precedent_version_id=version["id"]))
    embed_calls = len(fake_embeddings.calls)

    rag.reindex_gestora(gestora["id"], precedent["id"])
    assert len(db.select("precedent_chunks", precedent_version_id=version["id"])) == first
    assert len(fake_embeddings.calls) == embed_calls  # no re-embedding


def test_status_flip_updates_chunk_metadata_without_reembedding(
    db: dbmod.DevStore, fake_embeddings: _FakeEmbedder
) -> None:
    gestora = db.insert("gestoras", {"name": "G"})
    precedent, version = seed_precedent(db, gestora_id=gestora["id"], text="confidencialidad")
    rag.reindex_gestora(gestora["id"], precedent["id"])
    embed_calls = len(fake_embeddings.calls)

    db.update("precedent_versions", version["id"], {"status": PrecedentVersionStatus.superseded.value})
    rag.reindex_gestora(gestora["id"], precedent["id"])

    chunks = db.select("precedent_chunks", precedent_version_id=version["id"])
    assert all(c["version_status"] == "superseded" for c in chunks)
    assert len(fake_embeddings.calls) == embed_calls


def test_vector_backfill_when_provider_recovers(
    db: dbmod.DevStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    gestora = db.insert("gestoras", {"name": "G"})
    precedent, version = seed_precedent(db, gestora_id=gestora["id"], text="confidencialidad")

    # First sync with embeddings unavailable: rows stored without vectors.
    monkeypatch.setattr(providers, "get_embedding", lambda _name: None)
    rag.reindex_gestora(gestora["id"], precedent["id"])
    chunks = db.select("precedent_chunks", precedent_version_id=version["id"])
    assert chunks and all(c["embedding"] is None for c in chunks)

    # Provider recovers: the same sync fills the vectors in place.
    fake = _FakeEmbedder()
    monkeypatch.setattr(providers, "get_embedding", lambda _name: fake)
    rag.reindex_gestora(gestora["id"], precedent["id"])
    chunks = db.select("precedent_chunks", precedent_version_id=version["id"])
    assert all(c["embedding"] is not None for c in chunks)


def test_draft_versions_are_never_indexed(db: dbmod.DevStore, fake_embeddings: _FakeEmbedder) -> None:
    gestora = db.insert("gestoras", {"name": "G"})
    precedent, version = seed_precedent(db, gestora_id=gestora["id"], text="borrador", status="draft")
    rag.reindex_gestora(gestora["id"], precedent["id"])
    assert db.select("precedent_chunks", precedent_version_id=version["id"]) == []


# ---------------------------------------------------------------------------
# Retrieval fast path
# ---------------------------------------------------------------------------

def test_retrieve_ranks_semantically_not_by_recency(
    db: dbmod.DevStore, fake_embeddings: _FakeEmbedder
) -> None:
    """The degraded ranking picks the NEWEST active docx; the indexed path must
    pick the MOST SIMILAR one instead."""
    gestora = db.insert("gestoras", {"name": "G"})
    old_match, old_version = seed_precedent(
        db, gestora_id=gestora["id"],
        text="Acuerdo de confidencialidad. Obligaciones de confidencialidad estrictas.",
    )
    newer_offtopic, _ = seed_precedent(
        db, gestora_id=gestora["id"],
        text="Acta del consejo de administración. Acuerdos del consejo.",
    )
    # Make the off-topic precedent strictly newer.
    for v in db.select("precedent_versions", precedent_id=newer_offtopic["id"]):
        db.update("precedent_versions", v["id"], {"activated_at": "2026-12-31T00:00:00+00:00"})
    rag.reindex_gestora(gestora["id"])

    result = rag.retrieve(
        db, gestora_id=gestora["id"], doc_type=DOC_TYPE, language="es",
        query_text="Necesito un acuerdo de confidencialidad",
    )
    assert result.level == 0
    assert result.base_version_id == old_version["id"]
    assert "confidencialidad" in (result.base_text or "").lower()


def test_retrieve_indexed_never_leaks_other_gestora(
    db: dbmod.DevStore, fake_embeddings: _FakeEmbedder
) -> None:
    gestora_a = db.insert("gestoras", {"name": "A"})
    gestora_b = db.insert("gestoras", {"name": "B"})
    precedent_b, _ = seed_precedent(
        db, gestora_id=gestora_b["id"], text="Acuerdo de confidencialidad perfecto."
    )
    rag.reindex_gestora(gestora_b["id"])

    result = rag.retrieve(
        db, gestora_id=gestora_a["id"], doc_type=DOC_TYPE, language="es",
        query_text="acuerdo de confidencialidad",
    )
    # Gestora A has nothing: level 3, and B's text appears nowhere.
    assert result.level == 3
    assert all("perfecto" not in t for t in result.context_texts)


def test_retrieve_global_pool_respects_language_in_index(
    db: dbmod.DevStore, fake_embeddings: _FakeEmbedder
) -> None:
    es_precedent, es_version = seed_precedent(
        db, gestora_id=None, language="es", source="slp_curated",
        text="Acuerdo de confidencialidad plantilla española.",
    )
    en_precedent, _ = seed_precedent(
        db, gestora_id=None, language="en", source="slp_curated",
        text="Confidencialidad confidencialidad confidencialidad agreement.",
    )
    rag.reindex_global()

    result = rag.retrieve(
        db, gestora_id=db.insert("gestoras", {"name": "G"})["id"], doc_type=DOC_TYPE,
        language="es", query_text="acuerdo de confidencialidad",
    )
    assert result.level == 1
    assert result.base_version_id == es_version["id"]  # the EN one is filtered out


def test_retrieve_falls_back_to_files_when_index_empty(db: dbmod.DevStore) -> None:
    """No chunks + no embeddings (conftest network-off): original degraded path."""
    gestora = db.insert("gestoras", {"name": "G"})
    _, version = seed_precedent(db, gestora_id=gestora["id"], text="Texto precedente")
    result = rag.retrieve(
        db, gestora_id=gestora["id"], doc_type=DOC_TYPE, language="es", query_text="lo que sea"
    )
    assert result.level == 0
    assert result.base_version_id == version["id"]


def test_retrieve_model_base_gets_precedente_context_from_index(
    db: dbmod.DevStore, fake_embeddings: _FakeEmbedder
) -> None:
    gestora = db.insert("gestoras", {"name": "G"})
    model_precedent, model_version = seed_precedent(
        db, gestora_id=gestora["id"], source=PrecedentSource.gestora_model.value,
        text="MODELO de acuerdo de confidencialidad.",
    )
    seed_precedent(
        db, gestora_id=gestora["id"], text="PRECEDENTE pasado con confidencialidad."
    )
    rag.reindex_gestora(gestora["id"])

    result = rag.retrieve(
        db, gestora_id=gestora["id"], doc_type=DOC_TYPE, language="es",
        query_text="acuerdo de confidencialidad",
    )
    assert result.level == 0
    assert result.base_version_id == model_version["id"]  # modelo outranks precedente as base
    assert any("PRECEDENTE" in t for t in result.context_texts)  # 0b still contributes context
