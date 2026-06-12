-- ============================================================
-- Lol-AI-lo — Quality metrics + counsel SLA (v5, improvements #6 & #8)
-- Supabase / PostgreSQL
-- ============================================================

-- ------------------------------------------------------------
-- TABLES
-- ------------------------------------------------------------

-- requests: counsel SLA timestamps.
-- counsel_requested_at  — stamped when the request enters 'counsel_review'
--                         (Exit B "Solicitar Validación").
-- counsel_validated_at  — stamped when counsel validates ('validated').
alter table requests
  add column counsel_requested_at timestamptz,
  add column counsel_validated_at timestamptz;

-- Quality metric: draft→validated edit distance (the platform's core quality
-- KPI per doc_type and per gestora). One row per request:
--  - Exit B: similarity between the latest AI draft iteration and the final
--    (counsel_edit) version at validation time.
--  - Exit A: similarity 1.0 (client accepted the draft as-is — the strongest
--    quality signal), recorded at download time.
create table quality_metrics (
  id uuid primary key default uuid_generate_v4(),
  request_id uuid not null references requests(id) on delete cascade unique,
  gestora_id uuid not null,
  doc_type text not null,
  language text,
  draft_iteration integer not null,
  similarity real not null check (similarity between 0 and 1),
  chars_draft integer,
  chars_final integer,
  words_changed integer,
  refinements_used integer not null default 0,
  fallback_level integer,
  computed_at timestamptz not null default now()
);
create index idx_quality_metrics_gestora_doctype on quality_metrics(gestora_id, doc_type);

-- SLA notifications sent by the sweep (services/sla.py): one row per email,
-- used as the idempotency guard (one reminder + one escalation per request).
create table sla_events (
  id uuid primary key default uuid_generate_v4(),
  request_id uuid not null references requests(id) on delete cascade,
  kind text not null check (kind in ('reminder', 'escalation')),
  recipient_email text not null,
  sent_at timestamptz not null default now()
);
create index idx_sla_events_request on sla_events(request_id);

-- ------------------------------------------------------------
-- ROW LEVEL SECURITY
-- ------------------------------------------------------------

alter table quality_metrics enable row level security;
alter table sla_events enable row level security;

-- Quality metrics: internal KPI — admin and counsel only, never clients.
-- Rows are written by the backend service role (bypasses RLS); the INSERT
-- policy mirrors that for completeness.
create policy quality_metrics_select on quality_metrics for select using (
  current_user_role() in ('admin', 'counsel')
);
create policy quality_metrics_insert on quality_metrics for insert with check (true);

-- SLA events: admin/counsel SELECT; INSERT by the backend sweep.
create policy sla_events_select on sla_events for select using (
  current_user_role() in ('admin', 'counsel')
);
create policy sla_events_insert on sla_events for insert with check (true);
