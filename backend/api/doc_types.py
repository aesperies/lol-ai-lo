"""Document-type metadata endpoints (structured intake fields, improvement #5).

No gestora data is exposed here: the field registry is static platform
metadata, public to every authenticated user regardless of role.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from auth import get_current_user
from models import doc_fields
from models.schema import User

router = APIRouter(prefix="/api/doc-types", tags=["doc-types"])


# :path converter: catalog labels contain slashes ("NDA / Acuerdo de
# Confidencialidad"); frontend slugs ("nda") are accepted too.
@router.get("/{doc_type:path}/fields")
async def get_doc_type_fields(
    doc_type: str,
    user: User = Depends(get_current_user),
) -> Any:
    """Structured field specs for a doc_type, with resolved es+en labels.

    Doc types without registered fields return an empty list (freetext-only).
    """
    return {"doc_type": doc_type, "fields": doc_fields.resolved_fields(doc_type)}
