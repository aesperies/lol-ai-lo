-- ============================================================
-- Lol-AI-lo — Specialized drafting agents, critic loop, learned lessons (v8)
-- Supabase / PostgreSQL
-- ============================================================

-- ------------------------------------------------------------
-- TABLES
-- ------------------------------------------------------------

-- Drafting lessons learned from counsel-validated (Exit B) and accepted-as-is
-- (Exit A) documents (services/lessons.py).
--
-- INVIOLABLE ISOLATION RULE (SPEC guardrails 1 & 3): lessons are STRICTLY
-- gestora-siloed. gestora_id is NOT NULL and is the hard pre-filter on every
-- read (services.lessons.lessons_for). A lesson distilled from one gestora's
-- documents is NEVER retrievable for another gestora. There is NO global /
-- cross-gestora lesson pool, and none must ever be added — unlike precedents
-- there is intentionally no NULL-gestora (slp_curated / platform_base) branch
-- here.
create table drafting_lessons (
  id uuid primary key default uuid_generate_v4(),
  gestora_id uuid not null references gestoras(id) on delete cascade,
  branch text not null,
  doc_type text,
  lesson text not null,
  source_request_id uuid references requests(id) on delete set null,
  weight real not null default 1.0,
  created_at timestamptz not null default now()
);
-- Read path filters on (gestora_id, branch); index mirrors it.
create index idx_drafting_lessons_gestora_branch on drafting_lessons(gestora_id, branch);

-- Critic / reviewer trail (services/critic.py): one row per critic round for a
-- generation (or refinement) iteration. RLS mirrors the requests silo.
create table generation_reviews (
  id uuid primary key default uuid_generate_v4(),
  request_id uuid not null references requests(id) on delete cascade,
  iteration integer not null default 0,
  round integer not null,
  approved boolean not null,
  issues jsonb not null default '[]'::jsonb,
  model_note text,
  created_at timestamptz not null default now()
);
create index idx_generation_reviews_request on generation_reviews(request_id);

-- ------------------------------------------------------------
-- ROW LEVEL SECURITY
-- ------------------------------------------------------------

alter table drafting_lessons enable row level security;
alter table generation_reviews enable row level security;

-- Drafting lessons: gestora-siloed SELECT — a client sees ONLY its own
-- gestora's lessons; admin/counsel see all (cross-gestora by role, as
-- elsewhere). Rows are written by the backend service role (bypasses RLS); the
-- INSERT policy mirrors the silo for completeness. The select policy is the
-- defence-in-depth backstop for the application-level hard gestora_id filter.
create policy drafting_lessons_select on drafting_lessons for select using (
  current_user_role() in ('admin', 'counsel')
  or gestora_id = current_user_gestora()
);
create policy drafting_lessons_insert on drafting_lessons for insert with check (
  current_user_role() in ('admin', 'counsel')
  or gestora_id = current_user_gestora()
);

-- Generation reviews: mirror the requests silo (client sees reviews of own
-- gestora's requests; counsel/admin see all). Updates/inserts by the backend
-- generation job with the service role (bypasses RLS).
create policy generation_reviews_select on generation_reviews for select using (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from requests r join funds f on f.id = r.fund_id
    where r.id = generation_reviews.request_id and f.gestora_id = current_user_gestora()
  )
);
create policy generation_reviews_insert on generation_reviews for insert with check (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from requests r join funds f on f.id = r.fund_id
    where r.id = generation_reviews.request_id and f.gestora_id = current_user_gestora()
  )
);
