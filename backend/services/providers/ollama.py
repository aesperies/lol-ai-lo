"""Ollama — the LOCAL-FIRST default for both text generation and embeddings.

Needs no credential, only a reachable daemon (OLLAMA_BASE_URL); reachability
failures surface as ServiceNotConfiguredError (LLM) or None (embeddings —
caller degrades to weight/recency ranking, never a wider candidate pool).
"""
from __future__ import annotations

import json
from typing import Any, Iterator, Optional

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

    def stream(
        self,
        prompt: str,
        *,
        max_tokens: int,
        system: Optional[str],
        config: Any,
    ) -> Iterator[str]:
        """Stream deltas from ``/api/chat`` (newline-delimited JSON frames).

        Same error contract as complete(): unreachable daemon / non-200 →
        ServiceNotConfiguredError. No mid-stream retry — a broken stream
        propagates and the caller decides what to do with the partial text.
        """
        settings = get_settings()
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload: dict[str, Any] = {
            "model": config.ollama_llm_model,
            "messages": messages,
            "stream": True,
            "options": {"num_predict": max_tokens},
        }
        url = f"{config.ollama_base_url.rstrip('/')}/api/chat"

        try:
            with httpx.stream(
                "POST", url, json=payload, timeout=settings.ollama_timeout_seconds
            ) as response:
                if response.status_code != 200:
                    response.read()
                    raise ServiceNotConfiguredError(
                        "ollama",
                        f"Ollama returned HTTP {response.status_code}: {response.text[:200]}. "
                        f"Is the model '{config.ollama_llm_model}' pulled?",
                    )
                for line in response.iter_lines():
                    if not line.strip():
                        continue
                    try:
                        frame = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if frame.get("error"):
                        raise ServiceNotConfiguredError("ollama", str(frame["error"])[:200])
                    delta = (frame.get("message") or {}).get("content", "")
                    if delta:
                        yield delta
                    if frame.get("done"):
                        break
        except httpx.HTTPError as exc:
            raise ServiceNotConfiguredError(
                "ollama",
                f"Could not reach Ollama at {config.ollama_base_url}. "
                "Start it (`ollama serve`) or set LLM_PROVIDER=anthropic.",
            ) from exc


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
