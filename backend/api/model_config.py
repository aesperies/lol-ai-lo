"""Per-gestora model configuration endpoints (011_account_security.sql).

Admin-only. Each gestora may override the global LLM provider/model and supply
its own API keys (BYO keys), stored ENCRYPTED at rest (services/secrets.py).

The GET response NEVER returns decrypted keys — only ``anthropic_key_set`` /
``openai_key_set`` booleans. On PUT, a key field set to a non-empty string is
encrypted and stored, ``""`` clears the stored key, and omission leaves it
unchanged (write-only fields). Every change is audited (without key material).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from api import client_ip, get_gestora_or_404, now_iso
from auth import require_admin
from models.schema import (
    AuditAction,
    AuditResourceType,
    ModelConfigBody,
    ModelConfigOut,
    User,
)
from services import audit, db as dbmod, secrets

logger = logging.getLogger("lolailo.model_config")

router = APIRouter(prefix="/api/admin", tags=["admin-model-config"])

# Override columns that carry NO secret material (provider/model/base-url).
_PLAIN_FIELDS = (
    "llm_provider",
    "llm_model",
    "embedding_provider",
    "embedding_model",
    "ollama_base_url",
)



def _config_row(db: dbmod.Database, gestora_id: str) -> Optional[dict[str, Any]]:
    """The gestora's config row (None when unset). Queried by gestora_id —
    which is the table's PK — so it works on both the dev store and Supabase
    without depending on a generated ``id`` column."""
    rows = db.select("gestora_model_config", gestora_id=gestora_id)
    return rows[-1] if rows else None


def _serialize(gestora_id: str, row: Optional[dict[str, Any]]) -> ModelConfigOut:
    """Build the no-secrets response. ``row is None`` → platform default."""
    if row is None:
        return ModelConfigOut(gestora_id=gestora_id, is_default=True)
    return ModelConfigOut(
        gestora_id=gestora_id,
        llm_provider=row.get("llm_provider"),
        llm_model=row.get("llm_model"),
        embedding_provider=row.get("embedding_provider"),
        embedding_model=row.get("embedding_model"),
        ollama_base_url=row.get("ollama_base_url"),
        # Booleans only — the ciphertext (and certainly the plaintext) is never
        # returned to the client.
        anthropic_key_set=bool(row.get("anthropic_api_key_enc")),
        mistral_key_set=bool(row.get("mistral_api_key_enc")),
        xai_key_set=bool(row.get("xai_api_key_enc")),
        openai_key_set=bool(row.get("openai_api_key_enc")),
        is_default=False,
        updated_by=row.get("updated_by"),
        updated_at=row.get("updated_at"),
    )


@router.get("/gestoras/{gestora_id}/model-config", response_model=ModelConfigOut)
async def get_model_config(
    gestora_id: str,
    user: User = Depends(require_admin),
) -> Any:
    """The gestora's model-config override (platform default when none set).
    Never returns decrypted keys."""
    db = dbmod.get_db()
    get_gestora_or_404(db, gestora_id)
    return _serialize(gestora_id, _config_row(db, gestora_id))


@router.put("/gestoras/{gestora_id}/model-config", response_model=ModelConfigOut)
async def put_model_config(
    gestora_id: str,
    body: ModelConfigBody,
    http_request: Request,
    user: User = Depends(require_admin),
) -> Any:
    """Upsert the gestora's model-config override.

    Plain fields: value sets, ``""`` clears (→ global default). Key fields:
    non-empty encrypts+stores, ``""`` clears, omitted (None) leaves unchanged.
    The encrypted key material is never logged or echoed back.
    """
    db = dbmod.get_db()
    get_gestora_or_404(db, gestora_id)
    existing = _config_row(db, gestora_id)

    fields: dict[str, Any] = {}
    for name in _PLAIN_FIELDS:
        value = getattr(body, name)
        if value is not None:
            # Empty string clears the override back to the global default.
            fields[name] = value or None

    # Write-only key fields → store ciphertext (services/secrets.py), never plain.
    if body.anthropic_api_key is not None:
        fields["anthropic_api_key_enc"] = (
            secrets.encrypt(body.anthropic_api_key) if body.anthropic_api_key else None
        )
    if body.mistral_api_key is not None:
        fields["mistral_api_key_enc"] = (
            secrets.encrypt(body.mistral_api_key) if body.mistral_api_key else None
        )
    if body.xai_api_key is not None:
        fields["xai_api_key_enc"] = (
            secrets.encrypt(body.xai_api_key) if body.xai_api_key else None
        )
    if body.openai_api_key is not None:
        fields["openai_api_key_enc"] = (
            secrets.encrypt(body.openai_api_key) if body.openai_api_key else None
        )

    fields["updated_by"] = user.id
    fields["updated_at"] = now_iso()

    if existing:
        row = db.update("gestora_model_config", existing["id"], fields)
    else:
        row = db.insert("gestora_model_config", {"gestora_id": gestora_id, **fields})

    audit.log_action(
        db,
        user=user,
        action=AuditAction.model_config_updated,
        resource_type=AuditResourceType.model_config,
        resource_id=gestora_id,
        gestora_id=gestora_id,
        # Audit WHAT changed, never the key material: only booleans for keys.
        metadata={
            "llm_provider": row.get("llm_provider"),
            "llm_model": row.get("llm_model"),
            "embedding_provider": row.get("embedding_provider"),
            "embedding_model": row.get("embedding_model"),
            "ollama_base_url": row.get("ollama_base_url"),
            "anthropic_key_set": bool(row.get("anthropic_api_key_enc")),
            "mistral_key_set": bool(row.get("mistral_api_key_enc")),
            "xai_key_set": bool(row.get("xai_api_key_enc")),
            "openai_key_set": bool(row.get("openai_api_key_enc")),
        },
        ip_address=client_ip(http_request),
    )
    return _serialize(gestora_id, row)
