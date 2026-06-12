-- ============================================================
-- Lol-AI-lo — Iterative refinements (v3)
-- Supabase / PostgreSQL
-- ============================================================

-- ------------------------------------------------------------
-- ENUMS
-- ------------------------------------------------------------
create type refinement_status as enum ('pending', 'applied', 'failed');

-- ------------------------------------------------------------
-- TABLES
-- ------------------------------------------------------------

-- documents: every draft/redline version is tied to a refinement iteration
-- (0 = original generation, N = output of refinement N). Existing rows are
-- the original generation, hence DEFAULT 0.
alter table documents
  add column iteration integer not null default 0;
create index idx_documents_request_iteration on documents(request_id, iteration);

-- Iterative refinement requests: after generation (status 'review_pending')
-- the client may ask for up to max_refinements targeted natural-language
-- adjustments. Each applied refinement produces a new draft iteration plus a
-- redline regenerated against the SAME original precedent base, so the
-- redline always shows the cumulative change vs the precedent.
create table refinements (
  id uuid primary key default uuid_generate_v4(),
  request_id uuid not null references requests(id) on delete cascade,
  iteration integer not null,
  instruction text not null check (char_length(instruction) between 5 and 1000),
  status refinement_status not null default 'pending',
  -- Failure reason surfaced to the client (the [REFINEMENT-UNCLEAR: ...]
  -- reason from the LLM, or the final job error). NULL unless status='failed'.
  error text,
  created_by uuid references users(id),
  created_at timestamptz not null default now(),
  applied_at timestamptz,
  unique (request_id, iteration)
);
create index idx_refinements_request on refinements(request_id);

-- ------------------------------------------------------------
-- ROW LEVEL SECURITY
-- ------------------------------------------------------------

alter table refinements enable row level security;

-- Refinements: mirror the requests silo policies (client sees refinements of
-- own gestora's requests; counsel/admin see all). Status updates are
-- performed by the backend job runner with the service role (bypasses RLS).
create policy refinements_select on refinements for select using (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from requests r join funds f on f.id = r.fund_id
    where r.id = refinements.request_id and f.gestora_id = current_user_gestora()
  )
);
create policy refinements_insert on refinements for insert with check (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from requests r join funds f on f.id = r.fund_id
    where r.id = refinements.request_id and f.gestora_id = current_user_gestora()
  )
);
