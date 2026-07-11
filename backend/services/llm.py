"""LLM provider seam — the single entry point for all text generation.

Local-first: the default provider is **Ollama** (no credential, runs against a
local daemon at ``OLLAMA_BASE_URL``). **Anthropic** Claude is an optional,
env-selectable cloud fallback (``LLM_PROVIDER=anthropic``).

Callers use :func:`complete` for plain-text completions and
:func:`complete_json` when they need a parsed JSON object. This module owns
the per-gestora config RESOLUTION (fail-closed to local); the provider
implementations live in the services/providers registry — adding a provider
is one new module there, nothing here changes. Provider/network failures are
wrapped: a misconfigured or unreachable provider raises
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
from typing import Any, Iterator, Optional

# Kept as a module attribute on purpose: tests (and conftest's no-network
# guard) monkeypatch ``llm.httpx.post`` to stub every provider's HTTP layer —
# this IS the shared httpx module object the providers use.
import httpx  # noqa: F401

from config import get_settings

logger = logging.getLogger("lolailo.llm")


class EffectiveLLMConfig:
    """The provider/model/keys to use for ONE call.

    Resolved per call (:func:`resolve_config`): when a ``gestora_id`` is supplied
    and that gestora has a ``gestora_model_config`` override row, its non-NULL
    fields win; everything else falls back to the global settings (config.py).
    With no gestora (or no override) this is exactly the global configuration, so
    the seam stays backward-compatible (existing callers pass nothing → global).
    """

    __slots__ = (
        "llm_provider",
        "claude_model",
        "anthropic_api_key",
        "mistral_api_key",
        "mistral_model",
        "xai_api_key",
        "grok_model",
        "ollama_base_url",
        "ollama_llm_model",
        "model_pinned",
    )

    def __init__(
        self,
        *,
        llm_provider: str,
        claude_model: str,
        anthropic_api_key: str,
        ollama_base_url: str,
        ollama_llm_model: str,
        mistral_api_key: str = "",
        mistral_model: str = "",
        xai_api_key: str = "",
        grok_model: str = "",
        model_pinned: bool = False,
    ) -> None:
        self.llm_provider = llm_provider
        self.claude_model = claude_model
        self.anthropic_api_key = anthropic_api_key
        self.mistral_api_key = mistral_api_key
        self.mistral_model = mistral_model
        self.xai_api_key = xai_api_key
        self.grok_model = grok_model
        self.ollama_base_url = ollama_base_url
        self.ollama_llm_model = ollama_llm_model
        # True when a gestora pinned an explicit llm_model in its override —
        # the cost router (services/model_router.py) must never re-route it.
        self.model_pinned = model_pinned

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)


class EffectiveEmbeddingConfig:
    """The embedding provider/model/keys to use for ONE RAG call.

    Mirrors :class:`EffectiveLLMConfig` for the embedding side: the gestora's
    ``gestora_model_config`` row (embedding_provider / embedding_model /
    openai_api_key_enc / ollama_base_url) overrides the global settings.
    """

    __slots__ = (
        "embedding_provider",
        "embedding_model",
        "openai_api_key",
        "ollama_base_url",
        "ollama_embed_model",
        "mistral_api_key",
        "mistral_embed_model",
        "xai_api_key",
        "grok_embed_model",
    )

    def __init__(
        self,
        *,
        embedding_provider: str,
        embedding_model: str,
        openai_api_key: str,
        ollama_base_url: str,
        ollama_embed_model: str,
        mistral_api_key: str = "",
        mistral_embed_model: str = "mistral-embed",
        xai_api_key: str = "",
        grok_embed_model: str = "",
    ) -> None:
        self.embedding_provider = embedding_provider
        self.embedding_model = embedding_model
        self.openai_api_key = openai_api_key
        self.ollama_base_url = ollama_base_url
        self.ollama_embed_model = ollama_embed_model
        self.mistral_api_key = mistral_api_key
        self.mistral_embed_model = mistral_embed_model
        self.xai_api_key = xai_api_key
        self.grok_embed_model = grok_embed_model

    @property
    def resolved_embed_model(self) -> str:
        """Model name that produces (and must match) the stored vectors.

        ``precedent_chunks.embed_model`` (018) records this per row: vectors
        from different models are not comparable, so search filters on it.
        """
        if self.embedding_provider == "ollama":
            return self.ollama_embed_model
        if self.embedding_provider == "mistral":
            return self.mistral_embed_model
        if self.embedding_provider == "grok":
            if self.grok_embed_model:
                return self.grok_embed_model
            # Auto-discovery: the model id the provider resolved at runtime
            # (empty until the first successful call — nothing indexed yet).
            from services.providers import grok  # local import, no cycle
            return grok.discovered_embed_model() or ""
        return self.embedding_model


def _load_override_row(gestora_id: str) -> Optional[dict[str, Any]]:
    """The gestora's model-config override row (newest wins), or None.

    Raises on DB failure — callers decide the degradation, and for anything
    that could route content to a cloud provider the rule is FAIL CLOSED.
    """
    # Local import: keep services/llm.py importable with zero optional deps.
    from services import db as dbmod

    rows = dbmod.get_db().select("gestora_model_config", gestora_id=gestora_id)
    return rows[-1] if rows else None


def _local_llm_config(settings: Any) -> EffectiveLLMConfig:
    """Local-only (Ollama, no cloud key) — the fail-closed degradation target."""
    return EffectiveLLMConfig(
        llm_provider="ollama",
        claude_model=settings.claude_model,
        anthropic_api_key="",
        ollama_base_url=settings.ollama_base_url,
        ollama_llm_model=settings.ollama_llm_model,
    )


def _decrypt_byo(row: dict[str, Any], enc_field: str, provider_label: str,
                 env_name: str, gestora_id: str) -> Optional[str]:
    """Decrypt one BYO key from the gestora's override row, or None.

    A key that fails to decrypt is treated as "not set" (WARNING, never the
    plaintext) — the caller keeps the global env key. One helper instead of
    six copies of the same try/except (adding a provider = one call).
    """
    from services import secrets  # local import (optional-deps-free startup)

    enc = row.get(enc_field)
    if not enc:
        return None
    try:
        return secrets.decrypt(enc)
    except secrets.DecryptionError:
        logger.warning(
            "%s BYO key for gestora %s could not be decrypted; "
            "falling back to global %s.",
            provider_label, gestora_id, env_name,
        )
        return None


def resolve_config(
    gestora_id: Optional[str] = None, *, task: Optional[str] = None
) -> EffectiveLLMConfig:
    """Resolve the effective LLM config for an optional gestora and workload.

    Falls back to global settings when ``gestora_id`` is None or the gestora
    has no override row. When the override row CANNOT BE READ the resolution
    fails CLOSED to local Ollama: the gestora may have configured "local only",
    and sending its content to a cloud default on a transient DB error would
    violate the no-cloud-without-opt-in rule (CLAUDE.md). Encrypted BYO keys
    are decrypted here (services/secrets.py); a key that fails to decrypt is
    treated as "not set" (logged at WARNING, never the plaintext).

    ``task`` feeds the cost router (services/model_router.py): AFTER the
    provider is resolved (privacy decision), light-tier workloads may be
    routed to the provider's cheaper model (cost decision). A gestora-pinned
    ``llm_model`` disables routing for its calls.
    """
    settings = get_settings()
    config = EffectiveLLMConfig(
        llm_provider=settings.llm_provider,
        claude_model=settings.claude_model,
        anthropic_api_key=settings.anthropic_api_key,
        mistral_api_key=settings.mistral_api_key,
        mistral_model=settings.mistral_model,
        xai_api_key=settings.xai_api_key,
        grok_model=settings.grok_model,
        ollama_base_url=settings.ollama_base_url,
        ollama_llm_model=settings.ollama_llm_model,
    )
    # Local import: model_router imports config only; avoids a cycle here.
    from services import model_router

    if not gestora_id:
        return model_router.apply(config, task)

    try:
        row = _load_override_row(gestora_id)
    except Exception:  # noqa: BLE001 — resolution must never break a call
        logger.warning(
            "Could not load model config for gestora %s; failing CLOSED to "
            "local Ollama (cloud is opt-in and the opt-in is unreadable).",
            gestora_id,
        )
        return model_router.apply(_local_llm_config(settings), task)
    if row is None:
        return model_router.apply(config, task)

    if row.get("llm_provider"):
        config.llm_provider = row["llm_provider"]
    if row.get("llm_model"):
        # Stored generically as llm_model; maps onto the provider's model field.
        # An explicit gestora model PINS the call — the cost router skips it.
        config.claude_model = row["llm_model"]
        config.ollama_llm_model = row["llm_model"]
        config.mistral_model = row["llm_model"]
        config.grok_model = row["llm_model"]
        config.model_pinned = True
    if row.get("ollama_base_url"):
        config.ollama_base_url = row["ollama_base_url"]
    for enc_field, attr, label, env in (
        ("anthropic_api_key_enc", "anthropic_api_key", "Anthropic", "ANTHROPIC_API_KEY"),
        ("mistral_api_key_enc", "mistral_api_key", "Mistral", "MISTRAL_API_KEY"),
        ("xai_api_key_enc", "xai_api_key", "xAI", "XAI_API_KEY"),
    ):
        key = _decrypt_byo(row, enc_field, label, env, gestora_id)
        if key:
            setattr(config, attr, key)
    return model_router.apply(config, task)


def describe_model(
    gestora_id: Optional[str] = None, *, task: Optional[str] = None
) -> str:
    """``provider:model`` the given call would use — for trails/telemetry.

    Never raises (falls back to "?" on resolution errors): callers use this
    for observability (e.g. generation_reviews.model_note), never for control
    flow.
    """
    from services import model_router

    try:
        config = resolve_config(gestora_id, task=task)
        return f"{config.llm_provider}:{model_router.model_of(config)}"
    except Exception:  # noqa: BLE001 — observability must never break a call
        return "?"


def resolve_embedding_config(gestora_id: Optional[str] = None) -> EffectiveEmbeddingConfig:
    """Resolve the effective embedding config for an optional gestora.

    Same contract as :func:`resolve_config`: the gestora's override row wins
    field-by-field over global settings, and an unreadable override FAILS
    CLOSED to local Ollama — precedent text is the highest-volume content the
    platform sends to an embedding provider, so it never goes to a cloud
    default by accident.
    """
    settings = get_settings()
    config = EffectiveEmbeddingConfig(
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        openai_api_key=settings.openai_api_key,
        ollama_base_url=settings.ollama_base_url,
        ollama_embed_model=settings.ollama_embed_model,
        mistral_api_key=settings.mistral_api_key,
        mistral_embed_model=settings.mistral_embed_model,
        xai_api_key=settings.xai_api_key,
        grok_embed_model=settings.grok_embed_model,
    )
    if not gestora_id:
        return config

    try:
        row = _load_override_row(gestora_id)
    except Exception:  # noqa: BLE001 — resolution must never break a call
        logger.warning(
            "Could not load model config for gestora %s; failing CLOSED to "
            "local Ollama embeddings (cloud is opt-in and the opt-in is unreadable).",
            gestora_id,
        )
        return EffectiveEmbeddingConfig(
            embedding_provider="ollama",
            embedding_model=settings.embedding_model,
            openai_api_key="",
            ollama_base_url=settings.ollama_base_url,
            ollama_embed_model=settings.ollama_embed_model,
        )
    if row is None:
        return config

    if row.get("embedding_provider"):
        config.embedding_provider = row["embedding_provider"]
    if row.get("embedding_model"):
        # Stored generically; maps onto the selected provider's model field.
        config.embedding_model = row["embedding_model"]
        config.ollama_embed_model = row["embedding_model"]
        config.mistral_embed_model = row["embedding_model"]
        config.grok_embed_model = row["embedding_model"]
    if row.get("ollama_base_url"):
        config.ollama_base_url = row["ollama_base_url"]
    for enc_field, attr, label, env in (
        ("openai_api_key_enc", "openai_api_key", "OpenAI", "OPENAI_API_KEY"),
        ("mistral_api_key_enc", "mistral_api_key", "Mistral", "MISTRAL_API_KEY"),
        ("xai_api_key_enc", "xai_api_key", "xAI", "XAI_API_KEY"),
    ):
        key = _decrypt_byo(row, enc_field, label, env, gestora_id)
        if key:
            setattr(config, attr, key)
    return config


def complete(
    prompt: str,
    *,
    max_tokens: int = 8192,
    json_schema: Optional[dict[str, Any]] = None,
    system: Optional[str] = None,
    gestora_id: Optional[str] = None,
    task: Optional[str] = None,
    config_override: Optional[EffectiveLLMConfig] = None,
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
        gestora_id: When supplied and that gestora has a model-config override
            (account-security feature C), its provider/model/BYO-key win for this
            call; otherwise the global settings are used. Defaults to None →
            global behaviour, so existing callers are unaffected.
        task: Workload tag for the cost router (services/model_router.py) —
            light-tier tasks (critic, lessons, tabular, parse) may run on the
            provider's cheaper model. None → heavy tier (full model).

    Returns:
        The model's text response.

    Raises:
        ServiceNotConfiguredError: The selected provider is misconfigured or
            unreachable (API layers translate to HTTP 503).
    """
    # config_override: pre-resolved config for callers that must pin the
    # provider themselves (services/verifier.py cross-provider check). The
    # override is built FROM resolve_config, so privacy fail-closed semantics
    # are preserved upstream. Everyone else resolves per gestora as before.
    config = config_override or resolve_config(gestora_id, task=task)
    # Registry dispatch (services/providers): unknown providers raise
    # ServiceNotConfiguredError there (→ HTTP 503).
    from services import providers  # local import (optional-deps-free startup)

    return providers.get_llm(config.llm_provider).complete(
        prompt, max_tokens=max_tokens, json_schema=json_schema, system=system, config=config
    )


def stream(
    prompt: str,
    *,
    max_tokens: int = 2048,
    system: Optional[str] = None,
    gestora_id: Optional[str] = None,
    task: Optional[str] = None,
    config_override: Optional[EffectiveLLMConfig] = None,
) -> Iterator[str]:
    """Stream a plain-text completion as incremental deltas (chat Q&A).

    Mirrors :func:`complete` (same config resolution, same fail-closed
    privacy semantics, same ServiceNotConfiguredError contract) but yields
    text fragments as the provider produces them. Graceful degradation: a
    provider without a ``stream`` method degrades to ONE yield with the full
    complete() output — callers never need to know the difference.

    No JSON mode: structured output keeps using :func:`complete_json`.
    """
    config = config_override or resolve_config(gestora_id, task=task)
    from services import providers  # local import (optional-deps-free startup)

    provider = providers.get_llm(config.llm_provider)
    stream_fn = getattr(provider, "stream", None)
    if stream_fn is None:
        yield provider.complete(
            prompt, max_tokens=max_tokens, json_schema=None, system=system, config=config
        )
        return
    yield from stream_fn(prompt, max_tokens=max_tokens, system=system, config=config)


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
    gestora_id: Optional[str] = None,
    task: Optional[str] = None,
    config_override: Optional[EffectiveLLMConfig] = None,
) -> dict[str, Any]:
    """Generate JSON output and parse it into a dict.

    Calls :func:`complete` with ``json_schema=schema`` (native JSON mode on
    Ollama). If the first output is not valid JSON, performs ONE repair retry
    after stripping fences / extracting the first..last brace.

    ``gestora_id`` threads the per-gestora model-config override exactly like
    :func:`complete` (None → global behaviour).

    Raises:
        ServiceNotConfiguredError: Provider misconfigured or unreachable.
        ValueError: Output could not be parsed as JSON after the repair retry.
    """
    raw = complete(prompt, max_tokens=max_tokens, json_schema=schema, system=system, gestora_id=gestora_id, task=task, config_override=config_override)
    try:
        return _coerce_json(raw)
    except (ValueError, json.JSONDecodeError):
        logger.warning("LLM JSON output invalid; attempting one repair retry.")
    # Repair retry: re-ask, then coerce (fences/brace-slice). Propagate failure.
    raw = complete(prompt, max_tokens=max_tokens, json_schema=schema, system=system, gestora_id=gestora_id, task=task, config_override=config_override)
    return _coerce_json(raw)
