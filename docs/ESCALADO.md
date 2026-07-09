# Plan de escalado — 25 fondos · 100 documentos/mes

*Escrito el 9-jul-2026 a partir del código y de la infraestructura de producción reales
(Railway `backend` + volumen 5 GB, Vercel, Supabase `mmanoxhhkflsmoxtndwu`).*

---

## 1 · Qué significa esta escala (los números)

| Métrica | Valor | Implicación |
|---|---|---|
| Documentos | 100/mes ≈ **5/día laborable** | Throughput trivial; rara vez >2 generaciones simultáneas |
| Llamadas LLM por documento | 4–7 (parse *light*, draft *heavy*, ≤2 critic *light*, gate) | Con Sonnet + router de costes: **~0,15–0,60 $/doc → <60 $/mes** |
| Corpus RAG | 465 plantillas globales (Temis) + ~**1.200 precedentes/año** nuevos (cada validación entra automática como precedente activo) | El corpus se multiplica ×3-4 en un año: **la calidad de recuperación es el cuello real** |
| Usuarios activos | ~10-30 (gestoras + counsel + admin) | Sin problema de concurrencia |

**Conclusión:** el cuello de botella NO es capacidad de cómputo ni coste. Es, por este orden:
(1) calidad del RAG con un corpus creciente, (2) fiabilidad del pipeline de generación,
(3) operación (emails, alertas, secretos).

---

## 2 · RAG escalable — la pieza central

### 2.1 Estado actual (verificado en producción el 9-jul-2026)

- **En producción no hay búsqueda semántica.** `EMBEDDING_PROVIDER=ollama` en Railway,
  pero Railway no tiene Ollama → `_embed()` devuelve `None` y **todas** las recuperaciones
  usan el ranking degradado: idioma → peso → recencia. Con 15 modelos de NDA en la
  biblioteca global, hoy siempre gana "el más reciente en el idioma correcto", no el más
  parecido a la petición.
- **Aunque hubiera embeddings, el diseño no escala:** `rag.retrieve()` re-lee del disco y
  re-embebe *todos* los chunks de *todos* los candidatos en cada generación
  (O(candidatos × chunks) llamadas de embedding por documento). Con el corpus a un año
  vista serían cientos de llamadas y varios segundos/€ por generación, repetidos cada vez.
- Lo que SÍ está bien y se conserva: el pre-filtro duro por `gestora_id + doc_type` en la
  query (invariante de aislamiento), la cadena de niveles 0a→3, y la degradación
  determinista cuando no hay embeddings.

### 2.2 Diseño objetivo: vectores persistidos en Supabase (pgvector)

**Dónde:** en la misma base de datos Supabase. Postgres con la extensión `vector` (incluida
en Supabase, gratis) aguanta millones de chunks con índice HNSW — no hace falta ninguna
vector-DB dedicada (Pinecone, Weaviate…) a esta escala ni a 100× esta escala.

**Esquema (migración 018):**

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE precedent_chunks (
  id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  precedent_version_id  uuid NOT NULL REFERENCES precedent_versions(id) ON DELETE CASCADE,
  gestora_id            uuid NULL,            -- NULL = pool global (niveles 1-2)
  doc_type              text NOT NULL,
  language              text,
  source                text NOT NULL,        -- gestora_model / validated / slp_curated / ...
  version_status        text NOT NULL,        -- active / superseded
  chunk_index           int  NOT NULL,
  text                  text NOT NULL,
  embedding             vector(1024),         -- NULL si la gestora no tiene opt-in cloud
  created_at            timestamptz DEFAULT now()
);
CREATE INDEX ON precedent_chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ON precedent_chunks (gestora_id, doc_type);
```

**Flujo:**

1. **Indexación al escribir, no al leer.** Al subir/activar/supersedar un precedente se
   chunkéa (mismos 512 tokens/50 overlap actuales), se embebe y se insertan las filas.
   Los hooks `rag.reindex_gestora()` / `reindex_global()` ya existen como puntos de anclaje.
2. **Recuperación = 1 embedding + 1 SQL.** Se embebe solo la query y se hace
   `ORDER BY embedding <=> :query LIMIT k` **con el pre-filtro duro en el WHERE**
   (`gestora_id`, `doc_type`, `version_status`) — el aislamiento se aplica en SQL antes
   del ranking, exactamente como hoy pero sin re-leer archivos ni re-embeber nada.
3. **Backfill one-off** de la biblioteca Temis (465 docs) y de los silos existentes.
4. El **fallback degradado actual se conserva intacto** para gestoras sin embeddings.

**Privacidad (se mantiene el modelo actual):**

- Niveles 1-2 (plantillas globales, sin datos de ninguna gestora) → embeddings cloud sin
  conflicto. Esto ya da búsqueda semántica real a TODAS las gestoras sobre el pool global.
- Silos de gestora (niveles 0a/0b) → embeddings solo si la gestora tiene opt-in cloud
  (columna `embedding` NULL en caso contrario → su silo usa el ranking degradado, que en
  un silo pequeño y curado funciona razonablemente bien).

**Proveedor de embeddings a elegir (decisión de Antonio):**

| Opción | Pro | Contra |
|---|---|---|
| **Mistral embed (UE)** ★ recomendada | Residencia de datos en la UE (París) — coherente con el posicionamiento GDPR; ya tenemos provider de Mistral | Ecosistema algo menor |
| OpenAI `text-embedding-3-small` | Estándar de facto, barato | Datos a EE. UU.; proveedor nuevo que gestionar |

Coste de embeddings a plena carga: **<5 $/mes** (indexación incremental + 1 query por generación).

### 2.3 Qué NO hace falta

Vector-DB dedicada, re-ranking con cross-encoders, GraphRAG, fine-tuning. Con corpus
curado por gestora + pre-filtro por tipo de documento, ANN sobre pgvector sobra.

---

## 3 · Fiabilidad del pipeline de generación

- **Problema:** los jobs corren *dentro* del proceso uvicorn (asyncio + `to_thread`). Un
  deploy o reinicio de Railway a mitad de generación mata el job y la solicitud queda
  **atascada en `generating` para siempre** (no hay recuperación al arrancar — verificado).
- **Fix corto (1 h):** *sweep* de arranque — al iniciar la app, todo `generation_job` en
  `running` se marca `failed`, la request vuelve a `confirmed` y se notifica al usuario
  ("reintenta la generación"). Elimina el atasco permanente.
- **Fix medio (cuando duela):** segundo servicio en Railway ("worker") que consuma
  `generation_jobs` de Postgres con `FOR UPDATE SKIP LOCKED`. Sin Redis, sin Celery — la
  tabla ya existe y Postgres es la cola. Esto además permite deploys del backend sin
  interrumpir generaciones. **No es necesario para 5 docs/día; sí antes de 50/día.**

---

## 4 · Infraestructura y almacenamiento

| Pieza | Hoy | A esta escala | Acción |
|---|---|---|---|
| Archivos (modelos, precedentes, outputs) | Volumen Railway 5 GB (128 MB usados) montado en `/app/storage` | ~1-4 GB/año. Aguanta 12-18 meses, pero ata a 1 instancia y **sin backup gestionado** | Añadir **Supabase Storage** como tercer backend en `services/storage.py` (clave `supabase:{path}`, junto a `local:`/`drive:`) — backups, sin tope práctico, mismo proveedor que la DB |
| Backend | Railway 1 servicio, 1 worker uvicorn | Suficiente (LLM va por threadpool, el event loop no se bloquea) | Escala vertical si hace falta; worker separado según §3 |
| Base de datos | Supabase (plan actual a revisar) | Sobrada en volumen | **Pasar a plan Pro (25 $/mes)** antes de clientes reales: backups diarios + soporte |
| Frontend | Vercel | Sin cambios | — |

**Coste total estimado a plena carga: <110 $/mes** (Railway ~15 + Supabase Pro 25 + LLM <60 + embeddings <5).

---

## 5 · Operación antes de clientes reales (pendientes ya conocidos)

1. **Rotar secretos** (password de Postgres, `sb_secret`, API key de Anthropic) — pasaron
   por chats/pantallas durante el setup. *(Antonio: pospuesto "por ahora"; hacerlo antes
   del primer cliente real.)*
2. **Activar Resend** (emails reales): el flujo de counsel/SLA depende de emails que hoy
   van a consola. Incluir digest diario para counsel.
3. **Alerting:** Sentry (o similar) en backend + alertas de uso por gestora
   (`usage_alerts` ya existe, falta el canal).
4. Retirar los usuarios `@test.com` al terminar el piloto.
5. Rate limiting: existe (in-process, suficiente para 1 worker); revisar límites de
   `generation` por gestora cuando haya facturación (Roadmap F: créditos).

---

## 6 · Mejoras de UX priorizadas

### P1 — necesarias para operar 5 docs/día con 25 fondos

1. **Progreso de generación por etapas** en vez de spinner: "Buscando precedentes →
   Redactando → Revisando (critic) → Montando .docx". El backend conoce las fases;
   exponer `phase` en `generation_jobs` y pintarla. Reduce la ansiedad de una espera de
   1-3 min y las falsas sensaciones de cuelgue.
2. **Duplicar solicitud / plantillas de solicitud**: los servicers repiten los mismos
   documentos con las mismas partes; "nueva solicitud a partir de esta" ahorra el 80 % del
   intake recurrente.
3. **Búsqueda y filtros en `/documents`**: por fondo, tipo de documento, estado y fecha.
   Con 100 docs/mes la lista plana muere en semanas.
4. **Biblioteca visible para la gestora** (read-only): sus modelos y precedentes con
   estado activo/superseded. Hoy solo el admin la ve; enseñarla genera confianza en
   "de dónde sale mi documento" y detecta huecos ("no tenéis modelo de X").

### P2 — calidad de vida

5. **Comparador lado a lado** borrador ↔ redline en el visor HTML (hoy se descargan).
6. **Digest email diario para counsel** con su cola y vencimientos (depende de Resend).
7. **Onboarding wizard de gestora nueva**: subir modelos → invitar usuarios → primer
   documento guiado. Hoy ese camino requiere al admin en 3 pantallas distintas.
8. **Autocompletar partes/firmantes desde la ficha del fondo** (los datos del fondo/SPV
   ya están estructurados; el intake los re-pide en texto libre).

### P3 — pulido

9. i18n EN completa (fr/de siguen siendo shells), vista móvil para counsel (validar desde
   el móvil), atajos de teclado en la pantalla de revisión.

---

## 7 · Lo que explícitamente NO necesitamos a esta escala

Kubernetes, microservicios, Redis/Celery, réplicas múltiples del backend, vector-DB
dedicada, GraphQL, CDN propia. Postgres + un worker + pgvector cubren 10× esta carga.
Añadir cualquiera de estas piezas ahora sería coste y superficie de fallo sin beneficio.

---

## 8 · Secuencia propuesta

| Sprint | Contenido | Resultado visible |
|---|---|---|
| **1 — RAG real** ✅ *(código desplegado el 9-jul; falta MISTRAL_API_KEY + backfill)* | Grok/xAI elegido como proveedor (decisión de Antonio; embeddings vía /v1/embeddings con dimensions=1024) → migración 018 (pgvector, aplicada en prod) → indexer on-write → retrieve por ANN con fallback → script de backfill (`backend/scripts/backfill_rag_index.py`) | Búsqueda semántica funcionando en producción; generaciones basadas en el precedente *más parecido*, no el más reciente |
| **2 — Fiabilidad y operación** | Sweep de jobs huérfanos · Supabase Storage · rotación de secretos · Resend + digest | Ningún documento se queda atascado; archivos con backup; emails reales |
| **3 — UX P1** | Progreso por etapas · duplicar solicitud · búsqueda en documents · biblioteca visible | Operación diaria fluida para las gestoras |
| Continuo | Mantener `docs/ARQUITECTURA.html` al día (mandato de CLAUDE.md) | — |
