"""Anthropic Claude — optional CLOUD text generation (opt-in only).

Requires ANTHROPIC_API_KEY (global) or the gestora's encrypted BYO key. The
``anthropic`` package is a lazy optional dep: the app must start without it.
"""
from __future__ import annotations

from typing import Any, Optional

from config import ServiceNotConfiguredError, get_settings
from services.providers.base import json_instructions, retryable


class AnthropicLLM:
    name = "anthropic"

    def is_configured(self, settings: Any) -> bool:
        return bool(settings.anthropic_api_key)

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int,
        json_schema: Optional[dict[str, Any]],
        system: Optional[str],
        config: Any,
    ) -> str:
        """Call the Anthropic Claude API. JSON mode is prompt-driven (Anthropic
        has no ``format=json``)."""
        settings = get_settings()
        if not config.anthropic_api_key:
            raise ServiceNotConfiguredError("anthropic", "Set ANTHROPIC_API_KEY.")
        # Lazy import: heavy optional dep; app must start without it.
        import anthropic  # type: ignore[import-not-found]

        system_parts = [system] if system else []
        if json_schema is not None:
            system_parts.append(json_instructions(json_schema))

        # Key/model resolved per call (global default, or the gestora's BYO override).
        client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        kwargs: dict[str, Any] = {
            "model": config.claude_model,
            "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system_parts:
            kwargs["system"] = "\n\n".join(system_parts)

        def _do() -> Any:
            return client.messages.create(**kwargs)

        try:
            response = retryable(_do, settings.llm_retry_attempts)
        except anthropic.APIConnectionError as exc:  # type: ignore[attr-defined]
            raise ServiceNotConfiguredError(
                "anthropic", "Could not reach the Anthropic API."
            ) from exc
        except anthropic.BadRequestError as exc:  # type: ignore[attr-defined]
            # Cuenta sin crédito: el error de negocio más común. Debe llegar al
            # usuario como un 503 accionable, nunca como un 500 genérico.
            if "credit" in str(exc).lower():
                raise ServiceNotConfiguredError(
                    "anthropic",
                    "La cuenta de Anthropic no tiene crédito disponible. "
                    "Añade saldo en console.anthropic.com → Plans & Billing.",
                ) from exc
            raise
        except anthropic.AuthenticationError as exc:  # type: ignore[attr-defined]
            raise ServiceNotConfiguredError(
                "anthropic", "La API key de Anthropic no es válida o fue revocada."
            ) from exc
        except anthropic.RateLimitError as exc:  # type: ignore[attr-defined]
            raise ServiceNotConfiguredError(
                "anthropic",
                "Límite de peticiones de Anthropic alcanzado; espera unos segundos y reintenta.",
            ) from exc
        return "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
