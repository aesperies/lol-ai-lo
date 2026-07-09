-- ============================================================
-- 018 — Índice RAG persistido (pgvector)
--
-- Hasta ahora el RAG re-leía y re-embebía todos los candidatos en cada
-- generación (y en producción, sin Ollama, degradaba SIEMPRE a peso×recencia).
-- Esta migración persiste los chunks + embeddings de cada versión de
-- precedente, indexados al subir/activar (services/indexer.py), y la
-- recuperación pasa a ser 1 embedding de la query + 1 búsqueda ANN.
--
-- Invariante de aislamiento: el filtro por gestora_id/doc_type se aplica en
-- el WHERE de la función SQL, ANTES de ordenar por similitud — idéntico al
-- pre-filtro duro actual de services/rag.py. p_gestora_id NULL busca SOLO el
-- pool global (gestora_id IS NULL), nunca "todas las gestoras".
--
-- embed_model: cada fila registra el modelo que produjo su embedding; la
-- búsqueda exige coincidencia con el modelo de la query (vectores de modelos
-- distintos no son comparables). Dimensión fija 1024 (bge-m3 y mistral-embed).
-- ============================================================

create extension if not exists vector;

create table precedent_chunks (
  id uuid primary key default uuid_generate_v4(),
  precedent_version_id uuid not null references precedent_versions(id) on delete cascade,
  precedent_id uuid not null references precedents(id) on delete cascade,
  gestora_id uuid references gestoras(id) on delete cascade,  -- NULL = pool global
  doc_type text not null,
  language text,
  source text not null,
  version_status text not null,
  is_docx boolean not null default false,
  chunk_index integer not null,
  text text not null,
  embed_model text,
  embedding vector(1024),      -- NULL: indexado sin embeddings (silo sin opt-in / proveedor caído)
  created_at timestamptz not null default now()
);

create index idx_precedent_chunks_version on precedent_chunks(precedent_version_id);
create index idx_precedent_chunks_scope on precedent_chunks(gestora_id, doc_type);
create index idx_precedent_chunks_embedding on precedent_chunks
  using hnsw (embedding vector_cosine_ops);

alter table precedent_chunks enable row level security;

-- Búsqueda ANN con el pre-filtro de aislamiento en SQL. SECURITY INVOKER
-- (por defecto): solo la service-role key la invoca desde el backend.
create or replace function match_precedent_chunks(
  query_embedding vector(1024),
  p_embed_model text,
  p_gestora_id uuid,                    -- NULL = SOLO pool global
  p_doc_type text,
  p_source text default null,           -- filtro exacto (p. ej. gestora_model, slp_curated)
  p_exclude_source text default null,    -- p. ej. excluir gestora_model en el nivel 0b
  p_language text default null,          -- solo pools globales (espeja _global_candidates)
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
    and c.doc_type = p_doc_type
    and (p_source is null or c.source = p_source)
    and (p_exclude_source is null or c.source is distinct from p_exclude_source)
    and (p_language is null or c.language is null or c.language = p_language)
  order by c.embedding <=> query_embedding
  limit p_limit;
$$;
