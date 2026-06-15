"""LLM provider seam — the single entry point for all text generation.

Local-first: the default provider is **Ollama** (no credential, runs against a
local daemon at ``OLLAMA_BASE_URL``). **Anthropic** Claude is an optional,
env-selectable cloud fallback (``LLM_PROVIDER=anthropic``).

Callers use :func:`complete` for plain-text completions and
:func:`complete_json` when they need a parsed JSON object. Provider/network
failures are wrapped: a misconfigured or unreachable provider raises
:class:`ServiceNotConfiguredError` (API layers translate this to HTTP 503).
Transient network errors are retried with a short backoff (instant under
pytest).

Importable with zero optional deps installed: ``httpx`` is a hard dependency,
``anthropic`` stays lazily imported and is only needed when the provider is
switched to the cloud.
"""
from __future__ import annotations

import json
import logging
import sys
import time
from typing import Any, Optional

import httpx

from config import ServiceNotConfiguredError, get_settings

logger = logging.getLogger("lolailo.llm")

# Backoff base (seconds) between transient-network retries. Pinned to ~0 under
# pytest so the suite stays fast (mirrors the job_backoff pattern).
_RETRY_BACKOFF_BASE = 0.0 if "pytest" in sys.modules else 0.5


def _retryable(func, attempts: int):
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


def _json_instructions(schema: dict[str, Any]) -> str:
    """Prompt fragment instructing the model to emit JSON matching ``schema``."""
    return (
        "You must respond with a single valid JSON object and nothing else "
        "(no markdown, no code fences, no preamble). The object must match "
        "this JSON schema:\n"
        f"{json.dumps(schema, ensure_ascii=False)}"
    )


def _complete_ollama(
    prompt: str,
    *,
    max_tokens: int,
    json_schema: Optional[dict[str, Any]],
    system: Optional[str],
) -> str:
    """Call the local Ollama daemon's ``/api/chat`` endpoint (non-streaming)."""
    settings = get_settings()
    messages: list[dict[str, str]] = []
    system_parts = [system] if system else []
    if json_schema is not None:
        system_parts.append(_json_instructions(json_schema))
    if system_parts:
        messages.append({"role": "system", "content": "\n\n".join(system_parts)})
    messages.append({"role": "user", "content": prompt})

    payload: dict[str, Any] = {
        "model": settings.ollama_llm_model,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": max_tokens},
    }
    if json_schema is not None:
        payload["format"] = "json"  # Ollama JSON mode

    url = f"{settings.ollama_base_url.rstrip('/')}/api/chat"

    def _do() -> httpx.Response:
        return httpx.post(url, json=payload, timeout=settings.ollama_timeout_seconds)

    try:
        response = _retryable(_do, settings.llm_retry_attempts)
    except httpx.HTTPError as exc:
        raise ServiceNotConfiguredError(
            "ollama",
            f"Could not reach Ollama at {settings.ollama_base_url}. "
            "Start it (`ollama serve`) or set LLM_PROVIDER=anthropic.",
        ) from exc

    if response.status_code != 200:
        raise ServiceNotConfiguredError(
            "ollama",
            f"Ollama returned HTTP {response.status_code}: {response.text[:200]}. "
            f"Is the model '{settings.ollama_llm_model}' pulled?",
        )
    data = response.json()
    return (data.get("message") or {}).get("content", "")


def _complete_anthropic(
    prompt: str,
    *,
    max_tokens: int,
    json_schema: Optional[dict[str, Any]],
    system: Optional[str],
) -> str:
    """Call the Anthropic Claude API. JSON mode is prompt-driven (Anthropic has
    no ``format=json``)."""
    settings = get_settings()
    if not settings.anthropic_configured:
        raise ServiceNotConfiguredError("anthropic", "Set ANTHROPIC_API_KEY.")
    # Lazy import: heavy optional dep; app must start without it.
    import anthropic  # type: ignore[import-not-found]

    system_parts = [system] if system else []
    if json_schema is not None:
        system_parts.append(_json_instructions(json_schema))

    # TODO: real Anthropic API key required (ANTHROPIC_API_KEY).
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    kwargs: dict[str, Any] = {
        "model": settings.claude_model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if system_parts:
        kwargs["system"] = "\n\n".join(system_parts)

    def _do() -> Any:
        return client.messages.create(**kwargs)

    try:
        response = _retryable(_do, settings.llm_retry_attempts)
    except anthropic.APIConnectionError as exc:  # type: ignore[attr-defined]
        raise ServiceNotConfiguredError(
            "anthropic", "Could not reach the Anthropic API."
        ) from exc
    return "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )


def complete(
    prompt: str,
    *,
    max_tokens: int = 8192,
    json_schema: Optional[dict[str, Any]] = None,
    system: Optional[str] = None,
) -> str:
    """Generate a text completion via the configured provider.

    Args:
        prompt: The user prompt.
        max_tokens: Upper bound on generated tokens.
        json_schema: When provided, asks the provider for JSON output (Ollama
            uses native JSON mode; Anthropic relies on prompt discipline). The
            schema is also injected into the system prompt so the model knows
            the target shape. Use :func:`complete_json` to get a parsed dict.
        system: Optional system prompt.

    Returns:
        The model's text response.

    Raises:
        ServiceNotConfiguredError: The selected provider is misconfigured or
            unreachable (API layers translate to HTTP 503).
    """
    settings = get_settings()
    provider = settings.llm_provider
    if provider == "ollama":
        return _complete_ollama(
            prompt, max_tokens=max_tokens, json_schema=json_schema, system=system
        )
    if provider == "anthropic":
        return _complete_anthropic(
            prompt, max_tokens=max_tokens, json_schema=json_schema, system=system
        )
    raise ServiceNotConfiguredError(
        provider or "llm",
        "Unknown LLM_PROVIDER; expected 'ollama' or 'anthropic'.",
    )


def _coerce_json(raw: str) -> dict[str, Any]:
    """Parse ``raw`` into a dict, tolerating code fences and surrounding prose.

    Strips ``` / ```json fences, then falls back to the first ``{`` .. last
    ``}`` slice. Raises ValueError if nothing parseable is found.
    """
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        # Drop the opening fence line and any trailing fence.
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[:-3]
        cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(cleaned[start:end + 1])
    raise ValueError(f"No JSON object found in model output: {raw[:200]!r}")


def complete_json(
    prompt: str,
    schema: dict[str, Any],
    *,
    max_tokens: int = 8192,
    system: Optional[str] = None,
) -> dict[str, Any]:
    """Generate JSON output and parse it into a dict.

    Calls :func:`complete` with ``json_schema=schema`` (native JSON mode on
    Ollama). If the first output is not valid JSON, performs ONE repair retry
    after stripping fences / extracting the first..last brace.

    Raises:
        ServiceNotConfiguredError: Provider misconfigured or unreachable.
        ValueError: Output could not be parsed as JSON after the repair retry.
    """
    raw = complete(prompt, max_tokens=max_tokens, json_schema=schema, system=system)
    try:
        return _coerce_json(raw)
    except (ValueError, json.JSONDecodeError):
        logger.warning("LLM JSON output invalid; attempting one repair retry.")
    # Repair retry: re-ask, then coerce (fences/brace-slice). Propagate failure.
    raw = complete(prompt, max_tokens=max_tokens, json_schema=schema, system=system)
    return _coerce_json(raw)
