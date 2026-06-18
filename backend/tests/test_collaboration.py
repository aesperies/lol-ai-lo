"""Collaboration / sharing tests (012_collaboration.sql).

Proves the read-only share semantics AND the inviolable single-gestora rule:
an owner shares a request / tabular review with a SAME-gestora colleague, who
gains READ access (view + download / CSV export) but is blocked from every
owner-only action; a different same-gestora user who was NOT shared with gets
404; and a user from ANOTHER gestora can NEVER be added as a sharee nor gain
access. The suite never reaches the network (same conftest seams as the rest).
"""
from __future__ import annotations

from typing import Any

import pytest

from models.schema import DocumentVersionType, TabularReviewStatus
from services import db as dbmod, storage
from tests.conftest import DOC_TYPE, auth, seed_precedent


# ---------------------------------------------------------------------------
# Extra fixtures: a second client in gestora A (a "colleague") and helpers.
# ---------------------------------------------------------------------------

@pytest.fixture()
def colleague_a(db: dbmod.DevStore, seed: dict[str, Any]) -> dict[str, Any]:
    """A second CLIENT user in gestora A — the colleague to share WITH."""
    return db.insert(
        "users",
        {"email": "colega@alfa.es", "role": "client", "gestora_id": seed["gestora_a"]["id"]},
    )


@pytest.fixture()
def stranger_a(db: dbmod.DevStore, seed: dict[str, Any]) -> dict[str, Any]:
    """A THIRD client in gestora A who is never shared with (must get 404)."""
    return db.insert(
        "users",
        {"email": "ajeno@alfa.es", "role": "client", "gestora_id": seed["gestora_a"]["id"]},
    )


def _make_request_document(
    db: dbmod.DevStore, *, gestora_id: str, fund_id: str, user_id: str, text: str
) -> dict[str, Any]:
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


def _create_review(client, db: dbmod.DevStore, owner: dict[str, Any], *, gestora, fund) -> str:
    """Create a tabular review owned by ``owner`` over one in-silo precedent."""
    _, version = seed_precedent(db, gestora_id=gestora["id"], text="PRECEDENTE")
    payload = {
        "title": "Comparativa",
        "columns": [
            {"name": "Importe", "question": "¿Importe?", "col_type": "monetary"},
        ],
        "documents": [{"source_kind": "precedent_version", "source_id": version["id"]}],
    }
    res = client.post("/api/tabular-reviews", json=payload, headers=auth(owner))
    assert res.status_code == 201, res.text
    return res.json()["id"]


# ===========================================================================
# /api/my/colleagues
# ===========================================================================

class TestColleagues:
    def test_lists_same_gestora_clients_excluding_self(self, client, seed, colleague_a):
        res = client.get("/api/my/colleagues", headers=auth(seed["client_a"]))
        assert res.status_code == 200
        ids = {c["id"] for c in res.json()}
        assert colleague_a["id"] in ids
        assert seed["client_a"]["id"] not in ids  # excludes self

    def test_is_gestora_siloed(self, client, seed, colleague_a):
        """A gestora B client never appears in gestora A's colleague picker."""
        res = client.get("/api/my/colleagues", headers=auth(seed["client_a"]))
        ids = {c["id"] for c in res.json()}
        assert seed["client_b"]["id"] not in ids
        # And B's own picker never sees gestora A users.
        res_b = client.get("/api/my/colleagues", headers=auth(seed["client_b"]))
        ids_b = {c["id"] for c in res_b.json()}
        assert colleague_a["id"] not in ids_b
        assert seed["client_a"]["id"] not in ids_b


# ===========================================================================
# Request sharing — read access + owner-only gating
# ===========================================================================

class TestRequestSharing:
    def test_owner_shares_then_collaborator_reads_everything(
        self, client, db, seed, wf, colleague_a
    ):
        request_id, _ = wf.to_review_pending()  # owned by client_a

        # Share with the colleague.
        res = client.post(
            f"/api/requests/{request_id}/shares",
            json={"user_id": colleague_a["id"]},
            headers=auth(seed["client_a"]),
        )
        assert res.status_code == 201, res.text
        assert res.json()["gestora_id"] == seed["gestora_a"]["id"]

        col = auth(colleague_a)
        # GET the request, flagged shared_with_me.
        got = client.get(f"/api/requests/{request_id}", headers=col)
        assert got.status_code == 200
        assert got.json()["shared_with_me"] is True
        assert got.json()["is_owner"] is False
        assert got.json()["shared_by_email"] == seed["client_a"]["email"]

        # Documents (download + html), reviews — all readable.
        assert client.get(
            f"/api/requests/{request_id}/documents/draft/download", headers=col
        ).status_code == 200
        assert client.get(
            f"/api/requests/{request_id}/documents/draft/html", headers=col
        ).status_code == 200
        assert client.get(f"/api/requests/{request_id}/reviews", headers=col).status_code == 200
        assert client.get(f"/api/requests/{request_id}/refinements", headers=col).status_code == 200

        # It shows up in the colleague's list, flagged shared (not owned).
        listed = client.get("/api/requests", headers=col).json()
        mine = next(r for r in listed if r["id"] == request_id)
        assert mine["shared_with_me"] is True and mine["is_owner"] is False

    def test_unshared_same_gestora_user_gets_404(self, client, db, seed, wf, stranger_a):
        """A same-gestora user who was NOT shared with cannot see the request."""
        request_id, _ = wf.to_review_pending()
        st = auth(stranger_a)
        assert client.get(f"/api/requests/{request_id}", headers=st).status_code == 404
        assert client.get(
            f"/api/requests/{request_id}/documents/draft/download", headers=st
        ).status_code == 404
        # And it does not appear in their list.
        listed = client.get("/api/requests", headers=st).json()
        assert all(r["id"] != request_id for r in listed)

    def test_collaborator_blocked_from_owner_only_actions(
        self, client, db, seed, wf, colleague_a
    ):
        request_id, _ = wf.to_review_pending()
        client.post(
            f"/api/requests/{request_id}/shares",
            json={"user_id": colleague_a["id"]},
            headers=auth(seed["client_a"]),
        )
        col = auth(colleague_a)
        # Exit A acknowledge — owner only.
        assert client.post(
            f"/api/requests/{request_id}/exit-a/acknowledge",
            json={"acknowledged": True},
            headers=col,
        ).status_code == 403
        # Exit B — owner only.
        assert client.post(f"/api/requests/{request_id}/exit-b", headers=col).status_code == 403
        # Refinement — owner only.
        assert client.post(
            f"/api/requests/{request_id}/refinements",
            json={"instruction": "cambia algo"},
            headers=col,
        ).status_code == 403
        # Managing shares — owner only.
        assert client.post(
            f"/api/requests/{request_id}/shares",
            json={"user_id": seed["client_a"]["id"]},
            headers=col,
        ).status_code in (400, 403)
        assert client.delete(
            f"/api/requests/{request_id}/shares/{colleague_a['id']}", headers=col
        ).status_code == 403
        # But the OWNER may still manage the share list (re-add the colleague).
        assert client.post(
            f"/api/requests/{request_id}/shares",
            json={"user_id": colleague_a["id"]},
            headers=auth(seed["client_a"]),
        ).status_code == 201

    def test_self_share_rejected(self, client, db, seed, wf):
        request_id, _ = wf.to_review_pending()
        res = client.post(
            f"/api/requests/{request_id}/shares",
            json={"user_id": seed["client_a"]["id"]},
            headers=auth(seed["client_a"]),
        )
        assert res.status_code == 400

    def test_idempotent_share(self, client, db, seed, wf, colleague_a):
        request_id, _ = wf.to_review_pending()
        body = {"user_id": colleague_a["id"]}
        first = client.post(
            f"/api/requests/{request_id}/shares", json=body, headers=auth(seed["client_a"])
        )
        second = client.post(
            f"/api/requests/{request_id}/shares", json=body, headers=auth(seed["client_a"])
        )
        assert first.status_code == 201 and second.status_code == 201
        assert first.json()["id"] == second.json()["id"]
        shares = client.get(
            f"/api/requests/{request_id}/shares", headers=auth(seed["client_a"])
        ).json()
        assert len(shares) == 1

    def test_unshare_revokes_access(self, client, db, seed, wf, colleague_a):
        request_id, _ = wf.to_review_pending()
        client.post(
            f"/api/requests/{request_id}/shares",
            json={"user_id": colleague_a["id"]},
            headers=auth(seed["client_a"]),
        )
        col = auth(colleague_a)
        assert client.get(f"/api/requests/{request_id}", headers=col).status_code == 200
        assert client.delete(
            f"/api/requests/{request_id}/shares/{colleague_a['id']}",
            headers=auth(seed["client_a"]),
        ).status_code == 204
        # Access is gone -> 404 (no leak).
        assert client.get(f"/api/requests/{request_id}", headers=col).status_code == 404

    # --- THE INVIOLABLE RULE: cross-gestora can never be added nor gain access.
    def test_cannot_share_request_with_other_gestora_user(self, client, db, seed, wf):
        request_id, _ = wf.to_review_pending()  # gestora A
        res = client.post(
            f"/api/requests/{request_id}/shares",
            json={"user_id": seed["client_b"]["id"]},  # gestora B!
            headers=auth(seed["client_a"]),
        )
        # 404 (no leak that the B user exists) and NO share row created.
        assert res.status_code == 404
        assert db.select("request_shares", request_id=request_id) == []

    def test_other_gestora_user_never_gains_access_even_with_forged_row(
        self, client, db, seed, wf
    ):
        """Defence in depth: even if a cross-gestora share row is forced into the
        store, the ACCESS check still denies it (share only counts when sharee
        and resource are the same gestora)."""
        request_id, _ = wf.to_review_pending()  # gestora A
        db.insert(
            "request_shares",
            {
                "request_id": request_id,
                "gestora_id": seed["gestora_b"]["id"],  # mismatched on purpose
                "shared_with_user_id": seed["client_b"]["id"],
                "shared_by": seed["client_a"]["id"],
            },
        )
        assert client.get(
            f"/api/requests/{request_id}", headers=auth(seed["client_b"])
        ).status_code == 404


# ===========================================================================
# Tabular-review sharing — read access (view + CSV export) + owner-only gating
# ===========================================================================

class TestTabularSharing:
    def test_owner_shares_then_collaborator_views_and_exports(
        self, client, db, seed, colleague_a
    ):
        review_id = _create_review(
            client, db, seed["client_a"], gestora=seed["gestora_a"], fund=seed["fund_a"]
        )
        res = client.post(
            f"/api/tabular-reviews/{review_id}/shares",
            json={"user_id": colleague_a["id"]},
            headers=auth(seed["client_a"]),
        )
        assert res.status_code == 201

        col = auth(colleague_a)
        got = client.get(f"/api/tabular-reviews/{review_id}", headers=col)
        assert got.status_code == 200
        assert got.json()["shared_with_me"] is True
        assert got.json()["is_owner"] is False
        # CSV export by the collaborator.
        csv = client.get(f"/api/tabular-reviews/{review_id}/export.csv", headers=col)
        assert csv.status_code == 200
        assert "Documento" in csv.text
        # Shows up flagged in their list.
        listed = client.get("/api/tabular-reviews", headers=col).json()
        mine = next(r for r in listed if r["id"] == review_id)
        assert mine["shared_with_me"] is True and mine["is_owner"] is False

    def test_unshared_same_gestora_user_gets_404(self, client, db, seed, stranger_a):
        review_id = _create_review(
            client, db, seed["client_a"], gestora=seed["gestora_a"], fund=seed["fund_a"]
        )
        st = auth(stranger_a)
        assert client.get(f"/api/tabular-reviews/{review_id}", headers=st).status_code == 404
        assert client.get(
            f"/api/tabular-reviews/{review_id}/export.csv", headers=st
        ).status_code == 404

    def test_collaborator_blocked_from_owner_only_actions(
        self, client, db, seed, colleague_a
    ):
        review_id = _create_review(
            client, db, seed["client_a"], gestora=seed["gestora_a"], fund=seed["fund_a"]
        )
        client.post(
            f"/api/tabular-reviews/{review_id}/shares",
            json={"user_id": colleague_a["id"]},
            headers=auth(seed["client_a"]),
        )
        col = auth(colleague_a)
        assert client.post(f"/api/tabular-reviews/{review_id}/run", headers=col).status_code == 403
        assert client.post(
            f"/api/tabular-reviews/{review_id}/columns",
            json={"name": "X", "question": "¿X?", "col_type": "text"},
            headers=col,
        ).status_code == 403
        # Managing the share list — owner only.
        assert client.delete(
            f"/api/tabular-reviews/{review_id}/shares/{colleague_a['id']}", headers=col
        ).status_code == 403

    def test_self_share_rejected(self, client, db, seed):
        review_id = _create_review(
            client, db, seed["client_a"], gestora=seed["gestora_a"], fund=seed["fund_a"]
        )
        res = client.post(
            f"/api/tabular-reviews/{review_id}/shares",
            json={"user_id": seed["client_a"]["id"]},
            headers=auth(seed["client_a"]),
        )
        assert res.status_code == 400

    def test_unshare_revokes_access(self, client, db, seed, colleague_a):
        review_id = _create_review(
            client, db, seed["client_a"], gestora=seed["gestora_a"], fund=seed["fund_a"]
        )
        client.post(
            f"/api/tabular-reviews/{review_id}/shares",
            json={"user_id": colleague_a["id"]},
            headers=auth(seed["client_a"]),
        )
        col = auth(colleague_a)
        assert client.get(f"/api/tabular-reviews/{review_id}", headers=col).status_code == 200
        assert client.delete(
            f"/api/tabular-reviews/{review_id}/shares/{colleague_a['id']}",
            headers=auth(seed["client_a"]),
        ).status_code == 204
        assert client.get(f"/api/tabular-reviews/{review_id}", headers=col).status_code == 404

    # --- THE INVIOLABLE RULE for tabular reviews.
    def test_cannot_share_review_with_other_gestora_user(self, client, db, seed):
        review_id = _create_review(
            client, db, seed["client_a"], gestora=seed["gestora_a"], fund=seed["fund_a"]
        )
        res = client.post(
            f"/api/tabular-reviews/{review_id}/shares",
            json={"user_id": seed["client_b"]["id"]},  # gestora B!
            headers=auth(seed["client_a"]),
        )
        assert res.status_code == 404
        assert db.select("tabular_review_shares", review_id=review_id) == []

    def test_other_gestora_user_never_gains_access_even_with_forged_row(
        self, client, db, seed
    ):
        review_id = _create_review(
            client, db, seed["client_a"], gestora=seed["gestora_a"], fund=seed["fund_a"]
        )
        db.insert(
            "tabular_review_shares",
            {
                "review_id": review_id,
                "gestora_id": seed["gestora_b"]["id"],
                "shared_with_user_id": seed["client_b"]["id"],
                "shared_by": seed["client_a"]["id"],
            },
        )
        assert client.get(
            f"/api/tabular-reviews/{review_id}", headers=auth(seed["client_b"])
        ).status_code == 404
