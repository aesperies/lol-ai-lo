-- ============================================================
-- Lol-AI-lo — Billing usage alerts (v6, improvement #7)
-- Supabase / PostgreSQL
-- ============================================================

-- ------------------------------------------------------------
-- TABLES
-- ------------------------------------------------------------

-- Usage alert emails sent to a gestora's billing_email when its monthly
-- document_generated count crosses a tier-limit threshold (80% / 100%,
-- services/usage.py). One row per (gestora, period, threshold) — the UNIQUE
-- constraint is the idempotency guard so each alert fires exactly once.
create table usage_alerts (
  id uuid primary key default uuid_generate_v4(),
  gestora_id uuid not null references gestoras(id) on delete cascade,
  billing_period text not null check (billing_period ~ '^\d{4}-(0[1-9]|1[0-2])$'),
  threshold integer not null check (threshold in (80, 100)),
  sent_at timestamptz not null default now(),
  unique (gestora_id, billing_period, threshold)
);
create index idx_usage_alerts_gestora_period on usage_alerts(gestora_id, billing_period);

-- ------------------------------------------------------------
-- ROW LEVEL SECURITY
-- ------------------------------------------------------------

alter table usage_alerts enable row level security;

-- Billing internals: admin-only. Rows are written by the backend service
-- role (bypasses RLS); the INSERT policy mirrors that for completeness.
create policy usage_alerts_select on usage_alerts for select using (
  current_user_role() = 'admin'
);
create policy usage_alerts_insert on usage_alerts for insert with check (true);
