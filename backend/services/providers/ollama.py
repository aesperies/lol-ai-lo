"""Ollama — the LOCAL-FIRST default for both text generation and embeddings.

Needs no credential, only a reachable daemon (OLLAMA_BASE_URL); reachability
failures surface as ServiceNotConfiguredError (LLM) or None (embeddings —
caller degrades to weight/recency ranking, never a wider candidate pool).
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from config import ServiceNotConfiguredError, get_settings
from services.providers.base import json_instructions, retryable


class OllamaLLM:
    name = "ollama"

    def is_configured(self, settings: Any) -> bool:
        # No credential needed; daemon reachability is checked at call time.
        return True

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int,
        json_schema: Optional[dict[str, Any]],
        system: Optional[str],
        config: Any,
    ) -> str:
        """Call the local Ollama daemon's ``/api/chat`` endpoint (non-streaming)."""
        settings = get_settings()
        messages: list[dict[str, str]] = []
        system_parts = [system] if system else []
        if json_schema is not None:
            system_parts.append(json_instructions(json_schema))
        if system_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": config.ollama_llm_model,
            "messages": messages,
            "stream": False,
            "options": {"num_predict": max_tokens},
        }
        if json_schema is not None:
            payload["format"] = "json"  # Ollama JSON mode

        url = f"{config.ollama_base_url.rstrip('/')}/api/chat"

        def _do() -> httpx.Response:
            return httpx.post(url, json=payload, timeout=settings.ollama_timeout_seconds)

        try:
            response = retryable(_do, settings.llm_retry_attempts)
        except httpx.HTTPError as exc:
            raise ServiceNotConfiguredError(
                "ollama",
                f"Could not reach Ollama at {config.ollama_base_url}. "
                "Start it (`ollama serve`) or set LLM_PROVIDER=anthropic.",
            ) from exc

        if response.status_code != 200:
            raise ServiceNotConfiguredError(
                "ollama",
                f"Ollama returned HTTP {response.status_code}: {response.text[:200]}. "
                f"Is the model '{config.ollama_llm_model}' pulled?",
            )
        data = response.json()
        return (data.get("message") or {}).get("content", "")


class OllamaEmbeddings:
    name = "ollama"

    def is_configured(self, settings: Any) -> bool:
        return True

    def embed(self, texts: list[str], config: Any) -> Optional[list[list[float]]]:
        """Embed via the local daemon's ``/api/embeddings`` endpoint, looping
        per text. Returns None if Ollama is unreachable (caller degrades to
        weight/recency ranking — never a wider candidate pool)."""
        settings = get_settings()
        url = f"{config.ollama_base_url.rstrip('/')}/api/embeddings"
        vectors: list[list[float]] = []
        for text in texts:
            try:
                response = httpx.post(
                    url,
                    json={"model": config.ollama_embed_model, "prompt": text},
                    timeout=settings.ollama_timeout_seconds,
                )
            except httpx.HTTPError:
                return None
            if response.status_code != 200:
                return None
            vector = response.json().get("embedding")
            if not vector:
                return None
            vectors.append(vector)
        return vectors
