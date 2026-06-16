-- ============================================================
-- Lol-AI-lo — Tabular Review (multi-document extraction grid, v10)
-- Supabase / PostgreSQL
-- ============================================================
--
-- A gestora user selects several of THEIR OWN documents and defines columns
-- (each column = a question + an answer type). The system extracts one cell per
-- (document × column): a typed value + reasoning + a verifiable citation
-- (page + verbatim quote) from that document. The result is a grid (rows =
-- documents, columns = questions), exportable to CSV.
--
-- INVIOLABLE ISOLATION RULE (SPEC guardrails 1 & 3): tabular reviews and every
-- child row are STRICTLY gestora-siloed exactly like requests/documents. The
-- owning gestora is recorded ONCE on tabular_reviews.gestora_id; columns,
-- documents and cells inherit isolation via a join back to that parent. A
-- review's referenced documents (precedent_version OR generated request
-- document) MUST belong to the same gestora silo — the application layer
-- (services/tabular.py + api/tabular.py) hard-checks every reference against
-- the caller's gestora at create time, and these policies are the
-- defence-in-depth backstop. There is NO cross-gestora / global review pool.

-- ------------------------------------------------------------
-- ENUMS
-- ------------------------------------------------------------
create type tabular_review_status as enum ('draft', 'running', 'complete', 'failed');
create type tabular_col_type as enum (
  'text', 'number', 'percent', 'monetary', 'date', 'yes_no', 'tag'
);
-- A review document references EITHER a precedent_version or a generated
-- request document (both already live in the gestora silo).
create type tabular_source_kind as enum ('precedent_version', 'request_document');
create type tabular_cell_status as enum ('pending', 'done', 'error');

-- ------------------------------------------------------------
-- AUDIT actions + resource type
-- ------------------------------------------------------------
alter type audit_action add value if not exists 'tabular_review_created';
alter type audit_action add value if not exists 'tabular_review_run';
alter type audit_action add value if not exists 'tabular_review_column_added';
alter type audit_action add value if not exists 'tabular_review_column_deleted';
alter type audit_action add value if not exists 'tabular_review_document_deleted';
alter type audit_action add value if not exists 'tabular_review_exported';
alter type audit_resource_type add value if not exists 'tabular_review';

-- ------------------------------------------------------------
-- TABLE: tabular_reviews (the parent; carries the gestora silo)
-- ------------------------------------------------------------
create table tabular_reviews (
  id uuid primary key default uuid_generate_v4(),
  gestora_id uuid not null references gestoras(id) on delete cascade,
  fund_id uuid references funds(id) on delete set null,
  created_by uuid references users(id) on delete set null,
  title text not null,
  status tabular_review_status not null default 'draft',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index idx_tabular_reviews_gestora on tabular_reviews(gestora_id);

create trigger trg_tabular_reviews_updated_at
  before update on tabular_reviews
  for each row execute function set_updated_at();

-- ------------------------------------------------------------
-- TABLE: tabular_review_columns (one question + answer type each)
-- ------------------------------------------------------------
create table tabular_review_columns (
  id uuid primary key default uuid_generate_v4(),
  review_id uuid not null references tabular_reviews(id) on delete cascade,
  position int not null,
  name text not null,
  question text not null,
  col_type tabular_col_type not null,
  -- Allowed values for the 'tag' answer type (JSON array of strings); NULL otherwise.
  options jsonb,
  created_at timestamptz not null default now(),
  unique (review_id, position)
);
create index idx_tabular_review_columns_review on tabular_review_columns(review_id);

-- ------------------------------------------------------------
-- TABLE: tabular_review_documents (the rows of the grid)
-- ------------------------------------------------------------
-- source_id references EITHER a precedent_versions.id (source_kind=
-- 'precedent_version') or a documents.id (source_kind='request_document').
-- Not a hard FK because the column is polymorphic; the application validates
-- the reference AND that it belongs to the review's gestora silo.
create table tabular_review_documents (
  id uuid primary key default uuid_generate_v4(),
  review_id uuid not null references tabular_reviews(id) on delete cascade,
  position int not null,
  source_kind tabular_source_kind not null,
  source_id uuid not null,
  label text,
  created_at timestamptz not null default now()
);
create index idx_tabular_review_documents_review on tabular_review_documents(review_id);

-- ------------------------------------------------------------
-- TABLE: tabular_review_cells (one per document × column)
-- ------------------------------------------------------------
create table tabular_review_cells (
  id uuid primary key default uuid_generate_v4(),
  review_id uuid not null references tabular_reviews(id) on delete cascade,
  document_id uuid not null references tabular_review_documents(id) on delete cascade,
  column_id uuid not null references tabular_review_columns(id) on delete cascade,
  value text,
  reasoning text,
  -- {"page": <int|string|null>, "quote": "<verbatim excerpt>"} pointing to
  -- where in the document the answer was found (page is null for plain text).
  citation jsonb,
  status tabular_cell_status not null default 'pending',
  error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (document_id, column_id)
);
create index idx_tabular_review_cells_review on tabular_review_cells(review_id);

create trigger trg_tabular_review_cells_updated_at
  before update on tabular_review_cells
  for each row execute function set_updated_at();

-- ------------------------------------------------------------
-- ROW LEVEL SECURITY
-- ------------------------------------------------------------
-- All four tables are gestora-siloed exactly like requests/documents: a client
-- sees ONLY rows whose owning tabular_reviews.gestora_id is its own gestora;
-- admin/counsel are cross-gestora by role (SPEC actor matrix). The service role
-- bypasses RLS; the application layer enforces the same isolation explicitly.
alter table tabular_reviews enable row level security;
alter table tabular_review_columns enable row level security;
alter table tabular_review_documents enable row level security;
alter table tabular_review_cells enable row level security;

-- tabular_reviews: own gestora (clients), all (admin/counsel).
create policy tabular_reviews_select on tabular_reviews for select using (
  current_user_role() in ('admin', 'counsel')
  or gestora_id = current_user_gestora()
);
-- Inserts/updates by the owning gestora's client (own gestora) or admin/counsel.
create policy tabular_reviews_insert on tabular_reviews for insert with check (
  current_user_role() in ('admin', 'counsel')
  or gestora_id = current_user_gestora()
);
create policy tabular_reviews_update on tabular_reviews for update using (
  current_user_role() in ('admin', 'counsel')
  or gestora_id = current_user_gestora()
);

-- Child tables: isolation follows the parent review's gestora_id via a join.
create policy tabular_review_columns_select on tabular_review_columns for select using (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from tabular_reviews tr
    where tr.id = tabular_review_columns.review_id
      and tr.gestora_id = current_user_gestora()
  )
);
create policy tabular_review_columns_write on tabular_review_columns for all using (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from tabular_reviews tr
    where tr.id = tabular_review_columns.review_id
      and tr.gestora_id = current_user_gestora()
  )
);

create policy tabular_review_documents_select on tabular_review_documents for select using (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from tabular_reviews tr
    where tr.id = tabular_review_documents.review_id
      and tr.gestora_id = current_user_gestora()
  )
);
create policy tabular_review_documents_write on tabular_review_documents for all using (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from tabular_reviews tr
    where tr.id = tabular_review_documents.review_id
      and tr.gestora_id = current_user_gestora()
  )
);

create policy tabular_review_cells_select on tabular_review_cells for select using (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from tabular_reviews tr
    where tr.id = tabular_review_cells.review_id
      and tr.gestora_id = current_user_gestora()
  )
);
create policy tabular_review_cells_write on tabular_review_cells for all using (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from tabular_reviews tr
    where tr.id = tabular_review_cells.review_id
      and tr.gestora_id = current_user_gestora()
  )
);
