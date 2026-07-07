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
from typing import Any, Optional, Protocol

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


def json_instructions(schema: dict[str, Any]) -> str:
    """Prompt fragment instructing the model to emit JSON matching ``schema``."""
    return (
        "You must respond with a single valid JSON object and nothing else "
        "(no markdown, no code fences, no preamble). The object must match "
        "this JSON schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}"
    )
