# Diseño — Orquestador adaptativo de modelos

*Diseñado el 9-jul-2026. Objetivo declarado por Antonio: "usar todos los modelos del
mercado (incluidos open source cuando tenga la infra lista) y que el orquestador vaya
eligiendo según va mejor". Este documento convierte el router de costes actual
(`services/model_router.py`, reglas fijas task→tier) en un orquestador que decide con
datos — sin tocar jamás la capa de privacidad.*

---

## 0 · Principio rector (inviolable)

**La privacidad define el conjunto de candidatos; el orquestador optimiza DENTRO de él.**

Hoy hay dos decisiones en cadena y así se quedan:

1. *¿Quién puede ver el texto?* — configuración (global + override por gestora,
   fail-closed a local). El orquestador **nunca** amplía este conjunto: si una gestora
   solo permite Ollama local, sus candidatos son los modelos de Ollama, punto.
2. *¿Qué modelo, de los permitidos, hace este trabajo?* — hoy reglas fijas; el diseño
   de abajo lo hace adaptativo.

Otras dos reglas que se conservan tal cual: una gestora que **fija un modelo** no se
re-enruta jamás, y los workloads pesados nunca se degradan por accidente (prior actual
como red de seguridad).

---

## 1 · Qué existe ya y qué falta

| Señal / pieza | Estado | Dónde |
|---|---|---|
| Qué modelo sirvió cada ronda del critic | ✅ ya se graba | `generation_reviews.model_note` |
| **Cuánto cambió el abogado el borrador** (Exit B, similitud draft→validado) | ✅ ya se graba | `quality_metrics` (1 fila por request, difflib) |
| Puntuación/rondas del critic, gate pass/fail | ✅ ya se graba | `generation_reviews` |
| Refinamientos pedidos por el cliente (= insatisfacción) | ✅ derivable | `refinements` por request |
| Eventos de facturación por documento | ✅ | `usage_events` |
| **Tokens, latencia y coste por llamada LLM** | ❌ falta | nueva tabla `llm_calls` |
| Tarifa €/token por modelo | ❌ falta | tabla estática en código (`models/pricing.py`) |
| Agregado calidad×coste por (workload, modelo) | ❌ falta | vista/sweep `model_scorecards` |
| Punto de decisión con política dinámica | ❌ falta | extensión de `model_router.apply()` |

La conclusión importante: **el 70 % de la señal ya existe**. Falta la telemetría de
coste por llamada y el bucle que agrega y decide.

---

## 2 · Arquitectura (4 piezas)

```
   llamada LLM                      sweep periódico                admin / política
┌────────────────┐   escribe    ┌──────────────────┐   publica   ┌─────────────────┐
│ services/llm   │ ───────────► │ model_scorecards │ ──────────► │ /admin/quality  │
│  .complete()   │  llm_calls   │ (agregación por  │             │ vista Orquesta- │
│  + telemetría  │              │ workload×modelo) │             │ dor + toggles   │
└──────┬─────────┘              └──────────────────┘             └────────┬────────┘
       │ consulta                        ▲                                │ escribe
       ▼                                 │ join por request_id            ▼
┌────────────────┐              quality_metrics ·             ┌─────────────────┐
│ model_router   │              generation_reviews ·          │ routing_policies│
│  .apply()      │ ◄─────────── refinements                   │ (shadow|active) │
└────────────────┘   lee la política activa                   └─────────────────┘
```

### 2.1 Telemetría por llamada — tabla `llm_calls` (migración 020)

Una fila por llamada al LLM, escrita en el seam único (`services/llm.complete`), así
cubre TODOS los call sites sin tocarlos:

```sql
create table llm_calls (
  id uuid primary key default uuid_generate_v4(),
  gestora_id uuid references gestoras(id) on delete cascade,
  request_id uuid references requests(id) on delete set null,
  task text not null,            -- parse | generate | critic | ... (etiquetas actuales)
  provider text not null,        -- ollama | anthropic | mistral | grok
  model text not null,
  tokens_in integer,             -- del usage del proveedor; NULL si no lo reporta
  tokens_out integer,
  latency_ms integer not null,
  cost_eur numeric(10,6),        -- tokens × tarifa de models/pricing.py (NULL si local)
  ok boolean not null default true,   -- false = error/503 del proveedor
  created_at timestamptz not null default now()
);
create index on llm_calls (task, provider, model, created_at);
```

Reglas: escribir la fila **nunca bloquea la llamada** (try/except + log, como
`quality_metrics`); `request_id` viaja por el pipeline (ya llega `gestora_id`; añadir
`request_id` al seam es un parámetro opcional más). Retención: purga a 12 meses en el
sweep de retención existente.

### 2.2 Tarifas — `models/pricing.py`

Tabla estática `{(provider, model): (€_in/1M, €_out/1M)}` con los precios publicados
(Sonnet 3/15 $, Haiku 1/5 $, grok-4.5 2/6 $, grok-4.3 1,25/2,50 $, mistral…), y
`0` para Ollama local. Se actualiza a mano cuando cambien precios — es una tabla de
10 líneas, no un sistema.

### 2.3 Agregación — `model_scorecards`

Un sweep periódico (mismo patrón que el sweep de SLA: asyncio in-process, idempotente)
o cálculo a demanda desde el admin. Por cada celda **(task, provider, model[, doc_type
para generate])** sobre una ventana móvil de 90 días:

- **n** — nº de llamadas (una celda no puntúa hasta `n ≥ 20`).
- **fiabilidad** — % de llamadas `ok`.
- **coste medio** por llamada y por documento.
- **latencia** p50 / p95.
- **calidad compuesta (0–100)** — solo para celdas con outcome medible:

| Componente | Peso | Fuente | Por qué |
|---|---|---|---|
| Similitud draft→validado (Exit B) | **50 %** | `quality_metrics.similarity` | La corrección de un abogado humano es la verdad-terreno; cuanto menos toca, mejor era el borrador |
| Critic: puntuación 1ª ronda y nº de rondas hasta aprobar | 25 % | `generation_reviews` | Calidad automática inmediata |
| Tasa de refinamientos por request | 15 % | `refinements` | El cliente pidió cambios = el borrador no valió a la primera |
| Exit A directo (sin counsel, sin refinar) | 10 % | `usage_events` | Máxima señal de "valió a la primera" |

Para workloads *light* sin outcome propio (critic, lessons, tabular) la calidad se
mide distinto: el critic se evalúa por **acuerdo con el resultado** (¿lo que aprobó
acabó validado sin cambios?) y el parse por su tasa de escalado + ediciones del
cliente sobre los parámetros (`params_edited` ya está en el audit log).

**El scorecard es una métrica por celda: `calidad / coste`, con latencia como
desempate.** Nada de ML: agregación SQL pura, explicable línea a línea a un cliente.

### 2.4 Decisión — `routing_policies` + `model_router.apply()`

```sql
create table routing_policies (
  id uuid primary key default uuid_generate_v4(),
  task text not null,
  doc_type text,                 -- NULL = cualquier tipo
  provider text not null,        -- DEBE coincidir con el provider ya resuelto (capa 1)
  model text not null,
  mode text not null check (mode in ('shadow','active')),
  set_by text not null,          -- 'admin' | 'optimizer'
  rationale text,                -- "grok-4.3 iguala a haiku en critic con -18% coste (n=142)"
  created_at timestamptz not null default now()
);
```

`model_router.apply()` cambia una sola cosa: antes de aplicar la regla estática,
consulta si hay política `active` para (task, provider[, doc_type]). Si la hay, usa
ese modelo; si no, **las reglas actuales quedan como prior/fallback**. `shadow` no
cambia nada — solo marca qué habría elegido, y la elección hipotética se apunta en
`llm_calls` (columna `shadow_model text`) para comparar a posteriori.

---

## 3 · Política de decisión — cómo "va eligiendo según va mejor"

Por fases, de menos a más autonomía. Cada fase es útil por sí sola y ninguna
compromete un documento real hasta que los datos lo justifican:

**Fase 0 — Sombra (recopilar).** Telemetría activa, scorecard publicado en el admin,
cero cambios de rutas. Dura hasta tener `n ≥ 20` por celda relevante (~2-4 semanas al
ritmo actual de pruebas; días con 100 docs/mes).

**Fase 1 — Recomendación (humano decide).** El sweep genera recomendaciones cuando una
celda domina a la actual (misma calidad ±2 puntos con coste ≥15 % menor, o mejor
calidad a coste igual, con `n ≥ 20`): *"En `critic`, grok-4.3 iguala a Haiku (78 vs 77)
con -18 % de coste — ¿activar?"*. Antonio (admin) acepta con un clic → fila `active`
en `routing_policies` con su `rationale`. Todo auditado y reversible.

**Fase 2 — Auto solo en light.** Los workloads *light* (critic, gate, lessons, tabular,
parse) se auto-optimizan: el optimizador promociona la mejor celda directamente, con
**exploración epsilon = 10 %** (1 de cada 10 llamadas light prueba el segundo mejor
candidato para que el scorecard no se quede ciego ante modelos nuevos). Un modelo
recién añadido al registry entra automáticamente en la rotación de exploración light.
Equivocarse en una ronda de critic cuesta céntimos y no toca el documento — es el
sitio barato para explorar.

**Fase 3 — Heavy con red humana.** `generate`/`refine` (el documento real) **nunca se
auto-explora**: el coste de un borrador malo lo paga un abogado o un cliente. Aquí el
optimizador solo *recomienda* (como Fase 1) y el cambio lo activa el admin. La señal
que puede justificarlo es la de más peso: la distancia de edición del counsel por
doc_type y modelo. Con el tiempo, si un modelo demuestra dominar en un doc_type
concreto (n alto, meses de datos), se puede promover ese par a auto — decisión futura,
no de este diseño.

**Guardarraíles duros en todas las fases:**

1. Candidatos = solo modelos del **proveedor ya resuelto por la capa de privacidad**.
2. Gestora con modelo fijado → intocable (ya implementado, se conserva).
3. Celda sin `n ≥ 20` → prior estático actual.
4. Proveedor caído → cascada de degradación actual (503 accionable / skip del critic).
5. Exploración solo en light, tope 10 %, y desactivable global (`ORCHESTRATOR_EXPLORE=false`).
6. Toda decisión del optimizador deja `rationale` legible + entrada de auditoría.

---

## 4 · UI (vista "Orquestador" en /admin/quality)

- **Scorecard**: tabla por workload — filas = modelos, columnas = calidad, coste/doc,
  latencia p50, fiabilidad, n. La celda activa marcada; las shadow en gris.
- **Recomendaciones pendientes** con su rationale y botón aceptar/rechazar.
- **Historial de políticas** (quién/qué/cuándo, revertir con un clic).
- KPI de cabecera: € ahorrados/mes vs. ruta estática (comparando coste real vs. el
  que habría tenido el prior — calculable exactamente desde `llm_calls`).

---

## 5 · Plan de implementación

| Fase | Contenido | Esfuerzo |
|---|---|---|
| **F0 telemetría** | Migración 020 (`llm_calls`) · `models/pricing.py` · escritura en el seam `llm.complete` (+`request_id`) · tests | 1 día |
| **F1 scorecard** | Sweep de agregación · endpoint admin · vista Orquestador (solo lectura) | 1-2 días |
| **F2 recomendaciones** | Detector de dominancia · `routing_policies` (migración 021) · aceptar/rechazar en admin · `model_router` lee políticas `active` | 1-2 días |
| **F3 auto-light + epsilon** | Optimizador promociona en light · exploración 10 % · kill-switch | 1 día |
| F4 (futuro) | Auto-heavy por doc_type con meses de datos; candidatos multi-proveedor cuando una gestora permita varios clouds; modelos open-source vía Ollama/vLLM entran al registry y compiten solos | — |

Total hasta F3: **~1 semana de trabajo**, todo incremental y cada fase útil sin la
siguiente.

## 6 · Lo que este diseño NO hace (a propósito)

- Nada de bandits sofisticados, RL ni ML de enrutado: agregación SQL + una regla de
  dominancia. A este volumen (cientos de llamadas/mes) cualquier cosa más compleja es
  ruido con esteroides.
- No cruza proveedores sin permiso: elegir "el mejor del mercado" para una gestora
  solo aplica sobre los proveedores que esa gestora (o la plataforma) haya activado.
- No auto-experimenta con documentos reales (heavy) — ahí siempre hay un humano en el
  bucle hasta que meses de datos digan lo contrario.
