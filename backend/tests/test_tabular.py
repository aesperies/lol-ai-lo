"""Tabular Review tests — extraction grid, isolation, CSV export, statuses.

The suite never reaches the network: ``services.llm.complete_json`` is
monkeypatched per test, and the conftest simulates an unreachable Ollama daemon
so the LLM-down path is exercised by simply NOT patching the seam.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from models.schema import DocumentVersionType
from services import db as dbmod, storage, tabular
from tests.conftest import DOC_TYPE, auth, seed_precedent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request_document(
    db: dbmod.DevStore, *, gestora_id: str, fund_id: str, user_id: str, text: str
) -> dict[str, Any]:
    """A generated request DOCUMENT in a gestora silo (source_kind=request_document)."""
    request_row = db.insert(
        "requests",
        {
            "fund_id": fund_id,
            "user_id": user_id,
            "doc_type": DOC_TYPE,
            "freetext": "x",
            "language": "es",
            "status": "review_pending",
            "requires_counsel": False,
        },
    )
    key = storage.save(
        storage.outputs_path(gestora_id, fund_id, request_row["id"], "draft.txt"),
        text.encode("utf-8"),
    )
    return db.insert(
        "documents",
        {
            "request_id": request_row["id"],
            "version_type": DocumentVersionType.draft.value,
            "file_path": key,
            "uploaded_by": None,
        },
    )


def _fake_extraction(monkeypatch: pytest.MonkeyPatch, payload: dict[str, Any]) -> None:
    """Patch the llm seam so every cell extraction returns ``payload``."""
    from services import llm

    monkeypatch.setattr(
        llm,
        "complete_json",
        lambda prompt, schema, *, max_tokens=8192, system=None, gestora_id=None: dict(payload),
    )


def _create_review_payload(
    *, documents: list[dict[str, Any]], columns: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    return {
        "title": "Comparativa de actas",
        "columns": columns
        or [
            {"name": "Importe", "question": "¿Cuál es el importe de la llamada de capital?", "col_type": "monetary"},
            {"name": "Fecha", "question": "¿Cuál es la fecha de la reunión?", "col_type": "date"},
        ],
        "documents": documents,
    }


# ---------------------------------------------------------------------------
# Isolation (critical)
# ---------------------------------------------------------------------------

class TestTabularIsolation:
    def test_cannot_reference_other_gestora_precedent_version(self, client, db, seed):
        """A review referencing gestora B's precedent version is rejected (404)."""
        _, version_b = seed_precedent(db, gestora_id=seed["gestora_b"]["id"], text="PRECEDENTE BETA")
        payload = _create_review_payload(
            documents=[{"source_kind": "precedent_version", "source_id": version_b["id"]}]
        )
        response = client.post("/api/tabular-reviews", json=payload, headers=auth(seed["client_a"]))
        assert response.status_code == 404

    def test_cannot_reference_other_gestora_request_document(self, client, db, seed):
        """A review referencing gestora B's generated document is rejected (404)."""
        doc_b = _make_request_document(
            db,
            gestora_id=seed["gestora_b"]["id"],
            fund_id=seed["fund_b"]["id"],
            user_id=seed["client_b"]["id"],
            text="DOCUMENTO BETA",
        )
        payload = _create_review_payload(
            documents=[{"source_kind": "request_document", "source_id": doc_b["id"]}]
        )
        response = client.post("/api/tabular-reviews", json=payload, headers=auth(seed["client_a"]))
        assert response.status_code == 404

    def test_unknown_document_reference_is_404(self, client, seed):
        payload = _create_review_payload(
            documents=[{"source_kind": "precedent_version", "source_id": "does-not-exist"}]
        )
        response = client.post("/api/tabular-reviews", json=payload, headers=auth(seed["client_a"]))
        assert response.status_code == 404

    def test_get_and_list_are_gestora_siloed(self, client, db, seed):
        _, version_a = seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        payload = _create_review_payload(
            documents=[{"source_kind": "precedent_version", "source_id": version_a["id"]}]
        )
        created = client.post("/api/tabular-reviews", json=payload, headers=auth(seed["client_a"]))
        assert created.status_code == 201
        review_id = created.json()["id"]

        # Client B cannot read A's review (404 no-leak); counsel/admin can.
        assert client.get(f"/api/tabular-reviews/{review_id}", headers=auth(seed["client_b"])).status_code == 404
        assert client.get(f"/api/tabular-reviews/{review_id}", headers=auth(seed["client_a"])).status_code == 200
        assert client.get(f"/api/tabular-reviews/{review_id}", headers=auth(seed["counsel"])).status_code == 200

        # Listing is siloed.
        listed_b = client.get("/api/tabular-reviews", headers=auth(seed["client_b"])).json()
        assert all(r["id"] != review_id for r in listed_b)
        listed_a = client.get("/api/tabular-reviews", headers=auth(seed["client_a"])).json()
        assert any(r["id"] == review_id for r in listed_a)

    def test_status_and_export_are_siloed(self, client, db, seed):
        _, version_a = seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        payload = _create_review_payload(
            documents=[{"source_kind": "precedent_version", "source_id": version_a["id"]}]
        )
        review_id = client.post(
            "/api/tabular-reviews", json=payload, headers=auth(seed["client_a"])
        ).json()["id"]
        assert client.get(f"/api/tabular-reviews/{review_id}/status", headers=auth(seed["client_b"])).status_code == 404
        assert client.get(f"/api/tabular-reviews/{review_id}/export.csv", headers=auth(seed["client_b"])).status_code == 404


# ---------------------------------------------------------------------------
# Extraction (run_review fills typed cells with value + citation)
# ---------------------------------------------------------------------------

class TestTabularExtraction:
    def test_run_review_fills_cells_with_value_and_citation(
        self, db, seed, monkeypatch
    ):
        _, version_a = seed_precedent(
            db,
            gestora_id=seed["gestora_a"]["id"],
            text="Se aprueba una llamada de capital por importe de 500.000 euros el 15 de julio de 2026.",
        )
        review = db.insert(
            "tabular_reviews",
            {"gestora_id": seed["gestora_a"]["id"], "title": "T", "status": "draft"},
        )
        column = db.insert(
            "tabular_review_columns",
            {
                "review_id": review["id"],
                "position": 0,
                "name": "Importe",
                "question": "¿Importe de la llamada de capital?",
                "col_type": "monetary",
                "options": None,
            },
        )
        document = db.insert(
            "tabular_review_documents",
            {
                "review_id": review["id"],
                "position": 0,
                "source_kind": "precedent_version",
                "source_id": version_a["id"],
                "label": "Acta Alfa",
            },
        )
        _fake_extraction(
            monkeypatch,
            {
                "value": "€500.000",
                "reasoning": "El acta aprueba la llamada de capital por ese importe.",
                "citation": {"page": 1, "quote": "llamada de capital por importe de 500.000 euros"},
            },
        )

        asyncio.run(tabular.run_review(db, review["id"]))

        assert db.get("tabular_reviews", review["id"])["status"] == "complete"
        cells = db.select("tabular_review_cells", document_id=document["id"], column_id=column["id"])
        assert len(cells) == 1
        cell = cells[0]
        assert cell["status"] == "done"
        assert cell["value"] == "€500.000"
        assert cell["citation"]["page"] == 1
        assert "500.000 euros" in cell["citation"]["quote"]

    def test_tag_column_constrains_to_options(self, db, seed, monkeypatch):
        _, version_a = seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="Jurisdicción: España.")
        review = db.insert(
            "tabular_reviews",
            {"gestora_id": seed["gestora_a"]["id"], "title": "T", "status": "draft"},
        )
        options = ["España", "Francia", "Alemania"]
        db.insert(
            "tabular_review_columns",
            {
                "review_id": review["id"],
                "position": 0,
                "name": "Jurisdicción",
                "question": "¿Cuál es la jurisdicción?",
                "col_type": "tag",
                "options": options,
            },
        )
        db.insert(
            "tabular_review_documents",
            {
                "review_id": review["id"],
                "position": 0,
                "source_kind": "precedent_version",
                "source_id": version_a["id"],
                "label": "Doc",
            },
        )

        captured: dict[str, str] = {}

        def fake(prompt, schema, *, max_tokens=8192, system=None, gestora_id=None):
            captured["prompt"] = prompt
            return {
                "value": "España",
                "reasoning": "El documento indica la jurisdicción.",
                "citation": {"page": None, "quote": "Jurisdicción: España"},
            }

        from services import llm

        monkeypatch.setattr(llm, "complete_json", fake)

        asyncio.run(tabular.run_review(db, review["id"]))

        # The allowed options were listed in the prompt (constraint surfaced).
        for opt in options:
            assert opt in captured["prompt"]
        cells = db.select("tabular_review_cells", review_id=review["id"])
        assert cells[0]["value"] in options

    def test_llm_unreachable_marks_cells_error_and_review_failed(self, db, seed):
        """With the LLM seam NOT patched, the conftest simulates an unreachable
        daemon: cells become 'error' and the review 'failed' — no crash/hang."""
        _, version_a = seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="texto")
        review = db.insert(
            "tabular_reviews",
            {"gestora_id": seed["gestora_a"]["id"], "title": "T", "status": "draft"},
        )
        db.insert(
            "tabular_review_columns",
            {
                "review_id": review["id"],
                "position": 0,
                "name": "X",
                "question": "¿X?",
                "col_type": "text",
                "options": None,
            },
        )
        db.insert(
            "tabular_review_documents",
            {
                "review_id": review["id"],
                "position": 0,
                "source_kind": "precedent_version",
                "source_id": version_a["id"],
                "label": "Doc",
            },
        )

        # Must not raise.
        asyncio.run(tabular.run_review(db, review["id"]))

        assert db.get("tabular_reviews", review["id"])["status"] == "failed"
        cells = db.select("tabular_review_cells", review_id=review["id"])
        assert cells and all(c["status"] == "error" for c in cells)
        assert all(c["error"] for c in cells)


# ---------------------------------------------------------------------------
# API: status transitions, columns, CSV export
# ---------------------------------------------------------------------------

class TestTabularApi:
    def _seed_review(self, client, db, seed) -> str:
        _, version_a = seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="texto alfa")
        payload = _create_review_payload(
            documents=[{"source_kind": "precedent_version", "source_id": version_a["id"], "label": "Acta"}]
        )
        response = client.post("/api/tabular-reviews", json=payload, headers=auth(seed["client_a"]))
        assert response.status_code == 201, response.text
        return response.json()["id"]

    def test_create_starts_draft_with_pending_cells(self, client, db, seed):
        review_id = self._seed_review(client, db, seed)
        detail = client.get(f"/api/tabular-reviews/{review_id}", headers=auth(seed["client_a"])).json()
        assert detail["status"] == "draft"
        assert len(detail["columns"]) == 2
        assert len(detail["documents"]) == 1
        # 1 document × 2 columns = 2 pending cells.
        assert len(detail["cells"]) == 2
        assert all(c["status"] == "pending" for c in detail["cells"])

    def test_run_transitions_draft_to_running_then_complete(
        self, client, db, seed, monkeypatch
    ):
        _fake_extraction(
            monkeypatch,
            {"value": "v", "reasoning": "r", "citation": {"page": 1, "quote": "q"}},
        )
        review_id = self._seed_review(client, db, seed)
        run = client.post(f"/api/tabular-reviews/{review_id}/run", headers=auth(seed["client_a"]))
        assert run.status_code == 202
        assert run.json()["status"] == "running"

        # Job runs on the shared event loop; poll status to a terminal state.
        import time

        deadline = time.time() + 5.0
        status = None
        while time.time() < deadline:
            status = client.get(
                f"/api/tabular-reviews/{review_id}/status", headers=auth(seed["client_a"])
            ).json()
            if status["status"] in ("complete", "failed"):
                break
            time.sleep(0.02)
        assert status is not None and status["status"] == "complete"
        assert status["cell_done"] == status["cell_total"] == 2

    def test_add_column_creates_pending_cells(self, client, db, seed):
        review_id = self._seed_review(client, db, seed)
        response = client.post(
            f"/api/tabular-reviews/{review_id}/columns",
            json={"name": "Sí/No", "question": "¿Hay quórum?", "col_type": "yes_no"},
            headers=auth(seed["client_a"]),
        )
        assert response.status_code == 200
        detail = response.json()
        assert len(detail["columns"]) == 3
        # 1 document × 3 columns now.
        assert len(detail["cells"]) == 3

    def test_delete_column_removes_its_cells(self, client, db, seed):
        review_id = self._seed_review(client, db, seed)
        detail = client.get(f"/api/tabular-reviews/{review_id}", headers=auth(seed["client_a"])).json()
        column_id = detail["columns"][0]["id"]
        response = client.delete(
            f"/api/tabular-reviews/{review_id}/columns/{column_id}", headers=auth(seed["client_a"])
        )
        assert response.status_code == 200
        after = response.json()
        assert all(c["id"] != column_id for c in after["columns"])
        assert all(c["column_id"] != column_id for c in after["cells"])

    def test_csv_export_shape_and_content_type(self, client, db, seed, monkeypatch):
        _fake_extraction(
            monkeypatch,
            {"value": "€500.000", "reasoning": "r", "citation": {"page": 1, "quote": "q"}},
        )
        review_id = self._seed_review(client, db, seed)
        # Run via the API job so cells have values, then poll to a terminal state.
        assert client.post(
            f"/api/tabular-reviews/{review_id}/run", headers=auth(seed["client_a"])
        ).status_code == 202
        import time

        deadline = time.time() + 5.0
        while time.time() < deadline:
            status = client.get(
                f"/api/tabular-reviews/{review_id}/status", headers=auth(seed["client_a"])
            ).json()
            if status["status"] in ("complete", "failed"):
                break
            time.sleep(0.02)

        response = client.get(
            f"/api/tabular-reviews/{review_id}/export.csv", headers=auth(seed["client_a"])
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        body = response.text
        # Header row with the document label + the two question column names.
        assert "Documento" in body
        assert "Importe" in body
        assert "Fecha" in body
        assert "Acta" in body
        assert "€500.000" in body
        # Citations are NOT in the CSV (only in the app).
        assert "cita textual" in body.lower() or "citas" in body.lower()
