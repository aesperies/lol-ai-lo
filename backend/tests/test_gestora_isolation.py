"""Cross-gestora leakage tests (SPEC success metric: zero leakage).

Covers the three attack surfaces:
1. RAG retrieval (hard gestora_id pre-filter, fallback never crosses silos)
2. Request/document access via the API
3. Precedent library access via the API
"""
from __future__ import annotations

from models.schema import PrecedentSource
from services import rag
from tests.conftest import DOC_TYPE, auth, seed_precedent


# ---------------------------------------------------------------------------
# 1. RAG filter
# ---------------------------------------------------------------------------

class TestRagIsolation:
    def test_silo_retrieval_only_returns_own_gestora(self, db, seed):
        _, version_a = seed_precedent(
            db, gestora_id=seed["gestora_a"]["id"], text="TEXTO PRECEDENTE GESTORA ALFA"
        )
        _, version_b = seed_precedent(
            db, gestora_id=seed["gestora_b"]["id"], text="TEXTO PRECEDENTE GESTORA BETA"
        )

        result = rag.retrieve(
            db, gestora_id=seed["gestora_a"]["id"], doc_type=DOC_TYPE, language="es", query_text="acta"
        )
        assert result.level == 0
        assert result.base_version_id == version_a["id"]
        assert result.base_version_id != version_b["id"]
        assert "ALFA" in result.base_text
        assert all("BETA" not in text for text in result.context_texts)

    def test_empty_silo_never_borrows_other_gestora(self, db, seed):
        # Only gestora B has a precedent; A must hit Level 3, never B's silo.
        seed_precedent(db, gestora_id=seed["gestora_b"]["id"], text="TEXTO PRECEDENTE GESTORA BETA")

        result = rag.retrieve(
            db, gestora_id=seed["gestora_a"]["id"], doc_type=DOC_TYPE, language="es", query_text="acta"
        )
        assert result.level == 3
        assert result.base_text is None
        assert result.requires_counsel is True
        assert all("BETA" not in text for text in result.context_texts)

    def test_fallback_goes_to_global_templates_not_other_gestora(self, db, seed):
        seed_precedent(db, gestora_id=seed["gestora_b"]["id"], text="TEXTO PRECEDENTE GESTORA BETA")
        _, global_version = seed_precedent(
            db, gestora_id=None, source=PrecedentSource.slp_curated.value, text="PLANTILLA GLOBAL SLP"
        )

        result = rag.retrieve(
            db, gestora_id=seed["gestora_a"]["id"], doc_type=DOC_TYPE, language="es", query_text="acta"
        )
        assert result.level == 1
        assert result.base_version_id == global_version["id"]
        assert "GLOBAL" in result.base_text
        assert all("BETA" not in text for text in result.context_texts)

    def test_doc_type_is_part_of_hard_filter(self, db, seed):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], doc_type="NDA / Acuerdo de Confidencialidad")
        result = rag.retrieve(
            db, gestora_id=seed["gestora_a"]["id"], doc_type=DOC_TYPE, language="es", query_text="acta"
        )
        assert result.level == 3

    def test_pdf_precedent_never_generation_base(self, db, seed):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PDF DE REFERENCIA", extension=".pdf")
        result = rag.retrieve(
            db, gestora_id=seed["gestora_a"]["id"], doc_type=DOC_TYPE, language="es", query_text="acta"
        )
        # PDF (stored as plain text in test) may appear as reference context,
        # but never as base; with no .docx anywhere this is Level 3.
        assert result.level == 3
        assert result.base_text is None
        assert result.requires_counsel is True


# ---------------------------------------------------------------------------
# 2. Request + document access
# ---------------------------------------------------------------------------

class TestRequestIsolation:
    def test_client_cannot_read_other_gestora_request(self, wf, client, seed):
        request_id = wf.create()
        response = client.get(f"/api/requests/{request_id}", headers=auth(seed["client_b"]))
        assert response.status_code == 404
        # Counsel and admin are cross-gestora by design.
        assert client.get(f"/api/requests/{request_id}", headers=auth(seed["counsel"])).status_code == 200

    def test_request_listing_is_siloed(self, wf, client, seed):
        request_id = wf.create()
        listed_b = client.get("/api/requests", headers=auth(seed["client_b"])).json()
        assert all(r["id"] != request_id for r in listed_b)
        listed_a = client.get("/api/requests", headers=auth(seed["client_a"])).json()
        assert any(r["id"] == request_id for r in listed_a)

    def test_cannot_create_request_against_other_gestora_fund(self, client, seed):
        from tests.conftest import FREETEXT

        response = client.post(
            "/api/requests",
            json={"fund_id": seed["fund_b"]["id"], "doc_type": DOC_TYPE, "freetext": FREETEXT},
            headers=auth(seed["client_a"]),
        )
        assert response.status_code == 404

    def test_client_cannot_act_on_other_gestora_request(self, wf, client, seed):
        request_id, _ = wf.to_review_pending()
        headers_b = auth(seed["client_b"])
        assert client.post(f"/api/requests/{request_id}/exit-b", headers=headers_b).status_code == 404
        assert (
            client.post(
                f"/api/requests/{request_id}/exit-a/acknowledge",
                json={"acknowledged": True},
                headers=headers_b,
            ).status_code
            == 404
        )

    def test_document_download_is_siloed(self, wf, client, seed, db):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        request_id, _ = wf.to_review_pending()
        url = f"/api/requests/{request_id}/documents/draft/download"
        assert client.get(url, headers=auth(seed["client_b"])).status_code == 404
        assert client.get(url, headers=auth(seed["client_a"])).status_code == 200


# ---------------------------------------------------------------------------
# 3. Precedent library access
# ---------------------------------------------------------------------------

class TestPrecedentIsolation:
    def test_precedent_listing_is_siloed(self, client, db, seed):
        precedent_a, _ = seed_precedent(db, gestora_id=seed["gestora_a"]["id"])
        precedent_b, _ = seed_precedent(db, gestora_id=seed["gestora_b"]["id"])
        global_precedent, _ = seed_precedent(
            db, gestora_id=None, source=PrecedentSource.platform_base.value
        )

        listed = client.get("/api/precedents", headers=auth(seed["client_a"])).json()
        listed_ids = {p["id"] for p in listed}
        assert precedent_a["id"] in listed_ids
        assert global_precedent["id"] in listed_ids  # global templates readable by all
        assert precedent_b["id"] not in listed_ids

        # Admin sees everything.
        admin_ids = {p["id"] for p in client.get("/api/precedents", headers=auth(seed["admin"])).json()}
        assert {precedent_a["id"], precedent_b["id"], global_precedent["id"]} <= admin_ids

    def test_client_cannot_read_other_gestora_precedent_versions(self, client, db, seed):
        precedent_b, _ = seed_precedent(db, gestora_id=seed["gestora_b"]["id"])
        response = client.get(
            f"/api/precedents/{precedent_b['id']}/versions", headers=auth(seed["client_a"])
        )
        assert response.status_code == 404
        assert (
            client.get(
                f"/api/precedents/{precedent_b['id']}/versions", headers=auth(seed["client_b"])
            ).status_code
            == 200
        )

    def test_client_cannot_upload_precedents(self, client, seed):
        response = client.post(
            "/api/precedents",
            data={"doc_type": DOC_TYPE, "language": "es", "gestora_id": seed["gestora_a"]["id"]},
            files={"file": ("p.docx", b"x", "application/octet-stream")},
            headers=auth(seed["client_a"]),
        )
        assert response.status_code == 403
