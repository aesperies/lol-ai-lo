"""Persisted RAG index maintenance (precedent_chunks, migración 018).

Chunks + embeddings are written ONCE per precedent version — at upload,
activation or supersession — instead of re-reading and re-embedding every
candidate on every retrieval. ``sync_gestora``/``sync_global`` are idempotent
reconcilers (they double as the backfill):

- version indexable (active/superseded) and unindexed  → chunk + embed + insert
- version indexable but its status changed             → metadata-only update
- version indexable, rows stored without vectors, and the embedding provider
  is now available                                     → re-embed in place
- version no longer indexable (draft/candidate)        → delete its rows

Privacy follows the SAME resolution as retrieval (llm.resolve_embedding_config,
fail-closed to local): a gestora's precedent text goes to the provider that
gestora (or the platform default) selected — never anywhere else. When the
provider is unavailable the rows are stored with ``embedding=None`` so the
text is indexed and a later sync can fill the vectors in.

Vector dimension is pinned to 1024 (pgvector column, 018): bge-m3 and
mistral-embed both emit 1024 — a provider returning another dimension (e.g.
OpenAI's 1536) stores None and that silo keeps the degraded ranking.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from models.schema import PrecedentVersionStatus
from services import db as dbmod
from services import llm

logger = logging.getLogger("lolailo.indexer")

EXPECTED_DIM = 1024

_INDEXABLE_STATUSES = {
    PrecedentVersionStatus.active.value,
    PrecedentVersionStatus.superseded.value,
}


def _embed_batch(
    texts: list[str], config: llm.EffectiveEmbeddingConfig
) -> Optional[list[list[float]]]:
    """Embed via the registry; None when unavailable or wrong dimension."""
    from services import providers  # local import (optional-deps-free startup)

    provider = providers.get_embedding(config.embedding_provider)
    if provider is None:
        return None
    vectors = provider.embed(texts, config)
    if vectors is None:
        return None
    if any(len(v) != EXPECTED_DIM for v in vectors):
        logger.warning(
            "Embedding provider %s returned dimension != %d; storing chunks "
            "without vectors (degraded ranking for this content).",
            config.embedding_provider, EXPECTED_DIM,
        )
        return None
    return vectors


def _index_version(
    db: dbmod.Database,
    precedent: dict[str, Any],
    version: dict[str, Any],
    config: llm.EffectiveEmbeddingConfig,
) -> None:
    """Insert chunk rows for one version (assumes none exist yet).

    Structural chunking (022): the text is first split into sections/clauses
    (docx_renderer.split_sections) and chunked WITHIN each section, so no
    chunk straddles a clause boundary and every row records the clause it
    came from (``section``) — chat citations show "[1] LPA · CLÁUSULA 8".
    """
    from services import docx_renderer, rag  # local import: rag imports indexer lazily too

    text = rag._load_text(version["file_path"])
    if text is None:
        return  # unreadable/optional-dep formats simply stay unindexed
    entries: list[tuple[Optional[str], str]] = []  # (section_title, chunk_text)
    for section_title, section_text in docx_renderer.split_sections(text):
        for chunk_text in rag._chunk(section_text):
            entries.append((section_title, chunk_text))
    if not entries:
        return
    vectors = _embed_batch([chunk for _, chunk in entries], config)
    for i, (section_title, chunk_text) in enumerate(entries):
        db.insert(
            "precedent_chunks",
            {
                "precedent_version_id": version["id"],
                "precedent_id": precedent["id"],
                "gestora_id": precedent.get("gestora_id"),
                "doc_type": precedent["doc_type"],
                "language": precedent.get("language"),
                "source": precedent.get("source"),
                "version_status": version["status"],
                "is_docx": version["file_path"].lower().endswith(".docx"),
                "chunk_index": i,
                "text": chunk_text,
                "section": section_title,
                "embed_model": config.resolved_embed_model if vectors else None,
                "embedding": vectors[i] if vectors else None,
            },
        )


def _sync_version(
    db: dbmod.Database,
    precedent: dict[str, Any],
    version: dict[str, Any],
    config: llm.EffectiveEmbeddingConfig,
) -> None:
    existing = db.select("precedent_chunks", precedent_version_id=version["id"])
    indexable = version.get("status") in _INDEXABLE_STATUSES

    if not indexable:
        for row in existing:
            db.delete("precedent_chunks", row["id"])
        return

    if not existing:
        _index_version(db, precedent, version, config)
        return

    # Status flip (active <-> superseded): metadata-only update, no re-embed.
    if existing[0].get("version_status") != version["status"]:
        for row in existing:
            db.update("precedent_chunks", row["id"], {"version_status": version["status"]})

    # Vector backfill: rows stored while the provider was unavailable.
    if all(row.get("embedding") is None for row in existing):
        ordered = sorted(existing, key=lambda r: r.get("chunk_index", 0))
        vectors = _embed_batch([r["text"] for r in ordered], config)
        if vectors:
            for row, vector in zip(ordered, vectors):
                db.update(
                    "precedent_chunks",
                    row["id"],
                    {"embedding": vector, "embed_model": config.resolved_embed_model},
                )


def sync_gestora(db: dbmod.Database, gestora_id: str) -> None:
    """Reconcile ONE gestora silo's index (idempotent; safe to re-run)."""
    config = llm.resolve_embedding_config(gestora_id)
    for precedent in db.select("precedents", gestora_id=gestora_id):
        for version in db.select("precedent_versions", precedent_id=precedent["id"]):
            _sync_version(db, precedent, version, config)


def sync_global(db: dbmod.Database) -> None:
    """Reconcile the global template pool's index (SLP + platform base)."""
    config = llm.resolve_embedding_config(None)
    for precedent in db.select("precedents", gestora_id=None):
        for version in db.select("precedent_versions", precedent_id=precedent["id"]):
            _sync_version(db, precedent, version, config)

