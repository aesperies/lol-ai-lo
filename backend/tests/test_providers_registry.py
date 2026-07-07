"""Provider registry contract (services/providers).

Adding a provider = one module + one registry entry; these tests pin the
dispatch semantics the rest of the codebase relies on.
"""
from __future__ import annotations

import pytest

import config
from config import ServiceNotConfiguredError
from services import providers


@pytest.fixture()
def settings():
    return config.get_settings()


def test_known_llm_providers_registered() -> None:
    assert providers.get_llm("ollama").name == "ollama"
    assert providers.get_llm("anthropic").name == "anthropic"


def test_unknown_llm_provider_raises_503_error() -> None:
    with pytest.raises(ServiceNotConfiguredError):
        providers.get_llm("gpt-nonexistent")


def test_unknown_embedding_provider_degrades_to_none() -> None:
    """RAG must keep working (weight/recency ranking) on a bad provider name."""
    assert providers.get_embedding("nonexistent") is None
    assert providers.get_embedding("ollama") is not None
    assert providers.get_embedding("openai") is not None


def test_readiness_flags_delegate_to_providers(settings, monkeypatch) -> None:
    # Local providers need no credential.
    assert providers.llm_configured("ollama", settings) is True
    assert providers.embeddings_configured("ollama", settings) is True
    # Cloud providers require their key.
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    assert providers.llm_configured("anthropic", settings) is False
    assert providers.embeddings_configured("openai", settings) is False
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-x")
    monkeypatch.setattr(settings, "openai_api_key", "sk-y")
    assert providers.llm_configured("anthropic", settings) is True
    assert providers.embeddings_configured("openai", settings) is True
    # Unknown names are never "configured".
    assert providers.llm_configured("nonexistent", settings) is False


def test_settings_properties_route_through_registry(settings, monkeypatch) -> None:
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    assert settings.llm_configured is False
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-x")
    assert settings.llm_configured is True
