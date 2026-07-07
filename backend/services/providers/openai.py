"""OpenAI — optional CLOUD embeddings for RAG (opt-in only).

Requires OPENAI_API_KEY (global) or the gestora's encrypted BYO key. The
LlamaIndex embedding stack is a lazy optional dep.
"""
from __future__ import annotations

from typing import Any, Optional


class OpenAIEmbeddings:
    name = "openai"

    def is_configured(self, settings: Any) -> bool:
        return bool(settings.openai_api_key)

    def embed(self, texts: list[str], config: Any) -> Optional[list[list[float]]]:
        """Embed via OpenAI text-embedding through LlamaIndex, or None if the
        stack is unavailable (caller degrades to weight/recency ranking)."""
        if not config.openai_api_key:
            return None
        try:
            # Lazy imports: heavy optional deps.
            from llama_index.embeddings.openai import OpenAIEmbedding  # type: ignore[import-not-found]
        except ImportError:
            return None
        embedder = OpenAIEmbedding(model=config.embedding_model, api_key=config.openai_api_key)
        try:
            return embedder.get_text_embedding_batch(texts)
        except Exception:
            # Network/auth failure: degrade to weight/recency (never a wider pool).
            return None
