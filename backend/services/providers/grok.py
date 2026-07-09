"""Grok (xAI) — optional US cloud text generation (opt-in only).

Requires XAI_API_KEY (global) or the gestora's encrypted BYO key. Talks to
the OpenAI-compatible chat endpoint at api.x.ai over httpx — no extra SDK
dependency. xAI publishes NO embedding models (July 2026), so this provider
is generation-only; the RAG index keeps its own embedding provider.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from config import ServiceNotConfiguredError, get_settings
from services.providers.base import json_instructions, retryable

_API_URL = "https://api.x.ai/v1/chat/completions"


class GrokLLM:
    name = "grok"

    def is_configured(self, settings: Any) -> bool:
        return bool(settings.xai_api_key)

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int,
        json_schema: Optional[dict[str, Any]],
        system: Optional[str],
        config: Any,
    ) -> str:
        """Call the xAI chat-completions API. JSON mode is native
        (``response_format=json_object``) plus schema instructions in the
        system prompt, mirroring the Mistral/Ollama providers."""
        settings = get_settings()
        if not config.xai_api_key:
            raise ServiceNotConfiguredError("grok", "Set XAI_API_KEY (console.x.ai).")

        messages: list[dict[str, str]] = []
        system_parts = [system] if system else []
        if json_schema is not None:
            system_parts.append(json_instructions(json_schema))
        if system_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": config.grok_model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if json_schema is not None:
            payload["response_format"] = {"type": "json_object"}

        def _do() -> httpx.Response:
            return httpx.post(
                _API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {config.xai_api_key}"},
                timeout=settings.ollama_timeout_seconds,
            )

        try:
            response = retryable(_do, settings.llm_retry_attempts)
        except httpx.HTTPError as exc:
            raise ServiceNotConfiguredError(
                "grok", "Could not reach the xAI API."
            ) from exc

        if response.status_code != 200:
            raise ServiceNotConfiguredError(
                "grok",
                f"xAI returned HTTP {response.status_code}: {response.text[:200]}.",
            )
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("message") or {}).get("content", "") or ""


_EMBED_URL = "https://api.x.ai/v1/embeddings"
_EMBED_MODELS_URL = "https://api.x.ai/v1/embedding-models"
# The API caps the input list at 128 entries; stay under it.
_EMBED_BATCH = 100
# The persisted RAG index column is vector(1024) (migración 018): ask xAI for
# 1024-dim vectors explicitly via the `dimensions` request parameter.
_EMBED_DIMENSIONS = 1024

# Auto-discovered embedding model id (xAI exposes the account's models at
# /v1/embedding-models; the public docs don't publish a fixed name). Cached
# per process; an explicit GROK_EMBED_MODEL setting always wins.
_discovered_embed_model: Optional[str] = None


def discovered_embed_model() -> Optional[str]:
    """The auto-discovered embedding model id, if any (see GrokEmbeddings)."""
    return _discovered_embed_model


class GrokEmbeddings:
    """xAI embeddings for RAG (EMBEDDING_PROVIDER=grok).

    Degradation contract (same as the other embedding providers): NEVER
    raises — any configuration, network or HTTP failure returns None and the
    caller falls back to weight/recency ranking (never a wider pool).
    """

    name = "grok"

    def is_configured(self, settings: Any) -> bool:
        return bool(settings.xai_api_key)

    def _resolve_model(self, config: Any, api_key: str) -> str:
        explicit = getattr(config, "grok_embed_model", "")
        if explicit:
            return explicit
        global _discovered_embed_model
        if _discovered_embed_model:
            return _discovered_embed_model
        try:
            response = httpx.get(
                _EMBED_MODELS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=get_settings().ollama_timeout_seconds,
            )
        except httpx.HTTPError:
            return ""
        if response.status_code != 200:
            return ""
        models = response.json().get("models") or []
        if not models:
            return ""
        _discovered_embed_model = models[0].get("id") or ""
        return _discovered_embed_model

    def embed(self, texts: list[str], config: Any) -> Optional[list[list[float]]]:
        api_key = getattr(config, "xai_api_key", "")
        if not api_key or not texts:
            return None
        settings = get_settings()
        model = self._resolve_model(config, api_key)
        if not model:
            return None
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _EMBED_BATCH):
            batch = texts[start:start + _EMBED_BATCH]
            payload = {
                "model": model,
                "input": batch,
                "dimensions": _EMBED_DIMENSIONS,
                "encoding_format": "float",
            }

            def _do() -> httpx.Response:
                return httpx.post(
                    _EMBED_URL,
                    json=payload,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=settings.ollama_timeout_seconds,
                )

            try:
                response = retryable(_do, settings.llm_retry_attempts)
                if response.status_code == 400 and "dimensions" in response.text.lower():
                    # Model without matryoshka support: retry at native size —
                    # the indexer's dimension check guards the vector column.
                    payload.pop("dimensions", None)
                    response = retryable(_do, settings.llm_retry_attempts)
            except httpx.HTTPError:
                return None
            if response.status_code != 200:
                return None
            data = response.json().get("data") or []
            if len(data) != len(batch):
                return None
            data.sort(key=lambda item: item.get("index", 0))
            vectors.extend(item.get("embedding") or [] for item in data)
        return vectors if all(vectors) else None
