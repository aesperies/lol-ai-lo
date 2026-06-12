-- ============================================================
-- Lol-AI-lo — Counsel assignments + async generation jobs (v2)
-- Supabase / PostgreSQL
-- ============================================================

-- ------------------------------------------------------------
-- ENUMS
-- ------------------------------------------------------------
create type generation_job_status as enum ('queued', 'running', 'succeeded', 'failed');

-- ------------------------------------------------------------
-- TABLES
-- ------------------------------------------------------------

-- Counsel <-> gestora assignment: Exit B notifications route to the
-- gestora's PRIMARY counsel, then any backup assignment, then (no
-- assignment at all) broadcast to every counsel user.
create table counsel_assignments (
  id uuid primary key default uuid_generate_v4(),
  gestora_id uuid not null references gestoras(id) on delete cascade,
  counsel_user_id uuid not null references users(id) on delete cascade,
  is_primary boolean not null default false,
  created_at timestamptz not null default now(),
  unique (gestora_id, counsel_user_id)
);
create index idx_counsel_assignments_gestora on counsel_assignments(gestora_id);
-- At most ONE primary counsel per gestora.
create unique index idx_counsel_assignments_one_primary
  on counsel_assignments(gestora_id) where is_primary;

-- Only users with role 'counsel' may be assigned.
create or replace function check_counsel_assignment_role()
returns trigger as $$
begin
  if (select role from users where id = new.counsel_user_id) is distinct from 'counsel' then
    raise exception 'counsel_assignments: user % does not have role counsel', new.counsel_user_id;
  end if;
  return new;
end;
$$ language plpgsql;

create trigger trg_counsel_assignments_role
  before insert or update on counsel_assignments
  for each row execute function check_counsel_assignment_role();

-- Async generation jobs: one row per enqueued generation run for a request.
-- Executed by the in-process asyncio runner (services/jobs.py); state is
-- persisted here so it is inspectable/pollable through the API.
create table generation_jobs (
  id uuid primary key default uuid_generate_v4(),
  request_id uuid not null references requests(id) on delete cascade,
  status generation_job_status not null default 'queued',
  attempts integer not null default 0,
  max_attempts integer not null default 3,
  last_error text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  finished_at timestamptz,
  updated_at timestamptz not null default now()
);
create index idx_generation_jobs_request on generation_jobs(request_id);

create trigger trg_generation_jobs_updated_at
  before update on generation_jobs
  for each row execute function set_updated_at();

-- ------------------------------------------------------------
-- ROW LEVEL SECURITY
-- ------------------------------------------------------------

alter table counsel_assignments enable row level security;
alter table generation_jobs enable row level security;

-- Counsel assignments: admin full access; clients SELECT only their own
-- gestora's rows (so the intake form can show the assigned counsel's name);
-- counsel SELECT their own assignments.
create policy counsel_assignments_admin_write on counsel_assignments for all using (
  current_user_role() = 'admin'
);
create policy counsel_assignments_select on counsel_assignments for select using (
  current_user_role() = 'admin'
  or gestora_id = current_user_gestora()
  or counsel_user_id = auth.uid()
);

-- Generation jobs: mirror the requests silo policies (client sees jobs of
-- own gestora's requests; counsel/admin see all). Updates are performed by
-- the backend job runner with the service role (bypasses RLS).
create policy generation_jobs_select on generation_jobs for select using (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from requests r join funds f on f.id = r.fund_id
    where r.id = generation_jobs.request_id and f.gestora_id = current_user_gestora()
  )
);
create policy generation_jobs_insert on generation_jobs for insert with check (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from requests r join funds f on f.id = r.fund_id
    where r.id = generation_jobs.request_id and f.gestora_id = current_user_gestora()
  )
);
