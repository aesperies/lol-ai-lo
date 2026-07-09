-- ============================================================
-- 021 — Chat Q&A sobre el RAG de la gestora
--
-- El cliente pregunta en lenguaje natural a la documentación indexada de su
-- gestora (precedentes, modelos y pool global). Cada respuesta se genera
-- SOLO a partir de los chunks recuperados (grounding) y cita sus fuentes
-- (precedent_id / precedent_version_id), persistidas en citations.
--
-- Aislamiento: chat_conversations y chat_messages llevan gestora_id y las
-- consultas del backend filtran siempre por él (mismo pre-filtro duro que el
-- resto del stack). Una conversación es PRIVADA de su usuario.
--
-- match_precedent_chunks: p_doc_type pasa a ser opcional (NULL = todos los
-- tipos de documento del ámbito). El pipeline de generación sigue pasando
-- doc_type siempre; el chat busca en todo el silo de la gestora.
-- ============================================================

create table chat_conversations (
  id uuid primary key default uuid_generate_v4(),
  gestora_id uuid not null references gestoras(id) on delete cascade,
  user_id uuid not null references users(id) on delete cascade,
  title text,
  created_at timestamptz not null default now()
);
create index idx_chat_conversations_user on chat_conversations(gestora_id, user_id);

create table chat_messages (
  id uuid primary key default uuid_generate_v4(),
  conversation_id uuid not null references chat_conversations(id) on delete cascade,
  gestora_id uuid not null references gestoras(id) on delete cascade,
  role text not null check (role in ('user', 'assistant')),
  content text not null,
  citations jsonb,      -- [{precedent_id, precedent_version_id, doc_type, source, snippet}]
  verification jsonb,   -- hallazgos del verificador de grounding (NULL si no corrió)
  model_note text,      -- provider:model que generó la respuesta
  created_at timestamptz not null default now()
);
create index idx_chat_messages_conversation on chat_messages(conversation_id);

alter table chat_conversations enable row level security;
alter table chat_messages enable row level security;

alter type audit_action add value if not exists 'chat_message_sent';
alter type audit_resource_type add value if not exists 'conversation';

-- p_doc_type opcional: NULL busca en TODOS los doc_types del ámbito (chat).
-- El pre-filtro de aislamiento por gestora_id no cambia.
create or replace function match_precedent_chunks(
  query_embedding vector(1024),
  p_embed_model text,
  p_gestora_id uuid,                    -- NULL = SOLO pool global
  p_doc_type text,                      -- NULL = todos los doc_types
  p_source text default null,
  p_exclude_source text default null,
  p_language text default null,
  p_limit integer default 24
) returns table (
  id uuid,
  precedent_version_id uuid,
  precedent_id uuid,
  gestora_id uuid,
  doc_type text,
  language text,
  source text,
  version_status text,
  is_docx boolean,
  chunk_index integer,
  text text,
  similarity double precision
)
language sql stable as $$
  select
    c.id, c.precedent_version_id, c.precedent_id, c.gestora_id, c.doc_type,
    c.language, c.source, c.version_status, c.is_docx, c.chunk_index, c.text,
    1 - (c.embedding <=> query_embedding) as similarity
  from precedent_chunks c
  where c.embedding is not null
    and c.embed_model = p_embed_model
    and ((p_gestora_id is null and c.gestora_id is null) or c.gestora_id = p_gestora_id)
    and (p_doc_type is null or c.doc_type = p_doc_type)
    and (p_source is null or c.source = p_source)
    and (p_exclude_source is null or c.source is distinct from p_exclude_source)
    and (p_language is null or c.language is null or c.language = p_language)
  order by c.embedding <=> query_embedding
  limit p_limit;
$$;
