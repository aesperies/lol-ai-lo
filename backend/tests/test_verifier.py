"""Verificador cruzado anti-alucinaciones (services/verifier.py, 020).

El conftest fija VERIFY_ENABLED=false para toda la suite (el borrador fake no
es fiel al intake); estos tests lo activan por-test, mismo patrón que el rate
limiter.
"""
from __future__ import annotations

from typing import Any

import pytest

import config
from config import ServiceNotConfiguredError
from services import db as dbmod
from services import llm, verifier
from tests.conftest import auth, seed_precedent

DRAFT = (
    "CONTRATO DE CONFIDENCIALIDAD\n"
    "Entre Alfa Fund I, FCR y Acme Ventures GmbH.\n"
    "Importe comprometido: 500.000 euros.\n"
    "Fecha de la reunión: 15 de julio de 2026.\n"
    "El presente contrato se rige por el derecho español."
)

PARAMS = {
    "parties": [
        {"role": "fondo", "name": "Alfa Fund I, FCR"},
        {"role": "contraparte", "name": "Acme Ventures GmbH"},
    ],
    "key_terms": [{"field": "importe", "value": "500.000 EUR"}],
    "key_dates": [{"label": "fecha de reunión", "date": "2026-07-15"}],
    "jurisdiction": "España",
    "governing_law": "Derecho español",
}


@pytest.fixture()
def verify_on(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(config.get_settings(), "verify_enabled", True)


# ---------------------------------------------------------------------------
# Capa 1 — determinista
# ---------------------------------------------------------------------------

class TestDeterministic:
    def test_clean_draft_has_no_findings(self):
        assert verifier.deterministic_findings(DRAFT, PARAMS, "es") == []

    def test_missing_party_is_critical(self):
        params = {**PARAMS, "parties": PARAMS["parties"] + [
            {"role": "avalista", "name": "Empresa Fantasma SL"},
        ]}
        findings = verifier.deterministic_findings(DRAFT, params, "es")
        assert len(findings) == 1
        assert findings[0]["severity"] == "critical"
        assert "Empresa Fantasma SL" in findings[0]["problem"]

    def test_amount_mismatch_is_critical(self):
        params = {**PARAMS, "key_terms": [{"field": "importe", "value": "600.000 EUR"}]}
        findings = verifier.deterministic_findings(DRAFT, params, "es")
        assert len(findings) == 1
        assert "600.000" in findings[0]["problem"]

    def test_amount_separator_variants_match(self):
        # '500,000' y '500 000' colapsan a los mismos dígitos que '500.000'.
        for value in ("500,000 EUR", "500 000 €", "EUR 500000"):
            params = {**PARAMS, "key_terms": [{"field": "importe", "value": value}]}
            assert verifier.deterministic_findings(DRAFT, params, "es") == []

    def test_date_renderings_match_spanish_and_numeric(self):
        for draft_date in ("15/07/2026", "2026-07-15", "15 de julio de 2026"):
            draft = DRAFT.replace("15 de julio de 2026", draft_date)
            assert verifier.deterministic_findings(draft, PARAMS, "es") == []

    def test_missing_date_is_critical(self):
        draft = DRAFT.replace("Fecha de la reunión: 15 de julio de 2026.\n", "")
        findings = verifier.deterministic_findings(draft, PARAMS, "es")
        assert len(findings) == 1
        assert findings[0]["category"] == "dato_inventado"

    def test_short_names_and_textual_terms_are_skipped(self):
        params = {
            "parties": [{"role": "x", "name": "AB"}],  # <4 chars: sin cotejo
            "key_terms": [{"field": "regimen", "value": "confidencialidad mutua"}],
        }
        assert verifier.deterministic_findings("otro texto", params, "es") == []


# ---------------------------------------------------------------------------
# Selección de proveedor (privacidad)
# ---------------------------------------------------------------------------

class TestResolveVerifyConfig:
    def test_disabled_returns_none(self):
        assert verifier.resolve_verify_config(None) is None  # VERIFY_ENABLED=false

    def test_platform_default_crosses_provider(self, db, seed, verify_on, monkeypatch):
        # Drafter global anthropic; grok configurado → el auto cruza a grok.
        settings = config.get_settings()
        monkeypatch.setattr(settings, "llm_provider", "anthropic")
        monkeypatch.setattr(settings, "anthropic_api_key", "sk-a")
        monkeypatch.setattr(settings, "xai_api_key", "xai-b")
        cfg = verifier.resolve_verify_config(seed["gestora_a"]["id"])
        assert cfg is not None and cfg.llm_provider == "grok"
        # Tier light del router para la tarea verify.
        assert cfg.grok_model == settings.grok_light_model

    def test_explicit_gestora_provider_never_crosses(self, db, seed, verify_on, monkeypatch):
        settings = config.get_settings()
        monkeypatch.setattr(settings, "anthropic_api_key", "sk-a")
        monkeypatch.setattr(settings, "xai_api_key", "xai-b")
        db.insert(
            "gestora_model_config",
            {"gestora_id": seed["gestora_a"]["id"], "llm_provider": "anthropic"},
        )
        cfg = verifier.resolve_verify_config(seed["gestora_a"]["id"])
        assert cfg is not None and cfg.llm_provider == "anthropic"

    def test_gestora_verify_provider_pins(self, db, seed, verify_on, monkeypatch):
        monkeypatch.setattr(config.get_settings(), "mistral_api_key", "sk-m")
        db.insert(
            "gestora_model_config",
            {"gestora_id": seed["gestora_a"]["id"], "llm_provider": "anthropic",
             "verify_provider": "mistral"},
        )
        cfg = verifier.resolve_verify_config(seed["gestora_a"]["id"])
        assert cfg is not None and cfg.llm_provider == "mistral"

    def test_gestora_none_disables(self, db, seed, verify_on):
        db.insert(
            "gestora_model_config",
            {"gestora_id": seed["gestora_a"]["id"], "verify_provider": "none"},
        )
        assert verifier.resolve_verify_config(seed["gestora_a"]["id"]) is None

    def test_unreadable_config_fails_closed_to_local(self, db, seed, verify_on, monkeypatch):
        def boom(_gestora_id):
            raise RuntimeError("db down")

        monkeypatch.setattr(llm, "_load_override_row", boom)
        cfg = verifier.resolve_verify_config(seed["gestora_a"]["id"])
        assert cfg is not None and cfg.llm_provider == "ollama"


# ---------------------------------------------------------------------------
# Capa 2 — grounding de hallazgos LLM
# ---------------------------------------------------------------------------

class TestLLMGrounding:
    def test_hallucinated_quote_is_dropped_and_literal_kept(self):
        raw = [
            {"category": "contradiccion_interna", "severity": "critical",
             "problem": "Se contradice", "quote": "Importe comprometido: 500.000 euros."},
            {"category": "referencia_legal_dudosa", "severity": "critical",
             "problem": "Cita inventada", "quote": "artículo 999 de la Ley Imaginaria"},
            {"category": "categoria_desconocida", "severity": "critical",
             "problem": "x", "quote": "Importe comprometido: 500.000 euros."},
        ]
        grounded = verifier._ground_llm_findings(raw, DRAFT)
        assert len(grounded) == 1
        assert grounded[0]["category"] == "contradiccion_interna"
        assert grounded[0]["layer"] == "llm"


# ---------------------------------------------------------------------------
# run(): persistencia + forzado de Exit B + degradación
# ---------------------------------------------------------------------------

class TestRun:
    def test_critical_finding_persists_and_forces_counsel(self, db, seed, verify_on, monkeypatch):
        # Capa LLM saltada limpiamente (proveedor caído — conftest sin red).
        request = db.insert("requests", {"fund_id": seed["fund_a"]["id"], "status": "generating"})
        params = {**PARAMS, "parties": PARAMS["parties"] + [
            {"role": "avalista", "name": "Empresa Fantasma SL"},
        ]}
        result = verifier.run(
            db, request_id=request["id"], iteration=0,
            gestora_id=seed["gestora_a"]["id"], draft_text=DRAFT,
            params=params, language="es",
        )
        assert result["forced_counsel"] is True
        assert result["critical_count"] == 1
        assert result["llm_ran"] is False  # ollama inalcanzable → capa 2 saltada
        rows = db.select("verifications", request_id=request["id"])
        assert len(rows) == 1 and rows[0]["critical_count"] == 1

    def test_refinement_downgrades_deterministic_to_warning(self, db, seed, verify_on):
        request = db.insert("requests", {"fund_id": seed["fund_a"]["id"], "status": "generating"})
        params = {**PARAMS, "key_terms": [{"field": "importe", "value": "999.999 EUR"}]}
        result = verifier.run(
            db, request_id=request["id"], iteration=1,
            gestora_id=seed["gestora_a"]["id"], draft_text=DRAFT,
            params=params, language="es", deterministic_severity="warning",
        )
        assert result["forced_counsel"] is False
        assert result["critical_count"] == 0
        assert result["findings"][0]["severity"] == "warning"

    def test_llm_layer_findings_can_force_counsel(self, db, seed, verify_on, monkeypatch):
        def fake_complete_json(prompt, schema, **kwargs):
            return {"findings": [{
                "category": "referencia_legal_dudosa", "severity": "critical",
                "problem": "La norma citada no existe",
                "quote": "el derecho español",
            }]}

        monkeypatch.setattr(llm, "complete_json", fake_complete_json)
        request = db.insert("requests", {"fund_id": seed["fund_a"]["id"], "status": "generating"})
        result = verifier.run(
            db, request_id=request["id"], iteration=0,
            gestora_id=seed["gestora_a"]["id"], draft_text=DRAFT,
            params=PARAMS, language="es",
        )
        assert result["llm_ran"] is True
        assert result["forced_counsel"] is True
        assert result["findings"][0]["layer"] == "llm"

    def test_disabled_is_a_noop(self, db, seed):
        request = db.insert("requests", {"fund_id": seed["fund_a"]["id"], "status": "generating"})
        result = verifier.run(
            db, request_id=request["id"], iteration=0,
            gestora_id=seed["gestora_a"]["id"], draft_text="x", params=PARAMS, language="es",
        )
        assert result == {"findings": [], "critical_count": 0, "forced_counsel": False,
                          "provider": None, "model": None, "llm_ran": False}
        assert db.select("verifications", request_id=request["id"]) == []


# ---------------------------------------------------------------------------
# Integración: pipeline completo + endpoint
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_pipeline_forces_exit_b_and_endpoint_exposes_findings(
        self, wf, db, seed, monkeypatch
    ):
        monkeypatch.setattr(config.get_settings(), "verify_enabled", True)
        # El fake draft del conftest no contiene esta parte → crítico determinista.
        request_id = wf.create()
        assert wf.parse(request_id).status_code == 200
        edited = wf.client.get(
            f"/api/requests/{request_id}", headers=auth(seed["client_a"])
        ).json()["parsed_params"]
        edited["parties"] = edited["parties"] + [
            {"role": "avalista", "name": "Empresa Fantasma SL"}
        ]
        assert wf.confirm(request_id, edited=edited).status_code == 200
        assert wf.generate(request_id).status_code == 202
        job = wf.wait_for_job(request_id)
        assert job["status"] == "succeeded", job

        row = db.get("requests", request_id)
        assert row["requires_counsel"] is True  # Exit B forzado por el verificador

        res = wf.client.get(
            f"/api/requests/{request_id}/verifications", headers=auth(seed["client_a"])
        )
        assert res.status_code == 200
        body = res.json()
        assert len(body) == 1 and body[0]["forced_counsel"] is True
        assert any("Empresa Fantasma SL" in f["problem"] for f in body[0]["findings"])

        # Exit A queda bloqueado (regla existente para requires_counsel).
        ack = wf.client.post(
            f"/api/requests/{request_id}/exit-a/acknowledge",
            json={"acknowledged": True},
            headers=auth(seed["client_a"]),
        )
        assert ack.status_code in (409, 422)

    def test_clean_generation_records_clean_verification(self, wf, db, seed, monkeypatch):
        monkeypatch.setattr(config.get_settings(), "verify_enabled", True)
        # Con precedente en el silo la recuperación no es nivel 3 (que forzaría
        # Exit B por su propia regla y taparía la aserción del verificador).
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"])
        request_id, summary = wf.to_review_pending()
        rows = db.select("verifications", request_id=request_id)
        assert len(rows) == 1
        assert rows[0]["critical_count"] == 0
        assert summary["request"]["requires_counsel"] is False

    def test_verifications_endpoint_is_gestora_isolated(self, wf, db, seed, monkeypatch):
        monkeypatch.setattr(config.get_settings(), "verify_enabled", True)
        request_id, _ = wf.to_review_pending()
        res = wf.client.get(
            f"/api/requests/{request_id}/verifications", headers=auth(seed["client_b"])
        )
        assert res.status_code == 404  # 404-no-leak para otra gestora
