"""Precedent retrieval (RAG) with hard gestora isolation.

CRITICAL ISOLATION RULE (SPEC guardrails 1 & 3): the gestora_id + doc_type
filter is a HARD PRE-FILTER applied at the database query, BEFORE any semantic
ranking. Semantic search only ever ranks documents that already passed the
filter — it can never surface another gestora's precedent.

Fallback chain:
  Level 0a — gestora MODELOS (source=gestora_model): the gestora's master
             templates. Preferred generation base when an active .docx exists.
  Level 0b — gestora PRECEDENTES (every other in-silo source): past/validated
             documents. rag_weight 1.0 active / 0.3 superseded.
  Level 1  — SLP-curated global templates (gestora_id NULL). rag_weight 0.7.
  Level 2  — platform base global templates (gestora_id NULL). rag_weight 0.4.
  Level 3  — no precedent: generate from scratch, FORCES Exit B (requires_counsel).

Levels 0a and 0b are BOTH hard pre-filtered on gestora_id + doc_type — the
inviolable isolation rule applies to modelos exactly as it does to precedents
(a gestora's model is never the base for another gestora). Models only outrank
precedents WITHIN the same silo: 0a is tried as the generation base before 0b,
and precedentes still contribute as context regardless of which level provides
the base.

Only .docx precedents may serve as generation bases; PDFs are indexed as
read-only reference context (SPEC guardrail 7).

Embeddings are provider-agnostic (EMBEDDING_PROVIDER): local Ollama by default
(bge-m3, multilingual) or OpenAI text-embedding-3-small via LlamaIndex. Chunks
~512 tokens with 50 overlap, top-3 cosine. When the selected embedding
provider is unavailable the ranking degrades to rag_weight + recency
(deterministic), never to a wider candidate pool (isolation invariant).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from models.schema import LEVEL3_WARNING, PrecedentSource, PrecedentVersionStatus
from services import db as dbmod
from services import docx_renderer, llm, storage

# rag_weight by version status within the gestora silo (SPEC).
_SILO_WEIGHTS = {
    PrecedentVersionStatus.active.value: 1.0,
    PrecedentVersionStatus.superseded.value: 0.3,
}

CHUNK_TOKENS = 512
CHUNK_OVERLAP = 50
TOP_K = 3


@dataclass
class Candidate:
    precedent: dict[str, Any]
    version: dict[str, Any]
    weight: float
    text: str
    is_generation_base: bool  # .docx only


@dataclass
class RetrievalResult:
    level: int
    base_text: Optional[str]
    base_version_id: Optional[str]
    context_texts: list[str] = field(default_factory=list)
    requires_counsel: bool = False
    warning: Optional[str] = None


def _load_text(file_path: str) -> Optional[str]:
    """Extract text from a stored precedent file. PDFs use PyMuPDF and fall
    back to pytesseract OCR; both are optional deps — failures yield None
    (the precedent is simply skipped as context)."""
    try:
        data = storage.read(file_path)
    except Exception:
        return None
    lowered = file_path.lower()
    if lowered.endswith(".docx"):
        try:
            return docx_renderer.extract_text(data)
        except Exception:
            return None
    if lowered.endswith(".pdf"):
        try:
            import fitz  # type: ignore[import-not-found]  # PyMuPDF, lazy optional dep
        except ImportError:
            return None
        try:
            with fitz.open(stream=data, filetype="pdf") as pdf:
                text = "\n".join(page.get_text() for page in pdf)
            if text.strip():
                return text
            # Scanned PDF: OCR fallback.
            try:
                import pytesseract  # type: ignore[import-not-found]
                from PIL import Image  # type: ignore[import-not-found]
                import io as _io

                with fitz.open(stream=data, filetype="pdf") as pdf:
                    pages = []
                    for page in pdf:
                        pix = page.get_pixmap()
                        image = Image.open(_io.BytesIO(pix.tobytes("png")))
                        pages.append(pytesseract.image_to_string(image))
                return "\n".join(pages)
            except ImportError:
                return None
        except Exception:
            return None
    # Plain text fallback (used by tests and seeded templates).
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None


def load_version_text(version: dict[str, Any]) -> Optional[str]:
    """Re-read a stored precedent version's text (refinement redlines diff
    each new iteration against the SAME original precedent base)."""
    return _load_text(version["file_path"])


def _versions_for(db: dbmod.Database, precedent: dict[str, Any], statuses: dict[str, float]) -> list[Candidate]:
    candidates: list[Candidate] = []
    for version in db.select("precedent_versions", precedent_id=precedent["id"]):
        weight = statuses.get(version.get("status", ""))
        if weight is None:
            continue
        text = _load_text(version["file_path"])
        if text is None:
            continue
        is_docx = version["file_path"].lower().endswith(".docx")
        candidates.append(Candidate(precedent, version, weight, text, is_generation_base=is_docx))
    return candidates


_MODEL_SOURCE = PrecedentSource.gestora_model.value


def _model_candidates(db: dbmod.Database, gestora_id: str, doc_type: str) -> list[Candidate]:
    """Level 0a: gestora MASTER TEMPLATES (source=gestora_model). HARD pre-filter
    on gestora_id + doc_type at the DB query (isolation — models are siloed too).
    """
    candidates: list[Candidate] = []
    for precedent in db.select(
        "precedents", gestora_id=gestora_id, doc_type=doc_type, source=_MODEL_SOURCE
    ):
        candidates.extend(_versions_for(db, precedent, _SILO_WEIGHTS))
    return candidates


def _silo_candidates(db: dbmod.Database, gestora_id: str, doc_type: str) -> list[Candidate]:
    """Level 0b: gestora PRECEDENTES — every in-silo source EXCEPT gestora_model.
    HARD pre-filter on gestora_id + doc_type at the DB query."""
    candidates: list[Candidate] = []
    for precedent in db.select("precedents", gestora_id=gestora_id, doc_type=doc_type):
        if precedent.get("source") == _MODEL_SOURCE:
            continue  # handled by Level 0a (models outrank precedents as base)
        candidates.extend(_versions_for(db, precedent, _SILO_WEIGHTS))
    return candidates


def _global_candidates(db: dbmod.Database, source: str, doc_type: str, language: str, weight: float) -> list[Candidate]:
    """Levels 1-2: global template pools (gestora_id IS NULL only)."""
    candidates: list[Candidate] = []
    for precedent in db.select("precedents", gestora_id=None, doc_type=doc_type, source=source):
        if precedent.get("language") and language and precedent["language"] != language:
            continue
        for candidate in _versions_for(db, precedent, {PrecedentVersionStatus.active.value: weight}):
            candidate.weight = weight
            candidates.append(candidate)
    return candidates


def _chunk(text: str) -> list[str]:
    words = text.split()
    if not words:
        return []
    step = max(CHUNK_TOKENS - CHUNK_OVERLAP, 1)
    return [" ".join(words[i:i + CHUNK_TOKENS]) for i in range(0, len(words), step)]


def _embed(texts: list[str], config: llm.EffectiveEmbeddingConfig) -> Optional[list[list[float]]]:
    """Embed ``texts`` via the resolved provider, or None when unavailable.

    ``config`` comes from llm.resolve_embedding_config(gestora_id): the
    gestora's override (or fail-closed local Ollama) — never a raw global
    default when a gestora is in play. Dispatches through the provider
    registry (services/providers); an unknown provider degrades to None
    (weight/recency ranking) rather than failing retrieval.
    """
    from services import providers  # local import (optional-deps-free startup)

    provider = providers.get_embedding(config.embedding_provider)
    if provider is None:
        return None
    return provider.embed(texts, config)


def _semantic_scores(
    query: str, candidates: list[Candidate], config: llm.EffectiveEmbeddingConfig
) -> Optional[list[float]]:
    """Cosine similarity per candidate (max over chunks), or None if the
    selected embedding provider is unavailable — caller falls back to
    weight/recency ranking (never a wider candidate pool)."""
    query_vectors = _embed([query], config)
    if not query_vectors:
        return None
    query_vector = query_vectors[0]
    cosine = dbmod.cosine_similarity

    # ONE batched embed call for every candidate's chunks (cloud providers
    # batch internally; per-candidate calls were pure serial latency). Same
    # vectors, same scores, same degradation (any failure -> None).
    chunks_per_candidate = [_chunk(c.text)[:20] for c in candidates]
    flat = [chunk for chunks in chunks_per_candidate for chunk in chunks]
    if not flat:
        return None
    vectors = _embed(flat, config)
    if not vectors:
        return None

    scores: list[float] = []
    cursor = 0
    for chunks in chunks_per_candidate:
        chunk_vectors = vectors[cursor:cursor + len(chunks)]
        cursor += len(chunks)
        if not chunk_vectors:
            return None
        best = max((cosine(query_vector, v) for v in chunk_vectors), default=0.0)
        scores.append(best)
    return scores


def _rank(
    query: str,
    candidates: list[Candidate],
    config: llm.EffectiveEmbeddingConfig,
    language: str = "",
) -> list[Candidate]:
    similarities = _semantic_scores(query, candidates, config)
    if similarities is None:
        # Deterministic degradation: language match first (a Spanish request
        # must prefer the Spanish model over a newer English one), then
        # rag_weight desc, then most recent.
        def lang_match(c: Candidate) -> int:
            precedent_lang = c.precedent.get("language")
            return 1 if (language and precedent_lang == language) else 0

        return sorted(
            candidates,
            key=lambda c: (
                lang_match(c),
                c.weight,
                str(c.version.get("activated_at") or c.version.get("created_at") or ""),
            ),
            reverse=True,
        )
    paired = sorted(zip(candidates, similarities), key=lambda p: p[1] * p[0].weight, reverse=True)
    return [c for c, _ in paired]


# Max chunk texts contributed as context by the indexed path (chunks are ~512
# tokens; TOP_K on the file path returns whole documents, so more-but-smaller
# pieces keep prompt sizes comparable).
CONTEXT_CHUNKS = 8

# Weights for the global pools (active versions only), keyed by source.
_GLOBAL_WEIGHTS = {"slp_curated": 0.7, "platform_base": 0.4}


@dataclass
class _VersionHit:
    """One precedent version ranked from the persisted index."""

    version_id: str
    score: float  # max chunk similarity × level weight (same formula as _rank)
    is_docx: bool
    chunk_texts: list[str]  # most-similar-first


def _indexed_hits(
    db: dbmod.Database,
    *,
    config: llm.EffectiveEmbeddingConfig,
    query_vector: list[float],
    weights: dict[str, float],
    gestora_id: Optional[str],
    doc_type: str,
    source: Optional[str] = None,
    exclude_source: Optional[str] = None,
    language: Optional[str] = None,
) -> list[_VersionHit]:
    """Rank versions for ONE level from precedent_chunks (018), or [] when the
    level has no indexed vectors — the caller then falls back to the
    file-based path, so unindexed content is never silently dropped."""
    rows = db.search_chunks(
        gestora_id=gestora_id,
        doc_type=doc_type,
        query_embedding=query_vector,
        embed_model=config.resolved_embed_model,
        source=source,
        exclude_source=exclude_source,
        language=language,
    )
    by_version: dict[str, _VersionHit] = {}
    for row in rows:  # most-similar-first
        weight = weights.get(row.get("version_status", ""))
        if weight is None:
            continue
        hit = by_version.get(row["precedent_version_id"])
        if hit is None:
            by_version[row["precedent_version_id"]] = _VersionHit(
                version_id=row["precedent_version_id"],
                score=row["similarity"] * weight,
                is_docx=bool(row.get("is_docx")),
                chunk_texts=[row["text"]],
            )
        else:
            hit.chunk_texts.append(row["text"])
            hit.score = max(hit.score, row["similarity"] * weight)
    return sorted(by_version.values(), key=lambda h: h.score, reverse=True)


def _context_from_hits(hits: list[_VersionHit], limit: int = CONTEXT_CHUNKS) -> list[str]:
    texts: list[str] = []
    for hit in hits:
        for text in hit.chunk_texts:
            if len(texts) >= limit:
                return texts
            texts.append(text)
    return texts


def _base_text_for(db: dbmod.Database, hits: list[_VersionHit]) -> Optional[tuple[str, str]]:
    """(base_text, version_id) for the best .docx hit whose file still reads."""
    for hit in hits:
        if not hit.is_docx:
            continue
        version = db.get("precedent_versions", hit.version_id)
        if version is None:
            continue
        text = _load_text(version["file_path"])
        if text is not None:
            return text, hit.version_id
    return None


def retrieve(
    db: dbmod.Database,
    *,
    gestora_id: str,
    doc_type: str,
    language: str,
    query_text: str,
) -> RetrievalResult:
    """Walk the fallback chain and return the generation base + context.

    Fast path: the persisted index (precedent_chunks, 018) — ONE query
    embedding + one ANN search per level, no file re-reads except the chosen
    base. Levels without indexed vectors (silo not yet backfilled, embeddings
    unavailable) fall back per-level to the original file-based path, which in
    turn degrades to weight/recency ranking. The gestora_id + doc_type hard
    pre-filter applies identically on every path.
    """
    reference_context: list[str] = []  # PDF-only levels contribute context, never a base

    # Embedding config resolved ONCE per scope, honoring the gestora's
    # model-config override (fail-closed to local Ollama on error). Global
    # pools are indexed with the PLATFORM config — a gestora override changes
    # how her silo is embedded, never how the shared pool is queried.
    silo_config = llm.resolve_embedding_config(gestora_id)
    global_config = llm.resolve_embedding_config(None)

    _query_vectors: dict[tuple[str, str], Optional[list[float]]] = {}

    def query_vector(config: llm.EffectiveEmbeddingConfig) -> Optional[list[float]]:
        key = (config.embedding_provider, config.resolved_embed_model)
        if key not in _query_vectors:
            vectors = _embed([query_text], config)
            vector = vectors[0] if vectors else None
            if vector is not None:
                # The index column is vector(1024); a provider returning
                # another dimension cannot be compared (pgvector errors) —
                # degrade instead. Mirrors the indexer's dimension check.
                from services import indexer  # local import, no cycle

                if len(vector) != indexer.EXPECTED_DIM:
                    vector = None
            _query_vectors[key] = vector
        return _query_vectors[key]

    def silo_context_texts() -> list[str]:
        """Precedente (0b) context when a modelo provides the base."""
        vector = query_vector(silo_config)
        if vector is not None:
            hits = _indexed_hits(
                db, config=silo_config, query_vector=vector, weights=_SILO_WEIGHTS,
                gestora_id=gestora_id, doc_type=doc_type, exclude_source=_MODEL_SOURCE,
            )
            if hits:
                return _context_from_hits(hits)
        candidates = _silo_candidates(db, gestora_id, doc_type)
        return [c.text for c in _rank(query_text, candidates, silo_config, language)[:TOP_K]]

    # (level, chunk-search kwargs, file-candidates factory, per-status weights)
    level_specs: list[tuple[int, dict[str, Any], Any, dict[str, float], llm.EffectiveEmbeddingConfig]] = [
        (0, {"gestora_id": gestora_id, "source": _MODEL_SOURCE},
         lambda: _model_candidates(db, gestora_id, doc_type), _SILO_WEIGHTS, silo_config),
        (0, {"gestora_id": gestora_id, "exclude_source": _MODEL_SOURCE},
         lambda: _silo_candidates(db, gestora_id, doc_type), _SILO_WEIGHTS, silo_config),
        (1, {"gestora_id": None, "source": "slp_curated", "language": language or None},
         lambda: _global_candidates(db, "slp_curated", doc_type, language, 0.7),
         {PrecedentVersionStatus.active.value: _GLOBAL_WEIGHTS["slp_curated"]}, global_config),
        (2, {"gestora_id": None, "source": "platform_base", "language": language or None},
         lambda: _global_candidates(db, "platform_base", doc_type, language, 0.4),
         {PrecedentVersionStatus.active.value: _GLOBAL_WEIGHTS["platform_base"]}, global_config),
    ]

    for index, (level, chunk_filters, candidates_factory, weights, config) in enumerate(level_specs):
        is_model_level = index == 0

        # -- fast path: persisted index ------------------------------------
        vector = query_vector(config)
        hits = (
            _indexed_hits(
                db, config=config, query_vector=vector, weights=weights,
                doc_type=doc_type, **chunk_filters,
            )
            if vector is not None
            else []
        )
        if hits:
            base = _base_text_for(db, hits)
            if base is None:
                # PDFs only: keep as read-only reference and keep falling back.
                reference_context.extend(_context_from_hits(hits, TOP_K))
                continue
            base_text, base_version_id = base
            context = _context_from_hits(hits)
            if is_model_level:
                # Precedentes contribute context even when a model is the base.
                context += silo_context_texts()
            return RetrievalResult(
                level=level,
                base_text=base_text,
                base_version_id=base_version_id,
                context_texts=reference_context + context,
            )

        # -- fallback: file-based candidates (original path) ----------------
        candidates = candidates_factory()
        if not candidates:
            continue
        ranked = _rank(query_text, candidates, config, language)
        base_candidate = next((c for c in ranked if c.is_generation_base), None)
        if base_candidate is None:
            reference_context.extend(c.text for c in ranked[:TOP_K])
            continue
        context = [c.text for c in ranked[:TOP_K]]
        if is_model_level:
            context += silo_context_texts()
        return RetrievalResult(
            level=level,
            base_text=base_candidate.text,
            base_version_id=base_candidate.version["id"],
            context_texts=reference_context + context,
        )

    return RetrievalResult(
        level=3,
        base_text=None,
        base_version_id=None,
        context_texts=reference_context,
        requires_counsel=True,  # Level 3 ALWAYS forces Exit B (guardrail 10)
        warning=LEVEL3_WARNING,
    )


@dataclass
class ChatHit:
    """Un chunk recuperado para el chat Q&A, con su procedencia (cita)."""

    precedent_id: str
    precedent_version_id: str
    doc_type: str
    source: str
    text: str
    similarity: float
    section: Optional[str] = None


# Constante estándar de Reciprocal Rank Fusion: amortigua la diferencia entre
# posiciones altas sin que la cabeza de una lista domine a la otra.
_RRF_K = 60


def _rrf_merge(*ranked_lists: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fusión RRF de listas ya ordenadas (mejor primero) de filas de chunks.

    score(chunk) = Σ 1/(K + posición) sobre las listas donde aparece — un
    chunk que la búsqueda semántica Y la léxica encuentran sube; uno que solo
    aparece en una queda por detrás. Empates rotos por id (determinista).
    """
    scores: dict[str, float] = {}
    rows_by_id: dict[str, dict[str, Any]] = {}
    for rows in ranked_lists:
        for position, row in enumerate(rows):
            key = row["id"]
            rows_by_id[key] = row
            scores[key] = scores.get(key, 0.0) + 1.0 / (_RRF_K + position + 1)
    ordered = sorted(scores.items(), key=lambda item: (-item[1], item[0]))
    return [dict(rows_by_id[key], rrf_score=score) for key, score in ordered]


def search_silo(
    db: dbmod.Database,
    *,
    gestora_id: str,
    language: str,
    query_text: str,
    limit: int = CONTEXT_CHUNKS,
) -> list[ChatHit]:
    """Chat Q&A (021/022): los chunks más relevantes del silo de la gestora
    SIN fijar doc_type — la pregunta libre no sabe de tipos de documento.

    Búsqueda HÍBRIDA: semántica (pgvector) + texto completo (022), fusionadas
    con RRF. La mitad léxica cubre lo que los embeddings fallan (términos
    exactos: "cláusula 8.2", "hurdle rate") y sigue funcionando con el
    proveedor de embeddings caído. El pre-filtro duro de aislamiento por
    gestora_id se aplica idéntico en ambas mitades; lo único que se ensancha
    es el doc_type DENTRO del silo. Solo versiones ACTIVAS (un precedente
    sustituido puede contener términos obsoletos y una respuesta de chat no
    tiene el contexto para matizarlo).

    Fallback (silo sin indexar): lectura de ficheros + ranking determinista
    idéntico al de retrieve() — nunca un pool de candidatos más amplio.
    """
    active = PrecedentVersionStatus.active.value
    config = llm.resolve_embedding_config(gestora_id)

    vector: Optional[list[float]] = None
    vectors = _embed([query_text], config)
    if vectors:
        vector = vectors[0]
        from services import indexer  # local import, no cycle

        if len(vector) != indexer.EXPECTED_DIM:
            vector = None

    semantic_rows = (
        db.search_chunks(
            gestora_id=gestora_id,
            doc_type=None,
            query_embedding=vector,
            embed_model=config.resolved_embed_model,
            limit=limit * 2,  # margen para el filtro de estado de versión
        )
        if vector is not None
        else []
    )
    lexical_rows = db.search_chunks_text(
        gestora_id=gestora_id, query_text=query_text, limit=limit * 2
    )
    semantic_rows = [r for r in semantic_rows if r.get("version_status") == active]
    lexical_rows = [r for r in lexical_rows if r.get("version_status") == active]

    if semantic_rows or lexical_rows:
        merged = _rrf_merge(semantic_rows, lexical_rows)[:limit]
        return [
            ChatHit(
                precedent_id=row["precedent_id"],
                precedent_version_id=row["precedent_version_id"],
                doc_type=row.get("doc_type") or "",
                source=row.get("source") or "",
                text=row["text"],
                similarity=row.get("rrf_score") or 0.0,
                section=row.get("section"),
            )
            for row in merged
        ]

    # Fallback por ficheros: mismos candidatos que los niveles 0a/0b pero a
    # través de TODOS los doc_types del silo, versiones activas únicamente.
    candidates: list[Candidate] = []
    for precedent in db.select("precedents", gestora_id=gestora_id):
        candidates.extend(_versions_for(db, precedent, {active: 1.0}))
    if not candidates:
        return []
    ranked = _rank(query_text, candidates, config, language)[:TOP_K]
    per_doc = max(1, limit // max(len(ranked), 1))
    hits = []
    for candidate in ranked:
        for chunk in _chunk(candidate.text)[:per_doc]:
            hits.append(ChatHit(
                precedent_id=candidate.precedent["id"],
                precedent_version_id=candidate.version["id"],
                doc_type=candidate.precedent.get("doc_type") or "",
                source=candidate.precedent.get("source") or "",
                text=chunk,
                similarity=0.0,
            ))
    return hits[:limit]


def _reindex(gestora_id: Optional[str], precedent_id: Optional[str]) -> None:
    """Shared body for reindex_gestora/reindex_global (gestora_id None = the
    global SLP/platform pool). ``precedent_id`` scopes the sync to one
    precedent (the hot path from activate/supersede/delivery); without it the
    whole scope is reconciled (backfill / repair). Index failures never break
    the calling flow — retrieval falls back to the file-based path."""
    from services import indexer  # local import: indexer imports rag helpers

    db = dbmod.get_db()
    try:
        if precedent_id:
            precedent = db.get("precedents", precedent_id)
            if precedent is None:
                return
            config = llm.resolve_embedding_config(gestora_id)
            for version in db.select("precedent_versions", precedent_id=precedent_id):
                indexer._sync_version(db, precedent, version, config)
        elif gestora_id:
            indexer.sync_gestora(db, gestora_id)
        else:
            indexer.sync_global(db)
    except Exception:  # noqa: BLE001 — indexing must never break the caller
        _logger().exception(
            "RAG index sync failed for %s (retrieval will fall back)",
            f"gestora {gestora_id}" if gestora_id else "the global pool",
        )


def reindex_gestora(gestora_id: str, precedent_id: Optional[str] = None) -> None:
    """Sync the gestora silo's persisted index (precedent_chunks, 018)."""
    _reindex(gestora_id, precedent_id)


def reindex_global(precedent_id: Optional[str] = None) -> None:
    """Sync the global SLP/platform pool's persisted index."""
    _reindex(None, precedent_id)


def _logger():  # tiny indirection keeps module import light
    import logging

    return logging.getLogger("lolailo.rag")
