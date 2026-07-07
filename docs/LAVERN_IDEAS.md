# Ideas de lavern aplicables a Lol-AI-lo

**Fuente:** [AnttiHero/lavern](https://github.com/AnttiHero/lavern) (Apache 2.0 — reutilizable
con atribución). Analizado el 2026-07-08.

Lavern es un sistema de análisis legal agéntico: 67 agentes especializados (TypeScript,
Fastify, SQLite FTS5) que revisan documentos mediante un protocolo de debate con citas
obligatorias, tres capas de verificación y una "precedent board" con memoria entre
encargos. Sus propios autores reconocen que la superioridad frente a un único modelo
bien prompteado **no está validada**, y la latencia es de 5–10 min por análisis.

## Lo que Lol-AI-lo ya tiene (no copiar)

| Mecanismo lavern | Equivalente lolailo |
|---|---|
| Human gates (aprobación antes de entrega) | Exit A con acknowledgment explícito + Exit B counsel review |
| Citas obligatorias en findings | `ReviewIssue.citation {where, quote}` del critic (Feature 2) |
| Multi-client isolation + audit trail | Aislamiento por `gestora_id` (choke points en `services/db.py`) + `audit_log` append-only |
| Hybrid local-plus-frontier | Local-first Ollama + fallback Anthropic/OpenAI opt-in |
| Playbooks de revisión | `review_playbooks` (009) inyectados al critic |

## Propuestas priorizadas

### P1 — Verificador mecánico de citas (grounding verifier) · esfuerzo bajo, valor alto
Lavern valida **por string-matching** cada quote citada contra el documento parseado; una
finding cuya cita no aparece en el texto no entra en el board. En lolailo el critic ya
emite `{where, quote}` pero nadie verifica que la quote exista en el borrador: un issue
alucinado puede forzar una re-generación inútil.

**Implementación:** en `services/critic.py`, tras parsear los issues, descartar (o
degradar a `minor`) todo issue cuya `citation.quote` normalizada no haga substring-match
contra el texto del borrador. Puro Python, sin coste LLM, sin dependencias. Testeable en
`test_critic.py`.

### P2 — Refuerzo y decaimiento de lecciones · esfuerzo medio, valor alto
La precedent board de lavern promociona patrones `tentative → confirmed` cuando recurren
con veredictos consistentes, y decae los obsoletos. Las `drafting_lessons` de lolailo
(008) hoy solo se acumulan: el ruido crece con el tiempo.

**Implementación:** columnas `status (tentative|confirmed)`, `occurrences`,
`last_reinforced_at` en `drafting_lessons`; al registrar una lección se busca una
equivalente (mismo branch + doc_type + similitud de texto) y se refuerza en lugar de
duplicar; el prompt del drafting agent solo inyecta `confirmed` + las `tentative`
recientes; sweep de decaimiento junto al retention sweep existente.

### P3 — Puerta evaluadora antes de re-generar · esfuerzo bajo-medio
Capa 1 de lavern: un "evaluator gate" barato filtra findings débiles antes de escalar.
En lolailo cada ronda del critic puede disparar una re-generación completa (cara con
Ollama 14B). Una segunda llamada corta ("¿este issue es sustantivo y accionable? sí/no
por issue") sobre los issues `blocking/major` reduciría falsos positivos y rondas
inútiles. Opt-in por config (`CRITIC_GATE_ENABLED`), degradación elegante: si el LLM no
responde, se comportan como hoy.

### P4 — Proveedor cloud UE (Mistral) · esfuerzo medio, valor GDPR alto
El "EU mode" de lavern enruta todo por Mistral AI (París). El fallback cloud de lolailo
hoy es Anthropic/OpenAI (EEUU) — fricción GDPR para gestoras conservadoras. Añadir
`mistral` como `LLM_PROVIDER`/BYO-key por gestora daría un fallback cloud con residencia
de datos UE, coherente con el principio local-first.

**Implementación:** un provider más en `services/providers/` + clave en
`gestora_model_config` (la infraestructura BYO-keys cifradas de la 011 ya lo soporta,
solo hay que añadir la columna `mistral_api_key_enc` y el enrutado en `services/llm.py`).

### P5 — Debate rojo/azul opcional para documentos de alto riesgo · esfuerzo medio
Para requests con `requires_counsel` (Nivel 3), una única ronda adversarial —un agente
"red team" intenta refutar el borrador citando texto, el drafting agent responde— antes
de encolar al counsel humano. Le llega al abogado un borrador pre-desafiado con la lista
de objeciones supervivientes como comentarios (`counsel_comments`, migración 013).
Coste: 2 llamadas LLM extra; solo merece la pena en Exit B.

### P6 — Modo autónomo estilo Clawern · esfuerzo medio, valor operativo
Daemon con heartbeat (lavern usa 30 min) que vigila una carpeta por gestora
(`storage/gestoras/{id}/inbox/`) e ingesta automáticamente precedentes nuevos
(upload + versión + reindex), con notificación por email (Resend → consola como
siempre). Encaja con el conector Drive opcional ya previsto. El sweep-loop de SLA en
`main.py` (lifespan) ya da el patrón de scheduling a reutilizar.

### P7 — Confidence score en issues del critic · esfuerzo trivial
Lavern muestra confianza por finding en la entrega. Añadir `confidence: float` al JSON
del critic y mostrarlo como badge en el trail de revisiones (la UI de
`getRequestReviews` ya pinta issues). Útil para que el cliente calibre los "minor".

## Lo que NO conviene copiar

- **Los 67 agentes.** Contradice el principio "pragmático antes que sobre-ingeniería" del
  proyecto; los propios autores no han validado que supere a un modelo único bien
  prompteado, y la latencia se dispara (5–10 min). Las piezas de valor son las capas de
  verificación baratas (P1, P3), no el enjambre.
- **SQLite FTS5/BM25 como retrieval.** Lolailo ya tiene RAG con embeddings multilingües
  (bge-m3) y niveles de fallback; retroceder a keyword search sería una regresión.
- **La cola sin backend durable.** Lavern lo lista como limitación conocida; lolailo ya
  tiene `generation_jobs` con reintentos.

## Orden sugerido

1. P1 (grounding verifier) — una tarde, elimina la clase de error más peligrosa del critic.
2. P7 (confidence) — trivial, mejora la UX del trail.
3. P2 (lecciones con refuerzo/decay) — evita la degradación del sistema con el uso.
4. P4 (Mistral UE) — argumento comercial GDPR fuerte para gestoras.
5. P3 y P5 según presupuesto de latencia/coste LLM.
6. P6 cuando haya tracción operativa real (varias gestoras subiendo precedentes a diario).
