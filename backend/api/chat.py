"""Chat Q&A sobre el RAG de la gestora (021): conversaciones + SSE.

Modelo de acceso: una conversación es PRIVADA de su usuario (cliente) y vive
en su gestora — más restrictivo que requests (sin sharing, sin counsel/admin).
Cualquier otro usuario recibe 404 (patrón no-leak). El aislamiento por
gestora_id se re-verifica en cada acceso además del filtro en las queries.

El envío de mensaje responde ``text/event-stream``: eventos JSON data-only
(sources → delta* → verification? → done | error) producidos por
services/chat.ask. Un fallo del proveedor con el stream ya abierto llega como
evento ``error`` (la respuesta HTTP no puede convertirse en 503 a mitad).
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from api import client_ip
from auth import require_client
from models.schema import (
    AuditAction,
    AuditResourceType,
    ChatConversationCreate,
    ChatConversationOut,
    ChatFeedbackBody,
    ChatMessageCreate,
    ChatMessageOut,
    User,
)
from services import audit, chat
from services import db as dbmod
from services.rate_limit import rate_limit

logger = logging.getLogger("lolailo.chat")

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _gestora_or_403(user: User) -> str:
    if not user.gestora_id:
        raise HTTPException(status_code=403, detail="User has no gestora")
    return user.gestora_id


def _own_conversation_or_404(
    db: dbmod.Database, conversation_id: str, user: User
) -> dict[str, Any]:
    """404 (no-leak) salvo que la conversación sea del usuario Y su gestora."""
    row = db.get("chat_conversations", conversation_id)
    if (
        row is None
        or row.get("user_id") != user.id
        or not user.gestora_id
        or row.get("gestora_id") != user.gestora_id
    ):
        raise HTTPException(status_code=404, detail="Conversation not found")
    return row


@router.post("/conversations", response_model=ChatConversationOut, status_code=201)
async def create_conversation(
    body: ChatConversationCreate,
    user: User = Depends(require_client),
) -> Any:
    db = dbmod.get_db()
    gestora_id = _gestora_or_403(user)
    return db.insert(
        "chat_conversations",
        {"gestora_id": gestora_id, "user_id": user.id, "title": body.title},
    )


@router.get("/conversations", response_model=list[ChatConversationOut])
async def list_conversations(user: User = Depends(require_client)) -> Any:
    db = dbmod.get_db()
    gestora_id = _gestora_or_403(user)
    rows = db.select("chat_conversations", gestora_id=gestora_id, user_id=user.id)
    return list(reversed(rows))  # newest-first


@router.get("/conversations/{conversation_id}/messages", response_model=list[ChatMessageOut])
async def list_messages(
    conversation_id: str,
    user: User = Depends(require_client),
) -> Any:
    db = dbmod.get_db()
    _own_conversation_or_404(db, conversation_id, user)
    return db.select("chat_messages", conversation_id=conversation_id)


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: str,
    user: User = Depends(require_client),
) -> None:
    db = dbmod.get_db()
    _own_conversation_or_404(db, conversation_id, user)
    for message in db.select("chat_messages", conversation_id=conversation_id):
        db.delete("chat_messages", message["id"])
    db.delete("chat_conversations", conversation_id)


@router.post("/messages/{message_id}/feedback")
async def message_feedback(
    message_id: str,
    body: ChatFeedbackBody,
    user: User = Depends(require_client),
) -> Any:
    """Pulgar arriba/abajo sobre una respuesta del asistente (telemetría de
    calidad del RAG). Mismo modelo no-leak que el resto del chat."""
    db = dbmod.get_db()
    message = db.get("chat_messages", message_id)
    if message is None or message.get("role") != "assistant":
        raise HTTPException(status_code=404, detail="Message not found")
    _own_conversation_or_404(db, message["conversation_id"], user)
    db.update("chat_messages", message_id, {"feedback": body.feedback})
    return {"id": message_id, "feedback": body.feedback}


@router.post(
    "/conversations/{conversation_id}/messages",
    # LLM-cost endpoint (pregunta + verificación): 12/min por usuario.
    dependencies=[Depends(rate_limit("chat", 12))],
)
async def send_message(
    conversation_id: str,
    body: ChatMessageCreate,
    http_request: Request,
    user: User = Depends(require_client),
) -> StreamingResponse:
    """Envía una pregunta y streamea la respuesta grounded como SSE."""
    db = dbmod.get_db()
    conversation = _own_conversation_or_404(db, conversation_id, user)
    gestora_id = conversation["gestora_id"]

    if not conversation.get("title"):
        db.update(
            "chat_conversations",
            conversation_id,
            {"title": chat.title_from(body.content)},
        )

    # Auditoría al envío. El contenido NO va al audit log (dato de negocio de
    # la gestora); basta la traza de uso.
    audit.log_action(
        db,
        user=user,
        action=AuditAction.chat_message_sent,
        resource_type=AuditResourceType.conversation,
        resource_id=conversation_id,
        gestora_id=gestora_id,
        metadata={"chars": len(body.content)},
        ip_address=client_ip(http_request),
    )

    def event_stream():
        try:
            for event in chat.ask(db, conversation=conversation, question=body.content):
                yield chat.encode_sse(event)
        except Exception:  # noqa: BLE001 — stream abierto: el error viaja como evento
            logger.exception("Chat stream failed (conversation %s)", conversation_id)
            yield chat.encode_sse(
                {"type": "error", "detail": "Se ha producido un error inesperado."}
            )

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
