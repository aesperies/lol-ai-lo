-- ============================================================
-- 019 — Grok (xAI) como proveedor LLM opt-in
--
-- gestora_model_config.xai_api_key_enc: BYO key cifrada para el proveedor
-- Grok/xAI (mismo tratamiento write-only que las demás claves). Grok es
-- SOLO generación: xAI no publica modelos de embeddings (jul-2026), así que
-- el índice RAG (018) mantiene su propio EMBEDDING_PROVIDER.
-- ============================================================

alter table gestora_model_config
  add column if not exists xai_api_key_enc text;
