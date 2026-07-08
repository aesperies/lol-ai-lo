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
