"""Verificador cruzado anti-alucinaciones (020).

Tras el critic, una pasada independiente busca SOLO fallos garrafales — los
errores que un abogado consideraría inaceptables — en dos capas:

Capa 1 — DETERMINISTA (sin LLM, no puede alucinar): los datos duros que el
  cliente CONFIRMÓ en el intake (partes, importes, fechas clave) se cotejan
  contra el borrador por comparación de texto normalizado. Un dato confirmado
  ausente del borrador es el fallo garrafal por antonomasia y se detecta con
  precisión del 100%. Los campos parafraseables (jurisdicción, ley aplicable)
  se dejan a la capa 2 para no generar falsos positivos.

Capa 2 — LLM DE OTRO PROVEEDOR: un modelo de una familia distinta a la que
  redactó revisa con una checklist CERRADA (dato inventado, contradicción
  interna, referencia legal dudosa, idioma/jurisdicción incorrectos). Un
  modelo revisándose a sí mismo comparte sus puntos ciegos; uno ajeno falla
  diferente. Cada hallazgo debe citar el fragmento exacto del borrador
  (grounding, mismo mecanismo que el critic): si la cita no aparece
  literalmente, el hallazgo se descarta — el verificador también puede
  alucinar, y así se autoinvalida.

Política: un hallazgo crítico FUERZA Exit B (validación por abogado). El
verificador nunca reescribe, nunca entra en bucle con el drafter, y su fallo
nunca bloquea la generación (la capa 1 corre siempre; la 2 se salta con log).

Privacidad (regla conservadora):
- Gestora SIN override → el verificador usa VERIFY_PROVIDER de plataforma, o
  en auto el primer cloud configurado distinto del drafter (mismo semántica
  de opt-in de plataforma que el resto del stack).
- Gestora CON proveedor LLM explícito → su borrador NO cruza a otro proveedor
  salvo que ella misma fije ``verify_provider`` en su configuración.
- ``verify_provider='none'`` desactiva la capa 2 para esa gestora.
- Error leyendo la configuración → fail-closed: verificador local (Ollama).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from config import ServiceNotConfiguredError, get_settings
from services import db as dbmod
from services import llm, model_router

logger = logging.getLogger("lolailo.verifier")

# Proveedores cloud candidatos para el modo auto, en orden de preferencia.
# Ollama queda fuera del auto (en despliegues cloud no hay daemon y solo
# generaría ruido); una gestora local-only llega aquí por su propio override.
_AUTO_CANDIDATES = ("anthropic", "grok", "mistral")

_MONTHS = {
    "es": ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
           "agosto", "septiembre", "octubre", "noviembre", "diciembre"],
    "en": ["january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december"],
    "fr": ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
           "août", "septembre", "octobre", "novembre", "décembre"],
    "de": ["januar", "februar", "märz", "april", "mai", "juni", "juli",
           "august", "september", "oktober", "november", "dezember"],
}

_CATEGORIES = {
    "dato_inventado", "contradiccion_interna", "referencia_legal_dudosa",
    "idioma_incorrecto", "jurisdiccion_incorrecta",
}
_MAX_LLM_FINDINGS = 10

_VERIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "category": {"type": "string"},
                    "severity": {"type": "string", "enum": ["critical", "warning"]},
                    "problem": {"type": "string"},
                    "quote": {"type": "string"},
                    "where": {"type": "string"},
                },
                "required": ["category", "severity", "problem", "quote"],
            },
        },
    },
    "required": ["findings"],
}

_VERIFY_SYSTEM = (
    "Eres un verificador independiente de documentos legales. Tu ÚNICA misión "
    "es detectar FALLOS GARRAFALES en el borrador: errores que un abogado "
    "consideraría inaceptables. NO opines sobre estilo, redacción ni mejoras "
    "posibles.\n\n"
    "Categorías permitidas (campo category):\n"
    "- dato_inventado: partes, importes, fechas o hechos que NO están en los "
    "parámetros confirmados\n"
    "- contradiccion_interna: cláusulas del propio documento que se contradicen\n"
    "- referencia_legal_dudosa: cita de norma, ley o artículo que parece inventada\n"
    "- idioma_incorrecto: el documento no está en el idioma solicitado\n"
    "- jurisdiccion_incorrecta: jurisdicción o ley aplicable distintas de las confirmadas\n\n"
    "Para CADA hallazgo copia en 'quote' el fragmento problemático EXACTO y "
    "literal del borrador. Si no puedes citar el fragmento exacto, NO reportes "
    "el hallazgo. Si el documento no tiene fallos garrafales devuelve "
    '{"findings": []}. Ante la duda, NO reportes: prefiere silencio a ruido.'
)


def _normalise(text: str) -> str:
    """Case-folded, whitespace-collapsed text (mismo criterio que el critic)."""
    return " ".join(text.split()).casefold()


def _digits_only(text: str) -> str:
    """Solo dígitos — importes '500.000', '500 000' y '500,000' colapsan igual."""
    return re.sub(r"\D", "", text)


def _finding(layer: str, category: str, severity: str, problem: str,
             quote: str = "", where: str = "") -> dict[str, Any]:
    return {"layer": layer, "category": category, "severity": severity,
            "problem": problem, "quote": quote, "where": where}


def _date_renderings(iso: str, language: str) -> list[str]:
    """Formas aceptables de una fecha ISO en el borrador (todas normalizadas)."""
    match = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", iso.strip())
    if not match:
        return []  # fecha no parseable: no se puede cotejar con precisión
    year, month, day = match.group(1), int(match.group(2)), int(match.group(3))
    forms = [
        iso.strip(),
        f"{day:02d}/{month:02d}/{year}", f"{day}/{month}/{year}",
        f"{day:02d}-{month:02d}-{year}", f"{day:02d}.{month:02d}.{year}",
    ]
    for lang, months in _MONTHS.items():
        if language and lang != language:
            continue
        name = months[month - 1]
        forms += [
            f"{day} de {name} de {year}",   # es
            f"{name} {day}, {year}",         # en
            f"{day} {name} {year}",          # en/fr
            f"{day}. {name} {year}",         # de
        ]
    return [_normalise(f) for f in forms]


def deterministic_findings(
    draft_text: str, params: dict[str, Any], language: str = ""
) -> list[dict[str, Any]]:
    """Capa 1: datos confirmados del intake ausentes del borrador.

    Alta precisión por diseño: solo se cotejan datos literales (nombres de
    partes, secuencias de dígitos de importes, fechas en sus formas usuales).
    Un falso 'encontrado' es inocuo (no genera hallazgo); un 'ausente' es
    fiable. Los valores textuales parafraseables no se cotejan aquí.
    """
    findings: list[dict[str, Any]] = []
    haystack = _normalise(draft_text)
    haystack_digits = _digits_only(draft_text)

    for party in params.get("parties") or []:
        name = str((party or {}).get("name") or "").strip()
        if len(name) < 4:
            continue  # demasiado corto para un cotejo fiable
        if _normalise(name) not in haystack:
            findings.append(_finding(
                "deterministic", "dato_inventado", "critical",
                f"La parte confirmada «{name}» no aparece en el borrador.",
                where=f"parte: {party.get('role') or ''}".strip(),
            ))

    for term in params.get("key_terms") or []:
        value = str((term or {}).get("value") or "")
        digits = _digits_only(value)
        if len(digits) < 3:
            continue  # solo términos con componente numérico significativo
        if digits not in haystack_digits:
            findings.append(_finding(
                "deterministic", "dato_inventado", "critical",
                f"El término confirmado «{term.get('field')}: {value}» no aparece "
                "en el borrador (el importe/cifra no coincide).",
                where=f"término: {term.get('field') or ''}".strip(),
            ))

    for key_date in params.get("key_dates") or []:
        iso = str((key_date or {}).get("date") or "")
        renderings = _date_renderings(iso, language)
        if not renderings:
            continue
        if not any(r in haystack for r in renderings):
            findings.append(_finding(
                "deterministic", "dato_inventado", "critical",
                f"La fecha confirmada «{key_date.get('label')}: {iso}» no aparece "
                "en el borrador en ningún formato reconocible.",
                where=f"fecha: {key_date.get('label') or ''}".strip(),
            ))

    return findings


def resolve_verify_config(gestora_id: Optional[str]) -> Optional[llm.EffectiveLLMConfig]:
    """El EffectiveLLMConfig para la capa LLM, o None si está desactivada.

    Parte SIEMPRE de llm.resolve_config (hereda BYO keys y el fail-closed a
    local) y solo cambia el proveedor según la política de privacidad del
    docstring del módulo. El modelo se enruta al tier light (task='verify').
    """
    settings = get_settings()
    if not settings.verify_enabled:
        return None

    drafter = llm.resolve_config(gestora_id)  # fail-closed incluido

    override_row: Optional[dict[str, Any]] = None
    if gestora_id:
        try:
            override_row = llm._load_override_row(gestora_id)
        except Exception:  # noqa: BLE001 — fail CLOSED: verificador local
            logger.warning(
                "No se pudo leer la config de la gestora %s; verificador "
                "fail-closed a local (Ollama).", gestora_id,
            )
            return model_router.apply(llm._local_llm_config(settings), "verify")

    gestora_verify = (override_row or {}).get("verify_provider") or ""
    if gestora_verify == "none":
        return None
    if gestora_verify:
        target = gestora_verify
    elif (override_row or {}).get("llm_provider"):
        # Proveedor explícito de la gestora: su borrador no cruza a otro
        # proveedor sin su propio verify_provider.
        target = drafter.llm_provider
    elif settings.verify_provider:
        target = settings.verify_provider
    else:
        # Auto: primer cloud configurado distinto del drafter; si no hay,
        # mismo proveedor (la checklist sigue aportando, con menos cruce).
        from services import providers  # local import

        target = next(
            (name for name in _AUTO_CANDIDATES
             if name != drafter.llm_provider and providers.llm_configured(name, settings)),
            drafter.llm_provider,
        )

    config = llm.EffectiveLLMConfig(
        llm_provider=target,
        claude_model=drafter.claude_model,
        anthropic_api_key=drafter.anthropic_api_key,
        ollama_base_url=drafter.ollama_base_url,
        ollama_llm_model=drafter.ollama_llm_model,
        mistral_api_key=drafter.mistral_api_key,
        mistral_model=drafter.mistral_model,
        xai_api_key=drafter.xai_api_key,
        grok_model=drafter.grok_model,
        model_pinned=False,  # el verificador siempre puede ir al tier light
    )
    return model_router.apply(config, "verify")


def _ground_llm_findings(
    raw_findings: list[Any], draft_text: str
) -> list[dict[str, Any]]:
    """Normaliza y descarta hallazgos LLM sin cita literal en el borrador."""
    haystack = _normalise(draft_text)
    grounded: list[dict[str, Any]] = []
    for raw in raw_findings[:_MAX_LLM_FINDINGS * 2]:
        if not isinstance(raw, dict):
            continue
        category = str(raw.get("category") or "").strip().lower()
        if category not in _CATEGORIES:
            continue
        quote = str(raw.get("quote") or "").strip()
        if not quote or _normalise(quote) not in haystack:
            logger.info("Hallazgo del verificador descartado (cita no literal): %r", quote[:80])
            continue
        severity = str(raw.get("severity") or "warning").lower()
        grounded.append(_finding(
            "llm", category,
            severity if severity in ("critical", "warning") else "warning",
            str(raw.get("problem") or ""), quote=quote,
            where=str(raw.get("where") or ""),
        ))
        if len(grounded) >= _MAX_LLM_FINDINGS:
            break
    return grounded


def _llm_findings(
    draft_text: str,
    params: dict[str, Any],
    language: str,
    config: llm.EffectiveLLMConfig,
    gestora_id: Optional[str],
) -> list[dict[str, Any]]:
    import json as _json

    confirmed = {
        "idioma": language,
        "partes": params.get("parties") or [],
        "fechas_clave": params.get("key_dates") or [],
        "terminos_clave": params.get("key_terms") or [],
        "jurisdiccion": params.get("jurisdiction") or "",
        "ley_aplicable": params.get("governing_law") or "",
    }
    prompt = (
        "PARÁMETROS CONFIRMADOS POR EL CLIENTE:\n"
        f"{_json.dumps(confirmed, ensure_ascii=False)}\n\n"
        "BORRADOR A VERIFICAR:\n"
        f"{draft_text}"
    )
    raw = llm.complete_json(
        prompt, _VERIFY_SCHEMA, max_tokens=2000, system=_VERIFY_SYSTEM,
        gestora_id=gestora_id, task="verify", config_override=config,
    )
    return _ground_llm_findings(raw.get("findings") or [], draft_text)


def run(
    db: dbmod.Database,
    *,
    request_id: str,
    iteration: int,
    gestora_id: str,
    draft_text: str,
    params: dict[str, Any],
    language: str,
    deterministic_severity: str = "critical",
) -> dict[str, Any]:
    """Ambas capas + persistencia. Devuelve el resumen; NUNCA lanza por la
    capa LLM (proveedor caído → se salta con log; la determinista corre
    siempre). El caller decide forzar Exit B con ``forced_counsel``.

    ``deterministic_severity``: en refinamientos el cliente puede haber pedido
    cambiar un importe o fecha respecto a lo confirmado en el intake — ahí los
    hallazgos deterministas bajan a 'warning' (no fuerzan Exit B) y solo la
    capa LLM (contradicciones, referencias inventadas) mantiene el forzado.
    """
    settings = get_settings()
    if not settings.verify_enabled:
        return {"findings": [], "critical_count": 0, "forced_counsel": False,
                "provider": None, "model": None, "llm_ran": False}

    findings = deterministic_findings(draft_text, params, language)
    if deterministic_severity != "critical":
        for finding in findings:
            finding["severity"] = deterministic_severity
    provider: Optional[str] = None
    model: Optional[str] = None
    llm_ran = False

    config = resolve_verify_config(gestora_id)
    if config is not None:
        try:
            findings += _llm_findings(draft_text, params, language, config, gestora_id)
            llm_ran = True
            provider = config.llm_provider
            model = model_router.model_of(config)
        except (ServiceNotConfiguredError, ValueError) as exc:
            logger.warning("Capa LLM del verificador saltada (%s); la capa "
                           "determinista ya corrió.", exc)

    critical_count = sum(1 for f in findings if f["severity"] == "critical")
    forced_counsel = critical_count > 0
    db.insert(
        "verifications",
        {
            "request_id": request_id,
            "iteration": iteration,
            "provider": provider,
            "model": model,
            "findings": findings,
            "critical_count": critical_count,
            "forced_counsel": forced_counsel,
        },
    )
    if forced_counsel:
        logger.info(
            "Verificador: %d hallazgo(s) crítico(s) en request %s (iter %d) — "
            "se fuerza Exit B.", critical_count, request_id, iteration,
        )
    return {"findings": findings, "critical_count": critical_count,
            "forced_counsel": forced_counsel, "provider": provider,
            "model": model, "llm_ran": llm_ran}
