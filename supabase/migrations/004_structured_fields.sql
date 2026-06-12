-- ============================================================
-- Lol-AI-lo — Hybrid structured intake fields (v4, improvement #5)
-- Supabase / PostgreSQL
-- ============================================================

-- requests: client-provided structured intake values keyed by the doc_type's
-- field registry (backend/models/doc_fields.py). NULL for freetext-only
-- requests. Values are authoritative for the intake parser: they are merged
-- over the parser output server-side and never flagged [UNCLEAR].
alter table requests
  add column structured_fields jsonb;
