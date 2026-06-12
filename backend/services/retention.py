"""GDPR data-retention sweep (improvement #10, docs/GDPR.md).

Each gestora has a retention policy in months (data_retention_policies,
007_data_retention.sql; platform default DEFAULT_RETENTION_MONTHS when no row
exists). run_retention_sweep() finds requests that

    - are in status 'delivered' (the only terminal state — anything still in
      flight is never touched), AND
    - were created more than the gestora's policy months ago

and DELETES their stored document files plus their ``documents`` rows.

What is kept, and why (storage minimization vs audit immutability):
- The ``requests`` row survives as a tombstone: the audit trail references it
  and the SLP must be able to prove WHAT happened (who requested, who
  validated, when it was delivered) long after the document content itself is
  minimized away.
- ``audit_log`` is NEVER touched — it is append-only by design (guardrail 11)
  and is the legally relevant evidence trail.
- Files still referenced by the precedent library (precedent_versions.
  file_path) are kept: validated outputs become precedents with their own
  lifecycle (admin-managed supersede/delete), so the sweep only removes the
  per-request copy bookkeeping, never the shared bytes.

Exposed as POST /api/admin/retention/sweep (admin-only, api/admin_retention.py).
TODO: schedule via external cron (e.g. Railway cron hitting the endpoint, or
Supabase pg_cron) — the sweep is idempotent so overlapping runs are safe.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from services import db as dbmod, storage

logger = logging.getLogger("lolailo.retention")

# Platform default when a gestora has no explicit policy row (mirrors the SQL
# DEFAULT in 007_data_retention.sql).
DEFAULT_RETENTION_MONTHS = 60

# Calendar months expressed in days for cutoff arithmetic (365.25 / 12).
_DAYS_PER_MONTH = 30.4375


def policy_months(db: dbmod.Database, gestora_id: Optional[str]) -> int:
    """The gestora's retention policy in months (platform default if unset)."""
    if not gestora_id:
        return DEFAULT_RETENTION_MONTHS
    rows = db.select("data_retention_policies", gestora_id=gestora_id)
    return rows[-1]["months"] if rows else DEFAULT_RETENTION_MONTHS


def _created_at(row: dict[str, Any]) -> Optional[datetime]:
    stamp = row.get("created_at")
    if not stamp:
        return None
    try:
        created = datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created


def run_retention_sweep(db: Optional[dbmod.Database] = None) -> dict[str, int]:
    """One idempotent pass: delete documents + files of expired delivered
    requests. Returns the summary counts. NEVER touches audit_log."""
    # Local import: the gestora resolution helper lives in the auth layer.
    from auth import gestora_of_request

    db = db if db is not None else dbmod.get_db()
    now = datetime.now(timezone.utc)
    counts = {
        "requests_swept": 0,
        "documents_deleted": 0,
        "files_deleted": 0,
        "files_kept_as_precedent": 0,
    }

    # Files referenced by the precedent library are never deleted here (see
    # module docstring): collect every live precedent file path once.
    precedent_paths = {v["file_path"] for v in db.select("precedent_versions")}

    for row in db.select("requests", status="delivered"):
        created = _created_at(row)
        if created is None:
            continue
        months = policy_months(db, gestora_of_request(db, row))
        if created > now - timedelta(days=months * _DAYS_PER_MONTH):
            continue

        documents = db.select("documents", request_id=row["id"])
        if not documents:
            continue  # already swept (idempotency)

        file_paths: set[str] = set()
        for doc in documents:
            file_paths.add(doc["file_path"])
            db.delete("documents", doc["id"])
            counts["documents_deleted"] += 1
        for path in file_paths:
            if path in precedent_paths:
                counts["files_kept_as_precedent"] += 1
                continue
            try:
                storage.delete(path)
                counts["files_deleted"] += 1
            except Exception:  # noqa: BLE001 — a missing file must not abort the sweep
                logger.exception("Retention sweep could not delete %s (continuing)", path)
        counts["requests_swept"] += 1

    logger.info("Retention sweep: %s", counts)
    return counts
