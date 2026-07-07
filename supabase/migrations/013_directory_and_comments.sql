-- ============================================================
-- 013 — Directory endpoints + counsel review comments
--
-- Backs the endpoints the frontend already calls:
--   * GET/POST /api/gestoras, GET /api/funds, GET/POST /api/users
--     (new audit actions gestora_created / user_invited)
--   * GET/POST /api/requests/{id}/comments — the counsel review thread
--     (counsel_comments table, audit action counsel_comment_added)
-- ============================================================

alter type audit_action add value if not exists 'gestora_created';
alter type audit_action add value if not exists 'user_invited';
alter type audit_action add value if not exists 'counsel_comment_added';

-- ------------------------------------------------------------
-- TABLE: counsel_comments (review thread on a request)
-- ------------------------------------------------------------
-- author_name is denormalized at write time so the thread stays readable
-- if the author user row is later anonymised/deleted (GDPR erasure keeps
-- the thread intact without pointing at personal data).
create table counsel_comments (
  id uuid primary key default uuid_generate_v4(),
  request_id uuid not null references requests(id) on delete cascade,
  author_id uuid references users(id) on delete set null,
  author_name text not null,
  text text not null check (char_length(text) between 1 and 4000),
  created_at timestamptz not null default now()
);
create index idx_counsel_comments_request on counsel_comments(request_id);

-- ------------------------------------------------------------
-- ROW LEVEL SECURITY
-- ------------------------------------------------------------
-- Defence in depth (the backend service role bypasses RLS): comments follow
-- request visibility — admin/counsel cross-gestora by role, a client only on
-- requests of their own gestora. Writes are counsel/admin only (the review
-- thread is authored from the counsel panel).
alter table counsel_comments enable row level security;

create policy counsel_comments_select on counsel_comments for select using (
  current_user_role() in ('admin', 'counsel')
  or exists (
    select 1 from requests r
    join funds f on f.id = r.fund_id
    where r.id = counsel_comments.request_id
      and f.gestora_id = current_user_gestora()
  )
);

create policy counsel_comments_insert on counsel_comments for insert with check (
  current_user_role() in ('admin', 'counsel')
);
