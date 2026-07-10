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
from typing import Any, Optional, Protocol

from config import ServiceNotConfiguredError, get_settings

# Tables whose rows may never be mutated after insert (SPEC guardrail 11).
_APPEND_ONLY_TABLES = {"audit_log", "usage_events"}


class TenantScopeError(RuntimeError):
    """A select on a tenant table stated no tenant scope.

    Gestora isolation is enforced in this layer (the Supabase service-role key
    bypasses RLS, so Python is the only guardrail): forgetting the filter must
    be an error, never a silent cross-gestora leak.
    """


# Tables carrying per-gestora data (they have a gestora_id column, or — like
# requests — hang off one via fund_id). select() on these MUST state its scope:
#   - a gestora_id filter (None targets the global template pool), or
#   - a record/parent id filter (request_id, user_id, created_by, ...).
# Platform-wide system queries (admin metrics, billing, retention/SLA sweeps)
# must declare that intent explicitly via unscoped_select().
_TENANT_SCOPED_TABLES = {
    "audit_log",
    "chat_conversations",
    "chat_messages",
    "counsel_assignments",
    "data_retention_policies",
    "drafting_lessons",
    "funds",
    "gestora_model_config",
    "notifications",
    "precedent_chunks",
    "precedents",
    "quality_metrics",
    "request_shares",
    "requests",
    "review_playbooks",
    "tabular_review_shares",
    "tabular_reviews",
    "usage_alerts",
    "usage_events",
    "users",
}

# Non-id filter keys that still pin a query to one tenant's data.
_SCOPE_KEYS = {"created_by"}


def _assert_tenant_scoped(table: str, filters: dict[str, Any]) -> None:
    if table not in _TENANT_SCOPED_TABLES:
        return
    if "gestora_id" in filters:  # explicit None = global pool, still a choice
        return
    if any(key in _SCOPE_KEYS or key.endswith("_id") for key in filters):
        return
    raise TenantScopeError(
        f"select({table!r}) has no gestora_id or record-id filter. "
        "Add the tenant filter, or use unscoped_select() if this is a "
        "deliberate platform-wide system query."
    )


class Database(Protocol):
    """Behavioral contract shared by DevStore and SupabaseDB.

    Both backends MUST honor the same semantics (enforced by
    tests/test_db_contract.py):

    - ``select`` returns rows ordered oldest-first by creation time; callers
      throughout the codebase rely on ``rows[-1]`` being the newest row.
    - ``select`` filters with ``field=None`` match SQL NULL.
    - ``select`` on a tenant table without a tenant/record scope raises
      TenantScopeError; ``unscoped_select`` is the explicit escape hatch for
      platform-wide system queries.
    - ``update``/``delete`` on ``_APPEND_ONLY_TABLES`` raise PermissionError.
    """

    def insert(self, table: str, row: dict[str, Any]) -> dict[str, Any]: ...

    def get(self, table: str, row_id: str) -> Optional[dict[str, Any]]: ...

    def select(self, table: str, **filters: Any) -> list[dict[str, Any]]: ...

    def unscoped_select(self, table: str, **filters: Any) -> list[dict[str, Any]]: ...

    def update(self, table: str, row_id: str, fields: dict[str, Any]) -> dict[str, Any]: ...

    def delete(self, table: str, row_id: str) -> None: ...

    def search_chunks(
        self,
        *,
        gestora_id: Optional[str],
        doc_type: Optional[str],
        query_embedding: list[float],
        embed_model: str,
        source: Optional[str] = None,
        exclude_source: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 24,
    ) -> list[dict[str, Any]]:
        """ANN search over the persisted RAG index (precedent_chunks, 018).

        Isolation by construction: ``gestora_id`` is a REQUIRED keyword —
        None targets ONLY the global pool (gestora_id IS NULL), a value
        targets ONLY that gestora's silo; there is no cross-tenant form.
        ``doc_type`` None searches EVERY doc_type within that scope (chat
        Q&A, 021) — the tenant filter itself never widens. Rows are returned
        most-similar-first with a ``similarity`` field; only rows whose
        ``embed_model`` matches are comparable (vectors from different models
        never mix). ``language`` mirrors _global_candidates: rows with NULL
        language always match.
        """
        ...

    def search_chunks_text(
        self,
        *,
        gestora_id: Optional[str],
        query_text: str,
        doc_type: Optional[str] = None,
        source: Optional[str] = None,
        exclude_source: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 24,
    ) -> list[dict[str, Any]]:
        """Full-text search over the persisted RAG index (022) — the lexical
        half of hybrid retrieval. Same isolation-by-construction contract as
        :meth:`search_chunks`; unlike it, this needs NO embeddings, so it
        keeps working when the embedding provider is down. Rows return
        best-match-first with a ``rank`` field.
        """
        ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# Tables whose creation-time column is NOT created_at (ordering by a column
# the table lacks breaks the select in Postgres — invisible on the dev store,
# which stamps whatever we ask for). tests/test_db_contract.py parses the SQL
# migrations and asserts this map covers every table, so a future migration
# cannot silently reintroduce the mismatch.
_ORDER_COLUMN_OVERRIDES = {
    "audit_log": "timestamp",
    "data_retention_policies": "updated_at",
    "gestora_model_config": "updated_at",
    "quality_metrics": "computed_at",
    "sla_events": "sent_at",
    "usage_alerts": "sent_at",
}


def _order_column(table: str) -> str:
    """Creation-time column used to keep select() ordering identical in both
    backends (callers rely on rows[-1] being the newest row)."""
    return _ORDER_COLUMN_OVERRIDES.get(table, "created_at")


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
            # Mirror the SQL creation-time default: created_at, or the table's
            # override column (timestamp / updated_at / computed_at / sent_at).
            row.setdefault(_order_column(table), _now())
            # Mirror the SQL updated_at trigger for every table that has one.
            if table in ("requests", "generation_jobs", "tabular_reviews", "tabular_review_cells", "gestora_model_config"):
                row.setdefault("updated_at", _now())
            if table == "documents":
                # Mirrors the SQL DEFAULT 0 (003_refinements.sql).
                row.setdefault("iteration", 0)
            if table == "requests":
                # Mirrors the nullable jsonb column (004_structured_fields.sql).
                row.setdefault("structured_fields", None)
            if table == "users":
                # Mirrors the DEFAULT false (011_account_security.sql).
                row.setdefault("mfa_enabled", False)
            self._table(table)[row["id"]] = row
            return dict(row)

    def get(self, table: str, row_id: str) -> Optional[dict[str, Any]]:
        row = self._table(table).get(row_id)
        return dict(row) if row else None

    def select(self, table: str, **filters: Any) -> list[dict[str, Any]]:
        """Equality-filtered select. ``field=None`` matches SQL NULL."""
        _assert_tenant_scoped(table, filters)
        return self._select(table, filters)

    def unscoped_select(self, table: str, **filters: Any) -> list[dict[str, Any]]:
        """Deliberate platform-wide select (admin metrics, retention/SLA sweeps)."""
        return self._select(table, filters)

    def _select(self, table: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        rows = []
        for row in self._table(table).values():
            if all(row.get(k) == v for k, v in filters.items()):
                rows.append(dict(row))
        rows.sort(key=lambda r: str(r.get(_order_column(table)) or ""))
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
            if table in ("requests", "generation_jobs", "tabular_reviews", "tabular_review_cells", "gestora_model_config"):
                row["updated_at"] = _now()
            return dict(row)

    def delete(self, table: str, row_id: str) -> None:
        if table in _APPEND_ONLY_TABLES:
            raise PermissionError(f"{table} is append-only: DELETE not permitted")
        with self._lock:
            self._table(table).pop(row_id, None)

    def search_chunks(
        self,
        *,
        gestora_id: Optional[str],
        doc_type: Optional[str],
        query_embedding: list[float],
        embed_model: str,
        source: Optional[str] = None,
        exclude_source: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 24,
    ) -> list[dict[str, Any]]:
        """In-memory cosine ANN mirroring match_precedent_chunks (018/021)
        exactly — the contract suite asserts both backends rank identically."""

        def cosine(a: list[float], b: list[float]) -> float:
            dot = sum(x * y for x, y in zip(a, b))
            norm = (sum(x * x for x in a) ** 0.5) * (sum(y * y for y in b) ** 0.5)
            return dot / norm if norm else 0.0

        matches: list[dict[str, Any]] = []
        for row in self._table("precedent_chunks").values():
            if row.get("embedding") is None or row.get("embed_model") != embed_model:
                continue
            if row.get("gestora_id") != gestora_id:
                continue
            if doc_type is not None and row.get("doc_type") != doc_type:
                continue
            if source is not None and row.get("source") != source:
                continue
            if exclude_source is not None and row.get("source") == exclude_source:
                continue
            if language is not None and row.get("language") not in (None, language):
                continue
            out = {k: v for k, v in row.items() if k not in ("embedding", "embed_model", "created_at")}
            out["similarity"] = cosine(row["embedding"], query_embedding)
            matches.append(out)
        matches.sort(key=lambda r: r["similarity"], reverse=True)
        return matches[:limit]

    def search_chunks_text(
        self,
        *,
        gestora_id: Optional[str],
        query_text: str,
        doc_type: Optional[str] = None,
        source: Optional[str] = None,
        exclude_source: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 24,
    ) -> list[dict[str, Any]]:
        """In-memory keyword search mirroring match_precedent_chunks_text
        (022): token-overlap ranking approximates ts_rank well enough for the
        contract tests (exact filters are what matter for isolation)."""
        query_tokens = {t for t in query_text.casefold().split() if len(t) > 1}
        if not query_tokens:
            return []
        matches: list[dict[str, Any]] = []
        for row in self._table("precedent_chunks").values():
            if row.get("gestora_id") != gestora_id:
                continue
            if doc_type is not None and row.get("doc_type") != doc_type:
                continue
            if source is not None and row.get("source") != source:
                continue
            if exclude_source is not None and row.get("source") == exclude_source:
                continue
            if language is not None and row.get("language") not in (None, language):
                continue
            text_tokens = set(str(row.get("text") or "").casefold().split())
            overlap = sum(1 for t in query_tokens if t in text_tokens)
            if overlap == 0:
                continue
            out = {k: v for k, v in row.items() if k not in ("embedding", "embed_model", "created_at")}
            out["rank"] = overlap / len(query_tokens)
            matches.append(out)
        matches.sort(key=lambda r: r["rank"], reverse=True)
        return matches[:limit]


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
        _assert_tenant_scoped(table, filters)
        return self._select(table, filters)

    def unscoped_select(self, table: str, **filters: Any) -> list[dict[str, Any]]:
        """Deliberate platform-wide select (admin metrics, retention/SLA sweeps)."""
        return self._select(table, filters)

    def _select(self, table: str, filters: dict[str, Any]) -> list[dict[str, Any]]:
        query = self._client.table(table).select("*")
        for key, value in filters.items():
            # PostgREST signature is .is_(column, value); NULL filter must be
            # .is_(key, "null") — the reversed form silently mismatches rows.
            query = query.is_(key, "null") if value is None else query.eq(key, value)
        # Oldest-first, matching DevStore: callers rely on rows[-1] == newest
        # (llm.resolve_config, jobs.latest_job, retention.policy_months).
        res = query.order(_order_column(table), desc=False).execute()
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

    def search_chunks(
        self,
        *,
        gestora_id: Optional[str],
        doc_type: Optional[str],
        query_embedding: list[float],
        embed_model: str,
        source: Optional[str] = None,
        exclude_source: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 24,
    ) -> list[dict[str, Any]]:
        """ANN via the match_precedent_chunks SQL function (018/021) — the
        isolation pre-filter runs in the WHERE, before ordering by similarity."""
        res = self._client.rpc(
            "match_precedent_chunks",
            {
                "query_embedding": query_embedding,
                "p_embed_model": embed_model,
                "p_gestora_id": gestora_id,
                "p_doc_type": doc_type,
                "p_source": source,
                "p_exclude_source": exclude_source,
                "p_language": language,
                "p_limit": limit,
            },
        ).execute()
        return res.data or []

    def search_chunks_text(
        self,
        *,
        gestora_id: Optional[str],
        query_text: str,
        doc_type: Optional[str] = None,
        source: Optional[str] = None,
        exclude_source: Optional[str] = None,
        language: Optional[str] = None,
        limit: int = 24,
    ) -> list[dict[str, Any]]:
        """FTS via the match_precedent_chunks_text SQL function (022) — the
        isolation pre-filter runs in the WHERE, before ranking."""
        res = self._client.rpc(
            "match_precedent_chunks_text",
            {
                "p_query": query_text,
                "p_gestora_id": gestora_id,
                "p_doc_type": doc_type,
                "p_source": source,
                "p_exclude_source": exclude_source,
                "p_language": language,
                "p_limit": limit,
            },
        ).execute()
        return res.data or []


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
