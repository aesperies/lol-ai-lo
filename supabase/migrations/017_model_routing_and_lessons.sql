-- ============================================================
-- 017 (antes 014, renumerada por colisión entre sesiones) — Mistral BYO key + lessons reinforcement/decay (lavern P2/P4)
--
-- * gestora_model_config.mistral_api_key_enc: encrypted BYO key for the
--   Mistral EU cloud provider (same write-only handling as the other keys).
-- * drafting_lessons gains reinforcement state: a re-extracted near-duplicate
--   lesson bumps occurrences/weight/last_reinforced_at and is promoted
--   tentative -> confirmed at the threshold, instead of piling up duplicates.
--   Decay is computed at read time (services/lessons.py), no sweep needed.
-- ============================================================

alter table gestora_model_config
  add column if not exists mistral_api_key_enc text;

alter table drafting_lessons
  add column if not exists status text not null default 'tentative'
    check (status in ('tentative', 'confirmed')),
  add column if not exists occurrences integer not null default 1,
  add column if not exists last_reinforced_at timestamptz;
