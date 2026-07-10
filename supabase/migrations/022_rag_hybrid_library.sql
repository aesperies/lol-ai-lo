-- ============================================================
-- 022 — RAG híbrido + biblioteca del cliente + feedback del chat
--
-- 1) Búsqueda híbrida: a la búsqueda semántica (pgvector) se suma búsqueda
--    por texto completo (tsvector 'simple', sin stemming — predecible en
--    es/en/fr/de y fiel a términos legales exactos: "cláusula 8.2",
--    "hurdle rate"). La fusión RRF se hace en Python (services/rag.py);
--    el pre-filtro de aislamiento por gestora_id corre en el WHERE de
--    AMBAS funciones, idéntico a 018/021.
--
-- 2) Chunking estructural: cada chunk registra la sección/cláusula de la
--    que procede (precedent_chunks.section) — las citas del chat pasan de
--    "[1] LPA" a "[1] LPA · Cláusula 8". Se rellena al (re)indexar.
--
-- 3) Biblioteca del cliente: precedents.document_date (fecha del documento,
--    editable al subir; NULL = usar created_at) para ordenar la biblioteca
--    por fondo / año / trimestre / tipo.
--
-- 4) Feedback del chat: chat_messages.feedback ('up'/'down') — telemetría
--    de calidad de las respuestas.
-- ============================================================

alter table precedent_chunks add column if not exists section text;

alter table precedent_chunks add column if not exists text_search tsvector
  generated always as (to_tsvector('simple', text)) stored;
create index if not exists idx_precedent_chunks_text_search
  on precedent_chunks using gin (text_search);

alter table precedents add column if not exists document_date date;

alter table chat_messages add column if not exists feedback text
  check (feedback in ('up', 'down'));

-- La función vectorial devuelve ahora también section (cambia el tipo de
-- retorno → DROP + CREATE).
drop function if exists match_precedent_chunks(vector, text, uuid, text, text, text, text, integer);
create function match_precedent_chunks(
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
  section text,
  similarity double precision
)
language sql stable as $$
  select
    c.id, c.precedent_version_id, c.precedent_id, c.gestora_id, c.doc_type,
    c.language, c.source, c.version_status, c.is_docx, c.chunk_index, c.text,
    c.section,
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

-- Búsqueda por texto completo (mitad léxica de la híbrida). NO exige
-- embed_model: funciona incluso sobre chunks indexados sin vectores
-- (proveedor de embeddings caído) — la mitad léxica nunca degrada.
create or replace function match_precedent_chunks_text(
  p_query text,
  p_gestora_id uuid,                    -- NULL = SOLO pool global
  p_doc_type text default null,
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
  section text,
  rank double precision
)
language sql stable as $$
  select
    c.id, c.precedent_version_id, c.precedent_id, c.gestora_id, c.doc_type,
    c.language, c.source, c.version_status, c.is_docx, c.chunk_index, c.text,
    c.section,
    ts_rank(c.text_search, websearch_to_tsquery('simple', p_query))::double precision as rank
  from precedent_chunks c
  where c.text_search @@ websearch_to_tsquery('simple', p_query)
    and ((p_gestora_id is null and c.gestora_id is null) or c.gestora_id = p_gestora_id)
    and (p_doc_type is null or c.doc_type = p_doc_type)
    and (p_source is null or c.source = p_source)
    and (p_exclude_source is null or c.source is distinct from p_exclude_source)
    and (p_language is null or c.language is null or c.language = p_language)
  order by rank desc
  limit p_limit;
$$;
