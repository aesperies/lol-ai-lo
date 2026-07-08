-- ============================================================
-- 016 — Notificaciones in-app
--
-- Bandeja por usuario (campana en la UI). Complementa el email: cada evento
-- clave del flujo escribe una fila; la UI las lista y marca como leídas.
-- kind: counsel_requested | document_validated | comment_added |
--       generation_failed (texto libre para extensiones futuras).
-- ============================================================

create table notifications (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid not null references users(id) on delete cascade,
  gestora_id uuid references gestoras(id) on delete cascade,
  request_id uuid references requests(id) on delete cascade,
  kind text not null,
  title text not null,
  body text,
  read_at timestamptz,
  created_at timestamptz not null default now()
);
create index idx_notifications_user on notifications(user_id, read_at);
alter table notifications enable row level security;
