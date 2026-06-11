"""Precedent retrieval (RAG) with hard gestora isolation.

CRITICAL ISOLATION RULE (SPEC guardrails 1 & 3): the gestora_id + doc_type
filter is a HARD PRE-FILTER applied at the database query, BEFORE any semantic
ranking. Semantic search only ever ranks documents that already passed the
filter — it can never surface another gestora's precedent.

Fallback chain:
  Level 0 — gestora silo (gestora_id + doc_type). rag_weight 1.0 active / 0.3 superseded.
  Level 1 — SLP-curated global templates (gestora_id NULL). rag_weight 0.7.
  Level 2 — platform base global templates (gestora_id NULL). rag_weight 0.4.
  Level 3 — no precedent: generate from scratch, FORCES Exit B (requires_counsel).

Only .docx precedents may serve as generation bases; PDFs are indexed as
read-only reference context (SPEC guardrail 7).

Embeddings: OpenAI text-embedding-3-small via LlamaIndex, chunks ~512 tokens
with 50 overlap, top-3 cosine. When OpenAI/LlamaIndex are unavailable the
ranking degrades to rag_weight + recency (deterministic), never to a wider
candidate pool.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from config import get_settings
from models.schema import LEVEL3_WARNING, PrecedentVersionStatus
from services import db as dbmod
from services import docx_renderer, storage

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


def _silo_candidates(db: dbmod.Database, gestora_id: str, doc_type: str) -> list[Candidate]:
    """Level 0: HARD pre-filter on gestora_id + doc_type at the DB query."""
    candidates: list[Candidate] = []
    for precedent in db.select("precedents", gestora_id=gestora_id, doc_type=doc_type):
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


def _semantic_scores(query: str, candidates: list[Candidate]) -> Optional[list[float]]:
    """Cosine similarity per candidate (max over chunks), or None if the
    embedding stack is unavailable — caller falls back to weight/recency."""
    settings = get_settings()
    if not settings.openai_configured:
        return None
    try:
        # Lazy imports: heavy optional deps.
        from llama_index.embeddings.openai import OpenAIEmbedding  # type: ignore[import-not-found]
    except ImportError:
        return None

    # TODO: real OpenAI API key required (OPENAI_API_KEY).
    embedder = OpenAIEmbedding(model=settings.embedding_model, api_key=settings.openai_api_key)
    query_vector = embedder.get_text_embedding(query)

    def cosine(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
        return dot / norm if norm else 0.0

    scores: list[float] = []
    for candidate in candidates:
        chunk_vectors = embedder.get_text_embedding_batch(_chunk(candidate.text)[:20])
        best = max((cosine(query_vector, v) for v in chunk_vectors), default=0.0)
        scores.append(best)
    return scores


def _rank(query: str, candidates: list[Candidate]) -> list[Candidate]:
    similarities = _semantic_scores(query, candidates)
    if similarities is None:
        # Deterministic degradation: rag_weight desc, then most recent.
        return sorted(
            candidates,
            key=lambda c: (c.weight, str(c.version.get("activated_at") or c.version.get("created_at") or "")),
            reverse=True,
        )
    paired = sorted(zip(candidates, similarities), key=lambda p: p[1] * p[0].weight, reverse=True)
    return [c for c, _ in paired]


def retrieve(
    db: dbmod.Database,
    *,
    gestora_id: str,
    doc_type: str,
    language: str,
    query_text: str,
) -> RetrievalResult:
    """Walk the fallback chain and return the generation base + context."""
    reference_context: list[str] = []  # PDF-only levels contribute context, never a base

    levels: list[tuple[int, list[Candidate]]] = [
        (0, _silo_candidates(db, gestora_id, doc_type)),
        (1, _global_candidates(db, "slp_curated", doc_type, language, 0.7)),
        (2, _global_candidates(db, "platform_base", doc_type, language, 0.4)),
    ]
    for level, candidates in levels:
        if not candidates:
            continue
        ranked = _rank(query_text, candidates)
        base = next((c for c in ranked if c.is_generation_base), None)
        if base is None:
            # PDFs only: keep as read-only reference and keep falling back.
            reference_context.extend(c.text for c in ranked[:TOP_K])
            continue
        context = [c.text for c in ranked[:TOP_K]]
        return RetrievalResult(
            level=level,
            base_text=base.text,
            base_version_id=base.version["id"],
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


def reindex_gestora(gestora_id: str) -> None:
    """Re-index hook (precedent activated/superseded within a gestora silo).

    The current implementation queries + ranks per request, so the 'index' is
    always fresh; this hook exists for a future persisted vector index.
    TODO: persist a per-gestora LlamaIndex VectorStoreIndex and rebuild here.
    """


def reindex_global() -> None:
    """Re-index hook for the global SLP/platform template pool. See above."""
