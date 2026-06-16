-- ============================================================
-- Lol-AI-lo — Gestora master models + review playbooks (v9)
-- Supabase / PostgreSQL
-- ============================================================
--
-- Two siloed resources are added to the per-gestora taxonomy
-- (services/storage.py): modelos/ (gestora master templates) and playbooks/
-- (human-authored review rules). Both are STRICTLY gestora-siloed exactly like
-- precedents and lessons (SPEC guardrails 1 & 3): every read hard-filters on
-- gestora_id and no cross-gestora / global pool exists for either.

-- ------------------------------------------------------------
-- ENUM: gestora_model precedent source
-- ------------------------------------------------------------
-- A gestora_model reuses the precedents / precedent_versions infrastructure
-- (gestora-scoped, versioned, activated). It is stored under modelos/ and,
-- in RAG, outranks regular precedents as the generation base (Level 0a).
--
-- NOTE: `ALTER TYPE ... ADD VALUE` cannot run inside a transaction block on
-- some Postgres setups. If your migration runner wraps each file in a
-- transaction, run this statement on its own (outside the txn) first.
alter type precedent_source add value if not exists 'gestora_model';

-- ------------------------------------------------------------
-- ENUM: audit actions + resource type for playbooks
-- ------------------------------------------------------------
alter type audit_action add value if not exists 'playbook_created';
alter type audit_action add value if not exists 'playbook_updated';
alter type audit_action add value if not exists 'playbook_deleted';
alter type audit_resource_type add value if not exists 'playbook';

-- ------------------------------------------------------------
-- TABLE: review_playbooks
-- ------------------------------------------------------------
-- Human-authored review rules injected into the critic (services/critic.py via
-- services/playbooks.py). The critic enforces these on top of its built-in
-- substantive checks. Admin-only CRUD (api/playbooks.py).
--
-- INVIOLABLE ISOLATION RULE (SPEC guardrails 1 & 3): playbooks are STRICTLY
-- gestora-siloed. gestora_id is NOT NULL and is the hard pre-filter on every
-- read (services.playbooks.playbooks_for). A playbook authored for one gestora
-- is NEVER loaded into another gestora's review. There is NO global /
-- cross-gestora playbook pool, and none must ever be added.
create table review_playbooks (
  id uuid primary key default uuid_generate_v4(),
  gestora_id uuid not null references gestoras(id) on delete cascade,
  branch text,
  doc_type text,
  title text not null,
  content text not null,
  file_path text,
  is_active boolean not null default true,
  created_by uuid references users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
-- Read path filters on (gestora_id, branch); index mirrors it.
create index idx_review_playbooks_gestora_branch on review_playbooks(gestora_id, branch);

create trigger trg_review_playbooks_updated_at
  before update on review_playbooks
  for each row execute function set_updated_at();

-- ------------------------------------------------------------
-- ROW LEVEL SECURITY
-- ------------------------------------------------------------
alter table review_playbooks enable row level security;

-- Gestora-siloed SELECT: a client sees ONLY its own gestora's playbooks;
-- admin/counsel see all (cross-gestora by role, as elsewhere). The select
-- policy is the defence-in-depth backstop for the application-level hard
-- gestora_id filter in services.playbooks.
create policy review_playbooks_select on review_playbooks for select using (
  current_user_role() in ('admin', 'counsel')
  or gestora_id = current_user_gestora()
);
-- Writes are admin-only (api/playbooks.py is admin-gated; the policy mirrors
-- it). The backend service role bypasses RLS regardless.
create policy review_playbooks_admin_write on review_playbooks for all using (
  current_user_role() = 'admin'
);
