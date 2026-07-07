"""Workflow guardrail tests: status machine, Exit A/B rules, audit + usage."""
from __future__ import annotations

import pytest

from models.schema import PrecedentVersionStatus
from tests.conftest import auth, seed_precedent


def _audit_actions(db) -> list[str]:
    return [row["action"] for row in db.unscoped_select("audit_log")]


def _usage_types(db) -> list[str]:
    return [row["event_type"] for row in db.unscoped_select("usage_events")]


class TestGenerationGuards:
    def test_generate_blocked_before_confirmation(self, wf, db, seed):
        request_id = wf.create()
        assert wf.generate(request_id).status_code == 409  # still 'parsing'
        wf.parse(request_id)
        assert wf.generate(request_id).status_code == 409  # parsed but unconfirmed

    def test_confirm_blocked_when_not_generation_ready(self, wf):
        wf.llm["ready"] = False
        wf.llm["confidence"] = 0.4
        request_id = wf.create()
        wf.parse(request_id)
        assert wf.confirm(request_id).status_code == 422

    def test_generate_returns_503_when_llm_unconfigured(self, client, seed, fake_llm, wf, monkeypatch):
        import config

        request_id = wf.create()
        wf.parse(request_id)
        wf.confirm(request_id)
        # Default ollama is always configured; switch to the cloud provider
        # with no key to exercise the fail-fast 503 gate.
        monkeypatch.setattr(config.get_settings(), "llm_provider", "anthropic")
        monkeypatch.setattr(config.get_settings(), "anthropic_api_key", "")
        response = wf.generate(request_id)
        assert response.status_code == 503
        assert "anthropic" in response.json()["detail"].lower()
        # Status untouched: the request remains re-runnable once configured.
        assert db_status(client, seed, request_id) == "confirmed"

    def test_confirm_with_edits_logs_params_edited(self, wf, db):
        request_id = wf.create()
        parsed = wf.parse(request_id).json()["parsed_params"]
        edited = dict(parsed, jurisdiction="Luxemburgo")
        assert wf.confirm(request_id, edited=edited).status_code == 200
        actions = _audit_actions(db)
        assert "params_edited" in actions
        assert "params_confirmed" in actions


def db_status(client, seed, request_id: str) -> str:
    return client.get(f"/api/requests/{request_id}", headers=auth(seed["client_a"])).json()["status"]


class TestExitA:
    def test_full_exit_a_flow(self, wf, client, db, seed):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA ACTA")
        request_id, generated = wf.to_review_pending()
        headers = auth(seed["client_a"])

        assert generated["rag_level"] == 0
        assert generated["redline"] is not None
        assert db_status(client, seed, request_id) == "review_pending"

        # Both downloads available at review.
        assert client.get(f"/api/requests/{request_id}/documents/draft/download", headers=headers).status_code == 200
        assert client.get(f"/api/requests/{request_id}/documents/redline/download", headers=headers).status_code == 200

        # Download before acknowledgment is rejected (guardrail 9).
        assert client.post(f"/api/requests/{request_id}/exit-a/download", headers=headers).status_code == 409
        # Acknowledgment requires the explicit checkbox value.
        assert (
            client.post(
                f"/api/requests/{request_id}/exit-a/acknowledge", json={"acknowledged": False}, headers=headers
            ).status_code
            == 422
        )
        acknowledged = client.post(
            f"/api/requests/{request_id}/exit-a/acknowledge", json={"acknowledged": True}, headers=headers
        )
        assert acknowledged.status_code == 200
        assert acknowledged.json()["exit_a_acknowledged_at"] is not None

        download = client.post(f"/api/requests/{request_id}/exit-a/download", headers=headers)
        assert download.status_code == 200
        assert download.headers["content-type"].startswith("application/vnd.openxmlformats")
        assert db_status(client, seed, request_id) == "delivered"

        # Usage events for billing (YYYY-MM period).
        assert sorted(_usage_types(db)) == ["document_generated", "exit_a"]
        assert all(len(e["billing_period"]) == 7 for e in db.unscoped_select("usage_events"))

        # Exit A output becomes a precedent CANDIDATE (draft, admin approval pending).
        candidates = db.unscoped_select("precedents", source="validated_output")
        assert len(candidates) == 1
        versions = db.select("precedent_versions", precedent_id=candidates[0]["id"])
        assert versions[0]["status"] == PrecedentVersionStatus.draft.value
        assert versions[0]["rag_weight"] == 0.0

        for action in (
            "document_requested",
            "params_confirmed",
            "document_generated",
            "redline_generated",
            "draft_downloaded",
            "redline_downloaded",
            "exit_a_acknowledged",
            "exit_a_downloaded",
            "precedent_version_created",
        ):
            assert action in _audit_actions(db), action

    def test_missing_markers_block_exit_a(self, wf, client, db, seed):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        wf.llm["missing"] = True
        request_id, _ = wf.to_review_pending()
        headers = auth(seed["client_a"])

        acknowledge = client.post(
            f"/api/requests/{request_id}/exit-a/acknowledge", json={"acknowledged": True}, headers=headers
        )
        assert acknowledge.status_code == 409
        assert client.post(f"/api/requests/{request_id}/exit-a/download", headers=headers).status_code == 409
        # Exit B remains available.
        assert client.post(f"/api/requests/{request_id}/exit-b", headers=headers).status_code == 200


class TestLevel3ForcesExitB:
    def test_level3_generation_forces_counsel(self, wf, client, db, seed):
        # No precedents anywhere -> Level 3.
        request_id, generated = wf.to_review_pending()
        headers = auth(seed["client_a"])

        assert generated["rag_level"] == 3
        assert generated["requires_counsel"] is True
        assert generated["redline"] is None  # no precedent base to diff against
        assert generated["warning"] is not None

        # Exit A endpoints reject (guardrail 10).
        assert (
            client.post(
                f"/api/requests/{request_id}/exit-a/acknowledge", json={"acknowledged": True}, headers=headers
            ).status_code
            == 409
        )
        assert client.post(f"/api/requests/{request_id}/exit-a/download", headers=headers).status_code == 409

    def test_full_exit_b_flow(self, wf, client, db, seed):
        request_id, _ = wf.to_review_pending()  # Level 3
        client_headers = auth(seed["client_a"])
        counsel_headers = auth(seed["counsel"])

        assert client.post(f"/api/requests/{request_id}/exit-b", headers=client_headers).status_code == 200
        assert db_status(client, seed, request_id) == "counsel_review"

        assert client.post(f"/api/requests/{request_id}/review/start", headers=counsel_headers).status_code == 200
        edit = client.post(
            f"/api/requests/{request_id}/counsel/edit",
            json={"text": "ACTA REVISADA POR ABOGADO\nTexto corregido.", "comment": "Ajustes menores"},
            headers=counsel_headers,
        )
        assert edit.status_code == 200

        validated = client.post(f"/api/requests/{request_id}/validate", headers=counsel_headers)
        assert validated.status_code == 200
        assert validated.json()["status"] == "validated"

        # Counsel-validated output enters the library automatically as ACTIVE.
        precedents = db.unscoped_select("precedents", source="validated_output")
        assert len(precedents) == 1
        version = db.select("precedent_versions", precedent_id=precedents[0]["id"])[0]
        assert version["status"] == PrecedentVersionStatus.active.value
        assert version["rag_weight"] == 1.0

        # Client downloads the final -> delivered.
        final = client.get(
            f"/api/requests/{request_id}/documents/final/download", headers=client_headers
        )
        assert final.status_code == 200
        assert db_status(client, seed, request_id) == "delivered"

        assert sorted(_usage_types(db)) == ["document_generated", "exit_b_requested", "exit_b_validated"]
        for action in (
            "counsel_requested",
            "counsel_notified",
            "counsel_review_started",
            "counsel_edit_inline",
            "document_validated",
            "final_downloaded",
            "precedent_version_created",
            "precedent_activated",
        ):
            assert action in _audit_actions(db), action

    def test_counsel_upload_flow(self, wf, client, db, seed):
        from services import docx_renderer

        request_id, _ = wf.to_review_pending()
        client.post(f"/api/requests/{request_id}/exit-b", headers=auth(seed["client_a"]))
        upload = client.post(
            f"/api/requests/{request_id}/counsel/upload",
            files={
                "file": (
                    "edited.docx",
                    docx_renderer.render_docx("VERSIÓN EDITADA POR ABOGADO"),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
            headers=auth(seed["counsel"]),
        )
        assert upload.status_code == 200
        assert "counsel_edit_uploaded" in _audit_actions(db)


class TestStateMachine:
    def test_invalid_transitions_rejected(self, wf, client, db, seed):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE")
        request_id, _ = wf.to_review_pending()
        headers = auth(seed["client_a"])

        # Cannot re-generate once review is pending.
        assert wf.generate(request_id).status_code == 409
        # Cannot validate a request that is not in counsel review.
        assert client.post(f"/api/requests/{request_id}/validate", headers=auth(seed["counsel"])).status_code == 409

        # Deliver via Exit A, then Exit B must be rejected.
        client.post(f"/api/requests/{request_id}/exit-a/acknowledge", json={"acknowledged": True}, headers=headers)
        client.post(f"/api/requests/{request_id}/exit-a/download", headers=headers)
        assert client.post(f"/api/requests/{request_id}/exit-b", headers=headers).status_code == 409

    def test_final_download_requires_validated_or_delivered(self, wf, client, seed):
        request_id, _ = wf.to_review_pending()
        response = client.get(
            f"/api/requests/{request_id}/documents/final/download", headers=auth(seed["client_a"])
        )
        assert response.status_code == 409


class TestAuditImmutability:
    def test_audit_log_is_append_only(self, wf, db):
        wf.create()
        audit_row = db.unscoped_select("audit_log")[0]
        with pytest.raises(PermissionError):
            db.update("audit_log", audit_row["id"], {"action": "document_validated"})
        with pytest.raises(PermissionError):
            db.delete("audit_log", audit_row["id"])
