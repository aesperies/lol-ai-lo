"""Email notifications via Resend, with console fallback.

If RESEND_API_KEY is unset (or the resend package is missing) the email body
is logged to the console instead of sent — the workflow never blocks on email.
All client-facing email is sent from the Lol-AI-lo Legal SLP domain.
"""
from __future__ import annotations

import logging
from typing import Optional

from config import get_settings

logger = logging.getLogger("lolailo.email")
logging.basicConfig(level=logging.INFO)


def send_email(to: str, subject: str, body: str) -> dict:
    """Send (or log) one email. Returns a delivery descriptor."""
    settings = get_settings()
    if settings.resend_configured:
        try:
            import resend  # type: ignore[import-not-found]  # lazy optional dep
        except ImportError:
            logger.warning("RESEND_API_KEY set but resend package missing; logging instead.")
        else:
            # TODO: real Resend API key required (RESEND_API_KEY).
            resend.api_key = settings.resend_api_key
            result = resend.Emails.send(
                {"from": settings.email_from, "to": [to], "subject": subject, "text": body}
            )
            return {"delivery": "resend", "id": result.get("id"), "to": to, "subject": subject}

    logger.info("EMAIL (console fallback)\nFROM: %s\nTO: %s\nSUBJECT: %s\n%s",
                settings.email_from, to, subject, body)
    return {"delivery": "console", "to": to, "subject": subject}


def send_counsel_notification(
    *,
    counsel_name: str,
    counsel_email: str,
    fund_name: str,
    doc_type: str,
    requested_by: str,
    review_url: str,
    suggested_deadline: str,
) -> dict:
    """SPEC template: review-pending notification to counsel."""
    subject = f"[Lol-AI-lo] Revisión pendiente — {fund_name} — {doc_type}"
    body = (
        f"Hola {counsel_name},\n\n"
        f"Tienes un documento pendiente de revisión en Lol-AI-lo.\n\n"
        f"Fondo: {fund_name}\n"
        f"Tipo de documento: {doc_type}\n"
        f"Solicitado por: {requested_by}\n"
        f"Plazo sugerido: {suggested_deadline}\n\n"
        f"Revisar el documento: {review_url}\n\n"
        f"Lol-AI-lo Legal SLP"
    )
    return send_email(counsel_email, subject, body)


def send_client_ready(
    *,
    client_name: str,
    client_email: str,
    doc_type: str,
    fund_name: str,
    download_url: str,
    validated_by_counsel: Optional[str] = None,
) -> dict:
    """SPEC template: document-ready notification to the client."""
    subject = f"[Lol-AI-lo] Tu documento está listo — {doc_type}"
    validated_line = (
        f"Este documento ha sido validado por {validated_by_counsel}.\n" if validated_by_counsel else ""
    )
    body = (
        f"Hola {client_name},\n\n"
        f"Tu documento ya está disponible.\n\n"
        f"Tipo de documento: {doc_type}\n"
        f"Fondo: {fund_name}\n"
        f"{validated_line}\n"
        f"Descargar: {download_url}\n\n"
        f"Lol-AI-lo Legal SLP"
    )
    return send_email(client_email, subject, body)
