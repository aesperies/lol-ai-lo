"""GDPR retention tests (improvement #10): sweep semantics (delivered + old
only, per-gestora months, audit_log untouched) and the admin endpoints."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from services import retention, storage
from tests.conftest import auth


def _iso_months_ago(months: float) -> str:
    return (
        datetime.now(timezone.utc) - timedelta(days=months * 30.4375)
    ).isoformat()


def _make_request(
    db,
    seed: dict[str, Any],
    *,
    fund_key: str = "fund_a",
    user_key: str = "client_a",
    status: str = "delivered",
    months_ago: float = 70,
    n_docs: int = 2,
) -> tuple[dict[str, Any], list[str]]:
    """Insert one request with stored documents directly into the dev store."""
    row = db.insert(
        "requests",
        {
            "fund_id": seed[fund_key]["id"],
            "user_id": seed[user_key]["id"],
            "doc_type": "Acta de Reunión del Consejo",
            "freetext": "x" * 60,
            "status": status,
            "requires_counsel": False,
            "created_at": _iso_months_ago(months_ago),
        },
    )
    keys = []
    for i in range(n_docs):
        key = storage.save(
            f"gestoras/{seed[fund_key]['gestora_id']}/retention/{row['id']}/doc{i}.docx",
            b"PK\x03\x04 fake docx bytes",
        )
        db.insert(
            "documents",
            {
                "request_id": row["id"],
                "version_type": "draft" if i == 0 else "final",
                "file_path": key,
                "precedent_version_id": None,
                "uploaded_by": None,
            },
        )
        keys.append(key)
    return row, keys


def _file_exists(key: str) -> bool:
    try:
        storage.read(key)
        return True
    except FileNotFoundError:
        return False


class TestRetentionSweep:
    def test_sweeps_only_old_delivered_requests(self, db, seed):
        old_delivered, old_keys = _make_request(db, seed, months_ago=70)
        recent_delivered, recent_keys = _make_request(db, seed, months_ago=2)
        old_pending, pending_keys = _make_request(
            db, seed, months_ago=70, status="counsel_review"
        )

        counts = retention.run_retention_sweep(db)

        assert counts["requests_swept"] == 1
        assert counts["documents_deleted"] == 2
        assert counts["files_deleted"] == 2

        # Old delivered: documents + files gone, request row KEPT (tombstone).
        assert db.select("documents", request_id=old_delivered["id"]) == []
        assert all(not _file_exists(k) for k in old_keys)
        assert db.get("requests", old_delivered["id"]) is not None

        # Recent delivered and non-delivered: untouched.
        assert len(db.select("documents", request_id=recent_delivered["id"])) == 2
        assert all(_file_exists(k) for k in recent_keys)
        assert len(db.select("documents", request_id=old_pending["id"])) == 2
        assert all(_file_exists(k) for k in pending_keys)

    def test_respects_per_gestora_months(self, db, seed):
        # Same age (70 months) for both gestoras; A keeps the 60-month default
        # (-> swept), B has an explicit 120-month policy (-> kept).
        db.insert(
            "data_retention_policies",
            {"gestora_id": seed["gestora_b"]["id"], "months": 120},
        )
        req_a, keys_a = _make_request(db, seed, months_ago=70)
        req_b, keys_b = _make_request(
            db, seed, fund_key="fund_b", user_key="client_b", months_ago=70
        )

        counts = retention.run_retention_sweep(db)

        assert counts["requests_swept"] == 1
        assert db.select("documents", request_id=req_a["id"]) == []
        assert all(not _file_exists(k) for k in keys_a)
        assert len(db.select("documents", request_id=req_b["id"])) == 2
        assert all(_file_exists(k) for k in keys_b)

    def test_never_touches_audit_log(self, db, seed):
        _make_request(db, seed, months_ago=70)
        db.insert(
            "audit_log",
            {
                "user_id": seed["client_a"]["id"],
                "user_role": "client",
                "gestora_id": seed["gestora_a"]["id"],
                "action": "document_requested",
                "resource_type": "request",
                "resource_id": "r-old",
                "metadata": {},
                "ip_address": None,
            },
        )
        before = db.select("audit_log")
        retention.run_retention_sweep(db)
        assert db.select("audit_log") == before

    def test_keeps_files_referenced_by_precedent_library(self, db, seed):
        row, keys = _make_request(db, seed, months_ago=70, n_docs=1)
        # The delivered output became a precedent version (Exit A/B flow):
        # the SHARED file must survive even though the documents row goes.
        precedent = db.insert(
            "precedents",
            {
                "gestora_id": seed["gestora_a"]["id"],
                "fund_id": seed["fund_a"]["id"],
                "doc_type": row["doc_type"],
                "language": "es",
                "source": "validated_output",
            },
        )
        db.insert(
            "precedent_versions",
            {
                "precedent_id": precedent["id"],
                "version_number": 1,
                "file_path": keys[0],
                "status": "active",
                "rag_weight": 1.0,
            },
        )

        counts = retention.run_retention_sweep(db)

        assert counts["files_kept_as_precedent"] == 1
        assert counts["files_deleted"] == 0
        assert db.select("documents", request_id=row["id"]) == []
        assert _file_exists(keys[0])

    def test_sweep_is_idempotent(self, db, seed):
        _make_request(db, seed, months_ago=70)
        first = retention.run_retention_sweep(db)
        second = retention.run_retention_sweep(db)
        assert first["requests_swept"] == 1
        assert second == {
            "requests_swept": 0,
            "documents_deleted": 0,
            "files_deleted": 0,
            "files_kept_as_precedent": 0,
        }


class TestRetentionEndpoints:
    def test_get_default_policy(self, client, seed):
        response = client.get(
            f"/api/admin/gestoras/{seed['gestora_a']['id']}/retention",
            headers=auth(seed["admin"]),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["months"] == retention.DEFAULT_RETENTION_MONTHS
        assert body["is_default"] is True

    def test_put_then_get_roundtrip_and_audit(self, client, db, seed):
        gestora_id = seed["gestora_a"]["id"]
        put = client.put(
            f"/api/admin/gestoras/{gestora_id}/retention",
            json={"months": 24},
            headers=auth(seed["admin"]),
        )
        assert put.status_code == 200, put.text
        assert put.json()["months"] == 24
        assert put.json()["is_default"] is False

        got = client.get(
            f"/api/admin/gestoras/{gestora_id}/retention", headers=auth(seed["admin"])
        ).json()
        assert got["months"] == 24

        # Updating again upserts (single row per gestora) and is audited.
        client.put(
            f"/api/admin/gestoras/{gestora_id}/retention",
            json={"months": 36},
            headers=auth(seed["admin"]),
        )
        assert len(db.select("data_retention_policies", gestora_id=gestora_id)) == 1
        entries = db.select("audit_log", action="retention_policy_updated")
        assert len(entries) == 2
        assert entries[-1]["metadata"] == {"months": 36, "previous_months": 24}

    @pytest.mark.parametrize("months", [5, 121, 0, -1])
    def test_put_validation_bounds(self, client, seed, months):
        response = client.put(
            f"/api/admin/gestoras/{seed['gestora_a']['id']}/retention",
            json={"months": months},
            headers=auth(seed["admin"]),
        )
        assert response.status_code == 422

    def test_unknown_gestora_404(self, client, seed):
        assert (
            client.get(
                "/api/admin/gestoras/nope/retention", headers=auth(seed["admin"])
            ).status_code
            == 404
        )

    def test_endpoints_admin_only(self, client, seed):
        gestora_id = seed["gestora_a"]["id"]
        for user_key in ("client_a", "counsel"):
            headers = auth(seed[user_key])
            assert (
                client.get(f"/api/admin/gestoras/{gestora_id}/retention", headers=headers).status_code
                == 403
            )
            assert (
                client.put(
                    f"/api/admin/gestoras/{gestora_id}/retention",
                    json={"months": 12},
                    headers=headers,
                ).status_code
                == 403
            )
            assert (
                client.post("/api/admin/retention/sweep", headers=headers).status_code == 403
            )

    def test_sweep_endpoint_returns_counts_and_audits(self, client, db, seed):
        _make_request(db, seed, months_ago=70)
        response = client.post("/api/admin/retention/sweep", headers=auth(seed["admin"]))
        assert response.status_code == 200, response.text
        counts = response.json()
        assert counts["requests_swept"] == 1
        entries = db.select("audit_log", action="retention_sweep")
        assert len(entries) == 1
        assert entries[0]["metadata"] == counts
