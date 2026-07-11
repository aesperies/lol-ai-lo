"""Biblioteca del cliente (022): la vista de la gestora sobre su propio RAG.

Hasta ahora la biblioteca de precedentes solo era visible en el área de admin;
el cliente preguntaba al chat "a ciegas". Esta API le da:

- ``GET /api/my/library``: sus documentos (solo su silo — nunca el pool
  global ni otros silos), enriquecidos con fondo y fecha del documento para
  organizarlos por fondo / año / trimestre / tipo en el frontend.
- ``POST /api/my/library/upload``: subida de documentos al propio silo. El
  documento entra como versión BORRADOR (peso RAG 0.0) — el flujo existente
  de activación por admin decide cuándo empieza a alimentar el RAG. Así el
  cliente enriquece su biblioteca sin poder envenenar el índice por su cuenta.

Aislamiento: todas las queries filtran por la gestora del usuario; el fondo
de destino debe pertenecer a esa misma gestora.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request, UploadFile

from api import client_ip, validate_upload
from auth import require_client, require_gestora
from models.schema import (
    AuditAction,
    AuditResourceType,
    LibraryItemOut,
    PrecedentSource,
    PrecedentVersionStatus,
    User,
)
from services import audit
from services import db as dbmod
from services import storage

router = APIRouter(prefix="/api/my/library", tags=["library"])

_UPLOAD_EXTENSIONS = (".docx", ".pdf")

# Estado "representativo" de un precedente = el de su mejor versión.
_STATUS_PRIORITY = [
    PrecedentVersionStatus.active.value,
    PrecedentVersionStatus.draft.value,
    PrecedentVersionStatus.superseded.value,
]


def _representative_version(versions: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """La versión que representa al precedente en la biblioteca: la activa;
    si no hay, el último borrador; si no, la última sustituida."""
    for status in _STATUS_PRIORITY:
        matching = [v for v in versions if v.get("status") == status]
        if matching:
            return max(matching, key=lambda v: v.get("version_number", 0))
    return None


@router.get("", response_model=list[LibraryItemOut])
async def my_library(user: User = Depends(require_client)) -> Any:
    """Los documentos del silo de la gestora del usuario, con fondo y fecha.

    Una consulta por tabla + agrupación en memoria (mismo patrón anti-N+1 que
    api/precedents._with_versions). El frontend agrupa por fondo / año /
    trimestre / tipo a partir de fund_id + document_date (o created_at).
    """
    db = dbmod.get_db()
    gestora_id = require_gestora(user)

    precedents = db.select("precedents", gestora_id=gestora_id)
    if not precedents:
        return []
    from api.precedents import _with_versions  # mismo bulk-join que la vista admin

    funds = {f["id"]: f for f in db.select("funds", gestora_id=gestora_id)}

    items: list[dict[str, Any]] = []
    for precedent in _with_versions(db, precedents):
        version = _representative_version(precedent["versions"])
        fund = funds.get(precedent.get("fund_id") or "")
        items.append({
            "id": precedent["id"],
            "doc_type": precedent["doc_type"],
            "language": precedent.get("language") or "",
            "source": precedent.get("source") or "",
            "fund_id": precedent.get("fund_id"),
            "fund_name": fund.get("name") if fund else None,
            "document_date": precedent.get("document_date"),
            "created_at": precedent.get("created_at"),
            "version_id": version["id"] if version else None,
            "version_status": version.get("status") if version else None,
            "version_number": version.get("version_number") if version else None,
            "is_docx": bool(version and str(version.get("file_path", "")).lower().endswith(".docx")),
        })
    return items


@router.post("/upload", status_code=201)
async def upload_document(
    http_request: Request,
    file: UploadFile,
    doc_type: str = Form(...),
    language: str = Form("es"),
    fund_id: Optional[str] = Form(None),
    document_date: Optional[str] = Form(None),
    user: User = Depends(require_client),
) -> Any:
    """El cliente sube un documento a SU biblioteca (versión 1, borrador).

    No alimenta el RAG hasta que un admin la active (flujo existente de
    activación) — el cliente enriquece, el admin cura.
    """
    db = dbmod.get_db()
    gestora_id = require_gestora(user)

    if fund_id:
        fund = db.get("funds", fund_id)
        if fund is None or fund.get("gestora_id") != gestora_id:
            raise HTTPException(status_code=404, detail="Fund not found")
    parsed_date: Optional[str] = None
    if document_date:
        try:
            parsed_date = date.fromisoformat(document_date).isoformat()
        except ValueError:
            raise HTTPException(status_code=422, detail="document_date must be YYYY-MM-DD")

    data = await file.read()
    validate_upload(file.filename or "", data, _UPLOAD_EXTENSIONS)

    precedent = db.insert(
        "precedents",
        {
            "gestora_id": gestora_id,
            "fund_id": fund_id,
            "doc_type": doc_type,
            "language": language,
            "source": PrecedentSource.manual_upload.value,
            "document_date": parsed_date,
        },
    )
    extension = "." + (file.filename or "doc.docx").rsplit(".", 1)[-1].lower()
    key = storage.save(
        storage.precedentes_path(gestora_id, f"{precedent['id']}-v1{extension}"), data
    )
    version = db.insert(
        "precedent_versions",
        {
            "precedent_id": precedent["id"],
            "version_number": 1,
            "file_path": key,
            "status": PrecedentVersionStatus.draft.value,
            "rag_weight": 0.0,
            "created_by": user.id,
        },
    )
    for action, resource_type, resource_id in (
        (AuditAction.precedent_uploaded, AuditResourceType.precedent, precedent["id"]),
        (AuditAction.precedent_version_created, AuditResourceType.precedent_version, version["id"]),
    ):
        audit.log_action(
            db,
            user=user,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            gestora_id=gestora_id,
            metadata={"doc_type": doc_type, "language": language,
                      "source": PrecedentSource.manual_upload.value,
                      "filename": file.filename, "client_upload": True},
            ip_address=client_ip(http_request),
        )
    return {"precedent": precedent, "version": version}
