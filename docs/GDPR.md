# Lol-AI-lo — GDPR / Data Protection Notes

Practical engineering-side documentation of how personal data flows through
the platform (improvement #10). This is **not legal advice**: every section
marked `TODO (legal)` must be reviewed and signed off by the SLP's lawyers
before production. Companion document: [SECURITY.md](./SECURITY.md).

Roles (to be confirmed): each **gestora is the data controller** for the
personal data inside its requests and documents; **Lol-AI-lo Legal SLP is a
processor** (and controller for platform account data). `TODO (legal)`:
confirm the controller/processor split and reflect it in the DPA template
signed with each gestora.

## 1. Data inventory — what personal data lives where

| Data | Where | Contains | Retention |
|------|-------|----------|-----------|
| Platform accounts | Supabase Auth + `users` table | email, role, gestora link | life of the account |
| Document requests | `requests` (freetext, `parsed_params`, `structured_fields`) | names of parties, signatories, directors, investors; amounts; dates | per-gestora policy (see §5); request row kept as tombstone |
| Generated documents | `documents` rows + files in Google Drive or `LOCAL_STORAGE_DIR` | full legal documents — party names, addresses, UBO/KYC data for compliance doc types | per-gestora policy (see §5) |
| Precedent library | `precedents` / `precedent_versions` + files | counterparty data inside precedent documents | admin-managed (supersede/delete) |
| Audit trail | `audit_log` (append-only) | user id, role, action, ip_address, metadata | kept indefinitely (legal evidence; see §5 rationale) |
| Usage/billing | `usage_events`, `usage_alerts` | gestora-level counts only — no personal data beyond ids | indefinitely (billing records) |
| Emails | Resend (processor) | recipient name/email, fund + doc type, signed download links | per Resend's retention |
| LLM calls | Anthropic / OpenAI APIs | request freetext + precedent text (may contain personal data) | see §4 |

Notably **not** stored: no payment card data, no special-category (Art. 9)
data by design — KYC/AML doc types may carry identity data of UBOs, which is
ordinary personal data but high sensitivity in practice.

## 2. Lawful basis notes — `TODO (legal)` to confirm

- Platform accounts and workflow processing: **performance of a contract**
  (Art. 6(1)(b)) with the gestora.
- Personal data of third parties inside documents (directors, investors,
  UBOs): processed on the gestora's instructions — the gestora's own lawful
  basis (typically contract performance / legal obligation for AML/KYC).
- Audit log including IP addresses: **legitimate interest** (Art. 6(1)(f)) in
  security, fraud prevention and professional-liability evidence.
  `TODO (legal)`: document the balancing test (LIA).

## 3. Data residency

- **Supabase**: create the production project in an **EU region**
  (e.g. `eu-central-1` Frankfurt). Database, Auth and file metadata then stay
  in the EU.
- **Railway/Render (backend)**: choose an **EU region** deployment so request
  payloads are processed in the EU.
- **Vercel (frontend)**: static assets are globally CDN-cached (no personal
  data); set serverless function region to an EU region (`fra1`) if any
  server-side rendering touches API data. The browser talks to the EU backend
  directly.
- **Google Drive storage**: `TODO (legal)`: confirm Google Workspace data
  region policy (EU) for the service-account's Drive, or keep the
  local-filesystem/EU object-storage fallback.
- **Resend (email)**: US-based processor — relies on SCCs/DPF.
  `TODO (legal)`: confirm acceptability or switch to an EU email provider.

## 4. LLM processors (Anthropic + OpenAI)

- **Anthropic Claude** (intake parsing, generation, refinement): commercial
  API terms — **no training on API inputs/outputs**. Sign Anthropic's DPA;
  evaluate the zero-data-retention (ZDR) option for the API organization so
  prompts/outputs are not retained beyond processing.
- **OpenAI** (`text-embedding-3-small`, RAG embeddings only): API data is
  **not used for training** by default; sign the OpenAI DPA; retention is up
  to 30 days for abuse monitoring — evaluate the zero-retention option for
  the embeddings endpoint.
- Minimization already in place: only the precedent text, request freetext and
  structured fields needed for the task are sent; no auth data, no audit data,
  no cross-gestora content (RAG hard filter).
- `TODO (legal)`: both DPAs executed and listed in §7; confirm EU/SCC transfer
  mechanism for each.

## 5. Retention policy mechanism (implemented)

- Per-gestora policy in months (**6–120, default 60**), stored in
  `data_retention_policies` (`supabase/migrations/007_data_retention.sql`),
  editable in the admin UI (Gestoras page) or via the API:
  - `GET /api/admin/gestoras/{id}/retention`
  - `PUT /api/admin/gestoras/{id}/retention` `{"months": 24}`
- Sweep: `POST /api/admin/retention/sweep` (admin-only;
  `services/retention.py`; TODO: schedule via external cron). For every
  request in status `delivered` older than its gestora's policy it deletes
  the stored files **and** the `documents` rows.
- **What survives, and why** (storage minimization vs audit immutability):
  - the `requests` row remains as a tombstone so the audit trail stays
    coherent and the SLP can prove what was requested/validated/delivered;
  - `audit_log` is **never** touched — append-only legal evidence
    (professional liability of the SLP);
  - files still referenced by the precedent library are kept — they have
    their own admin-managed lifecycle.
  `TODO (legal)`: validate that tombstone + audit retention is defensible
  under storage-limitation (Art. 5(1)(e)); define an audit-log retention
  horizon if required.

## 6. Data subject rights handling

| Right | How |
|-------|-----|
| Access / portability (Art. 15/20) | **Implemented**: `GET /api/me/export` returns the requesting user's own data as a downloadable JSON bundle (profile + their requests + documents metadata + tabular reviews), gestora-scoped to what they can access — never another gestora's data (`services/data_subject.export_user_data`). Per-request views (`GET /api/requests` + `parsed_params`/`structured_fields`, document downloads, audit trail by `user_id`) remain available too. |
| Rectification (Art. 16) | Account email via Supabase Auth; document content via the refinement / counsel-edit flow. |
| Erasure (Art. 17) | **Implemented** (`services/data_subject.delete_user_data`, exposed as self-service `POST /api/me/delete` — confirmation field required — and admin-triggered `POST /api/admin/users/{id}/delete`). Two modes: `anonymize` (default — scrub PII on the user's own rows, keep tombstones) and `erase` (delete the user's own requests/documents/tabular reviews + storage files). The append-only `audit_log` is **never** touched in either mode (the immutability guardrail / legal-evidence trail); `usage_events` billing records are likewise retained. The per-gestora retention sweep still covers systematic deletion. Note: erasure against audit/billing records can be refused on legal-obligation/defense grounds — `TODO (legal)` per-case assessment. |
| Objection / restriction (Art. 21/18) | Manual via the SLP. `TODO (legal)`: intake procedure + response templates (30-day clock). |

Requests channel: `TODO (legal)`: designate the contact address (e.g.
privacy@lolailolegal.es) and the DPO question (likely not mandatory, confirm).

## 7. Subprocessor list

| Subprocessor | Purpose | Region | DPA | Notes |
|--------------|---------|--------|-----|-------|
| Supabase | DB, auth, RLS | EU (choose region) | `TODO (legal)` | service-role key backend-only |
| Anthropic | LLM parsing/generation | US (API) | `TODO (legal)` | no training on API data; evaluate ZDR |
| OpenAI | RAG embeddings | US (API) | `TODO (legal)` | no training on API data by default |
| Google (Drive) | document storage | `TODO` confirm EU | `TODO (legal)` | optional — local/EU storage fallback exists |
| Resend | transactional email | US | `TODO (legal)` | console fallback exists; consider EU alternative |
| Railway/Render | backend hosting | EU (choose region) | `TODO (legal)` | |
| Vercel | frontend hosting | global CDN / EU functions | `TODO (legal)` | no personal data in static assets |

`TODO (legal)`: publish this list to gestoras and define the
subprocessor-change notification mechanism required by the DPA.
