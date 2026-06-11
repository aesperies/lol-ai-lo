-- ============================================================
-- Lol-AI-lo — Initial Schema (v1)
-- Supabase / PostgreSQL
-- ============================================================

create extension if not exists "uuid-ossp";

-- ------------------------------------------------------------
-- ENUMS
-- ------------------------------------------------------------
create type user_role as enum ('client', 'counsel', 'admin');
create type subscription_tier as enum ('starter', 'growth', 'custom');
create type request_status as enum (
  'parsing', 'confirmed', 'generating', 'review_pending',
  'counsel_review', 'validated', 'delivered'
);
create type document_version_type as enum ('draft', 'redline', 'counsel_edit', 'final');
create type precedent_source as enum ('manual_upload', 'validated_output', 'slp_curated', 'platform_base');
create type precedent_version_status as enum ('draft', 'active', 'superseded');
create type audit_action as enum (
  'document_requested',
  'params_confirmed',
  'params_edited',
  'document_generated',
  'redline_generated',
  'draft_downloaded',
  'redline_downloaded',
  'exit_a_acknowledged',
  'exit_a_downloaded',
  'counsel_requested',
  'counsel_notified',
  'counsel_review_started',
  'counsel_edit_inline',
  'counsel_edit_uploaded',
  'document_validated',
  'final_downloaded',
  'precedent_uploaded',
  'precedent_activated',
  'precedent_superseded',
  'precedent_version_created'
);
create type audit_resource_type as enum ('request', 'document', 'precedent', 'precedent_version');
create type usage_event_type as enum ('document_generated', 'exit_a', 'exit_b_requested', 'exit_b_validated');

-- ------------------------------------------------------------
-- TABLES
-- ------------------------------------------------------------

create table gestoras (
  id uuid primary key default uuid_generate_v4(),
  name text not null,
  drive_folder_id text,
  subscription_tier subscription_tier not null default 'starter',
  billing_email text,
  created_at timestamptz not null default now()
);

create table funds (
  id uuid primary key default uuid_generate_v4(),
  gestora_id uuid not null references gestoras(id) on delete cascade,
  name text not null,
  jurisdiction text not null,
  created_at timestamptz not null default now()
);
create index idx_funds_gestora on funds(gestora_id);

-- Mirrors auth.users; id matches Supabase Auth user id.
-- gestora_id is NULL for admin and counsel (cross-gestora access).
create table users (
  id uuid primary key,
  email text not null unique,
  role user_role not null default 'client',
  gestora_id uuid references gestoras(id) on delete set null,
  created_at timestamptz not null default now(),
  constraint client_requires_gestora
    check (role <> 'client' or gestora_id is not null)
);
create index idx_users_gestora on users(gestora_id);

create table requests (
  id uuid primary key default uuid_generate_v4(),
  fund_id uuid not null references funds(id) on delete cascade,
  user_id uuid not null references users(id),
  doc_type text not null,
  doc_type_custom text,
  freetext text not null check (char_length(freetext) between 50 and 2000),
  language text,
  parsed_params jsonb,
  status request_status not null default 'parsing',
  requires_counsel boolean not null default false,
  exit_a_acknowledged_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index idx_requests_fund on requests(fund_id);
create index idx_requests_user on requests(user_id);
create index idx_requests_status on requests(status);

create table precedents (
  id uuid primary key default uuid_generate_v4(),
  gestora_id uuid references gestoras(id) on delete cascade,  -- NULL for slp_curated / platform_base global templates
  fund_id uuid references funds(id) on delete set null,        -- NULL = gestora-level precedent
  doc_type text not null,
  language text not null,
  source precedent_source not null default 'manual_upload',
  created_at timestamptz not null default now(),
  constraint gestora_sources_require_gestora
    check (source in ('slp_curated', 'platform_base') or gestora_id is not null)
);
create index idx_precedents_gestora_doctype on precedents(gestora_id, doc_type);
create index idx_precedents_source on precedents(source);

create table precedent_versions (
  id uuid primary key default uuid_generate_v4(),
  precedent_id uuid not null references precedents(id) on delete cascade,
  version_number integer not null,
  file_path text not null,
  status precedent_version_status not null default 'draft',
  rag_weight real not null default 0.0,  -- 1.0 active, 0.3 superseded, 0.0 draft
  activated_at timestamptz,
  superseded_at timestamptz,
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  unique (precedent_id, version_number)
);
create index idx_precedent_versions_precedent on precedent_versions(precedent_id);
create index idx_precedent_versions_status on precedent_versions(status);

create table documents (
  id uuid primary key default uuid_generate_v4(),
  request_id uuid not null references requests(id) on delete cascade,
  version_type document_version_type not null,
  file_path text not null,
  precedent_version_id uuid references precedent_versions(id),
  uploaded_by uuid references users(id),
  created_at timestamptz not null default now()
);
create index idx_documents_request on documents(request_id);

create table audit_log (
  id uuid primary key default uuid_generate_v4(),
  timestamp timestamptz not null default now(),
  user_id uuid,
  user_role text,
  gestora_id uuid,
  action audit_action not null,
  resource_type audit_resource_type not null,
  resource_id uuid,
  metadata jsonb,
  ip_address inet
);
create index idx_audit_log_gestora on audit_log(gestora_id);
create index idx_audit_log_resource on audit_log(resource_type, resource_id);
create index idx_audit_log_timestamp on audit_log(timestamp);

create table usage_events (
  id uuid primary key default uuid_generate_v4(),
  gestora_id uuid not null references gestoras(id),
  request_id uuid references requests(id),
  event_type usage_event_type not null,
  billing_period varchar(7) not null,  -- 'YYYY-MM'
  created_at timestamptz not null default now()
);
create index idx_usage_events_billing on usage_events(gestora_id, billing_period);

-- ------------------------------------------------------------
-- updated_at trigger
-- ------------------------------------------------------------
create or replace function set_updated_at()
returns trigger as $$
begin
  new.updated_at = now();
  return new;
end;
$$ language plpgsql;

create trigger trg_requests_updated_at
  before update on requests
  for each row execute function set_updated_at();

-- ------------------------------------------------------------
-- AUDIT LOG IMMUTABILITY — DB-level, belt and suspenders:
-- (1) trigger blocks UPDATE/DELETE for everyone incl. table owner,
-- (2) RLS allows INSERT only.
-- ------------------------------------------------------------
create or replace function forbid_audit_mutation()
returns trigger as $$
begin
  raise exception 'audit_log is append-only: % not permitted', tg_op;
end;
$$ language plpgsql;

create trigger trg_audit_log_immutable
  before update or delete on audit_log
  for each row execute function forbid_audit_mutation();

-- ------------------------------------------------------------
-- ROW LEVEL SECURITY
-- Helper functions read the caller's role/gestora from the users table
-- (auth.uid() = users.id under Supabase Auth).
-- ------------------------------------------------------------

create or replace function current_user_role()
returns user_role as $$
  select role from users where id = auth.uid()
$$ language sql stable security definer;

create or replace function current_user_gestora()
returns uuid as $$
  select gestora_id from users where id = auth.uid()
$$ language sql stable security definer;

alter table gestoras enable row level security;
alter table funds enable row level security;
alter table users enable row level security;
alter table requests enable row level security;
alter table documents enable row level security;
alter table precedents enable row level security;
alter table precedent_versions enable row level security;
alter table audit_log enable row level security;
alter table usage_events enable row level security;

-- Gestoras: clients see only their own; admin/counsel see all
create policy gestoras_select on gestoras for select using (
  current_user_role() in ('admin', 'counsel') or id = current_user_gestora()
);
create policy gestoras_admin_write on gestoras for all using (
  current_user_role() = 'admin'
);

-- Funds: siloed by gestora for clients
create policy funds_select on funds for select using (
  current_user_role() in ('admin', 'counsel') or gestora_id = current_user_gestora()
);
create policy funds_admin_write on funds for all using (
  current_user_role() = 'admin'
);

-- Users: see self; admin sees all
create policy users_select_self on users for select using (
  id = auth.uid() or current_user_role() = 'admin'
);
create policy users_admin_write on users for all using (
  current_user_role() = 'admin'
);

-- Requests: client sees own gestora's requests; counsel/admin see all
create policy requests_select on requests for select using (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from funds f
    where f.id = requests.fund_id and f.gestora_id = current_user_gestora()
  )
);
create policy requests_insert on requests for insert with check (
  user_id = auth.uid()
  and exists (
    select 1 from funds f
    where f.id = requests.fund_id and f.gestora_id = current_user_gestora()
  )
);
create policy requests_update on requests for update using (
  current_user_role() in ('admin', 'counsel')
  or (user_id = auth.uid() and exists (
    select 1 from funds f
    where f.id = requests.fund_id and f.gestora_id = current_user_gestora()
  ))
);

-- Documents: follow their request's gestora silo
create policy documents_select on documents for select using (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from requests r join funds f on f.id = r.fund_id
    where r.id = documents.request_id and f.gestora_id = current_user_gestora()
  )
);
create policy documents_insert on documents for insert with check (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from requests r join funds f on f.id = r.fund_id
    where r.id = documents.request_id and f.gestora_id = current_user_gestora()
  )
);

-- Precedents: gestora silo for clients; global templates (NULL gestora) readable by all
create policy precedents_select on precedents for select using (
  current_user_role() in ('admin', 'counsel')
  or gestora_id = current_user_gestora()
  or (gestora_id is null and source in ('slp_curated', 'platform_base'))
);
create policy precedents_admin_write on precedents for all using (
  current_user_role() = 'admin'
);

create policy precedent_versions_select on precedent_versions for select using (
  exists (
    select 1 from precedents p
    where p.id = precedent_versions.precedent_id
      and (
        current_user_role() in ('admin', 'counsel')
        or p.gestora_id = current_user_gestora()
        or (p.gestora_id is null and p.source in ('slp_curated', 'platform_base'))
      )
  )
);
create policy precedent_versions_write on precedent_versions for all using (
  current_user_role() in ('admin', 'counsel')
);

-- Audit log: INSERT only. No select policy for clients (admin can read own-platform audit).
create policy audit_log_insert on audit_log for insert with check (true);
create policy audit_log_admin_select on audit_log for select using (
  current_user_role() = 'admin'
);
-- No UPDATE/DELETE policies exist; trigger trg_audit_log_immutable blocks them regardless.

-- Usage events: admin only (billing)
create policy usage_events_admin on usage_events for select using (
  current_user_role() = 'admin'
);
create policy usage_events_insert on usage_events for insert with check (true);
