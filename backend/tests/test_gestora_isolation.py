"""Cross-gestora leakage tests (SPEC success metric: zero leakage).

Covers the three attack surfaces:
1. RAG retrieval (hard gestora_id pre-filter, fallback never crosses silos)
2. Request/document access via the API
3. Precedent library access via the API
"""
from __future__ import annotations

from models.doc_branches import Branch, branch_for
from models.schema import DocumentVersionType, PrecedentSource
from services import db as dbmod, lessons, playbooks, rag, storage
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

    def test_gestora_model_is_siloed(self, db, seed):
        """A gestora master template (modelos/, source=gestora_model) is HARD
        pre-filtered by gestora_id exactly like a precedent: gestora A's model is
        NEVER used as the base (or context) for gestora B."""
        _, model_a = seed_precedent(
            db,
            gestora_id=seed["gestora_a"]["id"],
            source=PrecedentSource.gestora_model.value,
            text="MODELO MAESTRO ALFA",
        )
        # B has only a regular precedent; A's model must never cross into B.
        _, precedent_b = seed_precedent(
            db, gestora_id=seed["gestora_b"]["id"], text="PRECEDENTE BETA"
        )

        result_b = rag.retrieve(
            db, gestora_id=seed["gestora_b"]["id"], doc_type=DOC_TYPE, language="es", query_text="acta"
        )
        assert result_b.base_version_id == precedent_b["id"]
        assert result_b.base_version_id != model_a["id"]
        assert "ALFA" not in (result_b.base_text or "")
        assert all("ALFA" not in text for text in result_b.context_texts)

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


# ---------------------------------------------------------------------------
# 4. Drafting lessons (drafting-agents Feature 3) — STRICTLY gestora-siloed
# ---------------------------------------------------------------------------

class TestLessonsIsolation:
    def test_lessons_never_cross_gestora(self, db, seed):
        """A lesson distilled from gestora A's validated documents must NEVER be
        retrievable for gestora B (the inviolable isolation rule — no global
        lesson pool exists)."""
        branch = branch_for(DOC_TYPE)
        db.insert(
            "drafting_lessons",
            {
                "gestora_id": seed["gestora_a"]["id"],
                "branch": branch.value,
                "doc_type": DOC_TYPE,
                "lesson": "LECCIÓN PRIVADA DE GESTORA ALFA",
                "source_request_id": None,
                "weight": 1.0,
            },
        )

        for_a = lessons.lessons_for(
            db, gestora_id=seed["gestora_a"]["id"], branch=branch, doc_type=DOC_TYPE
        )
        assert "LECCIÓN PRIVADA DE GESTORA ALFA" in for_a

        for_b = lessons.lessons_for(
            db, gestora_id=seed["gestora_b"]["id"], branch=branch, doc_type=DOC_TYPE
        )
        assert for_b == []
        assert "LECCIÓN PRIVADA DE GESTORA ALFA" not in for_b

    def test_extracted_lessons_are_anchored_to_their_gestora(self, db, seed, monkeypatch):
        """Lessons extracted for gestora A carry A's gestora_id and never reach B."""
        from services import llm

        monkeypatch.setattr(
            llm, "complete_json",
            lambda prompt, schema, *, max_tokens=8192, system=None, gestora_id=None: {
                "lessons": ["Regla generalizable de Alfa"]
            },
        )
        lessons.extract_lessons(
            gestora_id=seed["gestora_a"]["id"],
            branch=Branch.OPERACIONES_DE_FONDO,
            doc_type=DOC_TYPE,
            ai_draft_text="borrador breve",
            final_text="un documento final validado sustancialmente distinto y mas largo",
            source_request_id=None,
            db=db,
        )
        rows = db.select("drafting_lessons", gestora_id=seed["gestora_a"]["id"])
        assert rows and all(r["gestora_id"] == seed["gestora_a"]["id"] for r in rows)
        # None of them are visible to gestora B.
        assert lessons.lessons_for(
            db, gestora_id=seed["gestora_b"]["id"], branch=Branch.OPERACIONES_DE_FONDO
        ) == []


# ---------------------------------------------------------------------------
# 5. Review playbooks (drafting-agents) — STRICTLY gestora-siloed
# ---------------------------------------------------------------------------

class TestPlaybookIsolation:
    def test_playbooks_never_cross_gestora(self, db, seed):
        """A playbook authored for gestora A must NEVER be loaded into gestora
        B's review (the inviolable isolation rule — no global playbook pool)."""
        branch = branch_for(DOC_TYPE)
        db.insert(
            "review_playbooks",
            {
                "gestora_id": seed["gestora_a"]["id"],
                "branch": branch.value,
                "doc_type": DOC_TYPE,
                "title": "Reglas privadas Alfa",
                "content": "PLAYBOOK PRIVADO DE GESTORA ALFA",
                "file_path": None,
                "is_active": True,
            },
        )

        for_a = playbooks.playbooks_for(
            db, gestora_id=seed["gestora_a"]["id"], branch=branch, doc_type=DOC_TYPE
        )
        assert "PLAYBOOK PRIVADO DE GESTORA ALFA" in for_a

        for_b = playbooks.playbooks_for(
            db, gestora_id=seed["gestora_b"]["id"], branch=branch, doc_type=DOC_TYPE
        )
        assert for_b == []
        assert "PLAYBOOK PRIVADO DE GESTORA ALFA" not in for_b

    def test_client_cannot_read_other_gestora_playbook(self, client, db, seed):
        pb = db.insert(
            "review_playbooks",
            {
                "gestora_id": seed["gestora_b"]["id"],
                "branch": None,
                "doc_type": None,
                "title": "Beta",
                "content": "reglas beta",
                "file_path": None,
                "is_active": True,
            },
        )
        # Client A cannot see B's playbook (404 no-leak); client B can.
        assert client.get(f"/api/playbooks/{pb['id']}", headers=auth(seed["client_a"])).status_code == 404
        assert client.get(f"/api/playbooks/{pb['id']}", headers=auth(seed["client_b"])).status_code == 200

    def test_playbook_listing_is_siloed(self, client, db, seed):
        pb_b = db.insert(
            "review_playbooks",
            {
                "gestora_id": seed["gestora_b"]["id"],
                "branch": None,
                "doc_type": None,
                "title": "Beta",
                "content": "reglas beta",
                "file_path": None,
                "is_active": True,
            },
        )
        listed_a = client.get("/api/playbooks", headers=auth(seed["client_a"])).json()
        assert all(p["id"] != pb_b["id"] for p in listed_a)


# ---------------------------------------------------------------------------
# 6. Tabular Review (010_tabular_reviews.sql) — STRICTLY gestora-siloed
# ---------------------------------------------------------------------------

class TestTabularReviewIsolation:
    def test_cannot_reference_other_gestora_document_in_review(self, client, db, seed):
        """A tabular review referencing gestora B's precedent version OR generated
        document is rejected (404 no-leak); the same review built from gestora
        A's own document succeeds."""
        _, version_b = seed_precedent(db, gestora_id=seed["gestora_b"]["id"], text="PRECEDENTE BETA")
        # Cross-gestora precedent_version reference → 404.
        cross = client.post(
            "/api/tabular-reviews",
            json={
                "title": "Fuga",
                "columns": [{"name": "X", "question": "¿X?", "col_type": "text"}],
                "documents": [{"source_kind": "precedent_version", "source_id": version_b["id"]}],
            },
            headers=auth(seed["client_a"]),
        )
        assert cross.status_code == 404

        # Cross-gestora request_document reference → 404.
        request_b = db.insert(
            "requests",
            {
                "fund_id": seed["fund_b"]["id"],
                "user_id": seed["client_b"]["id"],
                "doc_type": DOC_TYPE,
                "freetext": "x",
                "language": "es",
                "status": "review_pending",
                "requires_counsel": False,
            },
        )
        key_b = storage.save(
            storage.outputs_path(
                seed["gestora_b"]["id"], seed["fund_b"]["id"], request_b["id"], "draft.txt"
            ),
            b"DOCUMENTO BETA",
        )
        doc_b = db.insert(
            "documents",
            {
                "request_id": request_b["id"],
                "version_type": DocumentVersionType.draft.value,
                "file_path": key_b,
                "uploaded_by": None,
            },
        )
        cross_doc = client.post(
            "/api/tabular-reviews",
            json={
                "title": "Fuga",
                "columns": [{"name": "X", "question": "¿X?", "col_type": "text"}],
                "documents": [{"source_kind": "request_document", "source_id": doc_b["id"]}],
            },
            headers=auth(seed["client_a"]),
        )
        assert cross_doc.status_code == 404

        # Own-gestora reference succeeds (control).
        _, version_a = seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        ok = client.post(
            "/api/tabular-reviews",
            json={
                "title": "Propia",
                "columns": [{"name": "X", "question": "¿X?", "col_type": "text"}],
                "documents": [{"source_kind": "precedent_version", "source_id": version_a["id"]}],
            },
            headers=auth(seed["client_a"]),
        )
        assert ok.status_code == 201

    def test_cells_never_expose_other_gestora_review(self, client, db, seed):
        """Gestora B can never read gestora A's review, its grid, or its cells."""
        _, version_a = seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        review_id = client.post(
            "/api/tabular-reviews",
            json={
                "title": "Privada Alfa",
                "columns": [{"name": "X", "question": "¿X?", "col_type": "text"}],
                "documents": [{"source_kind": "precedent_version", "source_id": version_a["id"]}],
            },
            headers=auth(seed["client_a"]),
        ).json()["id"]

        # B sees neither the review nor its grid/cells (404 no-leak).
        assert client.get(f"/api/tabular-reviews/{review_id}", headers=auth(seed["client_b"])).status_code == 404
        listed_b = client.get("/api/tabular-reviews", headers=auth(seed["client_b"])).json()
        assert all(r["id"] != review_id for r in listed_b)


# ---------------------------------------------------------------------------
# 7. Per-gestora model configuration (011_account_security.sql) — siloed
# ---------------------------------------------------------------------------

class TestModelConfigIsolation:
    def test_config_never_crosses_gestora(self, client, db, seed):
        """Gestora A's BYO model config (provider/model/encrypted key) is NEVER
        applied to — nor visible for — gestora B. Admin-only by role; the
        per-call LLM resolution is hard-keyed on gestora_id."""
        from services import llm, secrets

        # Admin sets a config (with a BYO key) for gestora A only.
        res = client.put(
            f"/api/admin/gestoras/{seed['gestora_a']['id']}/model-config",
            json={"llm_provider": "anthropic", "anthropic_api_key": "sk-ant-solo-alfa"},
            headers=auth(seed["admin"]),
        )
        assert res.status_code == 200
        assert "sk-ant-solo-alfa" not in res.text  # plaintext never echoed

        # B's config endpoint still reports the platform default (no row of its own).
        res_b = client.get(
            f"/api/admin/gestoras/{seed['gestora_b']['id']}/model-config",
            headers=auth(seed["admin"]),
        )
        assert res_b.json()["is_default"] is True

        # LLM resolution: A uses its override, B falls back to global — never A's.
        config_a = llm.resolve_config(seed["gestora_a"]["id"])
        config_b = llm.resolve_config(seed["gestora_b"]["id"])
        assert config_a.anthropic_api_key == "sk-ant-solo-alfa"
        assert config_b.anthropic_api_key != "sk-ant-solo-alfa"
        assert config_b.llm_provider == "ollama"

        # The stored key is encrypted at rest, scoped to A's row only.
        rows_a = db.select("gestora_model_config", gestora_id=seed["gestora_a"]["id"])
        rows_b = db.select("gestora_model_config", gestora_id=seed["gestora_b"]["id"])
        assert rows_a and rows_b == []
        assert secrets.decrypt(rows_a[-1]["anthropic_api_key_enc"]) == "sk-ant-solo-alfa"


# ---------------------------------------------------------------------------
# 8. Collaboration / sharing (012_collaboration.sql) — never crosses gestoras
# ---------------------------------------------------------------------------

class TestShareIsolation:
    def test_share_never_crosses_gestora(self, client, db, seed):
        """A request owned in gestora A can NEVER be shared with — nor leaked to
        — a gestora B user, at CREATE time or ACCESS time (the inviolable rule).

        The colleague picker is also gestora-siloed, so the cross-gestora user
        is never even offered as a candidate sharee.
        """
        # A gestora-A request.
        request_row = db.insert(
            "requests",
            {
                "fund_id": seed["fund_a"]["id"],
                "user_id": seed["client_a"]["id"],
                "doc_type": DOC_TYPE,
                "freetext": "x",
                "language": "es",
                "status": "review_pending",
                "requires_counsel": False,
            },
        )
        request_id = request_row["id"]

        # CREATE time: the B user is rejected (404, no leak) and no row is made.
        res = client.post(
            f"/api/requests/{request_id}/shares",
            json={"user_id": seed["client_b"]["id"]},
            headers=auth(seed["client_a"]),
        )
        assert res.status_code == 404
        assert db.select("request_shares", request_id=request_id) == []

        # The picker never offers the cross-gestora user.
        colleagues = client.get("/api/my/colleagues", headers=auth(seed["client_a"])).json()
        assert all(c["id"] != seed["client_b"]["id"] for c in colleagues)

        # ACCESS time: even a forged cross-gestora share row grants nothing.
        db.insert(
            "request_shares",
            {
                "request_id": request_id,
                "gestora_id": seed["gestora_b"]["id"],
                "shared_with_user_id": seed["client_b"]["id"],
                "shared_by": seed["client_a"]["id"],
            },
        )
        leaked = client.get(f"/api/requests/{request_id}", headers=auth(seed["client_b"]))
        assert leaked.status_code == 404
