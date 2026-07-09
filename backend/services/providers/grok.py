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
