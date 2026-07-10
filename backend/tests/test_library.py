"""Biblioteca del cliente (022): listado siloed, subida como borrador y
visor HTML de versiones de precedente."""
from __future__ import annotations

import io
from typing import Any

from services import db as dbmod
from services import docx_renderer
from tests.conftest import auth, seed_precedent


def _upload_files(filename: str = "lpa.docx") -> dict[str, Any]:
    data = docx_renderer.render_docx("CLÁUSULA 1 — OBJETO\nTexto del documento.")
    return {"file": (filename, io.BytesIO(data),
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}


class TestMyLibrary:
    def test_lists_only_own_silo_with_fund_and_dates(self, client, seed, db: dbmod.DevStore):
        precedent_a, version_a = seed_precedent(
            db, gestora_id=seed["gestora_a"]["id"], doc_type="LPA", text="Texto alfa.")
        db.update("precedents", precedent_a["id"], {
            "fund_id": seed["fund_a"]["id"], "document_date": "2025-05-10",
        })
        seed_precedent(db, gestora_id=seed["gestora_b"]["id"], doc_type="LPA", text="Texto beta.")
        seed_precedent(db, gestora_id=None, doc_type="LPA", text="Plantilla global.",
                       source="platform_base")

        response = client.get("/api/my/library", headers=auth(seed["client_a"]))
        assert response.status_code == 200, response.text
        items = response.json()
        assert [item["id"] for item in items] == [precedent_a["id"]]
        item = items[0]
        assert item["fund_name"] == seed["fund_a"]["name"]
        assert item["document_date"] == "2025-05-10"
        assert item["version_status"] == "active"
        assert item["version_id"] == version_a["id"]
        assert item["is_docx"] is True

    def test_counsel_and_admin_cannot_use_client_library(self, client, seed):
        for user_key in ("counsel", "admin"):
            response = client.get("/api/my/library", headers=auth(seed[user_key]))
            assert response.status_code == 403


class TestClientUpload:
    def test_upload_creates_draft_precedent_in_own_silo(self, client, seed, db: dbmod.DevStore):
        response = client.post(
            "/api/my/library/upload",
            files=_upload_files(),
            data={"doc_type": "LPA", "language": "es",
                  "fund_id": seed["fund_a"]["id"], "document_date": "2024-11-30"},
            headers=auth(seed["client_a"]),
        )
        assert response.status_code == 201, response.text
        payload = response.json()
        assert payload["precedent"]["gestora_id"] == seed["gestora_a"]["id"]
        assert payload["precedent"]["document_date"] == "2024-11-30"
        # Entra como BORRADOR: no alimenta el RAG hasta que un admin la active.
        assert payload["version"]["status"] == "draft"
        assert payload["version"]["rag_weight"] == 0.0

    def test_upload_rejects_foreign_fund_and_bad_date(self, client, seed):
        response = client.post(
            "/api/my/library/upload",
            files=_upload_files(),
            data={"doc_type": "LPA", "fund_id": seed["fund_b"]["id"]},
            headers=auth(seed["client_a"]),
        )
        assert response.status_code == 404  # fondo de OTRA gestora: no-leak

        response = client.post(
            "/api/my/library/upload",
            files=_upload_files(),
            data={"doc_type": "LPA", "document_date": "30/11/2024"},
            headers=auth(seed["client_a"]),
        )
        assert response.status_code == 422


class TestVersionHtml:
    def test_client_views_own_docx_version(self, client, seed, db: dbmod.DevStore):
        _, version = seed_precedent(
            db, gestora_id=seed["gestora_a"]["id"], doc_type="LPA",
            text="CLÁUSULA 1 — OBJETO\nEl objeto del contrato.")
        response = client.get(
            f"/api/precedents/versions/{version['id']}/html",
            headers=auth(seed["client_a"]),
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert "El objeto del contrato" in payload["html"]
        assert payload["doc_type"] == "LPA"

    def test_cross_gestora_is_404_and_pdf_is_409(self, client, seed, db: dbmod.DevStore):
        _, version_b = seed_precedent(
            db, gestora_id=seed["gestora_b"]["id"], doc_type="LPA", text="Texto beta.")
        response = client.get(
            f"/api/precedents/versions/{version_b['id']}/html",
            headers=auth(seed["client_a"]),
        )
        assert response.status_code == 404  # no-leak

        _, pdf_version = seed_precedent(
            db, gestora_id=seed["gestora_a"]["id"], doc_type="LPA",
            text="Texto pdf.", extension=".pdf")
        response = client.get(
            f"/api/precedents/versions/{pdf_version['id']}/html",
            headers=auth(seed["client_a"]),
        )
        assert response.status_code == 409
