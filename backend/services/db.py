"""Database access layer.

Two interchangeable backends behind one minimal interface:

- ``SupabaseDB``  — production: supabase-py with the service-role key
  (lazy-imported so the app runs without the package installed).
- ``DevStore``    — in-memory dict store used when ``DEV_AUTH_STUB=true``
  (local dev and the automated test suite).

The interface is intentionally tiny (insert/get/select/update) so every data
access path goes through code we can audit for gestora isolation.
"""
from __future__ import annotations

import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from config import ServiceNotConfiguredError, get_settings

# Tables whose rows may never be mutated after insert (SPEC guardrail 11).
_APPEND_ONLY_TABLES = {"audit_log", "usage_events"}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DevStore:
    """In-memory store mimicking the Postgres schema for dev/tests."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tables: dict[str, dict[str, dict[str, Any]]] = {}

    def _table(self, table: str) -> dict[str, dict[str, Any]]:
        return self._tables.setdefault(table, {})

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            row = dict(row)
            row.setdefault("id", str(uuid.uuid4()))
            row.setdefault("created_at", _now())
            if table in ("requests", "generation_jobs"):
                row.setdefault("updated_at", _now())
            if table == "audit_log":
                row.setdefault("timestamp", _now())
            self._table(table)[row["id"]] = row
            return dict(row)

    def get(self, table: str, row_id: str) -> Optional[dict[str, Any]]:
        row = self._table(table).get(row_id)
        return dict(row) if row else None

    def select(self, table: str, **filters: Any) -> list[dict[str, Any]]:
        """Equality-filtered select. ``field=None`` matches SQL NULL."""
        rows = []
        for row in self._table(table).values():
            if all(row.get(k) == v for k, v in filters.items()):
                rows.append(dict(row))
        rows.sort(key=lambda r: str(r.get("created_at") or ""))
        return rows

    def update(self, table: str, row_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        if table in _APPEND_ONLY_TABLES:
            # Mirrors trg_audit_log_immutable: append-only at the storage layer.
            raise PermissionError(f"{table} is append-only: UPDATE not permitted")
        with self._lock:
            row = self._table(table).get(row_id)
            if row is None:
                raise KeyError(f"{table}/{row_id} not found")
            row.update(fields)
            if table in ("requests", "generation_jobs"):
                row["updated_at"] = _now()
            return dict(row)

    def delete(self, table: str, row_id: str) -> None:
        if table in _APPEND_ONLY_TABLES:
            raise PermissionError(f"{table} is append-only: DELETE not permitted")
        with self._lock:
            self._table(table).pop(row_id, None)


class SupabaseDB:
    """Thin wrapper over supabase-py exposing the DevStore interface."""

    def __init__(self, url: str, service_role_key: str) -> None:
        # Lazy import: app must start without the supabase package installed.
        from supabase import create_client  # type: ignore[import-not-found]

        self._client = create_client(url, service_role_key)

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]:
        res = self._client.table(table).insert(row).execute()
        return res.data[0]

    def get(self, table: str, row_id: str) -> Optional[dict[str, Any]]:
        res = self._client.table(table).select("*").eq("id", row_id).limit(1).execute()
        return res.data[0] if res.data else None

    def select(self, table: str, **filters: Any) -> list[dict[str, Any]]:
        query = self._client.table(table).select("*")
        for key, value in filters.items():
            query = query.is_("null", key) if value is None else query.eq(key, value)  # type: ignore[arg-type]
        res = query.execute()
        return res.data or []

    def update(self, table: str, row_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        if table in _APPEND_ONLY_TABLES:
            raise PermissionError(f"{table} is append-only: UPDATE not permitted")
        res = self._client.table(table).update(fields).eq("id", row_id).execute()
        return res.data[0]

    def delete(self, table: str, row_id: str) -> None:
        if table in _APPEND_ONLY_TABLES:
            raise PermissionError(f"{table} is append-only: DELETE not permitted")
        self._client.table(table).delete().eq("id", row_id).execute()


Database = Any  # duck-typed: DevStore | SupabaseDB

_dev_store: Optional[DevStore] = None
_supabase_db: Optional[SupabaseDB] = None


def reset_dev_store() -> DevStore:
    """Replace the in-memory store (test isolation helper)."""
    global _dev_store
    _dev_store = DevStore()
    return _dev_store


def get_db() -> Database:
    """Resolve the active database backend.

    DEV_AUTH_STUB=true -> in-memory store (no Supabase needed).
    Otherwise Supabase must be configured; the app itself still imports and
    serves /health, but data endpoints raise 503 via ServiceNotConfiguredError.
    """
    global _dev_store, _supabase_db
    settings = get_settings()
    if settings.dev_auth_stub:
        if _dev_store is None:
            _dev_store = DevStore()
        return _dev_store
    if not settings.supabase_configured:
        raise ServiceNotConfiguredError(
            "supabase",
            "Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY, or DEV_AUTH_STUB=true.",
        )
    if _supabase_db is None:
        _supabase_db = SupabaseDB(settings.supabase_url, settings.supabase_service_role_key)
    return _supabase_db
