"""Behavioral contract shared by DevStore and SupabaseDB (services/db.py).

The whole test suite runs against DevStore, so nothing else exercises the
SupabaseDB code path. These tests run the SAME assertions against both
backends — SupabaseDB wired to an in-memory fake that mimics PostgREST
semantics strictly:

- ``.is_(column, value)`` only accepts null/not.null/true/false as value
  (PostgREST rejects anything else), so reversed arguments fail loudly.
- ``.order(column)`` fails on columns the table does not have (audit_log has
  ``timestamp``, not ``created_at``).
- Without ``.order()``, rows come back in arbitrary order (here: reversed
  insertion order), so any reliance on implicit recency ordering fails.

If a new method is added to the Database protocol, add it to the fake and
cover it here for both backends.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from services import db as dbmod


# ---------------------------------------------------------------------------
# Fake supabase-py client (PostgREST-strict)
# ---------------------------------------------------------------------------

_IS_OPERANDS = {"null", "not.null", "true", "false"}


class _FakeResult(SimpleNamespace):
    pass


class _FakeQuery:
    """One query builder per operation, chaining like supabase-py."""

    def __init__(self, table_name: str, rows: list[dict[str, Any]], action: str, payload: Any = None) -> None:
        self._table_name = table_name
        self._rows = rows  # live storage list, shared with the fake client
        self._action = action
        self._payload = payload
        self._filters: list[tuple[str, str, Any]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None

    # -- chainable filters ---------------------------------------------------
    def eq(self, column: str, value: Any) -> "_FakeQuery":
        self._filters.append(("eq", column, value))
        return self

    def is_(self, column: str, value: Any) -> "_FakeQuery":
        # PostgREST: IS filters only accept null / not.null / true / false.
        # Reversed arguments (.is_("null", column)) must blow up, not no-op.
        if str(value) not in _IS_OPERANDS:
            raise ValueError(
                f'PostgREST: "failed to parse filter (is.{value})" — '
                f".is_() operand must be one of {sorted(_IS_OPERANDS)}"
            )
        self._filters.append(("is", column, value))
        return self

    def order(self, column: str, desc: bool = False) -> "_FakeQuery":
        self._order = (column, desc)
        return self

    def limit(self, count: int) -> "_FakeQuery":
        self._limit = count
        return self

    # -- execution -------------------------------------------------------------
    def _matches(self, row: dict[str, Any]) -> bool:
        for op, column, value in self._filters:
            if op == "eq":
                if row.get(column) != value:
                    return False
            elif op == "is":
                if value == "null" and row.get(column) is not None:
                    return False
                if value == "not.null" and row.get(column) is None:
                    return False
        return True

    def execute(self) -> _FakeResult:
        if self._action == "insert":
            row = dict(self._payload)
            row.setdefault("id", str(uuid.uuid4()))
            # Mirror the SQL creation-time default of the REAL schema: most
            # tables have created_at, six use another column (see
            # dbmod._ORDER_COLUMN_OVERRIDES) — the fake must NOT invent
            # columns the real table lacks, or ordering bugs stay invisible.
            row.setdefault(dbmod._order_column(self._table_name), datetime.now(timezone.utc).isoformat())
            self._rows.append(row)
            return _FakeResult(data=[dict(row)])

        matched = [dict(r) for r in self._rows if self._matches(r)]

        if self._action == "update":
            for row in self._rows:
                if self._matches(row):
                    row.update(self._payload)
            return _FakeResult(data=[dict(r) for r in self._rows if self._matches(r)])

        if self._action == "delete":
            self._rows[:] = [r for r in self._rows if not self._matches(r)]
            return _FakeResult(data=matched)

        # select
        if self._order is not None:
            column, desc = self._order
            if matched and any(column not in r for r in matched):
                raise ValueError(f'PostgREST: column "{self._table_name}.{column}" does not exist')
            matched.sort(key=lambda r: str(r.get(column) or ""), reverse=desc)
        else:
            # No ORDER BY -> arbitrary order. Reversed insertion order on
            # purpose: any caller relying on implicit recency breaks here.
            matched.reverse()
        if self._limit is not None:
            matched = matched[: self._limit]
        return _FakeResult(data=matched)


class _FakeTable:
    def __init__(self, name: str, rows: list[dict[str, Any]]) -> None:
        self._name = name
        self._rows = rows

    def insert(self, row: dict[str, Any]) -> _FakeQuery:
        return _FakeQuery(self._name, self._rows, "insert", row)

    def select(self, _columns: str) -> _FakeQuery:
        return _FakeQuery(self._name, self._rows, "select")

    def update(self, fields: dict[str, Any]) -> _FakeQuery:
        return _FakeQuery(self._name, self._rows, "update", fields)

    def delete(self) -> _FakeQuery:
        return _FakeQuery(self._name, self._rows, "delete")


class _FakeSupabaseClient:
    def __init__(self) -> None:
        self._tables: dict[str, list[dict[str, Any]]] = {}

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(name, self._tables.setdefault(name, []))


# ---------------------------------------------------------------------------
# Parametrized backend fixture
# ---------------------------------------------------------------------------


@pytest.fixture(params=["devstore", "supabase"])
def backend(request: pytest.FixtureRequest) -> dbmod.Database:
    if request.param == "devstore":
        return dbmod.DevStore()
    # Bypass __init__ (it imports the real supabase package and dials out);
    # the contract is exercised through the same public methods either way.
    supa = dbmod.SupabaseDB.__new__(dbmod.SupabaseDB)
    supa._client = _FakeSupabaseClient()
    return supa


def _ts(minutes: int) -> str:
    return (datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=minutes)).isoformat()


# ---------------------------------------------------------------------------
# Contract tests
# ---------------------------------------------------------------------------


def test_insert_returns_row_with_id(backend: dbmod.Database) -> None:
    row = backend.insert("requests", {"gestora_id": "g1", "created_at": _ts(0)})
    assert row["id"]
    assert backend.get("requests", row["id"])["gestora_id"] == "g1"


def test_get_missing_returns_none(backend: dbmod.Database) -> None:
    assert backend.get("requests", str(uuid.uuid4())) is None


def test_select_orders_oldest_first_newest_last(backend: dbmod.Database) -> None:
    """rows[-1] must be the newest row — llm.resolve_config, jobs.latest_job
    and retention.policy_months all rely on this."""
    backend.insert("gestora_model_config", {"gestora_id": "g1", "provider": "old", "created_at": _ts(0)})
    backend.insert("gestora_model_config", {"gestora_id": "g1", "provider": "mid", "created_at": _ts(5)})
    backend.insert("gestora_model_config", {"gestora_id": "g1", "provider": "new", "created_at": _ts(9)})

    rows = backend.select("gestora_model_config", gestora_id="g1")
    assert [r["provider"] for r in rows] == ["old", "mid", "new"]
    assert rows[-1]["provider"] == "new"


def test_select_none_filter_matches_sql_null(backend: dbmod.Database) -> None:
    """gestora_id=None must match NULL rows only (global template levels in
    rag._global_candidates)."""
    backend.insert("precedents", {"gestora_id": None, "name": "global", "created_at": _ts(0)})
    backend.insert("precedents", {"gestora_id": "g1", "name": "siloed", "created_at": _ts(1)})

    rows = backend.select("precedents", gestora_id=None)
    assert [r["name"] for r in rows] == ["global"]


def test_select_none_and_equality_filters_combine(backend: dbmod.Database) -> None:
    backend.insert("precedents", {"gestora_id": None, "doc_type": "slp", "created_at": _ts(0)})
    backend.insert("precedents", {"gestora_id": None, "doc_type": "nda", "created_at": _ts(1)})
    backend.insert("precedents", {"gestora_id": "g1", "doc_type": "slp", "created_at": _ts(2)})

    rows = backend.select("precedents", gestora_id=None, doc_type="slp")
    assert len(rows) == 1
    assert rows[0]["gestora_id"] is None


def test_audit_log_select_orders_by_timestamp(backend: dbmod.Database) -> None:
    """audit_log has no created_at column in SQL; ordering must use timestamp
    or production selects on audit_log break."""
    backend.insert("audit_log", {"action": "first", "timestamp": _ts(0)})
    backend.insert("audit_log", {"action": "second", "timestamp": _ts(5)})

    rows = backend.unscoped_select("audit_log")
    assert [r["action"] for r in rows] == ["first", "second"]


def test_update_persists_fields(backend: dbmod.Database) -> None:
    row = backend.insert("requests", {"status": "draft", "created_at": _ts(0)})
    backend.update("requests", row["id"], {"status": "delivered"})
    assert backend.get("requests", row["id"])["status"] == "delivered"


@pytest.mark.parametrize("table", sorted(dbmod._APPEND_ONLY_TABLES))
def test_append_only_tables_reject_update_and_delete(backend: dbmod.Database, table: str) -> None:
    row = backend.insert(table, {"gestora_id": "g1"})
    with pytest.raises(PermissionError):
        backend.update(table, row["id"], {"gestora_id": "g2"})
    with pytest.raises(PermissionError):
        backend.delete(table, row["id"])


def test_order_column_exists_in_every_migrated_table() -> None:
    """Regression: SupabaseDB.select orders by _order_column(table); ordering
    by a column the table lacks breaks the query in Postgres (invisible on
    DevStore, which stamps whatever is asked). Parse the REAL migrations and
    assert the mapping is valid for every table — a future migration that adds
    a table without created_at must extend _ORDER_COLUMN_OVERRIDES."""
    import pathlib
    import re

    migrations = pathlib.Path(__file__).resolve().parents[2] / "supabase" / "migrations"
    sql = "\n".join(p.read_text() for p in sorted(migrations.glob("*.sql")))
    tables = re.findall(r"create table (\w+)\s*\((.*?)\n\);", sql, re.S | re.I)
    assert tables, "no CREATE TABLE statements found — did the migrations move?"
    for name, body in tables:
        column = dbmod._order_column(name)
        column_names = {
            m.group(1) for m in re.finditer(r"^\s*(\w+)\s+\w+", body, re.M)
        }
        assert column in column_names, (
            f"_order_column({name!r}) = {column!r} but the table's columns are "
            f"{sorted(column_names)}; add an override in dbmod._ORDER_COLUMN_OVERRIDES"
        )


def test_select_orders_by_override_column_on_tables_without_created_at(backend: dbmod.Database) -> None:
    """gestora_model_config (updated_at) was the production bug: selecting it
    must work and order by the override column on BOTH backends."""
    backend.insert("gestora_model_config", {"gestora_id": "g1", "llm_provider": "old", "updated_at": _ts(0)})
    rows = backend.select("gestora_model_config", gestora_id="g1")
    assert [r["llm_provider"] for r in rows] == ["old"]


def test_tenant_scope_enforced_with_unscoped_escape_hatch(backend: dbmod.Database) -> None:
    """Both backends refuse unscoped selects on tenant tables (isolation is
    enforced HERE — the service-role key bypasses RLS in production)."""
    with pytest.raises(dbmod.TenantScopeError):
        backend.select("requests", status="delivered")
    assert backend.unscoped_select("requests", status="delivered") == []


def test_delete_removes_row(backend: dbmod.Database) -> None:
    row = backend.insert("requests", {"status": "draft", "created_at": _ts(0)})
    backend.delete("requests", row["id"])
    assert backend.get("requests", row["id"]) is None
