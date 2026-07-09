"""Provider registry — the single dispatch point for LLM and embedding backends.

To add a provider: write one module in this package (see base.py for the
protocols) and register an instance below. services/llm.py, services/rag.py
and config.py all resolve providers from here; none of them needs editing.
"""
from __future__ import annotations

from typing import Any, Optional

from config import ServiceNotConfiguredError
from services.providers.anthropic import AnthropicLLM
from services.providers.base import EmbeddingProvider, LLMProvider
from services.providers.mistral import MistralEmbeddings, MistralLLM
from services.providers.ollama import OllamaEmbeddings, OllamaLLM
from services.providers.openai import OpenAIEmbeddings

_LLM_PROVIDERS: dict[str, LLMProvider] = {
    provider.name: provider for provider in (OllamaLLM(), AnthropicLLM(), MistralLLM())
}

_EMBEDDING_PROVIDERS: dict[str, EmbeddingProvider] = {
    provider.name: provider
    for provider in (OllamaEmbeddings(), OpenAIEmbeddings(), MistralEmbeddings())
}


def get_llm(name: str) -> LLMProvider:
    """The registered LLM provider, or ServiceNotConfiguredError (→ HTTP 503)."""
    provider = _LLM_PROVIDERS.get(name)
    if provider is None:
        raise ServiceNotConfiguredError(
            name or "llm",
            f"Unknown LLM_PROVIDER; expected one of {sorted(_LLM_PROVIDERS)}.",
        )
    return provider


def get_embedding(name: str) -> Optional[EmbeddingProvider]:
    """The registered embedding provider, or None (RAG degrades to
    weight/recency ranking on unknown providers rather than failing)."""
    return _EMBEDDING_PROVIDERS.get(name)


def llm_configured(name: str, settings: Any) -> bool:
    """Whether the named text-generation provider is usable (readiness flag)."""
    provider = _LLM_PROVIDERS.get(name)
    return provider.is_configured(settings) if provider else False


def embeddings_configured(name: str, settings: Any) -> bool:
    """Whether the named embedding provider is usable (readiness flag)."""
    provider = _EMBEDDING_PROVIDERS.get(name)
    return provider.is_configured(settings) if provider else False
