"""Business constants: workflow state machine, doc-type catalog, legal texts.

Split out of models/schema.py (which remains the backwards-compatible facade).
"""
from __future__ import annotations

from models.enums import RequestStatus


# ---------------------------------------------------------------------------
# Allowed workflow transitions (guardrail: enforced on every status change)
# ---------------------------------------------------------------------------

STATUS_TRANSITIONS: dict[RequestStatus, set[RequestStatus]] = {
    RequestStatus.parsing: {RequestStatus.confirmed},
    RequestStatus.confirmed: {RequestStatus.generating},
    # 'confirmed' = revert path after a generation job FINALLY fails, so the
    # client can re-trigger generation (services/jobs.py).
    RequestStatus.generating: {RequestStatus.review_pending, RequestStatus.confirmed},
    # 'generating' = iterative refinement loop (api/refinements.py): the
    # request re-enters generation and returns to 'review_pending' whether the
    # refinement is applied or fails (the previous draft stays valid).
    RequestStatus.review_pending: {
        RequestStatus.counsel_review,
        RequestStatus.delivered,
        RequestStatus.generating,
    },
    RequestStatus.counsel_review: {RequestStatus.validated},
    RequestStatus.validated: {RequestStatus.delivered},
    RequestStatus.delivered: set(),
}


# ---------------------------------------------------------------------------
# Document type catalog (grouped dropdown, SPEC.md)
# ---------------------------------------------------------------------------

DOC_TYPE_CATALOG: dict[str, list[str]] = {
    "🏛 Gobierno Corporativo": [
        "Acta de Reunión del Consejo",
        "Resolución del Consejo per rollam",
        "Acta de Junta General",
        "Resolución de Junta General sin Reunión",
        "Nombramiento / Cese de Administrador",
        "Poder General (Delegación de Facultades)",
        "Poder Especial",
    ],
    "💼 Operaciones de Fondo": [
        "Llamada de Capital (Capital Call Notice)",
        "Distribución a Inversores (Distribution Notice)",
        "Extensión del Período de Inversión",
        "Extensión del Plazo del Fondo",
        "Certificado de Participación del Inversor",
        "Waiver / Renuncia a Derecho Contractual",
    ],
    "📋 Gestión de Portfolio": [
        "Term Sheet (no vinculante)",
        "Carta de Intenciones (LOI)",
        "NDA / Acuerdo de Confidencialidad",
        "Acuerdo de Suscripción de Participaciones",
        "Resolución de Aprobación de Inversión",
        "Resolución de Seguimiento (Follow-on)",
        "Resolución de Desinversión",
    ],
    "⚖️ Cumplimiento y Regulatorio": [
        "Certificado de Titularidad Real (UBO)",
        "Declaración AML/KYC",
        "Certificado de Residencia Fiscal",
        "Comunicación a Regulador (CNMV / AMF / BaFin)",
        "Notificación AIFMD",
    ],
    "📝 Contratos con Terceros": [
        "Contrato de Prestación de Servicios",
        "Acuerdo de Asesoramiento (Advisory Agreement)",
        "Contrato de Gestor de Cartera Delegado",
        "Side Letter con Inversor",
    ],
    "🔧 Otros": [
        "Other (describir abajo)",
    ],
}

UNCLASSIFIABLE_MESSAGE = (
    "No hemos podido clasificar tu solicitud. Por favor reformúlala indicando "
    "el tipo de documento y las partes implicadas."
)

LEVEL3_WARNING = (
    "Este documento se ha generado sin precedente de referencia. La validación "
    "por abogado es obligatoria antes de su uso."
)

SLP_DISCLAIMER = (
    "Este documento ha sido generado por Lol-AI-lo Legal SLP. Su uso sin "
    "validación por abogado es responsabilidad exclusiva del cliente. "
    "Lol-AI-lo Legal SLP no asume responsabilidad por documentos descargados "
    "sin validación (Exit A)."
)

EXIT_A_CHECKBOX_TEXT = (
    "Entiendo que este documento no ha sido revisado por un abogado y asumo "
    "la responsabilidad de su uso."
)

# The exact confirmation phrase the client must type/send for a self-service
# deletion (also surfaced verbatim in the UI).
DATA_DELETE_CONFIRMATION = "ELIMINAR MIS DATOS"
