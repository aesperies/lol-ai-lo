"""Structural guardrails added by the refactor (Fase 1).

1. Tenant-scope choke point (services/db.py): a select on a tenant table with
   no tenant/record scope raises TenantScopeError instead of silently reading
   across gestoras (the Supabase service-role key bypasses RLS, so this layer
   is the only enforcement point).

2. Local-first fail-closed (services/llm.py): when a gestora's model-config
   override cannot be read, LLM and embedding resolution degrade to LOCAL
   Ollama — never to a cloud global default (cloud is opt-in; an unreadable
   opt-in means NO).

3. Per-gestora embedding override (services/llm.py + services/rag.py): the
   gestora_model_config embedding_* columns are honored, mirroring the LLM
   override.
"""
from __future__ import annotations

import pytest

import config
from services import db as dbmod
from services import llm, secrets


@pytest.fixture()
def settings():
    """The live Settings singleton; monkeypatch.setattr restores attributes."""
    return config.get_settings()


# ---------------------------------------------------------------------------
# 1. Tenant-scope choke point
# ---------------------------------------------------------------------------


class TestTenantScopeChokePoint:
    def test_unfiltered_select_on_tenant_table_raises(self, db) -> None:
        with pytest.raises(dbmod.TenantScopeError):
            db.select("requests")

    def test_attribute_only_filter_on_tenant_table_raises(self, db) -> None:
        """status/role/period filters do not pin a tenant — still an error."""
        with pytest.raises(dbmod.TenantScopeError):
            db.select("requests", status="delivered")
        with pytest.raises(dbmod.TenantScopeError):
            db.select("users", role="client")
        with pytest.raises(dbmod.TenantScopeError):
            db.select("usage_events", billing_period="2026-07")

    def test_gestora_filter_passes(self, db) -> None:
        assert db.select("requests", gestora_id="g1") == []

    def test_explicit_none_gestora_targets_global_pool(self, db) -> None:
        """gestora_id=None is a deliberate choice (global template levels)."""
        db.insert("precedents", {"gestora_id": None, "doc_type": "acta"})
        db.insert("precedents", {"gestora_id": "g1", "doc_type": "acta"})
        rows = db.select("precedents", gestora_id=None)
        assert len(rows) == 1 and rows[0]["gestora_id"] is None

    def test_record_id_filter_passes(self, db) -> None:
        """Parent/record-id filters (request_id, user_id, ...) pin the tenant."""
        assert db.select("requests", user_id="u1") == []
        assert db.select("request_shares", request_id="r1") == []

    def test_unscoped_select_is_the_explicit_escape_hatch(self, db) -> None:
        db.insert("requests", {"status": "delivered", "fund_id": "f1"})
        assert len(db.unscoped_select("requests", status="delivered")) == 1

    def test_non_tenant_tables_are_exempt(self, db) -> None:
        db.insert("gestoras", {"name": "Alpha"})
        assert len(db.select("gestoras")) == 1


# ---------------------------------------------------------------------------
# 2. Local-first fail-closed resolution
# ---------------------------------------------------------------------------


def _break_db(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom() -> None:
        raise RuntimeError("db unreachable")

    monkeypatch.setattr(dbmod, "get_db", _boom)


class TestFailClosedToLocal:
    def test_llm_config_fails_closed_to_ollama_when_override_unreadable(
        self, settings, monkeypatch
    ) -> None:
        """Global default = cloud + unreadable gestora override -> LOCAL, no key."""
        monkeypatch.setattr(settings, "llm_provider", "anthropic")
        monkeypatch.setattr(settings, "anthropic_api_key", "sk-global")
        _break_db(monkeypatch)

        config = llm.resolve_config("gestora-1")
        assert config.llm_provider == "ollama"
        assert config.anthropic_api_key == ""

    def test_embedding_config_fails_closed_to_ollama_when_override_unreadable(
        self, settings, monkeypatch
    ) -> None:
        monkeypatch.setattr(settings, "embedding_provider", "openai")
        monkeypatch.setattr(settings, "openai_api_key", "sk-global")
        _break_db(monkeypatch)

        config = llm.resolve_embedding_config("gestora-1")
        assert config.embedding_provider == "ollama"
        assert config.openai_api_key == ""

    def test_no_gestora_still_uses_global_settings(self, settings, monkeypatch) -> None:
        """Platform-level calls (no gestora in play) keep the global default."""
        monkeypatch.setattr(settings, "llm_provider", "anthropic")
        _break_db(monkeypatch)  # irrelevant: no override lookup without gestora
        assert llm.resolve_config().llm_provider == "anthropic"

    def test_gestora_without_override_row_uses_global_settings(self, db, settings, monkeypatch) -> None:
        monkeypatch.setattr(settings, "llm_provider", "anthropic")
        monkeypatch.setattr(settings, "anthropic_api_key", "sk-global")
        config = llm.resolve_config("gestora-1")
        assert config.llm_provider == "anthropic"
        assert config.anthropic_api_key == "sk-global"


# ---------------------------------------------------------------------------
# 3. Per-gestora embedding override
# ---------------------------------------------------------------------------


class TestEmbeddingOverride:
    def test_gestora_embedding_override_wins_over_global(self, db, settings) -> None:
        db.insert(
            "gestora_model_config",
            {
                "gestora_id": "gestora-1",
                "embedding_provider": "openai",
                "embedding_model": "text-embedding-3-large",
                "openai_api_key_enc": secrets.encrypt("sk-byo-openai"),
            },
        )
        config = llm.resolve_embedding_config("gestora-1")
        assert config.embedding_provider == "openai"
        assert config.embedding_model == "text-embedding-3-large"
        assert config.openai_api_key == "sk-byo-openai"
        # Global stays untouched for other gestoras.
        other = llm.resolve_embedding_config("gestora-2")
        assert other.embedding_provider == settings.embedding_provider

    def test_undecryptable_byo_key_falls_back_to_global_key(self, db, settings, monkeypatch) -> None:
        monkeypatch.setattr(settings, "openai_api_key", "sk-global")
        db.insert(
            "gestora_model_config",
            {
                "gestora_id": "gestora-1",
                "embedding_provider": "openai",
                "openai_api_key_enc": "not-real-ciphertext",
            },
        )
        config = llm.resolve_embedding_config("gestora-1")
        assert config.openai_api_key == "sk-global"

    def test_embedding_model_override_maps_to_ollama_model_too(self, db) -> None:
        db.insert(
            "gestora_model_config",
            {"gestora_id": "gestora-1", "embedding_model": "nomic-embed-text"},
        )
        config = llm.resolve_embedding_config("gestora-1")
        assert config.ollama_embed_model == "nomic-embed-text"
