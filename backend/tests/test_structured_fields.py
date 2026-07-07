"""Hybrid structured intake fields (improvement #5): registry endpoint,
intake validation, deterministic parser merge, generator integration and
freetext-only regression."""
from __future__ import annotations

import json

from models import doc_fields
from services import generator, intake_parser
from tests.conftest import DOC_TYPE, FREETEXT, auth

LLAMADA_LABEL = "Llamada de Capital (Capital Call Notice)"


# ---------------------------------------------------------------------------
# Registry + fields endpoint
# ---------------------------------------------------------------------------

class TestFieldsEndpoint:
    def test_fields_for_llamada_de_capital(self, client, seed):
        response = client.get(
            f"/api/doc-types/{LLAMADA_LABEL}/fields", headers=auth(seed["client_a"])
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        keys = [f["key"] for f in payload["fields"]]
        assert keys == [
            "importe_total",
            "fecha_limite_pago",
            "porcentaje_compromiso",
            "numero_llamada",
        ]
        importe = payload["fields"][0]
        assert importe["type"] == "amount"
        assert importe["required"] is True
        # Resolved es+en labels travel with each spec.
        assert importe["label"] == {"es": "Importe total", "en": "Total amount"}
        # nº de llamada is the only optional field.
        assert payload["fields"][3]["required"] is False

    def test_frontend_slug_resolves_to_same_fields(self, client, seed):
        response = client.get(
            "/api/doc-types/llamada_capital/fields", headers=auth(seed["client_a"])
        )
        assert response.status_code == 200
        assert [f["key"] for f in response.json()["fields"]] == [
            "importe_total",
            "fecha_limite_pago",
            "porcentaje_compromiso",
            "numero_llamada",
        ]

    def test_uncovered_doc_type_returns_empty_list(self, client, seed):
        response = client.get(
            "/api/doc-types/Declaración AML/KYC/fields", headers=auth(seed["client_a"])
        )
        assert response.status_code == 200
        assert response.json()["fields"] == []

    def test_requires_authentication(self, client, seed):
        response = client.get(f"/api/doc-types/{LLAMADA_LABEL}/fields")
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# Intake validation (POST /api/requests)
# ---------------------------------------------------------------------------

class TestIntakeValidation:
    def test_unknown_structured_key_rejected_422(self, client, seed):
        response = client.post(
            "/api/requests",
            json={
                "fund_id": seed["fund_a"]["id"],
                "doc_type": DOC_TYPE,  # Acta de Reunión del Consejo
                "freetext": FREETEXT,
                "structured_fields": {"importe_total": "1.000 EUR"},
            },
            headers=auth(seed["client_a"]),
        )
        assert response.status_code == 422
        assert "importe_total" in response.json()["detail"]

    def test_known_structured_fields_stored_on_row(self, client, db, seed):
        structured = {"fecha_reunion": "2026-07-15", "asistentes": "Consejo al completo"}
        response = client.post(
            "/api/requests",
            json={
                "fund_id": seed["fund_a"]["id"],
                "doc_type": DOC_TYPE,
                "freetext": FREETEXT,
                "structured_fields": structured,
            },
            headers=auth(seed["client_a"]),
        )
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["structured_fields"] == structured
        assert db.get("requests", body["id"])["structured_fields"] == structured
        # Audit metadata records WHICH keys were provided (not just that some were).
        entry = db.unscoped_select("audit_log", action="document_requested")[-1]
        assert entry["metadata"]["structured_field_keys"] == ["asistentes", "fecha_reunion"]

    def test_required_structured_keys_may_be_missing_at_submit(self, client, seed):
        # Only one of the three Acta fields: accepted (the parser flags gaps).
        response = client.post(
            "/api/requests",
            json={
                "fund_id": seed["fund_a"]["id"],
                "doc_type": DOC_TYPE,
                "freetext": FREETEXT,
                "structured_fields": {"asistentes": "Consejo al completo"},
            },
            headers=auth(seed["client_a"]),
        )
        assert response.status_code == 201, response.text


# ---------------------------------------------------------------------------
# Parser merge (real parse_intake, monkeypatched Claude call)
# ---------------------------------------------------------------------------

def _fake_claude_response(monkeypatch, payload: dict, captured: dict) -> None:
    # Patch the LLM JSON seam the parser now uses (services/llm.py). The parser
    # builds the prompt and post-processes the parsed dict identically.
    def fake_complete_json(prompt: str, schema: dict, **kwargs) -> dict:
        captured["prompt"] = prompt
        return json.loads(json.dumps(payload, ensure_ascii=False))

    monkeypatch.setattr(intake_parser.llm, "complete_json", fake_complete_json)


class TestParserMerge:
    PARSER_OUTPUT = {
        "language": "es",
        "doc_type_confirmed": LLAMADA_LABEL,
        "parties": [{"role": "fondo", "name": "Alfa Fund I"}],
        "key_dates": [],
        "jurisdiction": "España",
        "governing_law": "Derecho español",
        # Conflicting parser extraction for a structured-covered field:
        "key_terms": [{"field": "Importe total", "value": "300.000 EUR"}],
        "summary": "Llamada de capital.",
        "confidence": 0.8,
        # Structured-covered field flagged unclear by the model:
        "unclear_fields": ["importe_total"],
        "generation_ready": False,
    }

    STRUCTURED = {
        "importe_total": "500.000 EUR",
        "fecha_limite_pago": "2026-07-15",
    }

    def test_structured_values_win_and_clear_unclear(self, monkeypatch):
        captured: dict = {}
        _fake_claude_response(monkeypatch, dict(self.PARSER_OUTPUT), captured)

        parsed = intake_parser.parse_intake(
            LLAMADA_LABEL, FREETEXT, structured_fields=dict(self.STRUCTURED)
        )

        # Deterministic override: the client value replaced the conflict.
        importe_terms = [
            t for t in parsed["key_terms"] if t["field"] == "Importe total"
        ]
        assert importe_terms == [
            {"field": "Importe total", "value": "500.000 EUR", "source": "client_confirmed"}
        ]
        # Date-typed structured field landed in key_dates.
        assert {
            "label": "Fecha límite de pago",
            "date": "2026-07-15",
            "source": "client_confirmed",
        } in parsed["key_dates"]
        # Covered field left unclear_fields; generation_ready recomputed.
        assert parsed["unclear_fields"] == []
        assert parsed["generation_ready"] is True

    def test_prompt_includes_structured_section_and_rule(self, monkeypatch):
        captured: dict = {}
        _fake_claude_response(monkeypatch, dict(self.PARSER_OUTPUT), captured)
        intake_parser.parse_intake(
            LLAMADA_LABEL, FREETEXT, structured_fields=dict(self.STRUCTURED)
        )
        prompt = captured["prompt"]
        assert "structured_fields (client-provided, authoritative" in prompt
        assert '"importe_total": "500.000 EUR"' in prompt
        assert intake_parser.STRUCTURED_FIELDS_RULE in prompt
        # The section was spliced into the INPUT block, before OUTPUT.
        assert prompt.index('"importe_total"') < prompt.index("OUTPUT (JSON only")

    def test_prompt_untouched_without_structured_fields(self, monkeypatch):
        captured: dict = {}
        _fake_claude_response(monkeypatch, dict(self.PARSER_OUTPUT), captured)
        intake_parser.parse_intake(LLAMADA_LABEL, FREETEXT)
        expected = intake_parser.INTAKE_PROMPT.replace(
            "{doc_type}", LLAMADA_LABEL
        ).replace("{freetext}", FREETEXT)
        assert captured["prompt"] == expected

    def test_unclear_fields_from_freetext_stay_unclear(self, monkeypatch):
        payload = dict(self.PARSER_OUTPUT)
        payload["unclear_fields"] = ["importe_total", "jurisdiction"]
        _fake_claude_response(monkeypatch, payload, {})
        parsed = intake_parser.parse_intake(
            LLAMADA_LABEL, FREETEXT, structured_fields=dict(self.STRUCTURED)
        )
        assert parsed["unclear_fields"] == ["jurisdiction"]
        assert parsed["generation_ready"] is False

    def test_party_field_merged_into_parties(self, monkeypatch):
        payload = dict(self.PARSER_OUTPUT)
        payload["doc_type_confirmed"] = "NDA / Acuerdo de Confidencialidad"
        payload["parties"] = [
            {"role": "Contraparte", "name": "¿Solaria?"},  # parser guess
        ]
        payload["unclear_fields"] = []
        _fake_claude_response(monkeypatch, payload, {})
        parsed = intake_parser.parse_intake(
            "NDA / Acuerdo de Confidencialidad",
            FREETEXT,
            structured_fields={"contraparte": "Solaria Robotics SL"},
        )
        assert parsed["parties"] == [
            {"role": "Contraparte", "name": "Solaria Robotics SL", "source": "client_confirmed"}
        ]


# ---------------------------------------------------------------------------
# Generator integration (structured values inside {key_terms})
# ---------------------------------------------------------------------------

class TestGeneratorIntegration:
    def test_structured_values_reach_generator_key_terms(
        self, client, db, seed, wf, monkeypatch
    ):
        captured: dict = {}
        original_fake = generator.generate_document

        def capture_generate(**kwargs):
            captured.update(kwargs)
            return original_fake(**kwargs)

        monkeypatch.setattr(generator, "generate_document", capture_generate)

        structured = {"fecha_reunion": "2026-07-15", "asistentes": "Consejo al completo"}
        request_id = wf.create(structured_fields=structured)
        assert wf.parse(request_id).status_code == 200
        assert wf.confirm(request_id).status_code == 200
        assert wf.generate(request_id).status_code == 202
        job = wf.wait_for_job(request_id)
        assert job["status"] == "succeeded", job

        key_terms = captured["key_terms"]
        assert {
            "field": "Fecha de la reunión",
            "value": "2026-07-15",
            "source": "client_confirmed",
        } in key_terms
        assert {
            "field": "Asistentes",
            "value": "Consejo al completo",
            "source": "client_confirmed",
        } in key_terms
        # Parser-derived terms are preserved alongside.
        assert {"field": "importe", "value": "500.000 EUR"} in key_terms

    def test_merge_replaces_conflicting_term_for_generator(self):
        merged = doc_fields.merge_structured_key_terms(
            [{"field": "Fecha de la reunión", "value": "2026-01-01"}],
            DOC_TYPE,
            {"fecha_reunion": "2026-07-15"},
        )
        assert merged == [
            {
                "field": "Fecha de la reunión",
                "value": "2026-07-15",
                "source": "client_confirmed",
            }
        ]


# ---------------------------------------------------------------------------
# Regression: freetext-only requests are byte-for-byte unchanged
# ---------------------------------------------------------------------------

class TestFreetextOnlyRegression:
    def test_full_flow_without_structured_fields(self, wf, db):
        request_id, summary = wf.to_review_pending()
        row = db.get("requests", request_id)
        assert row["structured_fields"] is None
        assert row["status"] == "review_pending"
        # parsed_params carry no client_confirmed markers.
        params = row["parsed_params"]
        for entry in params["parties"] + params["key_dates"] + params["key_terms"]:
            assert "source" not in entry
        assert summary["draft"] is not None

    def test_merge_noop_on_empty_structured_values(self, monkeypatch):
        payload = {
            "language": "es",
            "doc_type_confirmed": LLAMADA_LABEL,
            "parties": [],
            "key_dates": [],
            "jurisdiction": "España",
            "governing_law": "Derecho español",
            "key_terms": [],
            "summary": "x",
            "confidence": 0.5,
            "unclear_fields": ["importe_total"],
            "generation_ready": False,
        }
        _fake_claude_response(monkeypatch, payload, {})
        # Empty-string values are ignored: nothing merged, still not ready.
        parsed = intake_parser.parse_intake(
            LLAMADA_LABEL, FREETEXT, structured_fields={"importe_total": "  "}
        )
        assert parsed["key_terms"] == []
        assert parsed["unclear_fields"] == ["importe_total"]
        assert parsed["generation_ready"] is False
