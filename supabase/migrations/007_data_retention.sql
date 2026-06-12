-- ============================================================
-- Lol-AI-lo — GDPR data retention (v7, improvement #10)
-- Supabase / PostgreSQL
-- ============================================================

-- ------------------------------------------------------------
-- ENUM EXTENSIONS (audit trail for retention actions)
-- ------------------------------------------------------------

alter type audit_action add value if not exists 'retention_policy_updated';
alter type audit_action add value if not exists 'retention_sweep';
alter type audit_resource_type add value if not exists 'gestora';

-- ------------------------------------------------------------
-- TABLES
-- ------------------------------------------------------------

-- Per-gestora data-retention policy (docs/GDPR.md). The retention sweep
-- (services/retention.py, POST /api/admin/retention/sweep) deletes the
-- stored document files + documents rows of 'delivered' requests older than
-- the policy. The requests row and the append-only audit_log are KEPT:
-- storage minimization applies to document content, while the audit trail
-- remains the SLP's immutable evidence of what happened (guardrail 11).
-- Default 60 months (5 years); bounds 6-120 mirror RetentionPolicyBody.
create table data_retention_policies (
  id uuid primary key default uuid_generate_v4(),
  gestora_id uuid unique not null references gestoras(id) on delete cascade,
  months integer not null default 60 check (months between 6 and 120),
  updated_by uuid references users(id) on delete set null,
  updated_at timestamptz not null default now()
);

-- ------------------------------------------------------------
-- ROW LEVEL SECURITY
-- ------------------------------------------------------------

alter table data_retention_policies enable row level security;

-- Compliance setting agreed between the SLP and each gestora: admin-only.
-- Rows are written by the backend service role (bypasses RLS); the policies
-- mirror that for completeness.
create policy data_retention_policies_select on data_retention_policies for select using (
  current_user_role() = 'admin'
);
create policy data_retention_policies_write on data_retention_policies for all using (
  current_user_role() = 'admin'
);
