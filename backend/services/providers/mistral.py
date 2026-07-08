"""Mistral AI — optional EU cloud text generation (opt-in only).

The GDPR-friendlier cloud fallback: data residency in the EU (Paris), for
gestoras that accept cloud processing but not a US provider. Requires
MISTRAL_API_KEY (global) or the gestora's encrypted BYO key. Talks to the
OpenAI-compatible chat endpoint over httpx — no extra SDK dependency.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

from config import ServiceNotConfiguredError, get_settings
from services.providers.base import json_instructions, retryable

_API_URL = "https://api.mistral.ai/v1/chat/completions"


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

        def _do() -> httpx.Response:
            return httpx.post(
                _API_URL,
                json=payload,
                headers={"Authorization": f"Bearer {config.mistral_api_key}"},
                timeout=settings.ollama_timeout_seconds,
            )

        try:
            response = retryable(_do, settings.llm_retry_attempts)
        except httpx.HTTPError as exc:
            raise ServiceNotConfiguredError(
                "mistral", "Could not reach the Mistral API."
            ) from exc

        if response.status_code != 200:
            raise ServiceNotConfiguredError(
                "mistral",
                f"Mistral returned HTTP {response.status_code}: {response.text[:200]}.",
            )
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("message") or {}).get("content", "") or ""
