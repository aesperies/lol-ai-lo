"""Mistral AI — optional EU cloud text generation AND embeddings (opt-in only).

The GDPR-friendlier cloud fallback: data residency in the EU (Paris), for
gestoras that accept cloud processing but not a US provider. Requires
MISTRAL_API_KEY (global) or the gestora's encrypted BYO key. Talks to the
OpenAI-compatible endpoints over httpx — no extra SDK dependency.

``MistralEmbeddings`` backs the persisted RAG index (migración 018):
mistral-embed produces 1024-dim vectors, the same dimension as bge-m3, so
local and EU-cloud embeddings share the pgvector column.
"""
from __future__ import annotations

from typing import Any, Iterator, Optional

import httpx

from config import ServiceNotConfiguredError, get_settings
from services.providers.base import (
    complete_openai_chat,
    json_instructions,
    retryable,
    stream_openai_sse,
)

_API_URL = "https://api.mistral.ai/v1/chat/completions"
_EMBED_URL = "https://api.mistral.ai/v1/embeddings"
# Mistral caps batch size; stay well under it (chunks are ~512 tokens each).
_EMBED_BATCH = 64


class MistralLLM:
    name = "mistral"

    def is_configured(self, settings: Any) -> bool:
        return bool(settings.mistral_api_key)

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int,
        json_schema: Optional[dict[str, Any]],
        system: Optional[str],
        config: Any,
    ) -> str:
        """Call the Mistral chat-completions API. JSON mode is native
        (``response_format=json_object``) plus schema instructions in the
        system prompt, mirroring the Ollama provider."""
        settings = get_settings()
        if not config.mistral_api_key:
            raise ServiceNotConfiguredError("mistral", "Set MISTRAL_API_KEY.")

        messages: list[dict[str, str]] = []
        system_parts = [system] if system else []
        if json_schema is not None:
            system_parts.append(json_instructions(json_schema))
        if system_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": config.mistral_model,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if json_schema is not None:
            payload["response_format"] = {"type": "json_object"}

        return complete_openai_chat(
            url=_API_URL,
            payload=payload,
            api_key=config.mistral_api_key,
            provider_name="mistral",
            unreachable_hint="Could not reach the Mistral API.",
            timeout=settings.ollama_timeout_seconds,
            retry_attempts=settings.llm_retry_attempts,
        )

    def stream(
        self,
        prompt: str,
        *,
        max_tokens: int,
        system: Optional[str],
        config: Any,
    ) -> Iterator[str]:
        """Stream deltas from the OpenAI-compatible SSE endpoint."""
        settings = get_settings()
        if not config.mistral_api_key:
            raise ServiceNotConfiguredError("mistral", "Set MISTRAL_API_KEY.")
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        yield from stream_openai_sse(
            url=_API_URL,
            payload={
                "model": config.mistral_model,
                "messages": messages,
                "max_tokens": max_tokens,
                "stream": True,
            },
            api_key=config.mistral_api_key,
            provider_name="mistral",
            unreachable_hint="Could not reach the Mistral API.",
            timeout=settings.ollama_timeout_seconds,
        )


class MistralEmbeddings:
    """EU-cloud embeddings for RAG (EMBEDDING_PROVIDER=mistral).

    Degradation contract (same as OpenAIEmbeddings): NEVER raises — any
    configuration, network or HTTP failure returns None and the caller falls
    back to weight/recency ranking (never a wider candidate pool).
    """

    name = "mistral"

    def is_configured(self, settings: Any) -> bool:
        return bool(settings.mistral_api_key)

    def embed(self, texts: list[str], config: Any) -> Optional[list[list[float]]]:
        api_key = getattr(config, "mistral_api_key", "")
        if not api_key or not texts:
            return None
        settings = get_settings()
        vectors: list[list[float]] = []
        for start in range(0, len(texts), _EMBED_BATCH):
            batch = texts[start:start + _EMBED_BATCH]

            def _do() -> httpx.Response:
                return httpx.post(
                    _EMBED_URL,
                    json={"model": config.mistral_embed_model, "input": batch},
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=settings.ollama_timeout_seconds,
                )

            try:
                response = retryable(_do, settings.llm_retry_attempts)
            except httpx.HTTPError:
                return None
            if response.status_code != 200:
                return None
            data = response.json().get("data") or []
            if len(data) != len(batch):
                return None
            vectors.extend(item.get("embedding") or [] for item in data)
        return vectors if all(vectors) else None
