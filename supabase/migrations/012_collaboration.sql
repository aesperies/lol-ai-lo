-- ============================================================
-- Lol-AI-lo — Collaboration / Sharing (v12)
-- Supabase / PostgreSQL
-- ============================================================
--
-- Lets an OWNER share two read-only resources with same-gestora colleagues:
--   (1) a REQUEST (the whole document thread: params, draft/redline/final,
--       reviews, downloads), and
--   (2) a TABULAR REVIEW (view + CSV export).
--
-- Access semantics (documented in api/sharing.py + auth.py docstrings):
--   A collaborator gets READ access only — they can view the request, its
--   documents and reviews, and download; and view + CSV-export a tabular
--   review. The OWNER keeps EVERY mutating / irreversible action (Exit A
--   acknowledgment, requesting counsel / Exit B, refinements, the counsel
--   flow, deleting, and managing the share list itself).
--
-- THE INVIOLABLE RULE (SPEC guardrail 1 — gestora isolation extended to
-- sharing): a share is STRICTLY within a single gestora. Sharer, sharee AND
-- the shared resource MUST all belong to the SAME gestora. This is enforced
-- at TWO layers:
--   * gestora_id is NOT NULL on every share row (recorded once, = the
--     resource's gestora) and the app layer (api/sharing.py) rejects any
--     sharee whose gestora_id differs from the resource's gestora at CREATE
--     time, and re-checks sharer/sharee/resource gestora equality at ACCESS
--     time (auth.assert_request_access / api/tabular._assert_review_access);
--   * the RLS policies below are the defence-in-depth backstop. There is NO
--     cross-gestora share, ever.

-- ------------------------------------------------------------
-- AUDIT actions (extend the enum)
-- ------------------------------------------------------------
-- NOTE: ``ALTER TYPE ... ADD VALUE`` cannot run inside a transaction block on
-- PostgreSQL < 12 and, even on >= 12, a newly added enum value cannot be used
-- in the SAME transaction that adds it. Supabase applies each migration file
-- in its own transaction, so these ADD VALUEs must NOT be referenced by DML in
-- this file (they are not — they are only used at runtime by api/sharing.py).
-- If you ever combine this with seed DML, split the ADD VALUEs into their own
-- migration that runs (and commits) first.
alter type audit_action add value if not exists 'resource_shared';
alter type audit_action add value if not exists 'resource_unshared';

-- ------------------------------------------------------------
-- TABLE: request_shares (one collaborator per request)
-- ------------------------------------------------------------
-- gestora_id is recorded once on the share row (= the request's gestora). It
-- is NOT NULL so a share can never be "gestora-less", and the app layer keeps
-- sharer/sharee/resource all in the same silo. unique(request_id,
-- shared_with_user_id) makes adding the same collaborator idempotent.
create table request_shares (
  id uuid primary key default uuid_generate_v4(),
  request_id uuid not null references requests(id) on delete cascade,
  gestora_id uuid not null references gestoras(id) on delete cascade,
  shared_with_user_id uuid not null references users(id) on delete cascade,
  shared_by uuid not null references users(id) on delete cascade,
  created_at timestamptz not null default now(),
  unique (request_id, shared_with_user_id)
);
create index idx_request_shares_shared_with on request_shares(shared_with_user_id);

-- ------------------------------------------------------------
-- TABLE: tabular_review_shares (one collaborator per tabular review)
-- ------------------------------------------------------------
-- Same shape and same inviolable single-gestora rule as request_shares.
create table tabular_review_shares (
  id uuid primary key default uuid_generate_v4(),
  review_id uuid not null references tabular_reviews(id) on delete cascade,
  gestora_id uuid not null references gestoras(id) on delete cascade,
  shared_with_user_id uuid not null references users(id) on delete cascade,
  shared_by uuid not null references users(id) on delete cascade,
  created_at timestamptz not null default now(),
  unique (review_id, shared_with_user_id)
);
create index idx_tabular_review_shares_shared_with on tabular_review_shares(shared_with_user_id);

-- ------------------------------------------------------------
-- ROW LEVEL SECURITY
-- ------------------------------------------------------------
-- gestora_id NOT NULL + the app-layer same-gestora checks at create AND access
-- time keep sharing fully siloed; these policies are the defence-in-depth
-- backstop (the backend service role bypasses RLS). A share row is:
--   * SELECTABLE by the sharer (shared_by), the sharee (shared_with_user_id),
--     or admin/counsel (cross-gestora by role, SPEC actor matrix);
--   * INSERT/DELETE-able only by the resource OWNER acting within the same
--     gestora (the resource's gestora must equal the caller's gestora, and the
--     share row's gestora_id must match it too).
alter table request_shares enable row level security;
alter table tabular_review_shares enable row level security;

-- request_shares: visible to sharer / sharee / admin / counsel.
create policy request_shares_select on request_shares for select using (
  current_user_role() in ('admin', 'counsel')
  or shared_by = auth.uid()
  or shared_with_user_id = auth.uid()
);
-- Insert/delete by the request owner, within the same gestora as the request.
create policy request_shares_write on request_shares for all using (
  current_user_role() = 'admin'
  or (
    gestora_id = current_user_gestora()
    and exists (
      select 1 from requests r
      join funds f on f.id = r.fund_id
      where r.id = request_shares.request_id
        and r.user_id = auth.uid()
        and f.gestora_id = current_user_gestora()
    )
  )
) with check (
  current_user_role() = 'admin'
  or (
    gestora_id = current_user_gestora()
    and exists (
      select 1 from requests r
      join funds f on f.id = r.fund_id
      where r.id = request_shares.request_id
        and r.user_id = auth.uid()
        and f.gestora_id = current_user_gestora()
    )
    -- The sharee MUST be a user of the SAME gestora (inviolable rule).
    and exists (
      select 1 from users u
      where u.id = request_shares.shared_with_user_id
        and u.gestora_id = current_user_gestora()
    )
  )
);

-- tabular_review_shares: visible to sharer / sharee / admin / counsel.
create policy tabular_review_shares_select on tabular_review_shares for select using (
  current_user_role() in ('admin', 'counsel')
  or shared_by = auth.uid()
  or shared_with_user_id = auth.uid()
);
-- Insert/delete by the review owner, within the same gestora as the review.
create policy tabular_review_shares_write on tabular_review_shares for all using (
  current_user_role() = 'admin'
  or (
    gestora_id = current_user_gestora()
    and exists (
      select 1 from tabular_reviews tr
      where tr.id = tabular_review_shares.review_id
        and tr.created_by = auth.uid()
        and tr.gestora_id = current_user_gestora()
    )
  )
) with check (
  current_user_role() = 'admin'
  or (
    gestora_id = current_user_gestora()
    and exists (
      select 1 from tabular_reviews tr
      where tr.id = tabular_review_shares.review_id
        and tr.created_by = auth.uid()
        and tr.gestora_id = current_user_gestora()
    )
    -- The sharee MUST be a user of the SAME gestora (inviolable rule).
    and exists (
      select 1 from users u
      where u.id = tabular_review_shares.shared_with_user_id
        and u.gestora_id = current_user_gestora()
    )
  )
);
