"""Background document pipelines: initial generation and iterative refinement.

Both run inside a generation job (services/jobs.py) enqueued by their
endpoints (api/documents.py, api/refinements.py); raising makes the job runner
retry. They share the same closing shape — save draft .docx, insert document
row, audit, then redline against the precedent base — with two policy
differences the docstrings call out: which base text the redline diffs against
and how an unclear refinement short-circuits.
"""
from __future__ import annotations

from typing import Any, Optional

from config import get_settings
from models.doc_branches import branch_for
from models.schema import (
    AuditAction,
    AuditResourceType,
    DocumentVersionType,
    RefinementStatus,
    RequestStatus,
    UsageEventType,
    User,
)
from models import doc_fields
from services import (
    audit,
    db as dbmod,
    docx_renderer,
    drafting_agents,
    generator,
    rag,
    redline as redline_service,
    storage,
    usage,
    verifier,
)
from services.workflow import latest_document, now_iso, transition


def _save_draft_with_audit(
    db: dbmod.Database,
    *,
    request_row: dict[str, Any],
    gestora_id: str,
    user: User,
    ip_address: Optional[str],
    text: str,
    filename: str,
    precedent_version_id: Optional[str],
    iteration: Optional[int],
    audit_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Persist a draft .docx + document row + document_generated audit entry."""
    request_id = request_row["id"]
    draft_key = storage.save(
        storage.outputs_path(gestora_id, request_row["fund_id"], request_id, filename),
        docx_renderer.render_docx(text),
    )
    fields: dict[str, Any] = {
        "request_id": request_id,
        "version_type": DocumentVersionType.draft.value,
        "file_path": draft_key,
        "precedent_version_id": precedent_version_id,
        "uploaded_by": None,
    }
    if iteration is not None:
        fields["iteration"] = iteration
    draft_doc = db.insert("documents", fields)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.document_generated,
        resource_type=AuditResourceType.document,
        resource_id=draft_doc["id"],
        gestora_id=gestora_id,
        metadata={"request_id": request_id, **audit_metadata},
        ip_address=ip_address,
    )
    return draft_doc


def _save_redline_with_audit(
    db: dbmod.Database,
    *,
    request_row: dict[str, Any],
    gestora_id: str,
    user: User,
    ip_address: Optional[str],
    base_text: str,
    text: str,
    filename: str,
    precedent_version_id: Optional[str],
    iteration: Optional[int],
    audit_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Persist a redline .docx (tracked changes vs the precedent base) + audit."""
    request_id = request_row["id"]
    redline_key = storage.save(
        storage.outputs_path(gestora_id, request_row["fund_id"], request_id, filename),
        redline_service.build_redline(base_text, text),
    )
    fields: dict[str, Any] = {
        "request_id": request_id,
        "version_type": DocumentVersionType.redline.value,
        "file_path": redline_key,
        "precedent_version_id": precedent_version_id,
        "uploaded_by": None,
    }
    if iteration is not None:
        fields["iteration"] = iteration
    redline_doc = db.insert("documents", fields)
    audit.log_action(
        db,
        user=user,
        action=AuditAction.redline_generated,
        resource_type=AuditResourceType.document,
        resource_id=redline_doc["id"],
        gestora_id=gestora_id,
        metadata={
            "request_id": request_id,
            "author": redline_service.REDLINE_AUTHOR,
            **audit_metadata,
        },
        ip_address=ip_address,
    )
    return redline_doc


def run_generation(
    db: dbmod.Database,
    request_id: str,
    gestora_id: str,
    user: User,
    ip_address: Optional[str],
) -> None:
    """The generation pipeline: RAG -> specialized drafter + critic -> docx ->
    redline vs the retrieved precedent base."""
    settings = get_settings()
    row = db.get("requests", request_id)
    if row is None:
        raise RuntimeError(f"Request {request_id} disappeared during generation")
    params = row.get("parsed_params") or {}
    fund = db.get("funds", row["fund_id"]) or {}
    gestora = db.get("gestoras", gestora_id) or {}
    language = row.get("language") or params.get("language") or "es"

    # RAG: hard gestora_id + doc_type pre-filter, then fallback chain.
    # Structured intake fields need no RAG change: retrieval is already keyed
    # by doc_type (+ gestora/language/freetext); the structured values only
    # affect the parser and the generation prompt below.
    retrieval = rag.retrieve(
        db,
        gestora_id=gestora_id,
        doc_type=row["doc_type"],
        language=language,
        query_text=row["freetext"],
    )
    if retrieval.requires_counsel:
        # Level 3 ALWAYS forces Exit B (guardrail 10).
        db.update("requests", request_id, {"requires_counsel": True})
        row["requires_counsel"] = True

    # Structured intake values travel inside {key_terms} marked as
    # client-confirmed (source: 'client_confirmed'); they replace any
    # conflicting parser-derived term. Idempotent when the parser merge
    # already injected them into parsed_params.
    key_terms = doc_fields.merge_structured_key_terms(
        params.get("key_terms", []),
        row["doc_type"],
        row.get("structured_fields") or {},
    )

    # Specialized branch agent (Feature 1) + critic loop (Feature 2). The
    # branch persona is passed as the LLM system message and the gestora's
    # learned lessons (Feature 3, siloed) are injected as extra guidance — the
    # verbatim GENERATION_PROMPT is never edited. The critic runs as extra LLM
    # passes inside this async job and degrades to a no-op when the LLM is
    # unreachable.
    branch = branch_for(row["doc_type"])
    review_result = drafting_agents.draft_with_review(
        doc_type=row["doc_type"],
        language=language,
        fund_name=fund.get("name", ""),
        gestora_name=gestora.get("name", ""),
        jurisdiction=params.get("jurisdiction") or fund.get("jurisdiction", ""),
        governing_law=params.get("governing_law", ""),
        parties=params.get("parties", []),
        key_terms=key_terms,
        freetext=row["freetext"],
        precedent_text=retrieval.base_text,
        parsed_params=params,
        gestora_id=gestora_id,
        db=db,
    )
    text = review_result.text
    if retrieval.warning:
        text = f"{text}\n\n{retrieval.warning}"

    # Persist the critic review trail (one row per round) and, if the critic
    # could not get the draft approved within budget, force Exit B.
    for review_round in review_result.rounds:
        db.insert(
            "generation_reviews",
            {
                "request_id": request_id,
                "iteration": 0,
                "round": review_round.round,
                "approved": review_round.approved,
                "issues": review_round.issues,
                "model_note": review_round.model_note,
            },
        )
    if review_result.forced_counsel:
        db.update("requests", request_id, {"requires_counsel": True})
        row["requires_counsel"] = True

    # Verificador cruzado (020): capa determinista + LLM de otro proveedor.
    # Nunca bloquea la generación; un hallazgo crítico fuerza Exit B.
    verification: Optional[dict[str, Any]] = None
    try:
        verification = verifier.run(
            db,
            request_id=request_id,
            iteration=0,
            gestora_id=gestora_id,
            draft_text=review_result.text,
            params={**params, "key_terms": key_terms},
            language=language,
        )
        if verification["forced_counsel"] and not row.get("requires_counsel"):
            db.update("requests", request_id, {"requires_counsel": True})
            row["requires_counsel"] = True
    except Exception:  # noqa: BLE001 — el verificador jamás rompe el flujo
        logger.exception("Verificador cruzado falló para request %s", request_id)

    _save_draft_with_audit(
        db,
        request_row=row,
        gestora_id=gestora_id,
        user=user,
        ip_address=ip_address,
        text=text,
        filename="draft.docx",
        precedent_version_id=retrieval.base_version_id,
        iteration=None,
        audit_metadata={
            "doc_type": row["doc_type"],
            "language": language,
            "rag_level": retrieval.level,
            "precedent_version_id": retrieval.base_version_id,
            "model": settings.claude_model,
            # Specialized drafting branch (Feature 1).
            "branch": branch.value,
            # Critic loop outcome (Feature 2): only populated when the critic ran.
            "critic": {
                "rounds": len(review_result.rounds),
                "approved": review_result.approved,
                "forced_counsel": review_result.forced_counsel,
            },
            # Verificador cruzado (020): resumen auditable.
            "verification": (
                {
                    "critical": verification["critical_count"],
                    "findings": len(verification["findings"]),
                    "provider": verification["provider"],
                    "llm_ran": verification["llm_ran"],
                }
                if verification is not None
                else None
            ),
        },
    )
    usage.record_usage(
        db, gestora_id=gestora_id, request_id=request_id, event_type=UsageEventType.document_generated
    )

    if retrieval.base_text is not None:
        _save_redline_with_audit(
            db,
            request_row=row,
            gestora_id=gestora_id,
            user=user,
            ip_address=ip_address,
            base_text=retrieval.base_text,
            text=text,
            filename="redline.docx",
            precedent_version_id=retrieval.base_version_id,
            iteration=None,
            audit_metadata={"base_precedent_version_id": retrieval.base_version_id},
        )

    # On success the workflow continues exactly as before.
    transition(db, db.get("requests", request_id), RequestStatus.review_pending)


def run_refinement(
    db: dbmod.Database,
    request_id: str,
    refinement_id: str,
    gestora_id: str,
    user: User,
    ip_address: Optional[str],
) -> None:
    """Refinement pipeline: extract current draft -> LLM -> docx -> redline vs
    the ORIGINAL precedent base (cumulative change across iterations)."""
    settings = get_settings()
    row = db.get("requests", request_id)
    refinement = db.get("refinements", refinement_id)
    if row is None or refinement is None:
        raise RuntimeError(f"Request {request_id} or refinement {refinement_id} disappeared")
    iteration = refinement["iteration"]
    instruction = refinement["instruction"]

    current_draft = latest_document(db, request_id, DocumentVersionType.draft)
    if current_draft is None:
        raise RuntimeError(f"No draft to refine for request {request_id}")
    current_text = docx_renderer.extract_text(storage.read(current_draft["file_path"]))

    text = generator.refine_document(
        current_text=current_text, instruction=instruction, gestora_id=gestora_id
    )
    unclear_reason = generator.refinement_unclear_reason(text)
    if unclear_reason is not None:
        # Handled (non-retryable) outcome: the previous iteration stays the
        # valid draft, no documents are created, the reason reaches the client.
        db.update(
            "refinements",
            refinement_id,
            {"status": RefinementStatus.failed.value, "error": unclear_reason},
        )
        transition(db, db.get("requests", request_id), RequestStatus.review_pending)
        audit.log_action(
            db,
            user=user,
            action=AuditAction.document_generated,
            resource_type=AuditResourceType.request,
            resource_id=request_id,
            gestora_id=gestora_id,
            metadata={
                "refinement": True,
                "iteration": iteration,
                "instruction": instruction,
                "refinement_failed": unclear_reason,
            },
            ip_address=ip_address,
        )
        return

    # The precedent base id was propagated draft -> draft from iteration 0,
    # so every redline diffs against the SAME original precedent.
    base_version_id = current_draft.get("precedent_version_id")

    # Verificador cruzado (020) sobre el borrador refinado. Los hallazgos
    # deterministas bajan a 'warning' aquí: la instrucción del cliente pudo
    # pedir legítimamente cambiar un importe/fecha respecto al intake.
    try:
        verification = verifier.run(
            db,
            request_id=request_id,
            iteration=iteration,
            gestora_id=gestora_id,
            draft_text=text,
            params=(row.get("parsed_params") or {}),
            language=row.get("language") or (row.get("parsed_params") or {}).get("language") or "es",
            deterministic_severity="warning",
        )
        if verification["forced_counsel"]:
            db.update("requests", request_id, {"requires_counsel": True})
    except Exception:  # noqa: BLE001
        logger.exception("Verificador cruzado falló en refinamiento %s", refinement_id)

    _save_draft_with_audit(
        db,
        request_row=row,
        gestora_id=gestora_id,
        user=user,
        ip_address=ip_address,
        text=text,
        filename=f"draft_v{iteration}.docx",
        precedent_version_id=base_version_id,
        iteration=iteration,
        audit_metadata={
            "refinement": True,
            "iteration": iteration,
            "instruction": instruction,
            "model": settings.claude_model,
        },
    )
    # Each applied refinement consumes an LLM generation — billable.
    usage.record_usage(
        db, gestora_id=gestora_id, request_id=request_id, event_type=UsageEventType.document_generated
    )

    base_version = db.get("precedent_versions", base_version_id) if base_version_id else None
    base_text = rag.load_version_text(base_version) if base_version else None
    if base_text is not None:
        _save_redline_with_audit(
            db,
            request_row=row,
            gestora_id=gestora_id,
            user=user,
            ip_address=ip_address,
            base_text=base_text,
            text=text,
            filename=f"redline_v{iteration}.docx",
            precedent_version_id=base_version_id,
            iteration=iteration,
            audit_metadata={
                "refinement": True,
                "iteration": iteration,
                "instruction": instruction,
                "base_precedent_version_id": base_version_id,
            },
        )

    db.update(
        "refinements",
        refinement_id,
        {"status": RefinementStatus.applied.value, "applied_at": now_iso()},
    )
    transition(db, db.get("requests", request_id), RequestStatus.review_pending)
