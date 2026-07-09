"""Chat Q&A sobre el RAG de la gestora (021).

El cliente pregunta en lenguaje natural a la documentación indexada de su
gestora. Cada respuesta se genera SOLO a partir de los chunks recuperados
(rag.search_silo — pre-filtro duro por gestora_id, sin doc_type) y cita sus
fuentes. El flujo por mensaje es un generador de eventos SSE:

    sources → delta* → verification? → done   (o error)

- ``sources``: las citas (precedent_id / version / doc_type / snippet) se
  conocen ANTES de generar — el frontend las pinta de inmediato.
- ``delta``: fragmentos de texto según los produce el proveedor (llm.stream;
  un proveedor sin streaming degrada a un único delta con la respuesta entera).
- ``verification``: grounding posterior con el verificador cruzado (020):
  un LLM de OTRO proveedor marca afirmaciones de la respuesta sin soporte en
  los extractos. Cada hallazgo debe citar el fragmento literal de la
  RESPUESTA o se descarta (el verificador también puede alucinar). Nunca
  bloquea: si falla, se omite con log.
- Sin documentación indexada no se llama al LLM: respuesta fija honesta
  (graceful degradation, y evita alucinar sobre un contexto vacío).

Privacidad: mismo seam que el resto del stack — llm.stream/complete_json
resuelven el proveedor por gestora con fail-closed a Ollama local.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Iterator, Optional

from config import ServiceNotConfiguredError
from services import db as dbmod
from services import llm, model_router, rag

logger = logging.getLogger("lolailo.chat")

# Últimos N mensajes de la conversación incluidos como contexto conversacional.
HISTORY_LIMIT = 12
# Chunks recuperados por pregunta (mismo presupuesto que el RAG de generación).
SOURCE_CHUNKS = rag.CONTEXT_CHUNKS
_SNIPPET_CHARS = 240
_MAX_VERIFY_FINDINGS = 5

NO_SOURCES_ANSWER = (
    "No he encontrado documentación relevante en la biblioteca de tu gestora "
    "para esa pregunta. Puede que el documento no esté subido o aún no esté "
    "indexado. Prueba a reformular la pregunta o consulta con tu administrador."
)

_CHAT_SYSTEM = (
    "Eres el asistente documental de una gestora de fondos de capital riesgo. "
    "Respondes preguntas usando EXCLUSIVAMENTE la información de los EXTRACTOS "
    "numerados que se te proporcionan (fragmentos de los precedentes y modelos "
    "de la propia gestora).\n\n"
    "Reglas:\n"
    "- Si la respuesta no está en los extractos, di claramente que la "
    "documentación disponible no lo cubre. NUNCA inventes datos, cláusulas ni "
    "referencias.\n"
    "- Cita los extractos que uses con su número entre corchetes, p. ej. [1].\n"
    "- Responde en el idioma de la pregunta.\n"
    "- Sé conciso y preciso; esto es documentación legal, no opinión jurídica. "
    "No des asesoramiento legal: describe lo que dicen los documentos."
)

_VERIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "problem": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["problem", "quote"],
            },
        },
    },
    "required": ["findings"],
}

_VERIFY_SYSTEM = (
    "Eres un verificador independiente. Se te dan unos EXTRACTOS de "
    "documentación y una RESPUESTA generada a partir de ellos. Tu ÚNICA misión "
    "es detectar afirmaciones materiales de la RESPUESTA que NO estén "
    "respaldadas por los EXTRACTOS (datos, importes, fechas, cláusulas o "
    "referencias que no aparecen en ellos).\n\n"
    "Para CADA hallazgo copia en 'quote' el fragmento problemático EXACTO y "
    "literal de la RESPUESTA. Si no puedes citarlo literal, NO lo reportes. "
    "Las frases donde la propia respuesta admite que la documentación no cubre "
    'algo NO son hallazgos. Si todo está respaldado devuelve {"findings": []}. '
    "Ante la duda, NO reportes: prefiere silencio a ruido."
)


def title_from(question: str) -> str:
    """Título de conversación derivado de la primera pregunta."""
    collapsed = " ".join(question.split())
    return collapsed[:80] + ("…" if len(collapsed) > 80 else "")


def _citations(hits: list[rag.ChatHit]) -> list[dict[str, Any]]:
    return [
        {
            "index": i + 1,
            "precedent_id": hit.precedent_id,
            "precedent_version_id": hit.precedent_version_id,
            "doc_type": hit.doc_type,
            "source": hit.source,
            "snippet": hit.text[:_SNIPPET_CHARS],
        }
        for i, hit in enumerate(hits)
    ]


def _build_prompt(
    hits: list[rag.ChatHit], history: list[dict[str, Any]], question: str
) -> str:
    excerpts = "\n\n".join(
        f"[{i + 1}] (tipo: {hit.doc_type or 'desconocido'})\n{hit.text}"
        for i, hit in enumerate(hits)
    )
    parts = [f"EXTRACTOS DE LA DOCUMENTACIÓN DE TU GESTORA:\n{excerpts}"]
    if history:
        lines = "\n".join(
            f"{'Usuario' if m['role'] == 'user' else 'Asistente'}: {m['content']}"
            for m in history
        )
        parts.append(f"CONVERSACIÓN PREVIA:\n{lines}")
    parts.append(f"PREGUNTA:\n{question}")
    return "\n\n".join(parts)


def _verify_grounding(
    answer: str, hits: list[rag.ChatHit], gestora_id: str
) -> Optional[dict[str, Any]]:
    """Grounding de la respuesta con el verificador cruzado (020).

    Reutiliza resolve_verify_config (misma política de privacidad: la capa se
    salta si la gestora la desactivó o su borrador no debe cruzar proveedor) y
    el mecanismo de auto-invalidación por cita literal. Nunca lanza.
    """
    from services import verifier  # local import: verifier importa llm

    if not answer.strip() or not hits:
        return None
    config = verifier.resolve_verify_config(gestora_id)
    if config is None:
        return None
    excerpts = "\n\n".join(f"[{i + 1}] {hit.text}" for i, hit in enumerate(hits))
    prompt = f"EXTRACTOS:\n{excerpts}\n\nRESPUESTA A VERIFICAR:\n{answer}"
    try:
        raw = llm.complete_json(
            prompt, _VERIFY_SCHEMA, max_tokens=1000, system=_VERIFY_SYSTEM,
            gestora_id=gestora_id, task="verify", config_override=config,
        )
    except (ServiceNotConfiguredError, ValueError) as exc:
        logger.warning("Verificación de grounding del chat saltada (%s).", exc)
        return None
    haystack = verifier._normalise(answer)
    findings: list[dict[str, Any]] = []
    for item in (raw.get("findings") or [])[:_MAX_VERIFY_FINDINGS * 2]:
        if not isinstance(item, dict):
            continue
        quote = str(item.get("quote") or "").strip()
        if not quote or verifier._normalise(quote) not in haystack:
            continue  # cita no literal: el hallazgo se autoinvalida
        findings.append({
            "category": "afirmacion_sin_soporte",
            "problem": str(item.get("problem") or ""),
            "quote": quote,
        })
        if len(findings) >= _MAX_VERIFY_FINDINGS:
            break
    return {
        "findings": findings,
        "provider": config.llm_provider,
        "model": model_router.model_of(config),
    }


def ask(
    db: dbmod.Database,
    *,
    conversation: dict[str, Any],
    question: str,
) -> Iterator[dict[str, Any]]:
    """Procesa una pregunta y produce los eventos SSE del turno.

    Persiste el mensaje del usuario, recupera fuentes, streamea la respuesta,
    la verifica y persiste el mensaje del asistente (citations + verification
    + model_note). El caller (api/chat.py) serializa los eventos y audita.
    """
    gestora_id = conversation["gestora_id"]
    conversation_id = conversation["id"]

    # Historial ANTES de insertar la pregunta (la pregunta va aparte al prompt).
    history = db.select("chat_messages", conversation_id=conversation_id)[-HISTORY_LIMIT:]
    db.insert(
        "chat_messages",
        {
            "conversation_id": conversation_id,
            "gestora_id": gestora_id,
            "role": "user",
            "content": question,
        },
    )

    hits = rag.search_silo(
        db, gestora_id=gestora_id, language="", query_text=question, limit=SOURCE_CHUNKS
    )
    citations = _citations(hits)
    yield {"type": "sources", "citations": citations}

    if not hits:
        # Silo vacío o sin nada indexado: respuesta fija, sin llamada al LLM.
        message = db.insert(
            "chat_messages",
            {
                "conversation_id": conversation_id,
                "gestora_id": gestora_id,
                "role": "assistant",
                "content": NO_SOURCES_ANSWER,
                "citations": [],
                "verification": None,
                "model_note": None,
            },
        )
        yield {"type": "delta", "text": NO_SOURCES_ANSWER}
        yield {"type": "done", "message_id": message["id"]}
        return

    prompt = _build_prompt(hits, history, question)
    parts: list[str] = []
    try:
        for delta in llm.stream(
            prompt, max_tokens=2048, system=_CHAT_SYSTEM,
            gestora_id=gestora_id, task="chat",
        ):
            parts.append(delta)
            yield {"type": "delta", "text": delta}
    except ServiceNotConfiguredError as exc:
        # Proveedor caído a mitad de turno: el error llega como evento SSE
        # (la respuesta HTTP ya está abierta, no puede convertirse en 503).
        logger.warning("Chat: proveedor LLM no disponible (%s).", exc)
        yield {"type": "error", "detail": str(exc)}
        return

    answer = "".join(parts)
    verification = _verify_grounding(answer, hits, gestora_id)
    if verification is not None and verification["findings"]:
        yield {"type": "verification", **verification}

    message = db.insert(
        "chat_messages",
        {
            "conversation_id": conversation_id,
            "gestora_id": gestora_id,
            "role": "assistant",
            "content": answer,
            "citations": citations,
            "verification": verification,
            "model_note": llm.describe_model(gestora_id, task="chat"),
        },
    )
    yield {"type": "done", "message_id": message["id"]}


def encode_sse(event: dict[str, Any]) -> str:
    """Un evento del generador como frame SSE (data-only, JSON)."""
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
