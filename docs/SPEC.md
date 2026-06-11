# Lol-AI-lo — Platform Specification (v1)

Document generation and review platform for European VC fund servicers. Fund clients request corporate/fund documentation in natural language; the platform generates it using fund-specific precedents (RAG) and optionally routes it to external counsel for validation before delivery.

## Actors

| Role | Description | Permissions |
|------|-------------|-------------|
| `client` | In-house counsel or fund manager at a fund | Submit requests, view own documents, download outputs |
| `counsel` | External lawyer (servicer side) | Review flagged documents, validate, upload final version |
| `admin` | Servicer staff | Manage gestoras, funds, users, precedent library |

## Data Hierarchy

```
Gestora (Management Company)
  └── Funds → Documents → Requests / Drafts / Redlines / Final Versions
  └── Precedent Library (siloed per gestora, NOT shared)
```

**CRITICAL ISOLATION RULE:** Precedents, documents, and data are fully siloed per gestora. Every DB query must filter by `gestora_id`. No cross-gestora access ever. RAG filter on `gestora_id` is a hard pre-filter, not a soft ranking signal.

## Tech Stack

- Frontend: Next.js 14 (App Router) + Tailwind CSS
- Backend: Python + FastAPI
- Auth: Supabase Auth (roles: client / counsel / admin)
- DB: Supabase (PostgreSQL)
- LLM: Anthropic Claude API — `claude-sonnet-4-20250514`
- RAG: LlamaIndex + OpenAI `text-embedding-3-small`
- Precedent storage: Google Drive API (one folder per gestora); local-filesystem fallback
- Doc generation: python-docx; Redline: python-docx diff (author = "Lol-AI-lo AI")
- PDF: PyMuPDF (text) + pytesseract (OCR)
- Email: Resend API (log-to-console fallback)
- Hosting: Vercel (frontend) + Railway/Render (backend)

## Database Schema (authoritative — see supabase/migrations/001_initial_schema.sql)

- `gestoras(id, name, drive_folder_id, subscription_tier ENUM('starter','growth','custom'), billing_email, created_at)`
- `funds(id, gestora_id, name, jurisdiction, created_at)`
- `users(id, email, role ENUM('client','counsel','admin'), gestora_id NULL for admin/counsel, created_at)`
- `requests(id, fund_id, user_id, doc_type, doc_type_custom, freetext, language, parsed_params JSONB, status ENUM('parsing','confirmed','generating','review_pending','counsel_review','validated','delivered'), requires_counsel BOOL, exit_a_acknowledged_at, created_at, updated_at)`
- `documents(id, request_id, version_type ENUM('draft','redline','counsel_edit','final'), file_path, precedent_version_id, uploaded_by, created_at)`
- `precedents(id, gestora_id, fund_id NULLABLE, doc_type, language, source ENUM('manual_upload','validated_output','slp_curated','platform_base'), created_at)`
- `precedent_versions(id, precedent_id, version_number, file_path, status ENUM('draft','active','superseded'), rag_weight FLOAT, activated_at, superseded_at, created_by)`
- `audit_log(id, timestamp, user_id, user_role, gestora_id, action ENUM(...20 actions...), resource_type, resource_id, metadata JSONB, ip_address)` — **append-only, RLS enforced: INSERT only**
- `usage_events(id, gestora_id, request_id, event_type ENUM('document_generated','exit_a','exit_b_requested','exit_b_validated'), billing_period 'YYYY-MM', created_at)`

## Master Workflow

1. **CLIENT intake form**: Fund (dropdown filtered by gestora) + Document type (grouped dropdown, see catalog) + free text (min 50 / max 2000 chars) + optional "validación por abogado" toggle (default OFF).
2. **INTAKE PARSER (Claude)**: detect language; extract doc_type_confirmed, parties, dates, jurisdiction, key terms; return structured JSON + human summary in detected language. If confidence < 0.7 on any field → flag unclear, `generation_ready: false`, do NOT generate. If doc_type='other' and unclassifiable → message: "No hemos podido clasificar tu solicitud. Por favor reformúlala indicando el tipo de documento y las partes implicadas."
3. **CLIENT confirms** parsed parameters (or edits inline → log `params_edited`).
4. **GENERATION**: RAG retrieves top-3 precedents from gestora silo (fallback chain below); Claude generates document using precedent as template; python-docx renders .docx draft; redline engine generates second .docx (tracked changes vs precedent base, author "Lol-AI-lo AI").
5. **CLIENT REVIEWS REDLINE** — receives both [Descargar Borrador] and [Descargar Redline vs. Precedente]:
   - **EXIT A** "Me vale": explicit acknowledgment checkbox required → [Confirmar y Descargar] → status `delivered` → doc becomes precedent candidate (pending admin approval).
   - **EXIT B** "Validación por abogado": [Solicitar Validación] → Resend email to counsel → status `counsel_review`.
6. **COUNSEL REVIEW (Exit B)**: draft + redline side by side; edit inline (rich text) OR download/edit/upload .docx; comments/flags; [Validar y Entregar].
7. **FINAL DELIVERY (Exit B)**: client emailed download link; status `validated` → `delivered`; validated doc enters precedent library **automatically** (counsel validation sufficient, no admin approval).

## Document Type Catalog (grouped dropdown)

- 🏛 Gobierno Corporativo: Acta de Reunión del Consejo; Resolución del Consejo per rollam; Acta de Junta General; Resolución de Junta General sin Reunión; Nombramiento / Cese de Administrador; Poder General (Delegación de Facultades); Poder Especial
- 💼 Operaciones de Fondo: Llamada de Capital (Capital Call Notice); Distribución a Inversores (Distribution Notice); Extensión del Período de Inversión; Extensión del Plazo del Fondo; Certificado de Participación del Inversor; Waiver / Renuncia a Derecho Contractual
- 📋 Gestión de Portfolio: Term Sheet (no vinculante); Carta de Intenciones (LOI); NDA / Acuerdo de Confidencialidad; Acuerdo de Suscripción de Participaciones; Resolución de Aprobación de Inversión; Resolución de Seguimiento (Follow-on); Resolución de Desinversión
- ⚖️ Cumplimiento y Regulatorio: Certificado de Titularidad Real (UBO); Declaración AML/KYC; Certificado de Residencia Fiscal; Comunicación a Regulador (CNMV / AMF / BaFin); Notificación AIFMD
- 📝 Contratos con Terceros: Contrato de Prestación de Servicios; Acuerdo de Asesoramiento (Advisory Agreement); Contrato de Gestor de Cartera Delegado; Side Letter con Inversor
- 🔧 Otros: Other (describir abajo)

## Intake Parser — Claude Prompt (verbatim)

```
You are a legal document intake parser for a European VC fund servicer.
Your job is to extract structured parameters from a client's document request.
INPUT:
- doc_type: {doc_type}
- freetext: {freetext}
OUTPUT (JSON only, no preamble):
{
  "language": "es|en|fr|de|other",
  "doc_type_confirmed": "string",
  "parties": [{"role": "string", "name": "string"}],
  "key_dates": [{"label": "string", "date": "string"}],
  "jurisdiction": "string",
  "governing_law": "string",
  "key_terms": [{"field": "string", "value": "string"}],
  "summary": "2-sentence human-readable summary in detected language",
  "confidence": 0.0-1.0,
  "unclear_fields": ["list of fields with confidence < 0.7"],
  "generation_ready": true|false
}
Rules:
- Respond ONLY in JSON. No markdown, no preamble.
- If confidence < 0.7 on any field, set generation_ready: false
- Always respond in the same language as the freetext
- For European VC context: assume AIFMD applies, default jurisdiction
  to Spain (CNMV) unless stated otherwise
```

## Document Generator — Claude Prompt (verbatim)

```
You are a senior European VC fund legal document drafter.
Your task is to generate a complete, professional {doc_type} in {language}.
CONTEXT:
- Fund: {fund_name}
- Gestora: {gestora_name}
- Jurisdiction: {jurisdiction}
- Governing Law: {governing_law}
- Parties: {parties}
- Key Terms: {key_terms}
- Client Instructions: {freetext}
PRECEDENT (retrieved from fund's document library):
{precedent_text}
INSTRUCTIONS:
1. Use the precedent as your structural and stylistic template
2. Adapt all variable fields (parties, dates, amounts) to the current request
3. Maintain the same governing law and jurisdiction as the precedent unless
   the client explicitly requests otherwise
4. Flag any clause where you deviate from the precedent with:
   [DEVIATION: reason]
5. Flag any field you could not fill from the available information with:
   [MISSING: field name]
6. Output the full document text, ready for conversion to .docx
7. Use formal legal register appropriate for {jurisdiction}
8. Apply 2026 European VC market standards
CRITICAL: Do not invent parties, amounts, or dates not provided in the input.
```

## Redline Engine

- python-docx + custom diff logic; generated doc vs closest matching precedent (doc_type + language)
- Output .docx with tracked changes, author = "Lol-AI-lo AI" (never client/counsel name)
- Mark: insertions, deletions, material modifications. Do NOT mark: formatting changes, date/party field fills.

## RAG Configuration

- Embeddings: text-embedding-3-small; chunks 512 tokens, overlap 50; top-3 cosine similarity
- Hard pre-filter: `gestora_id` + `doc_type` before semantic search
- PDFs: PyMuPDF (text) / pytesseract (scanned); indexed as read-only reference only — **never generation base**. Only .docx precedents are generation bases.
- Re-index on: precedent version activated (gestora silo), precedent superseded (rag_weight → 0.3, keep), new SLP template (global pool)

### Precedent Fallback Chain

- **Level 0** — Gestora silo (gestora_id + doc_type match). rag_weight 1.0 active / 0.3 superseded. Generation base.
- **Level 1** — SLP-curated templates (`/lol-ai-lo-templates/slp-curated/{es,en,fr}/`). rag_weight 0.7. Generation base.
- **Level 2** — Platform base templates (`/lol-ai-lo-templates/platform-base/{es,en,fr}/`). rag_weight 0.4. Generation base.
- **Level 3** — No precedent: generate from scratch following RAG corpus structure. **FORCES Exit B** (counsel mandatory, client cannot bypass). Warning: "Este documento se ha generado sin precedente de referencia. La validación por abogado es obligatoria antes de su uso."

### Drive Folder Structure

```
/lol-ai-lo-templates/{slp-curated,platform-base}/{es,en,fr}/
/gestoras/{gestora_id}/precedents/
/gestoras/{gestora_id}/funds/{fund_id}/documents/
```

## Email Templates (Resend, sent from Lol-AI-lo Legal SLP domain)

To counsel: `Subject: [Lol-AI-lo] Revisión pendiente — {fund_name} — {doc_type}` — body: greeting {counsel_name}, fund, type, requested-by, suggested deadline, review_url.
To client: `Subject: [Lol-AI-lo] Tu documento está listo — {doc_type}` — body: greeting {client_name}, type, fund, optional validated-by-counsel line, download_url.

## Corporate Structure

- **Lol-AI-lo SL** (tech): operates platform, charges subscriptions, licenses tech to SLP. Never signs legal services contracts with funds.
- **Lol-AI-lo Legal SLP** (legal): signs legal services contracts, holds RC profesional, employs counsel, responsible for delivered outputs.
- Disclaimer on every generated document: "Este documento ha sido generado por Lol-AI-lo Legal SLP. Su uso sin validación por abogado es responsabilidad exclusiva del cliente. Lol-AI-lo Legal SLP no asume responsabilidad por documentos descargados sin validación (Exit A)."
- Exit A checkbox text: "Entiendo que este documento no ha sido revisado por un abogado y asumo la responsabilidad de su uso."

## Pricing / Usage

Subscription per gestora/month: Starter (2 funds, 20 docs), Growth (5 funds, 75 docs), Custom. Overage per doc: Exit A €X < Exit B €Y. Counsel compensation internal to SLP, not exposed. All usage events logged to `usage_events` for billing.

## Guardrails (inviolable)

1. Gestora isolation — every query filters `gestora_id`
2. Never generate without `generation_ready: true` and client confirmation
3. RAG gestora filter is hard, never soft
4. All output language = input language (detection mandatory)
5. `[MISSING]` fields block Exit A delivery — counsel review required
6. Redline author always "Lol-AI-lo AI"
7. PDF precedents = RAG reference only, never generation base
8. Admin approval required before validated output becomes active precedent — EXCEPT counsel-validated docs (automatic)
9. Exit A requires explicit acknowledgment checkbox
10. Level 3 fallback always forces Exit B
11. Audit log append-only (DB-level RLS)
12. All usage events logged for billing

## Service Readiness Matrix (graceful degradation)

Each external service independently toggleable via env vars. If not configured:
- Resend → log email to console/file instead of sending
- Google Drive → local filesystem fallback (`./storage/`)
- Anthropic / OpenAI → endpoints return 503 with clear "service not configured" detail
- Supabase → backend refuses to start only for DB itself; auth can run in dev-stub mode

## Success Metrics v1

- Generation < 60s from confirmation; redline < 30s; counsel email < 2 min
- Zero cross-gestora leakage (automated test suite required)
- ES / EN primary languages at launch (i18n shell for FR / DE)
