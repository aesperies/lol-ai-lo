"""Account & security: MFA status mirror + GDPR data-subject rights (A & B).

Covers: the MFA status mirror endpoint + profile flag; export returns ONLY the
requesting user's data (and never another gestora's); anonymise/erase never
touch audit_log and remove the user's own rows/files; admin-triggered deletion;
and the confirmation interlock.
"""
from __future__ import annotations

import json

from models.schema import DATA_DELETE_CONFIRMATION
from services import db as dbmod, storage
from tests.conftest import auth


def _audit_snapshot(db: dbmod.DevStore) -> list[dict]:
    return db.select("audit_log")


# ---------------------------------------------------------------------------
# Feature A — MFA status mirror
# ---------------------------------------------------------------------------

class TestMfaMirror:
    def test_profile_exposes_mfa_flag_default_false(self, client, seed):
        res = client.get("/api/me", headers=auth(seed["client_a"]))
        assert res.status_code == 200
        body = res.json()
        assert body["id"] == seed["client_a"]["id"]
        assert body["mfa_enabled"] is False

    def test_enable_then_disable_mirror(self, client, seed, db):
        on = client.post(
            "/api/me/mfa", json={"enabled": True}, headers=auth(seed["client_a"])
        )
        assert on.status_code == 200
        assert on.json()["mfa_enabled"] is True
        assert db.get("users", seed["client_a"]["id"])["mfa_enabled"] is True
        # Reflected in the profile.
        assert client.get("/api/me", headers=auth(seed["client_a"])).json()["mfa_enabled"] is True

        off = client.post(
            "/api/me/mfa", json={"enabled": False}, headers=auth(seed["client_a"])
        )
        assert off.json()["mfa_enabled"] is False

    def test_mfa_change_is_audited(self, client, seed, db):
        client.post("/api/me/mfa", json={"enabled": True}, headers=auth(seed["client_a"]))
        events = [e for e in db.select("audit_log") if e["action"] == "mfa_status_changed"]
        assert events
        assert events[-1]["metadata"]["enabled"] is True
        assert events[-1]["resource_id"] == seed["client_a"]["id"]

    def test_mfa_is_per_user(self, client, seed, db):
        client.post("/api/me/mfa", json={"enabled": True}, headers=auth(seed["client_a"]))
        # client_b is untouched.
        assert db.get("users", seed["client_b"]["id"])["mfa_enabled"] is False


# ---------------------------------------------------------------------------
# Feature B — Data export (Art. 15/20)
# ---------------------------------------------------------------------------

class TestExport:
    def test_export_returns_own_data(self, wf, client, seed):
        request_id, _ = wf.to_review_pending()
        res = client.get("/api/me/export", headers=auth(seed["client_a"]))
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("application/json")
        bundle = json.loads(res.content)
        assert bundle["user_id"] == seed["client_a"]["id"]
        assert any(r["id"] == request_id for r in bundle["requests"])
        # Profile included; documents metadata present.
        assert bundle["profile"]["email"] == seed["client_a"]["email"]
        assert isinstance(bundle["documents"], list)

    def test_export_excludes_other_gestora_data(self, wf, client, seed):
        """client_b's export must NOT contain client_a's request (isolation)."""
        request_a, _ = wf.to_review_pending(user=seed["client_a"], fund=seed["fund_a"])
        res_b = client.get("/api/me/export", headers=auth(seed["client_b"]))
        bundle_b = json.loads(res_b.content)
        assert all(r["id"] != request_a for r in bundle_b["requests"])
        assert bundle_b["user_id"] == seed["client_b"]["id"]

    def test_export_is_audited(self, client, seed, db):
        client.get("/api/me/export", headers=auth(seed["client_a"]))
        assert any(e["action"] == "data_exported" for e in db.select("audit_log"))


# ---------------------------------------------------------------------------
# Feature B — Deletion (Art. 17): anonymise / erase, audit immutability
# ---------------------------------------------------------------------------

class TestDeletion:
    def test_confirmation_required(self, client, seed):
        res = client.post(
            "/api/me/delete", json={"confirm": "wrong", "mode": "erase"},
            headers=auth(seed["client_a"]),
        )
        assert res.status_code == 422

    def test_anonymize_scrubs_pii_keeps_tombstone_and_audit(self, wf, client, seed, db):
        request_id, _ = wf.to_review_pending()
        audit_before = len(_audit_snapshot(db))
        assert db.get("requests", request_id)["freetext"] != "[erased]"

        res = client.post(
            "/api/me/delete",
            json={"confirm": DATA_DELETE_CONFIRMATION, "mode": "anonymize"},
            headers=auth(seed["client_a"]),
        )
        assert res.status_code == 200
        # Request row survives as a tombstone with scrubbed PII.
        row = db.get("requests", request_id)
        assert row is not None
        assert row["freetext"] == "[erased]"
        assert row["parsed_params"] is None
        # Profile email scrubbed.
        assert db.get("users", seed["client_a"]["id"])["email"].startswith("[erased]")
        # audit_log NEVER shrinks (append-only); the deletion itself adds a row.
        audit_after = _audit_snapshot(db)
        assert len(audit_after) >= audit_before
        assert any(e["action"] == "data_subject_deleted" for e in audit_after)

    def test_erase_removes_rows_and_files_but_not_audit(self, wf, client, seed, db):
        request_id, _ = wf.to_review_pending()
        docs = db.select("documents", request_id=request_id)
        assert docs
        file_path = docs[0]["file_path"]
        # The file exists before erasure.
        assert storage.read(file_path)
        audit_before = len(_audit_snapshot(db))

        res = client.post(
            "/api/me/delete",
            json={"confirm": DATA_DELETE_CONFIRMATION, "mode": "erase"},
            headers=auth(seed["client_a"]),
        )
        assert res.status_code == 200
        counts = res.json()
        assert counts["requests_erased"] >= 1
        # The request + its documents are gone.
        assert db.get("requests", request_id) is None
        assert db.select("documents", request_id=request_id) == []
        # The stored file is gone.
        try:
            storage.read(file_path)
            file_gone = False
        except Exception:
            file_gone = True
        assert file_gone
        # audit_log preserved (append-only): never fewer rows than before.
        assert len(_audit_snapshot(db)) >= audit_before

    def test_erase_does_not_touch_audit_log_rows(self, wf, client, seed, db):
        """Explicitly assert the pre-existing audit rows are all still present."""
        request_id, _ = wf.to_review_pending()
        ids_before = {e["id"] for e in db.select("audit_log")}
        client.post(
            "/api/me/delete",
            json={"confirm": DATA_DELETE_CONFIRMATION, "mode": "erase"},
            headers=auth(seed["client_a"]),
        )
        ids_after = {e["id"] for e in db.select("audit_log")}
        # Every prior audit row survives (append-only); only additions allowed.
        assert ids_before <= ids_after

    def test_admin_can_delete_for_a_user(self, wf, client, seed, db):
        request_id, _ = wf.to_review_pending(user=seed["client_a"], fund=seed["fund_a"])
        res = client.post(
            f"/api/admin/users/{seed['client_a']['id']}/delete",
            json={"confirm": DATA_DELETE_CONFIRMATION, "mode": "erase"},
            headers=auth(seed["admin"]),
        )
        assert res.status_code == 200
        assert db.get("requests", request_id) is None
        events = [e for e in db.select("audit_log") if e["action"] == "data_subject_deleted"]
        assert events and events[-1]["metadata"]["self_service"] is False

    def test_admin_delete_requires_confirmation(self, client, seed):
        res = client.post(
            f"/api/admin/users/{seed['client_a']['id']}/delete",
            json={"confirm": "nope", "mode": "erase"},
            headers=auth(seed["admin"]),
        )
        assert res.status_code == 422

    def test_admin_delete_unknown_user_404(self, client, seed):
        res = client.post(
            "/api/admin/users/missing/delete",
            json={"confirm": DATA_DELETE_CONFIRMATION, "mode": "erase"},
            headers=auth(seed["admin"]),
        )
        assert res.status_code == 404

    def test_client_cannot_admin_delete(self, client, seed):
        res = client.post(
            f"/api/admin/users/{seed['client_b']['id']}/delete",
            json={"confirm": DATA_DELETE_CONFIRMATION, "mode": "erase"},
            headers=auth(seed["client_a"]),
        )
        assert res.status_code == 403
