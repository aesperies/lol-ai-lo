"""GDPR data-subject rights (RGPD arts. 15/17) — export + erasure.

Complements the per-gestora retention sweep (services/retention.py) with
INDIVIDUAL data-subject rights:

- :func:`export_user_data` — Art. 15/20 access & portability. Returns a single
  JSON-serialisable dict with the user's profile, their own requests, the
  documents metadata for those requests, and the tabular reviews they created.
  Everything is gestora-scoped to what the user can access; NO other gestora's
  data is ever included (the inviolable isolation rule, SPEC guardrails 1 & 3).

- :func:`delete_user_data` — Art. 17 erasure. Two modes:
    * ``anonymize`` (default) — scrubs PII on the user's own rows (request
      freetext / parsed params / structured fields, and the user's email) but
      keeps the row skeletons as tombstones, exactly like the retention sweep.
    * ``erase`` — deletes the user's own requests/documents/tabular reviews and
      their stored files from storage.

Audit vs. erasure tension (same rationale as the retention sweep, docs/GDPR.md):
the append-only ``audit_log`` is the SLP's immutable legal-evidence trail
(professional liability) and is the storage layer's append-only guarantee
(guardrail 11). Neither mode EVER touches it — erasure requests against
audit/billing records can be refused on legal-obligation / defence grounds.
``usage_events`` (billing records, no personal data beyond ids) are likewise
left intact. The audit immutability is enforced regardless: the storage layer
raises PermissionError on any audit_log UPDATE/DELETE.
"""
from __future__ import annotations

import logging
from typing import Any, Literal, Optional

from services import db as dbmod, storage

logger = logging.getLogger("lolailo.data_subject")

DeleteMode = Literal["anonymize", "erase"]

# Marker left on scrubbed PII fields so a tombstone is unmistakable in the DB.
_SCRUBBED = "[erased]"


def _requests_for_user(db: dbmod.Database, user_id: str) -> list[dict[str, Any]]:
    """The requests the user OWNS (request.user_id == user_id). Already siloed:
    a request belongs to one user inside one gestora's fund."""
    return db.select("requests", user_id=user_id)


def export_user_data(db: dbmod.Database, user_id: str) -> dict[str, Any]:
    """Assemble the Art. 15/20 export bundle for one user.

    Strictly limited to the user's own data: the profile, their requests, the
    documents metadata for those requests, and the tabular reviews they created.
    Never includes another gestora's (or another user's) content.
    """
    profile = db.get("users", user_id) or {"id": user_id}

    requests = _requests_for_user(db, user_id)
    request_ids = {r["id"] for r in requests}

    # Documents metadata for the user's own requests only (no file bytes).
    documents = [
        doc
        for rid in request_ids
        for doc in db.select("documents", request_id=rid)
    ]

    # Tabular reviews the user created (created_by). Headers only — the grid is
    # reconstructible from the platform and references siloed documents.
    tabular_reviews = db.select("tabular_reviews", created_by=user_id)

    return {
        "schema": "lol-ai-lo.data-subject-export.v1",
        "user_id": user_id,
        "profile": {
            "id": profile.get("id"),
            "email": profile.get("email"),
            "role": profile.get("role"),
            "gestora_id": profile.get("gestora_id"),
            "mfa_enabled": bool(profile.get("mfa_enabled", False)),
            "created_at": profile.get("created_at"),
        },
        "requests": requests,
        "documents": documents,
        "tabular_reviews": tabular_reviews,
        # Spelled out so the recipient knows what is intentionally NOT included.
        "excluded": {
            "audit_log": "retained as immutable legal evidence (RGPD art. 17(3)(b/e))",
            "usage_events": "retained as billing records",
            "other_gestoras": "never included (tenant isolation)",
        },
    }


def _delete_request_files(db: dbmod.Database, request_id: str) -> int:
    """Delete stored files of a request's documents, skipping any still
    referenced by the precedent library (their own admin-managed lifecycle).
    Returns the number of files removed. Missing files never abort."""
    precedent_paths = {v["file_path"] for v in db.select("precedent_versions")}
    files_deleted = 0
    seen: set[str] = set()
    for doc in db.select("documents", request_id=request_id):
        path = doc["file_path"]
        if path not in seen and path not in precedent_paths:
            seen.add(path)
            try:
                storage.delete(path)
                files_deleted += 1
            except Exception:  # noqa: BLE001 — a missing file must not abort erasure
                logger.exception("Erasure could not delete %s (continuing)", path)
        db.delete("documents", doc["id"])
    return files_deleted


def delete_user_data(
    db: dbmod.Database,
    user_id: str,
    *,
    mode: DeleteMode = "anonymize",
) -> dict[str, Any]:
    """Apply the user's erasure/anonymisation request. Returns summary counts.

    NEVER touches ``audit_log`` or ``usage_events`` (see module docstring).
    """
    requests = _requests_for_user(db, user_id)
    counts = {
        "mode": mode,
        "requests_anonymized": 0,
        "requests_erased": 0,
        "documents_deleted": 0,
        "files_deleted": 0,
        "tabular_reviews_deleted": 0,
        "profile_anonymized": False,
    }

    if mode == "erase":
        for row in requests:
            counts["documents_deleted"] += len(db.select("documents", request_id=row["id"]))
            counts["files_deleted"] += _delete_request_files(db, row["id"])
            db.delete("requests", row["id"])
            counts["requests_erased"] += 1
        # Tabular reviews the user created (cascade their child rows).
        for review in db.select("tabular_reviews", created_by=user_id):
            for child_table in (
                "tabular_review_cells",
                "tabular_review_columns",
                "tabular_review_documents",
            ):
                for child in db.select(child_table, review_id=review["id"]):
                    db.delete(child_table, child["id"])
            db.delete("tabular_reviews", review["id"])
            counts["tabular_reviews_deleted"] += 1
    else:  # anonymize — scrub PII, keep tombstones (audit trail stays coherent).
        for row in requests:
            db.update(
                "requests",
                row["id"],
                {
                    "freetext": _SCRUBBED,
                    "parsed_params": None,
                    "structured_fields": None,
                },
            )
            counts["requests_anonymized"] += 1

    # The user's profile email is PII in both modes: scrub it but keep the row
    # (role/gestora link + the user_id are referenced by the audit trail).
    profile = db.get("users", user_id)
    if profile is not None:
        db.update("users", user_id, {"email": f"{_SCRUBBED}-{user_id}", "mfa_enabled": False})
        counts["profile_anonymized"] = True

    logger.info("Data-subject deletion for %s: %s", user_id, counts)
    return counts
