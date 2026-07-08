"""Tests for the LLM provider seam (services/llm.py).

All network is mocked (no real Ollama/Anthropic). Covers provider selection,
the Ollama HTTP path, JSON mode + repair retry, the lazy Anthropic path,
unreachable-provider -> ServiceNotConfiguredError, and transient-error retry.
"""
from __future__ import annotations

import json
import sys
import types

import httpx
import pytest

import config
from services import llm, rag


@pytest.fixture()
def settings():
    """Fresh settings object whose attributes can be monkeypatched per test."""
    config.get_settings.cache_clear()
    s = config.get_settings()
    return s


def _ollama_response(content: str, status_code: int = 200) -> httpx.Response:
    return httpx.Response(
        status_code=status_code,
        json={"message": {"role": "assistant", "content": content}},
        request=httpx.Request("POST", "http://localhost:11434/api/chat"),
    )


# ---------------------------------------------------------------------------
# Provider selection
# ---------------------------------------------------------------------------

def test_default_provider_is_ollama(settings):
    assert settings.llm_provider == "ollama"
    assert settings.llm_configured is True


def test_unknown_provider_raises(settings, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "frobnicate")
    with pytest.raises(config.ServiceNotConfiguredError):
        llm.complete("hi")


# ---------------------------------------------------------------------------
# Ollama path (httpx mocked)
# ---------------------------------------------------------------------------

def test_ollama_complete_plain_text(settings, monkeypatch):
    captured: dict = {}

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["payload"] = json
        return _ollama_response("Hola mundo")

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    out = llm.complete("Di hola", max_tokens=128)

    assert out == "Hola mundo"
    assert captured["url"].endswith("/api/chat")
    assert captured["payload"]["stream"] is False
    assert captured["payload"]["model"] == settings.ollama_llm_model
    assert captured["payload"]["options"]["num_predict"] == 128
    # No json_schema -> no JSON mode.
    assert "format" not in captured["payload"]


def test_ollama_json_mode_sets_format_and_parses(settings, monkeypatch):
    captured: dict = {}
    schema = {"type": "object", "properties": {"x": {"type": "number"}}}

    def fake_post(url, json=None, timeout=None):
        captured["payload"] = json
        return _ollama_response(json_lib_dumps({"x": 42}))

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    out = llm.complete_json("give me x", schema)

    assert out == {"x": 42}
    assert captured["payload"]["format"] == "json"
    # Schema is injected into the system message so the model knows the shape.
    system_msg = captured["payload"]["messages"][0]
    assert system_msg["role"] == "system"
    assert '"x"' in system_msg["content"]


def test_complete_json_repair_retry_on_fenced_output(settings, monkeypatch):
    """First call returns fenced/garbage JSON; one repair retry succeeds."""
    calls = {"n": 0}

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _ollama_response("Here you go:\n```json\n{\"x\": 7}\n```")
        return _ollama_response('{"x": 7}')

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    # The first (fenced) output is actually repairable by _coerce_json, so it
    # parses on the FIRST call without a second network round-trip.
    out = llm.complete_json("give x", {"type": "object"})
    assert out == {"x": 7}
    assert calls["n"] == 1


def test_complete_json_repair_retry_on_garbage(settings, monkeypatch):
    """First call returns prose with an embedded object; brace-slice recovers it
    without a second round-trip (still valid via _coerce_json)."""
    calls = {"n": 0}

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        return _ollama_response("Sure! {\"x\": 9} hope that helps")

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    out = llm.complete_json("give x", {"type": "object"})
    assert out == {"x": 9}
    assert calls["n"] == 1


def test_complete_json_second_call_repairs_unparseable_first(settings, monkeypatch):
    """First output has NO JSON at all -> repair retry re-asks the provider."""
    outputs = ["totally not json at all", '{"x": 1}']
    calls = {"n": 0}

    def fake_post(url, json=None, timeout=None):
        out = outputs[calls["n"]]
        calls["n"] += 1
        return _ollama_response(out)

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    out = llm.complete_json("give x", {"type": "object"})
    assert out == {"x": 1}
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# Unreachable provider / transient retry
# ---------------------------------------------------------------------------

def test_ollama_unreachable_raises_service_not_configured(settings, monkeypatch):
    def fake_post(url, json=None, timeout=None):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    with pytest.raises(config.ServiceNotConfiguredError) as exc:
        llm.complete("hi")
    assert "ollama" in str(exc.value).lower()


def test_ollama_non_200_raises_service_not_configured(settings, monkeypatch):
    def fake_post(url, json=None, timeout=None):
        return _ollama_response("model not found", status_code=404)

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    with pytest.raises(config.ServiceNotConfiguredError):
        llm.complete("hi")


def test_transient_error_then_success(settings, monkeypatch):
    """First attempt raises a transient network error; the retry succeeds."""
    monkeypatch.setattr(settings, "llm_retry_attempts", 2)
    calls = {"n": 0}

    def fake_post(url, json=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadError("temporary blip")
        return _ollama_response("recovered")

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    out = llm.complete("hi")
    assert out == "recovered"
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# Anthropic path (lazy import monkeypatched)
# ---------------------------------------------------------------------------

def _install_fake_anthropic(monkeypatch, capture: dict, reply: str = "claude says hi"):
    """Install a fake ``anthropic`` module into sys.modules for the lazy import."""

    class _Block:
        type = "text"
        text = reply

    class _Resp:
        content = [_Block()]

    class _Messages:
        def create(self, **kwargs):
            capture["kwargs"] = kwargs
            return _Resp()

    class _Client:
        def __init__(self, api_key=None):
            capture["api_key"] = api_key
            self.messages = _Messages()

    fake = types.ModuleType("anthropic")
    fake.Anthropic = _Client
    fake.APIConnectionError = type("APIConnectionError", (Exception,), {})
    fake.BadRequestError = type("BadRequestError", (Exception,), {})
    fake.AuthenticationError = type("AuthenticationError", (Exception,), {})
    fake.RateLimitError = type("RateLimitError", (Exception,), {})
    monkeypatch.setitem(sys.modules, "anthropic", fake)
    return fake


def test_anthropic_path(settings, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    capture: dict = {}
    _install_fake_anthropic(monkeypatch, capture)

    out = llm.complete("hello", system="be terse")
    assert out == "claude says hi"
    assert capture["api_key"] == "test-key"
    assert capture["kwargs"]["model"] == settings.claude_model
    assert capture["kwargs"]["system"] == "be terse"


def test_anthropic_unconfigured_raises(settings, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
    with pytest.raises(config.ServiceNotConfiguredError) as exc:
        llm.complete("hi")
    assert "anthropic" in str(exc.value).lower()


def test_anthropic_json_mode_injects_schema_into_system(settings, monkeypatch):
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    capture: dict = {}
    _install_fake_anthropic(monkeypatch, capture, reply='{"ok": true}')

    out = llm.complete_json(
        "give ok", {"type": "object", "properties": {"ok": {"type": "boolean"}}}
    )
    assert out == {"ok": True}
    # JSON shape is injected into the system prompt (Anthropic has no JSON mode).
    assert '"ok"' in capture["kwargs"]["system"]


def test_anthropic_no_credit_raises_actionable_503(settings, monkeypatch):
    """Cuenta sin crédito -> ServiceNotConfiguredError con mensaje accionable
    (regresión: antes burbujeaba como 500 genérico)."""
    monkeypatch.setattr(settings, "llm_provider", "anthropic")
    monkeypatch.setattr(settings, "anthropic_api_key", "test-key")
    capture: dict = {}
    fake = _install_fake_anthropic(monkeypatch, capture)

    def _boom(**kwargs):
        raise fake.BadRequestError(
            "Your credit balance is too low to access the Anthropic API."
        )

    fake.Anthropic(api_key="x").messages.create = _boom  # sanity del fake
    class _Messages:
        def create(self, **kwargs):
            raise fake.BadRequestError(
                "Your credit balance is too low to access the Anthropic API."
            )
    class _Client:
        def __init__(self, api_key=None):
            self.messages = _Messages()
    fake.Anthropic = _Client

    with pytest.raises(config.ServiceNotConfiguredError) as exc:
        llm.complete("hi")
    assert "crédito" in str(exc.value)


def test_rank_prefers_request_language_when_degraded(settings):
    """Ranking degradado (sin embeddings): una petición 'es' prefiere el modelo
    español aunque el inglés sea más reciente (regresión del NDA US)."""
    def cand(lang, activated):
        return rag.Candidate(
            precedent={"language": lang},
            version={"id": lang, "activated_at": activated},
            weight=1.0,
            text=f"texto {lang}",
            is_generation_base=True,
        )

    es = cand("es", "2026-01-01T00:00:00+00:00")
    en = cand("en", "2026-06-01T00:00:00+00:00")  # más reciente
    embed_config = llm.resolve_embedding_config()  # conftest corta la red -> degradado

    ranked = rag._rank("query", [es, en], embed_config, language="es")
    assert ranked[0].precedent["language"] == "es"
    # Sin idioma en la petición: manda la recencia (comportamiento anterior).
    ranked = rag._rank("query", [es, en], embed_config, language="")
    assert ranked[0].precedent["language"] == "en"


# ---------------------------------------------------------------------------
# RAG embeddings provider (services/rag.py)
# ---------------------------------------------------------------------------

def test_rag_embed_ollama_path(settings, monkeypatch):
    assert settings.embedding_provider == "ollama"
    calls: list[str] = []

    def fake_post(url, json=None, timeout=None):
        calls.append(json["prompt"])
        assert url.endswith("/api/embeddings")
        assert json["model"] == settings.ollama_embed_model
        return httpx.Response(
            200,
            json={"embedding": [0.1, 0.2, 0.3]},
            request=httpx.Request("POST", url),
        )

    # llm.httpx IS the httpx module, shared with rag.py's lazy import.
    monkeypatch.setattr(llm.httpx, "post", fake_post)
    vectors = rag._embed(["hello", "world"], llm.resolve_embedding_config())
    assert vectors == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert calls == ["hello", "world"]


def test_rag_embed_degrades_to_none_when_unreachable(settings, monkeypatch):
    """Unreachable embeddings -> None so retrieval falls back to weight/recency
    (never a wider candidate pool — isolation invariant)."""

    def fake_post(url, json=None, timeout=None):
        raise httpx.ConnectError("no daemon")

    monkeypatch.setattr(llm.httpx, "post", fake_post)
    assert rag._embed(["x"], llm.resolve_embedding_config()) is None
    assert rag._semantic_scores("q", [], llm.resolve_embedding_config()) is None


# small helper to avoid shadowing the `json` param name in fake_post closures
def json_lib_dumps(obj) -> str:
    return json.dumps(obj)
