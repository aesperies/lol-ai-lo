# Lol-AI-lo

Plataforma de generación y revisión de documentación societaria y de fondos para *fund servicers* europeos de venture capital. Los clientes (abogados in-house / gestores de fondos) solicitan documentos en lenguaje natural; la plataforma los genera usando precedentes propios de cada gestora (RAG) y, opcionalmente, los enruta a un abogado externo para validación antes de la entrega.

> Especificación completa: [docs/SPEC.md](docs/SPEC.md)

## Arquitectura

| Capa | Tecnología |
|------|-----------|
| Frontend | Next.js 14 (App Router) + Tailwind CSS |
| Backend | Python + FastAPI |
| Auth / DB | Supabase (PostgreSQL, roles: `client` / `counsel` / `admin`) |
| LLM | Anthropic Claude (`claude-sonnet-4-20250514`) |
| RAG | LlamaIndex + OpenAI `text-embedding-3-small` |
| Almacenamiento de precedentes | Google Drive (fallback: filesystem local) |
| Generación .docx / redline | python-docx (autor del redline: "Lol-AI-lo AI") |
| Email | Resend (fallback: log en consola) |

## Regla de oro

**El aislamiento por gestora es inviolable.** Precedentes, documentos y datos están silados por `gestora_id` en cada consulta (RLS en Supabase + filtro duro en el RAG). El audit log es append-only a nivel de base de datos.

## Puesta en marcha (desarrollo)

1. **Variables de entorno** — copia [.env.example](.env.example):
   - `backend/.env` (variables del backend)
   - `frontend/.env.local` (variables `NEXT_PUBLIC_*`)

   Sin credenciales, la plataforma degrada con elegancia: emails se loguean en consola, el almacenamiento usa `./storage`, y los endpoints LLM devuelven 503 con mensaje claro. Con `DEV_AUTH_STUB=true` no necesitas Supabase para desarrollar.

2. **Base de datos** — aplica la migración en tu proyecto Supabase:
   ```bash
   supabase db push   # o ejecuta supabase/migrations/001_initial_schema.sql en el SQL editor
   ```

3. **Backend**:
   ```bash
   cd backend
   python3 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   uvicorn main:app --reload --port 8000
   ```

4. **Frontend**:
   ```bash
   cd frontend
   npm install
   npm run dev   # http://localhost:3000
   ```

5. **Tests** (incluye la suite de aislamiento entre gestoras):
   ```bash
   cd backend && pytest tests/ -v
   ```

## Flujo maestro

```
Cliente → Formulario de intake → Parser (Claude) → Confirmación de parámetros
       → Generación (RAG + Claude + python-docx) → Borrador + Redline
       → EXIT A: descarga directa (checkbox de responsabilidad obligatorio)
       → EXIT B: validación por abogado → revisión → entrega final
                 (el documento validado entra automáticamente en la biblioteca de precedentes)
```

Sin precedente disponible (Level 3), la validación por abogado es **obligatoria** — Exit A queda deshabilitado.

## Estructura corporativa

- **Lol-AI-lo SL** — entidad tecnológica: opera la plataforma y factura suscripciones a las gestoras.
- **Lol-AI-lo Legal SLP** — entidad legal: firma los contratos de servicios jurídicos, emplea a los abogados (counsel) y responde de los documentos entregados. Todos los emails a clientes salen de su dominio.

## Despliegue

- Frontend → Vercel (`frontend/`)
- Backend → Railway o Render (`backend/`, `uvicorn main:app`)
- DB/Auth → Supabase
