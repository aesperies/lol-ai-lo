-- ============================================================
-- Lol-AI-lo — Account & security features (v11)
-- Supabase / PostgreSQL
-- ============================================================
--
-- Three independent account/security features land together:
--
-- A. MFA / 2FA (TOTP). Supabase Auth enforces the actual TOTP factor
--    (enroll/challenge/verify, client-side via @supabase/supabase-js). The
--    backend only MIRRORS the enabled status on users.mfa_enabled for display
--    and an admin overview; it never stores the secret.
--
-- B. GDPR data-subject rights (RGPD arts. 15/17): self-service data export and
--    erasure/anonymisation. No new tables — the export reads existing rows and
--    the deletion scrubs/erases the user's own requests/documents/reviews. As
--    with the retention sweep (007), the append-only audit_log is NEVER touched
--    (guardrail 11 / immutable legal evidence).
--
-- C. Per-gestora model configuration (BYO keys): each gestora may override the
--    global LLM provider/model and supply its own (ENCRYPTED) API keys, on top
--    of the global services/llm.py defaults. Admin-only.

-- ------------------------------------------------------------
-- ENUM EXTENSIONS (audit trail for the new actions/resources)
-- ------------------------------------------------------------
alter type audit_action add value if not exists 'mfa_status_changed';
alter type audit_action add value if not exists 'data_exported';
alter type audit_action add value if not exists 'data_subject_deleted';
alter type audit_action add value if not exists 'model_config_updated';
alter type audit_resource_type add value if not exists 'user';
alter type audit_resource_type add value if not exists 'model_config';

-- ------------------------------------------------------------
-- FEATURE A — users.mfa_enabled status mirror
-- ------------------------------------------------------------
-- Display/overview ONLY: Supabase Auth is the authority that actually enforces
-- the TOTP factor. The client flips this via POST /api/me/mfa after a
-- successful Supabase verify/unenroll; we never store the TOTP secret here.
alter table users add column if not exists mfa_enabled boolean not null default false;

-- ------------------------------------------------------------
-- FEATURE C — per-gestora model configuration (BYO keys)
-- ------------------------------------------------------------
-- One optional override row per gestora. NULL columns fall back to the global
-- settings (config.py). API keys are stored ENCRYPTED at rest (services/
-- secrets.py); the *_enc columns hold ciphertext only — plaintext keys are
-- NEVER logged or returned by the API (GET returns booleans like
-- anthropic_key_set instead).
-- NOTE: ``gestora_id`` is the logical key (one config row per gestora, enforced
-- UNIQUE). A surrogate ``id`` PK is kept so the tiny db abstraction
-- (services/db.py get/update by id) works uniformly across the dev store and
-- Supabase — the same shape as data_retention_policies (007).
create table gestora_model_config (
  id uuid primary key default uuid_generate_v4(),
  gestora_id uuid unique not null references gestoras(id) on delete cascade,
  llm_provider text,
  llm_model text,
  embedding_provider text,
  embedding_model text,
  anthropic_api_key_enc text,
  openai_api_key_enc text,
  ollama_base_url text,
  updated_by uuid references users(id) on delete set null,
  updated_at timestamptz not null default now()
);

create trigger trg_gestora_model_config_updated_at
  before update on gestora_model_config
  for each row execute function set_updated_at();

-- ------------------------------------------------------------
-- ROW LEVEL SECURITY
-- ------------------------------------------------------------
-- Admin-only: the model configuration (and especially the encrypted keys) is a
-- platform-administration setting, never client/counsel readable. The backend
-- service role bypasses RLS; these policies are the defence-in-depth backstop
-- and mirror the data_retention_policies (007) admin-only pattern.
alter table gestora_model_config enable row level security;

create policy gestora_model_config_select on gestora_model_config for select using (
  current_user_role() = 'admin'
);
create policy gestora_model_config_write on gestora_model_config for all using (
  current_user_role() = 'admin'
);
