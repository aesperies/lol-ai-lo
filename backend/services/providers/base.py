"""Provider protocols + helpers shared by the provider implementations.

Adding a provider = one new module in this package implementing
:class:`LLMProvider` or :class:`EmbeddingProvider` (or both), plus one
registry entry in ``__init__.py``. Nothing else in the codebase changes —
``llm.complete``, ``rag._embed`` and the config readiness flags all dispatch
through the registry.

The ``config`` argument the providers receive is the per-call effective
configuration (llm.EffectiveLLMConfig / llm.EffectiveEmbeddingConfig): the
gestora's override or the global defaults, resolved fail-closed by
services/llm.py. Providers are duck-typed on it to keep this package free of
an import cycle with services/llm.py.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any, Iterator, Optional, Protocol

import httpx

logger = logging.getLogger("lolailo.providers")


class LLMProvider(Protocol):
    """A text-generation backend (one per module in this package)."""

    name: str

    def complete(
        self,
        prompt: str,
        *,
        max_tokens: int,
        json_schema: Optional[dict[str, Any]],
        system: Optional[str],
        config: Any,
    ) -> str: ...

    def stream(
        self,
        prompt: str,
        *,
        max_tokens: int,
        system: Optional[str],
        config: Any,
    ) -> Iterator[str]:
        """Yield text deltas as the provider produces them (chat Q&A).

        Plain-text only (no JSON mode — structured output keeps using
        :meth:`complete`). llm.stream() degrades to a single-yield complete()
        when a provider lacks this method, so implementing it is optional.
        """
        ...

    def is_configured(self, settings: Any) -> bool: ...


class EmbeddingProvider(Protocol):
    """An embedding backend for RAG."""

    name: str

    def embed(self, texts: list[str], config: Any) -> Optional[list[list[float]]]: ...

    def is_configured(self, settings: Any) -> bool: ...


# Backoff base (seconds) between transient-network retries. Pinned to ~0 under
# pytest so the suite stays fast (mirrors the job_backoff pattern).
_RETRY_BACKOFF_BASE = 0.0 if "pytest" in sys.modules else 0.5


def retryable(func, attempts: int):
    """Call ``func`` up to ``attempts`` times, retrying on transient httpx
    network errors with a short exponential backoff. Non-network errors and
    the final failure propagate to the caller."""
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            return func()
        except (httpx.ConnectError, httpx.ReadError, httpx.WriteError, httpx.RemoteProtocolError) as exc:
            last_exc = exc
            if attempt >= attempts:
                break
            logger.warning("LLM transient network error (attempt %d/%d): %s", attempt, attempts, exc)
            time.sleep(_RETRY_BACKOFF_BASE * (2 ** (attempt - 1)))
    assert last_exc is not None
    raise last_exc


def complete_openai_chat(
    *,
    url: str,
    payload: dict[str, Any],
    api_key: str,
    provider_name: str,
    unreachable_hint: str,
    timeout: float,
    retry_attempts: int,
) -> str:
    """Non-streaming completion against an OpenAI-compatible chat endpoint
    (Mistral, xAI) — the single-shot sibling of :func:`stream_openai_sse`.
    Same error contract as every provider: connection/HTTP failures raise
    ServiceNotConfiguredError (the API layer translates to HTTP 503)."""
    from config import ServiceNotConfiguredError  # local import, no cycle

    def _do() -> httpx.Response:
        return httpx.post(
            url,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    try:
        response = retryable(_do, retry_attempts)
    except httpx.HTTPError as exc:
        raise ServiceNotConfiguredError(provider_name, unreachable_hint) from exc

    if response.status_code != 200:
        raise ServiceNotConfiguredError(
            provider_name,
            f"{provider_name} returned HTTP {response.status_code}: "
            f"{response.text[:200]}.",
        )
    choices = response.json().get("choices") or []
    if not choices:
        return ""
    return (choices[0].get("message") or {}).get("content", "") or ""


def stream_openai_sse(
    *,
    url: str,
    payload: dict[str, Any],
    api_key: str,
    provider_name: str,
    unreachable_hint: str,
    timeout: float,
) -> Iterator[str]:
    """Stream text deltas from an OpenAI-compatible chat-completions SSE
    endpoint (Mistral, xAI). The payload must already carry ``stream: true``.

    Connection/HTTP failures raise ServiceNotConfiguredError exactly like the
    providers' non-streaming path (the API layer translates to HTTP 503). No
    mid-stream retry: a broken stream propagates — the caller decides whether
    the partial answer is usable.
    """
    from config import ServiceNotConfiguredError  # local import, no cycle

    try:
        with httpx.stream(
            "POST",
            url,
            json=payload,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        ) as response:
            if response.status_code != 200:
                response.read()
                raise ServiceNotConfiguredError(
                    provider_name,
                    f"{provider_name} returned HTTP {response.status_code}: "
                    f"{response.text[:200]}.",
                )
            for line in response.iter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError:
                    continue  # keep-alive / partial frame: skip, never crash
                choices = parsed.get("choices") or [{}]
                delta = (choices[0].get("delta") or {}).get("content") or ""
                if delta:
                    yield delta
    except httpx.HTTPError as exc:
        raise ServiceNotConfiguredError(provider_name, unreachable_hint) from exc


def json_instructions(schema: dict[str, Any]) -> str:
    """Prompt fragment instructing the model to emit JSON matching ``schema``."""
    return (
        "You must respond with a single valid JSON object and nothing else "
        "(no markdown, no code fences, no preamble). The object must match "
        "this JSON schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}"
    )
