"""Tabular Review endpoints — multi-document extraction grid (prefix /api).

A gestora user defines columns (a question + an answer type) over a set of
their OWN documents; the system extracts one typed, cited cell per
(document × column). Strictly gestora-siloed: every referenced document is
hard-checked against the caller's gestora at create time, and every
review/cell read uses the same 404-no-leak access pattern as the request
endpoints.
"""
from __future__ import annotations

import csv
import io
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from auth import get_current_user, require_client
from models.schema import (
    AuditAction,
    AuditResourceType,
    TabularCellOut,
    TabularColumnCreate,
    TabularColumnOut,
    TabularDocumentCreate,
    TabularDocumentOut,
    TabularReviewCreate,
    TabularReviewDetailOut,
    TabularReviewOut,
    TabularReviewStatus,
    TabularReviewStatusOut,
    TabularSourceKind,
    User,
    UserRole,
)
from services import audit, db as dbmod, tabular
from services.jobs import get_runner

router = APIRouter(prefix="/api/tabular-reviews", tags=["tabular-reviews"])

logger = logging.getLogger("lolailo.tabular")

_NOT_FOUND = "Tabular review not found"


def _ip(http_request: Request) -> Optional[str]:
    return http_request.client.host if http_request.client else None


# ---------------------------------------------------------------------------
# Gestora isolation helpers (SPEC guardrail 1) — same 404-no-leak pattern as
# the request endpoints (auth.assert_request_access).
# ---------------------------------------------------------------------------

def _get_review_or_404(db: dbmod.Database, review_id: str) -> dict[str, Any]:
    row = db.get("tabular_reviews", review_id)
    if row is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return row


def _assert_review_access(db: dbmod.Database, user: User, review: dict[str, Any]) -> str:
    """404 unless the user may access this review. Returns the gestora_id.

    Clients only ever see reviews of their own gestora; counsel/admin are
    cross-gestora by design. 404 (not 403) avoids leaking other gestoras' ids.
    """
    gestora_id = review.get("gestora_id")
    if user.role in (UserRole.counsel, UserRole.admin):
        return gestora_id or ""
    if gestora_id is None or user.gestora_id != gestora_id:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return gestora_id


def _document_belongs_to_gestora(
    db: dbmod.Database, ref: TabularDocumentCreate, gestora_id: str
) -> bool:
    """HARD cross-gestora check for ONE referenced document (isolation).

    A precedent_version is in-silo when its precedent's gestora_id matches; a
    request_document is in-silo when its request's fund's gestora_id matches.
    Returns False for missing rows or any cross-gestora reference (the caller
    rejects with 404 — never leak which case it was).
    """
    if ref.source_kind is TabularSourceKind.precedent_version:
        version = db.get("precedent_versions", ref.source_id)
        if version is None:
            return False
        precedent = db.get("precedents", version["precedent_id"])
        return bool(precedent and precedent.get("gestora_id") == gestora_id)

    if ref.source_kind is TabularSourceKind.request_document:
        document = db.get("documents", ref.source_id)
        if document is None:
            return False
        request_row = db.get("requests", document["request_id"])
        if request_row is None:
            return False
        fund = db.get("funds", request_row["fund_id"])
        return bool(fund and fund.get("gestora_id") == gestora_id)

    return False


def _serialize_detail(db: dbmod.Database, review: dict[str, Any]) -> TabularReviewDetailOut:
    """Assemble the full grid (columns + documents + cells) for one review."""
    review_id = review["id"]
    columns = sorted(
        db.select("tabular_review_columns", review_id=review_id),
        key=lambda c: c.get("position", 0),
    )
    documents = sorted(
        db.select("tabular_review_documents", review_id=review_id),
        key=lambda d: d.get("position", 0),
    )
    cells = db.select("tabular_review_cells", review_id=review_id)
    return TabularReviewDetailOut(
        **review,
        columns=[TabularColumnOut(**c) for c in columns],
        documents=[TabularDocumentOut(**d) for d in documents],
        cells=[TabularCellOut(**c) for c in cells],
    )


def _create_pending_cells(
    db: dbmod.Database,
    *,
    review_id: str,
    document_ids: list[str],
    column_ids: list[str],
) -> None:
    """Create 'pending' cells for the given document × column combinations,
    skipping any that already exist (idempotent)."""
    for document_id in document_ids:
        for column_id in column_ids:
            if db.select(
                "tabular_review_cells", document_id=document_id, column_id=column_id
            ):
                continue
            db.insert(
                "tabular_review_cells",
                {
                    "review_id": review_id,
                    "document_id": document_id,
                    "column_id": column_id,
                    "value": None,
                    "reasoning": None,
                    "citation": None,
                    "status": "pending",
                    "error": None,
                },
            )


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------

@router.post("", response_model=TabularReviewDetailOut, status_code=201)
async def create_review(
    body: TabularReviewCreate,
    http_request: Request,
    user: User = Depends(require_client),
) -> Any:
    """Create a tabular review (status 'draft') with columns and documents.

    Validates that EVERY referenced document belongs to the caller's gestora
    (hard isolation check); a cross-gestora or unknown reference is rejected
    with 404 and never leaks which document existed.
    """
    db = dbmod.get_db()
    gestora_id = user.gestora_id
    if gestora_id is None:
        # require_client guarantees a client, who always has a gestora.
        raise HTTPException(status_code=403, detail="Client has no gestora")

    if body.fund_id is not None:
        fund = db.get("funds", body.fund_id)
        if fund is None or fund["gestora_id"] != gestora_id:
            raise HTTPException(status_code=404, detail="Fund not found")

    # HARD cross-gestora pre-filter on every referenced document.
    for ref in body.documents:
        if not _document_belongs_to_gestora(db, ref, gestora_id):
            raise HTTPException(status_code=404, detail="Document not found")

    review = db.insert(
        "tabular_reviews",
        {
            "gestora_id": gestora_id,
            "fund_id": body.fund_id,
            "created_by": user.id,
            "title": body.title,
            "status": TabularReviewStatus.draft.value,
        },
    )

    column_ids: list[str] = []
    for position, col in enumerate(body.columns):
        row = db.insert(
            "tabular_review_columns",
            {
                "review_id": review["id"],
                "position": position,
                "name": col.name,
                "question": col.question,
                "col_type": col.col_type.value,
                "options": col.options,
            },
        )
        column_ids.append(row["id"])

    document_ids: list[str] = []
    for position, ref in enumerate(body.documents):
        row = db.insert(
            "tabular_review_documents",
            {
                "review_id": review["id"],
                "position": position,
                "source_kind": ref.source_kind.value,
                "source_id": ref.source_id,
                "label": ref.label,
            },
        )
        document_ids.append(row["id"])

    _create_pending_cells(
        db, review_id=review["id"], document_ids=document_ids, column_ids=column_ids
    )

    audit.log_action(
        db,
        user=user,
        action=AuditAction.tabular_review_created,
        resource_type=AuditResourceType.tabular_review,
        resource_id=review["id"],
        gestora_id=gestora_id,
        metadata={
            "title": body.title,
            "fund_id": body.fund_id,
            "column_count": len(column_ids),
            "document_count": len(document_ids),
        },
        ip_address=_ip(http_request),
    )
    return _serialize_detail(db, review)


# ---------------------------------------------------------------------------
# Run (enqueue extraction)
# ---------------------------------------------------------------------------

@router.post("/{review_id}/run", status_code=202)
async def run_review_endpoint(
    review_id: str,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Any:
    """Set the review 'running' and enqueue extraction via the JobRunner (202)."""
    db = dbmod.get_db()
    review = _get_review_or_404(db, review_id)
    gestora_id = _assert_review_access(db, user, review)

    db.update("tabular_reviews", review_id, {"status": TabularReviewStatus.running.value})
    job = get_runner().enqueue(
        db,
        request_id=review_id,
        factory=lambda: tabular.run_review(db, review_id),
        # On final failure, leave the review 'failed' so the UI stops polling.
        on_final_failure=lambda _exc: db.update(
            "tabular_reviews", review_id, {"status": TabularReviewStatus.failed.value}
        ),
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.tabular_review_run,
        resource_type=AuditResourceType.tabular_review,
        resource_id=review_id,
        gestora_id=gestora_id,
        metadata={"job_id": job["id"]},
        ip_address=_ip(http_request),
    )
    return {"review_id": review_id, "status": TabularReviewStatus.running.value, "job_id": job["id"]}


# ---------------------------------------------------------------------------
# List / detail / status (gestora-siloed)
# ---------------------------------------------------------------------------

@router.get("", response_model=list[TabularReviewOut])
async def list_reviews(user: User = Depends(get_current_user)) -> Any:
    """List tabular reviews. Clients see only their own gestora's reviews;
    counsel/admin see all (cross-gestora by role)."""
    db = dbmod.get_db()
    if user.role in (UserRole.counsel, UserRole.admin):
        return db.select("tabular_reviews")
    return db.select("tabular_reviews", gestora_id=user.gestora_id)


@router.get("/{review_id}", response_model=TabularReviewDetailOut)
async def get_review(review_id: str, user: User = Depends(get_current_user)) -> Any:
    db = dbmod.get_db()
    review = _get_review_or_404(db, review_id)
    _assert_review_access(db, user, review)
    return _serialize_detail(db, review)


@router.get("/{review_id}/status", response_model=TabularReviewStatusOut)
async def get_review_status(review_id: str, user: User = Depends(get_current_user)) -> Any:
    """Lightweight progress payload for the polling loop while a review runs."""
    db = dbmod.get_db()
    review = _get_review_or_404(db, review_id)
    _assert_review_access(db, user, review)
    cells = db.select("tabular_review_cells", review_id=review_id)
    return TabularReviewStatusOut(
        id=review_id,
        status=review["status"],
        cell_total=len(cells),
        cell_done=sum(1 for c in cells if c.get("status") == "done"),
        cell_error=sum(1 for c in cells if c.get("status") == "error"),
    )


# ---------------------------------------------------------------------------
# Column / document mutations (minimal, consistent)
# ---------------------------------------------------------------------------

@router.post("/{review_id}/columns", response_model=TabularReviewDetailOut)
async def add_column(
    review_id: str,
    body: TabularColumnCreate,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Any:
    """Add a column; creates 'pending' cells for it across all documents."""
    db = dbmod.get_db()
    review = _get_review_or_404(db, review_id)
    gestora_id = _assert_review_access(db, user, review)

    existing = db.select("tabular_review_columns", review_id=review_id)
    position = max((c.get("position", 0) for c in existing), default=-1) + 1
    column = db.insert(
        "tabular_review_columns",
        {
            "review_id": review_id,
            "position": position,
            "name": body.name,
            "question": body.question,
            "col_type": body.col_type.value,
            "options": body.options,
        },
    )
    document_ids = [d["id"] for d in db.select("tabular_review_documents", review_id=review_id)]
    _create_pending_cells(
        db, review_id=review_id, document_ids=document_ids, column_ids=[column["id"]]
    )
    audit.log_action(
        db,
        user=user,
        action=AuditAction.tabular_review_column_added,
        resource_type=AuditResourceType.tabular_review,
        resource_id=review_id,
        gestora_id=gestora_id,
        metadata={"column_id": column["id"], "name": body.name, "col_type": body.col_type.value},
        ip_address=_ip(http_request),
    )
    return _serialize_detail(db, review)


@router.delete("/{review_id}/columns/{column_id}", response_model=TabularReviewDetailOut)
async def delete_column(
    review_id: str,
    column_id: str,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Any:
    """Delete a column and its cells."""
    db = dbmod.get_db()
    review = _get_review_or_404(db, review_id)
    gestora_id = _assert_review_access(db, user, review)
    column = db.get("tabular_review_columns", column_id)
    if column is None or column["review_id"] != review_id:
        raise HTTPException(status_code=404, detail="Column not found")
    for cell in db.select("tabular_review_cells", review_id=review_id, column_id=column_id):
        db.delete("tabular_review_cells", cell["id"])
    db.delete("tabular_review_columns", column_id)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.tabular_review_column_deleted,
        resource_type=AuditResourceType.tabular_review,
        resource_id=review_id,
        gestora_id=gestora_id,
        metadata={"column_id": column_id},
        ip_address=_ip(http_request),
    )
    return _serialize_detail(db, review)


@router.delete("/{review_id}/documents/{document_id}", response_model=TabularReviewDetailOut)
async def delete_document(
    review_id: str,
    document_id: str,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Any:
    """Delete a document (grid row) and its cells."""
    db = dbmod.get_db()
    review = _get_review_or_404(db, review_id)
    gestora_id = _assert_review_access(db, user, review)
    document = db.get("tabular_review_documents", document_id)
    if document is None or document["review_id"] != review_id:
        raise HTTPException(status_code=404, detail="Document not found")
    for cell in db.select("tabular_review_cells", review_id=review_id, document_id=document_id):
        db.delete("tabular_review_cells", cell["id"])
    db.delete("tabular_review_documents", document_id)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.tabular_review_document_deleted,
        resource_type=AuditResourceType.tabular_review,
        resource_id=review_id,
        gestora_id=gestora_id,
        metadata={"document_id": document_id},
        ip_address=_ip(http_request),
    )
    return _serialize_detail(db, review)


# ---------------------------------------------------------------------------
# CSV export (one row per document, one column per question; values only)
# ---------------------------------------------------------------------------

@router.get("/{review_id}/export.csv")
async def export_review_csv(
    review_id: str,
    http_request: Request,
    user: User = Depends(get_current_user),
) -> Response:
    """CSV export: one row per document, one column per question (values only).

    Citations live in the app; a header note records that. Mirrors the billing
    CSV export approach (csv.writer over a StringIO buffer)."""
    db = dbmod.get_db()
    review = _get_review_or_404(db, review_id)
    gestora_id = _assert_review_access(db, user, review)

    columns = sorted(
        db.select("tabular_review_columns", review_id=review_id),
        key=lambda c: c.get("position", 0),
    )
    documents = sorted(
        db.select("tabular_review_documents", review_id=review_id),
        key=lambda d: d.get("position", 0),
    )
    cells = db.select("tabular_review_cells", review_id=review_id)
    # (document_id, column_id) -> value, for O(1) lookup per grid position.
    by_pos = {(c["document_id"], c["column_id"]): c for c in cells}

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    # Note row (citations are only available in the app).
    writer.writerow(["# Citas (página + cita textual) disponibles solo en la aplicación."])
    writer.writerow(["Documento", *[col["name"] for col in columns]])
    for doc in documents:
        row = [doc.get("label") or doc["source_id"]]
        for col in columns:
            cell = by_pos.get((doc["id"], col["id"]))
            row.append((cell or {}).get("value") or "")
        writer.writerow(row)

    audit.log_action(
        db,
        user=user,
        action=AuditAction.tabular_review_exported,
        resource_type=AuditResourceType.tabular_review,
        resource_id=review_id,
        gestora_id=gestora_id,
        metadata={"document_count": len(documents), "column_count": len(columns)},
        ip_address=_ip(http_request),
    )
    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="tabular-review-{review_id}.csv"'
        },
    )
