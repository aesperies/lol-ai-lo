"""Cost-aware model routing (services/model_router.py) + Mistral provider.

Covers: task→tier mapping, light-model swap per provider, gestora-pinned
models never re-routed, routing disabled flag, describe_model, the intake
parse light→heavy escalation, and the Mistral BYO key resolution.
"""
from __future__ import annotations

from typing import Any

import pytest

import config
from services import llm, model_router, providers, secrets
from tests.conftest import auth


@pytest.fixture(autouse=True)
def _light_models(monkeypatch: pytest.MonkeyPatch):
    """Give ollama a light model so routing is observable in tests."""
    monkeypatch.setattr(config.get_settings(), "ollama_light_model", "qwen2.5:7b-instruct")


class TestTiers:
    def test_heavy_tasks(self):
        assert model_router.tier_for("generate") == model_router.HEAVY
        assert model_router.tier_for("refine") == model_router.HEAVY
        assert model_router.tier_for(None) == model_router.HEAVY
        assert model_router.tier_for("unknown-task") == model_router.HEAVY

    def test_light_tasks(self):
        for task in ("parse", "critic", "critic_gate", "lessons", "tabular"):
            assert model_router.tier_for(task) == model_router.LIGHT


class TestRouting:
    def test_light_task_swaps_ollama_model(self):
        cfg = llm.resolve_config(task="critic")
        assert cfg.ollama_llm_model == "qwen2.5:7b-instruct"

    def test_heavy_task_keeps_standard_model(self):
        cfg = llm.resolve_config(task="generate")
        assert cfg.ollama_llm_model == config.get_settings().ollama_llm_model

    def test_untagged_call_keeps_standard_model(self):
        cfg = llm.resolve_config()
        assert cfg.ollama_llm_model == config.get_settings().ollama_llm_model

    def test_routing_disabled_is_noop(self, monkeypatch):
        monkeypatch.setattr(config.get_settings(), "model_routing_enabled", False)
        cfg = llm.resolve_config(task="critic")
        assert cfg.ollama_llm_model == config.get_settings().ollama_llm_model

    def test_empty_light_model_is_noop(self, monkeypatch):
        monkeypatch.setattr(config.get_settings(), "ollama_light_model", "")
        cfg = llm.resolve_config(task="critic")
        assert cfg.ollama_llm_model == config.get_settings().ollama_llm_model

    def test_gestora_pinned_model_never_rerouted(self, db, seed):
        db.insert(
            "gestora_model_config",
            {"gestora_id": seed["gestora_a"]["id"], "llm_model": "modelo-fijado"},
        )
        cfg = llm.resolve_config(seed["gestora_a"]["id"], task="critic")
        assert cfg.model_pinned is True
        assert cfg.ollama_llm_model == "modelo-fijado"

    def test_describe_model_reports_routed_model(self):
        assert llm.describe_model(task="critic") == "ollama:qwen2.5:7b-instruct"
        assert llm.describe_model(task="generate") == (
            f"ollama:{config.get_settings().ollama_llm_model}"
        )


class TestParseEscalation:
    def test_low_confidence_escalates_to_heavy(self, monkeypatch):
        from services import intake_parser

        calls: list[Any] = []

        def fake_complete_json(prompt, schema, *, max_tokens=8192, system=None,
                               gestora_id=None, task=None, **kwargs):
            calls.append(task)
            if task == "parse":
                return {"confidence": 0.3, "generation_ready": False}
            return {"confidence": 0.9, "generation_ready": True,
                    "doc_type_confirmed": "Acta de Reunión del Consejo"}

        monkeypatch.setattr(llm, "complete_json", fake_complete_json)
        parsed = intake_parser.parse_intake("Acta de Reunión del Consejo", "texto largo")
        assert calls == ["parse", "parse_escalated"]
        assert parsed["confidence"] == 0.9

    def test_no_escalation_when_tiers_equal(self, monkeypatch):
        """Zero-config (no light model): escalation would be a duplicate call."""
        monkeypatch.setattr(config.get_settings(), "ollama_light_model", "")
        from services import intake_parser

        calls: list[Any] = []

        def fake_complete_json(prompt, schema, *, max_tokens=8192, system=None,
                               gestora_id=None, task=None, **kwargs):
            calls.append(task)
            return {"confidence": 0.2}

        monkeypatch.setattr(llm, "complete_json", fake_complete_json)
        intake_parser.parse_intake("Acta de Reunión del Consejo", "texto largo")
        assert calls == ["parse"]

    def test_confident_parse_never_escalates(self, monkeypatch):
        from services import intake_parser

        calls: list[Any] = []

        def fake_complete_json(prompt, schema, *, max_tokens=8192, system=None,
                               gestora_id=None, task=None, **kwargs):
            calls.append(task)
            return {"confidence": 0.95, "generation_ready": True}

        monkeypatch.setattr(llm, "complete_json", fake_complete_json)
        intake_parser.parse_intake("Acta de Reunión del Consejo", "texto largo")
        assert calls == ["parse"]


class TestMistral:
    def test_provider_registered(self):
        assert providers.get_llm("mistral").name == "mistral"

    def test_unconfigured_readiness(self):
        assert providers.llm_configured("mistral", config.get_settings()) is False

    def test_byo_key_resolution(self, db, seed):
        db.insert(
            "gestora_model_config",
            {
                "gestora_id": seed["gestora_a"]["id"],
                "llm_provider": "mistral",
                "mistral_api_key_enc": secrets.encrypt("sk-mistral-byo"),
            },
        )
        cfg = llm.resolve_config(seed["gestora_a"]["id"], task="generate")
        assert cfg.llm_provider == "mistral"
        assert cfg.mistral_api_key == "sk-mistral-byo"
        assert cfg.mistral_model == config.get_settings().mistral_model

    def test_light_routing_on_mistral(self, db, seed):
        db.insert(
            "gestora_model_config",
            {"gestora_id": seed["gestora_a"]["id"], "llm_provider": "mistral"},
        )
        cfg = llm.resolve_config(seed["gestora_a"]["id"], task="critic")
        assert cfg.mistral_model == config.get_settings().mistral_light_model

    def test_model_config_api_roundtrips_mistral_key(self, client, seed, db):
        gestora_id = seed["gestora_a"]["id"]
        res = client.put(
            f"/api/admin/gestoras/{gestora_id}/model-config",
            headers=auth(seed["admin"]),
            json={"llm_provider": "mistral", "mistral_api_key": "sk-live-secreta"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["mistral_key_set"] is True
        assert "sk-live-secreta" not in res.text
        row = db.select("gestora_model_config", gestora_id=gestora_id)[-1]
        assert row["mistral_api_key_enc"] != "sk-live-secreta"
        assert secrets.decrypt(row["mistral_api_key_enc"]) == "sk-live-secreta"


class TestGrok:
    def test_provider_registered(self):
        assert providers.get_llm("grok").name == "grok"

    def test_unconfigured_readiness(self):
        assert providers.llm_configured("grok", config.get_settings()) is False

    def test_byo_key_resolution(self, db, seed):
        db.insert(
            "gestora_model_config",
            {
                "gestora_id": seed["gestora_a"]["id"],
                "llm_provider": "grok",
                "xai_api_key_enc": secrets.encrypt("xai-byo-key"),
            },
        )
        cfg = llm.resolve_config(seed["gestora_a"]["id"], task="generate")
        assert cfg.llm_provider == "grok"
        assert cfg.xai_api_key == "xai-byo-key"
        assert cfg.grok_model == config.get_settings().grok_model

    def test_light_routing_on_grok(self, db, seed):
        db.insert(
            "gestora_model_config",
            {"gestora_id": seed["gestora_a"]["id"], "llm_provider": "grok"},
        )
        cfg = llm.resolve_config(seed["gestora_a"]["id"], task="critic")
        assert cfg.grok_model == config.get_settings().grok_light_model

    def test_pinned_model_disables_routing(self, db, seed):
        db.insert(
            "gestora_model_config",
            {"gestora_id": seed["gestora_a"]["id"], "llm_provider": "grok", "llm_model": "grok-4.5"},
        )
        cfg = llm.resolve_config(seed["gestora_a"]["id"], task="critic")
        assert cfg.grok_model == "grok-4.5"  # pinned: the cost router must not touch it

    def test_model_config_api_roundtrips_xai_key(self, client, seed, db):
        gestora_id = seed["gestora_a"]["id"]
        res = client.put(
            f"/api/admin/gestoras/{gestora_id}/model-config",
            headers=auth(seed["admin"]),
            json={"llm_provider": "grok", "xai_api_key": "xai-live-secreta"},
        )
        assert res.status_code == 200
        body = res.json()
        assert body["xai_key_set"] is True
        assert "xai-live-secreta" not in res.text
        row = db.select("gestora_model_config", gestora_id=gestora_id)[-1]
        assert row["xai_api_key_enc"] != "xai-live-secreta"
        assert secrets.decrypt(row["xai_api_key_enc"]) == "xai-live-secreta"

    def test_complete_json_mode_and_error_mapping(self, monkeypatch):
        """GrokLLM: JSON nativo (response_format) y errores → 503 accionable."""
        from config import ServiceNotConfiguredError
        from services.providers.grok import GrokLLM

        captured: dict[str, Any] = {}

        class _Resp:
            status_code = 200

            @staticmethod
            def json():
                return {"choices": [{"message": {"content": '{"ok": true}'}}]}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["url"] = url
            captured["payload"] = json
            return _Resp()

        monkeypatch.setattr(llm.httpx, "post", fake_post)
        cfg = llm.EffectiveLLMConfig(
            llm_provider="grok", claude_model="", anthropic_api_key="",
            ollama_base_url="", ollama_llm_model="",
            xai_api_key="xai-test", grok_model="grok-4.5",
        )
        out = GrokLLM().complete(
            "hola", max_tokens=64, json_schema={"type": "object"}, system=None, config=cfg
        )
        assert out == '{"ok": true}'
        assert captured["url"].startswith("https://api.x.ai/")
        assert captured["payload"]["response_format"] == {"type": "json_object"}
        assert captured["payload"]["model"] == "grok-4.5"

        # Sin key -> 503 accionable, nunca una llamada de red.
        cfg.xai_api_key = ""
        with pytest.raises(ServiceNotConfiguredError):
            GrokLLM().complete("hola", max_tokens=64, json_schema=None, system=None, config=cfg)


class TestGrokEmbeddings:
    @pytest.fixture(autouse=True)
    def _reset_discovery(self, monkeypatch):
        from services.providers import grok
        monkeypatch.setattr(grok, "_discovered_embed_model", None)

    def _config(self, **overrides):
        defaults = dict(
            embedding_provider="grok", embedding_model="", openai_api_key="",
            ollama_base_url="", ollama_embed_model="",
            xai_api_key="xai-test", grok_embed_model="grok-embed-x",
        )
        defaults.update(overrides)
        return llm.EffectiveEmbeddingConfig(**defaults)

    def test_registered(self):
        assert providers.get_embedding("grok").name == "grok"

    def test_embed_requests_1024_dims(self, monkeypatch):
        from services.providers.grok import GrokEmbeddings

        captured: dict[str, Any] = {}

        class _Resp:
            status_code = 200
            text = ""

            @staticmethod
            def json():
                return {"data": [
                    {"index": 1, "embedding": [0.2] * 1024},
                    {"index": 0, "embedding": [0.1] * 1024},
                ]}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["url"] = url
            captured["payload"] = json
            return _Resp()

        monkeypatch.setattr(llm.httpx, "post", fake_post)
        vectors = GrokEmbeddings().embed(["uno", "dos"], self._config())
        assert captured["url"] == "https://api.x.ai/v1/embeddings"
        assert captured["payload"]["model"] == "grok-embed-x"
        assert captured["payload"]["dimensions"] == 1024
        # data llega desordenado; se reordena por index
        assert vectors[0][0] == 0.1 and vectors[1][0] == 0.2

    def test_autodiscovers_model_when_unset(self, monkeypatch):
        from services.providers import grok

        class _ModelsResp:
            status_code = 200

            @staticmethod
            def json():
                return {"models": [{"id": "grok-embed-auto", "aliases": []}]}

        class _EmbedResp:
            status_code = 200
            text = ""

            @staticmethod
            def json():
                return {"data": [{"index": 0, "embedding": [0.5] * 1024}]}

        monkeypatch.setattr(llm.httpx, "get", lambda url, headers=None, timeout=None: _ModelsResp())
        captured: dict[str, Any] = {}

        def fake_post(url, json=None, headers=None, timeout=None):
            captured["payload"] = json
            return _EmbedResp()

        monkeypatch.setattr(llm.httpx, "post", fake_post)
        cfg = self._config(grok_embed_model="")
        vectors = grok.GrokEmbeddings().embed(["hola"], cfg)
        assert vectors is not None
        assert captured["payload"]["model"] == "grok-embed-auto"
        # resolved_embed_model refleja el modelo descubierto (clave para que
        # el índice y la query usen el mismo embed_model)
        assert cfg.resolved_embed_model == "grok-embed-auto"

    def test_degrades_to_none_on_failure(self, monkeypatch):
        from services.providers.grok import GrokEmbeddings

        def fake_post(url, json=None, headers=None, timeout=None):
            raise llm.httpx.ConnectError("down")

        monkeypatch.setattr(llm.httpx, "post", fake_post)
        assert GrokEmbeddings().embed(["hola"], self._config()) is None
        # Sin key: tampoco llama a la red.
        assert GrokEmbeddings().embed(["hola"], self._config(xai_api_key="")) is None
