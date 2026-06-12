"""Hybrid structured intake fields per document type (improvement #5).

``DOC_TYPE_FIELDS`` maps every doc_type of the catalog (models/schema.py
DOC_TYPE_CATALOG — exact Spanish labels) to a list of field specs:

    {key, label_i18n_key, type, required, options?, help?}

with type one of 'text' | 'date' | 'amount' | 'percent' | 'party' | 'select'.
Doc types without an entry are freetext-only (empty list = unchanged behavior).

Client-provided structured values are AUTHORITATIVE: they are surfaced to the
intake parser as ground truth and deterministically merged over the parser
output afterwards (merge_structured_into_parsed), so a hallucinated or
[UNCLEAR] extraction can never override what the client typed.

Framework-free module: validation raises ValueError; the API layer maps it
to HTTP 422.
"""
from __future__ import annotations

from typing import Any, Optional

# ---------------------------------------------------------------------------
# Field labels (resolved es+en; the frontend mirrors these keys in lib/i18n.ts)
# ---------------------------------------------------------------------------

FIELD_LABELS: dict[str, dict[str, str]] = {
    "docfields.importe_total": {"es": "Importe total", "en": "Total amount"},
    "docfields.fecha_limite_pago": {"es": "Fecha límite de pago", "en": "Payment deadline"},
    "docfields.porcentaje_compromiso": {"es": "Porcentaje sobre compromiso", "en": "Percentage of commitment"},
    "docfields.numero_llamada": {"es": "Nº de llamada", "en": "Call number"},
    "docfields.importe": {"es": "Importe", "en": "Amount"},
    "docfields.fecha": {"es": "Fecha", "en": "Date"},
    "docfields.concepto": {"es": "Concepto / origen", "en": "Concept / origin"},
    "docfields.contraparte": {"es": "Contraparte", "en": "Counterparty"},
    "docfields.duracion_meses": {"es": "Duración (meses)", "en": "Duration (months)"},
    "docfields.modalidad": {"es": "Unilateral o recíproco", "en": "Unilateral or mutual"},
    "docfields.fecha_reunion": {"es": "Fecha de la reunión", "en": "Meeting date"},
    "docfields.asistentes": {"es": "Asistentes", "en": "Attendees"},
    "docfields.acuerdos_principales": {"es": "Acuerdos principales", "en": "Main resolutions"},
    "docfields.persona": {"es": "Persona", "en": "Person"},
    "docfields.cargo": {"es": "Cargo", "en": "Position"},
    "docfields.tipo": {"es": "Tipo", "en": "Type"},
    "docfields.fecha_efecto": {"es": "Fecha de efecto", "en": "Effective date"},
    "docfields.apoderado": {"es": "Apoderado", "en": "Attorney-in-fact"},
    "docfields.facultades": {"es": "Facultades", "en": "Powers granted"},
    "docfields.vigencia": {"es": "Vigencia", "en": "Validity (end date)"},
    "docfields.compania_objetivo": {"es": "Compañía objetivo", "en": "Target company"},
    "docfields.importe_inversion": {"es": "Importe de inversión", "en": "Investment amount"},
    "docfields.valoracion_premoney": {"es": "Valoración pre-money", "en": "Pre-money valuation"},
    "docfields.tipo_instrumento": {"es": "Tipo de instrumento", "en": "Instrument type"},
    "docfields.inversor": {"es": "Inversor", "en": "Investor"},
    "docfields.derechos_solicitados": {"es": "Derechos solicitados", "en": "Requested rights"},
    "docfields.fecha_referencia": {"es": "Fecha de referencia", "en": "Reference date"},
    "docfields.nueva_fecha": {"es": "Nueva fecha", "en": "New date"},
    "docfields.justificacion": {"es": "Justificación", "en": "Justification"},
}


def _spec(
    key: str,
    label_i18n_key: str,
    type_: str,
    required: bool = True,
    options: Optional[list[str]] = None,
    help_: Optional[str] = None,
) -> dict[str, Any]:
    spec: dict[str, Any] = {
        "key": key,
        "label_i18n_key": label_i18n_key,
        "type": type_,
        "required": required,
    }
    if options is not None:
        spec["options"] = options
    if help_ is not None:
        spec["help"] = help_
    return spec


# Shared by "Extensión del Período de Inversión" and "Extensión del Plazo del Fondo".
_EXTENSION_FIELDS: list[dict[str, Any]] = [
    _spec("nueva_fecha", "docfields.nueva_fecha", "date"),
    _spec("justificacion", "docfields.justificacion", "text", required=False),
]

# Keyed by the EXACT catalog labels in models/schema.py DOC_TYPE_CATALOG.
# Doc types absent from this dict are freetext-only (fields_for -> []).
DOC_TYPE_FIELDS: dict[str, list[dict[str, Any]]] = {
    "Llamada de Capital (Capital Call Notice)": [
        _spec("importe_total", "docfields.importe_total", "amount"),
        _spec("fecha_limite_pago", "docfields.fecha_limite_pago", "date"),
        _spec(
            "porcentaje_compromiso",
            "docfields.porcentaje_compromiso",
            "percent",
            help_="0-100",
        ),
        _spec("numero_llamada", "docfields.numero_llamada", "text", required=False),
    ],
    "Distribución a Inversores (Distribution Notice)": [
        _spec("importe", "docfields.importe", "amount"),
        _spec("fecha", "docfields.fecha", "date"),
        _spec(
            "concepto",
            "docfields.concepto",
            "select",
            options=["desinversión", "dividendos", "intereses", "otro"],
        ),
    ],
    "NDA / Acuerdo de Confidencialidad": [
        _spec("contraparte", "docfields.contraparte", "party"),
        _spec("duracion_meses", "docfields.duracion_meses", "text"),
        _spec(
            "modalidad",
            "docfields.modalidad",
            "select",
            options=["unilateral", "recíproco"],
        ),
    ],
    "Acta de Reunión del Consejo": [
        _spec("fecha_reunion", "docfields.fecha_reunion", "date"),
        _spec("asistentes", "docfields.asistentes", "text"),
        _spec("acuerdos_principales", "docfields.acuerdos_principales", "text"),
    ],
    "Nombramiento / Cese de Administrador": [
        _spec("persona", "docfields.persona", "party"),
        _spec("cargo", "docfields.cargo", "text"),
        _spec("tipo", "docfields.tipo", "select", options=["nombramiento", "cese"]),
        _spec("fecha_efecto", "docfields.fecha_efecto", "date"),
    ],
    "Poder Especial": [
        _spec("apoderado", "docfields.apoderado", "party"),
        _spec("facultades", "docfields.facultades", "text"),
        _spec("vigencia", "docfields.vigencia", "date", required=False),
    ],
    "Term Sheet (no vinculante)": [
        _spec("compania_objetivo", "docfields.compania_objetivo", "party"),
        _spec("importe_inversion", "docfields.importe_inversion", "amount"),
        _spec(
            "valoracion_premoney",
            "docfields.valoracion_premoney",
            "amount",
            required=False,
        ),
        _spec(
            "tipo_instrumento",
            "docfields.tipo_instrumento",
            "select",
            options=["equity", "convertible", "SAFE"],
        ),
    ],
    "Side Letter con Inversor": [
        _spec("inversor", "docfields.inversor", "party"),
        _spec("derechos_solicitados", "docfields.derechos_solicitados", "text"),
    ],
    "Certificado de Participación del Inversor": [
        _spec("inversor", "docfields.inversor", "party"),
        _spec("fecha_referencia", "docfields.fecha_referencia", "date"),
    ],
    "Extensión del Período de Inversión": _EXTENSION_FIELDS,
    "Extensión del Plazo del Fondo": _EXTENSION_FIELDS,
}

# The frontend identifies doc types by slug (frontend/lib/catalog.ts values)
# while the backend catalog uses the Spanish labels; accept both so the
# fields endpoint and intake validation work with either identifier.
FRONTEND_SLUG_ALIASES: dict[str, str] = {
    "llamada_capital": "Llamada de Capital (Capital Call Notice)",
    "distribucion_inversores": "Distribución a Inversores (Distribution Notice)",
    "nda": "NDA / Acuerdo de Confidencialidad",
    "acta_reunion_consejo": "Acta de Reunión del Consejo",
    "nombramiento_cese_administrador": "Nombramiento / Cese de Administrador",
    "poder_especial": "Poder Especial",
    "term_sheet": "Term Sheet (no vinculante)",
    "side_letter_inversor": "Side Letter con Inversor",
    "certificado_participacion_inversor": "Certificado de Participación del Inversor",
    "extension_periodo_inversion": "Extensión del Período de Inversión",
    "extension_plazo_fondo": "Extensión del Plazo del Fondo",
}


def fields_for(doc_type: str) -> list[dict[str, Any]]:
    """Field specs for a doc_type (catalog label or frontend slug); [] when
    the doc type is freetext-only."""
    canonical = FRONTEND_SLUG_ALIASES.get(doc_type.strip().lower(), doc_type)
    return DOC_TYPE_FIELDS.get(canonical, [])


def resolved_fields(doc_type: str) -> list[dict[str, Any]]:
    """Field specs with resolved es+en labels (fields endpoint payload)."""
    return [
        {**spec, "label": FIELD_LABELS.get(spec["label_i18n_key"], {})}
        for spec in fields_for(doc_type)
    ]


def label_es(spec: dict[str, Any]) -> str:
    return FIELD_LABELS.get(spec["label_i18n_key"], {}).get("es", spec["key"])


def validate_structured_fields(doc_type: str, structured_fields: dict[str, Any]) -> None:
    """Reject keys that are not in the registry for this doc_type.

    Required keys MAY be missing at submit time — the parser flags them as
    unclear; only unknown keys are an error (API layer -> HTTP 422).
    """
    known = {spec["key"] for spec in fields_for(doc_type)}
    unknown = sorted(set(structured_fields) - known)
    if unknown:
        raise ValueError(
            f"Unknown structured fields for doc_type '{doc_type}': {', '.join(unknown)}"
        )


# ---------------------------------------------------------------------------
# Deterministic post-merge over the parser output
# ---------------------------------------------------------------------------

def _covers(spec: dict[str, Any], name: str) -> bool:
    """True when a parser-side field name refers to this structured field
    (matches the registry key or its Spanish label, case-insensitive)."""
    normalized = name.strip().casefold()
    return normalized in (spec["key"].casefold(), label_es(spec).casefold())


def _clean_values(
    doc_type: str, structured_fields: dict[str, Any]
) -> list[tuple[dict[str, Any], str]]:
    """(spec, value) pairs for the non-empty structured values provided."""
    pairs: list[tuple[dict[str, Any], str]] = []
    for spec in fields_for(doc_type):
        raw = structured_fields.get(spec["key"])
        if raw is None:
            continue
        value = str(raw).strip()
        if value:
            pairs.append((spec, value))
    return pairs


def merge_structured_into_parsed(
    parsed: dict[str, Any], doc_type: str, structured_fields: dict[str, Any]
) -> dict[str, Any]:
    """Deterministically merge client-provided structured values over the
    parser output (we never trust the LLM alone to honor them):

    - party fields  -> parties   (role = Spanish label)
    - date fields   -> key_dates (label = Spanish label)
    - other fields  -> key_terms (field = Spanish label)
    Conflicting parser extractions are replaced; merged entries carry
    ``source: 'client_confirmed'``. Fields covered by structured input are
    removed from unclear_fields and generation_ready is recomputed.
    """
    pairs = _clean_values(doc_type, structured_fields)
    if not pairs:
        return parsed

    parties = list(parsed.get("parties") or [])
    key_dates = list(parsed.get("key_dates") or [])
    key_terms = list(parsed.get("key_terms") or [])
    unclear = list(parsed.get("unclear_fields") or [])

    for spec, value in pairs:
        label = label_es(spec)
        if spec["type"] == "party":
            parties = [p for p in parties if not _covers(spec, str(p.get("role", "")))]
            parties.append({"role": label, "name": value, "source": "client_confirmed"})
        elif spec["type"] == "date":
            key_dates = [d for d in key_dates if not _covers(spec, str(d.get("label", "")))]
            key_dates.append({"label": label, "date": value, "source": "client_confirmed"})
        else:
            key_terms = [t for t in key_terms if not _covers(spec, str(t.get("field", "")))]
            key_terms.append({"field": label, "value": value, "source": "client_confirmed"})
        unclear = [u for u in unclear if not _covers(spec, str(u))]

    parsed["parties"] = parties
    parsed["key_dates"] = key_dates
    parsed["key_terms"] = key_terms
    parsed["unclear_fields"] = unclear
    # Recompute readiness with the SPEC post-rules; an unclassifiable request
    # (message set) stays not-ready regardless of structured input.
    if not parsed.get("message"):
        confidence = float(parsed.get("confidence") or 0.0)
        parsed["generation_ready"] = confidence >= 0.7 and not unclear
    return parsed


def merge_structured_key_terms(
    key_terms: list[dict[str, Any]], doc_type: str, structured_fields: dict[str, Any]
) -> list[dict[str, Any]]:
    """key_terms for the generator prompt with ALL structured values included
    (the generator receives no key_dates, so dates/parties travel here too),
    marked as client-confirmed. Conflicting entries are replaced."""
    merged = list(key_terms)
    for spec, value in _clean_values(doc_type, structured_fields):
        merged = [t for t in merged if not _covers(spec, str(t.get("field", "")))]
        merged.append(
            {"field": label_es(spec), "value": value, "source": "client_confirmed"}
        )
    return merged
