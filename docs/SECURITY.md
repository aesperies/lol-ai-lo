# Lol-AI-lo — Security Overview

Threat model summary and production hardening checklist for the Lol-AI-lo
platform (improvement #9). Companion document: [GDPR.md](./GDPR.md).

## Threat model summary

The platform stores legal documents and personal data for multiple competing
management companies (gestoras). The primary threats, in order of impact:

1. **Cross-tenant data leakage** — a client of gestora A reading gestora B's
   requests, documents, or precedents.
2. **Unauthorized document access** — leaked or forged download links, session
   theft, scraping.
3. **Malicious uploads** — counsel `.docx` uploads and admin precedent uploads
   used to smuggle executable or oversized content into storage.
4. **Abuse of LLM endpoints** — cost amplification or denial of service via
   the generation/refinement/parse endpoints.
5. **Tampering with the evidence trail** — modification of audit history.

## Controls in place

### Multi-tenant isolation (dual enforcement)
- **App layer**: every data access path goes through the tiny `services/db.py`
  interface; request access is checked by `auth.assert_request_access`, which
  resolves the owning gestora and returns **404 (not 403)** to clients outside
  the silo so other tenants' resource ids are not even discoverable.
- **DB layer**: Postgres Row Level Security policies on every table
  (`supabase/migrations/*.sql`) keyed on `current_user_role()` /
  `current_user_gestora()`. The backend uses the service-role key (bypasses
  RLS), so RLS is the *second* line of defense — it protects against direct
  PostgREST access and future code paths that skip the app-layer checks.
- **RAG**: `gestora_id` is a hard pre-filter on retrieval, never a soft
  ranking signal; the fallback chain never crosses silos
  (`tests/test_gestora_isolation.py` asserts zero leakage).

### Signed, expiring download URLs
- Email links must not depend on a session: `services/signed_urls.py` issues
  HMAC-SHA256 tokens (`base64url(payload).base64url(signature)`) pinned to one
  `request_id` + `version_type`, expiring after `SIGNED_URL_TTL_HOURS`
  (default 72h).
- `GET /api/download/{token}` verifies with a constant-time comparison
  (`hmac.compare_digest`); invalid/expired/tampered tokens get a 404. Every
  signed download is audited with `{"mode": "signed_link"}`.
- Secret: `URL_SIGNING_SECRET`. Without it a process-stable random fallback is
  derived (dev only) and a warning logged.

### Rate limiting
- In-process sliding-window limiter (`services/rate_limit.py`), no new
  dependencies. Applied limits:
  - generation: 6/min per user
  - refinement: 6/min per user
  - intake parse: 10/min per user
  - signed download (auth-free): 30/min per IP
- Exceeding a limit returns **429 + Retry-After**. Toggle:
  `RATE_LIMIT_ENABLED`.

### Upload validation
- Counsel `.docx` uploads and admin precedent uploads (`.docx`/`.pdf`) enforce
  (a) an extension allowlist, (b) a max size (`MAX_UPLOAD_MB`, default 15),
  and (c) magic-bytes checks (`PK\x03\x04` for docx, `%PDF` for pdf). Any
  violation is a 422 and nothing is stored.

### Security headers & CORS
- Middleware (`main.py`) on every response: `X-Content-Type-Options: nosniff`,
  `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`,
  and `Cache-Control: no-store` on all `/api` responses (documents and
  personal data must never land in shared caches).
- CORS is restricted to the single `FRONTEND_URL` origin and the
  methods/headers the frontend actually uses.

### Append-only audit trail
- `audit_log` is append-only at **both** layers: a DB trigger + RLS (INSERT
  only) in production, and a `PermissionError` on UPDATE/DELETE in the storage
  layer (`services/db.py`, `_APPEND_ONLY_TABLES`). The GDPR retention sweep
  explicitly never touches it (see GDPR.md).

### Workflow guardrails
- A strict request state machine (`STATUS_TRANSITIONS`) prevents skipping
  confirmation, generation, acknowledgment or validation steps; Exit A
  re-reads the stored draft server-side so blockers cannot be bypassed with
  tampered client state.

### 2FA / MFA (Supabase TOTP)
- Implemented via **Supabase Auth native TOTP MFA**, which is largely
  client-side (`@supabase/supabase-js` `auth.mfa.enroll/challenge/verify/
  unenroll/listFactors`). The account security page
  (`app/(client)/account/security`) lets a logged-in user enroll a TOTP factor
  (QR / otpauth URI + secret), verify the 6-digit code to activate, list
  factors and unenroll. Supabase enforces the actual factor.
- The backend **mirrors** the status for display + an admin overview: a
  `users.mfa_enabled` column (`011_account_security.sql`), updated via
  `POST /api/me/mfa {enabled}` after a successful Supabase verify/unenroll, and
  surfaced on the profile (`GET /api/me`). The change is audited
  (`mfa_status_changed`). The platform never stores the TOTP secret.
- In dev-stub mode (no Supabase) the page shows a clear "no disponible en modo
  desarrollo" state and never crashes.
- `TODO`: require MFA for `admin` and `counsel` roles (policy enforcement) once
  the production Supabase project is provisioned.

### Per-gestora model configuration & secrets at rest
- Each gestora may optionally override the LLM provider/model and supply its own
  API keys on top of the global `services/llm.py` defaults
  (`gestora_model_config`, admin-only, `011_account_security.sql`). Keys are
  stored **encrypted at rest** via `services/secrets.py` — a dependency-light,
  stdlib-only authenticated scheme (HMAC-SHA256 keystream XOR, encrypt-then-MAC)
  keyed on `SECRETS_ENCRYPTION_KEY` (process-stable random fallback + warning
  when unset, mirroring `URL_SIGNING_SECRET`). The admin API never returns
  decrypted keys (only `*_key_set` booleans); plaintext keys are never logged.

## NOT yet covered — production checklist
- [ ] **Penetration test** — pending; schedule before onboarding the first
      external gestora.
- [ ] **Redis-based rate limiting** — the current limiter is per-process; N
      workers multiply every limit by N. Move to Redis (or an API gateway)
      for multi-worker deployments.
- [ ] **Secrets manager** — secrets currently come from environment variables
      (`.env`). Move `URL_SIGNING_SECRET`, `SUPABASE_SERVICE_ROLE_KEY`,
      `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `RESEND_API_KEY` and the Google
      service-account JSON into a managed secrets store (Railway/Render
      secrets at minimum; ideally Doppler/Vault/AWS SM) with rotation.
- [ ] **Set `URL_SIGNING_SECRET`** — mandatory in production; the random
      fallback breaks links across restarts/workers.
- [ ] **Content-Security-Policy** — the API serves JSON/binary only; add a
      strict CSP on the Next.js frontend (Vercel headers).
- [ ] **Virus/malware scanning of uploads** — magic-bytes checks stop format
      confusion, not embedded malware; add ClamAV or a scanning service if
      uploads ever become client-facing.
- [ ] **External scheduler hardening** — the SLA and retention sweeps run
      in-process today (single worker); move to cron + the admin endpoints.
- [ ] **Backups & restore drills** — Supabase PITR + storage backups,
      restore procedure tested.
