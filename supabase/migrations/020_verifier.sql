-- ============================================================
-- 020 — Verificador cruzado anti-alucinaciones
--
-- Tras el critic, un verificador independiente busca SOLO fallos garrafales:
--   Capa 1 (determinista, sin LLM): datos duros del intake confirmado
--     (partes, importes, fechas) cotejados contra el borrador por string-match.
--   Capa 2 (LLM de OTRO proveedor): checklist cerrada (dato inventado,
--     contradicción interna, referencia legal dudosa, idioma/jurisdicción);
--     cada hallazgo debe citar el fragmento exacto o se descarta (grounding).
-- Un hallazgo crítico fuerza Exit B (validación por abogado). El verificador
-- nunca reescribe ni bloquea la generación.
--
-- verifications: una fila por verificación (generación inicial iteration=0,
-- refinamientos iteration=N). gestora_model_config.verify_provider: override
-- por gestora ('none' desactiva; NULL = política de plataforma; un proveedor
-- lo fija). Regla de privacidad: una gestora con proveedor LLM explícito
-- nunca ve su borrador enviado a un proveedor distinto salvo que ella misma
-- fije verify_provider.
-- ============================================================

create table verifications (
  id uuid primary key default uuid_generate_v4(),
  request_id uuid not null references requests(id) on delete cascade,
  iteration integer not null default 0,
  provider text,                -- proveedor LLM de la capa 2 (NULL si no corrió)
  model text,
  findings jsonb not null default '[]'::jsonb,
  critical_count integer not null default 0,
  forced_counsel boolean not null default false,
  created_at timestamptz not null default now()
);
create index idx_verifications_request on verifications(request_id);
alter table verifications enable row level security;

alter table gestora_model_config
  add column if not exists verify_provider text;
