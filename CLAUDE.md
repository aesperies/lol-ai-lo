Project Context - lol-ai-lo

## Overview
lol-ai-lo es una plataforma de generación y revisión de documentos para gestoras de fondos de capital riesgo (VC fund servicers) en Europa. 

Los clientes (in-house counsel o fund managers) pueden solicitar documentos corporativos y de fondos en lenguaje natural. El sistema genera los documentos usando RAG sobre los precedentes propios de cada gestora, y opcionalmente los envía a counsel externo para validación/redline antes de la entrega final.

**Principios clave del proyecto:**
- Local-first por defecto (los datos no salen de la máquina del usuario)
- Aislamiento estricto por gestora (`gestora_id`)
- Cumplimiento GDPR y confidencialidad
- Graceful degradation (funciona aunque fallen servicios opcionales)
- Auditabilidad (append-only audit logs)

## Tech Stack

### Frontend
- Next.js 14 (App Router)
- TypeScript + Tailwind CSS
- Se comunica con el backend vía API REST

### Backend
- Python + FastAPI
- Uvicorn como servidor
- python-docx para generación de documentos con redlines

### LLM & Embeddings (por defecto local)
- **LLM**: Ollama (`qwen2.5:14b-instruct` recomendado, o 7b como fallback)
- **Embeddings**: Ollama `bge-m3` (multilingüe)
- **Fallbacks cloud**: Anthropic Claude (LLM) y OpenAI (embeddings)

### Base de datos y Auth
- Supabase (PostgreSQL + Row Level Security)
- Modo desarrollo: `DEV_AUTH_STUB=true` (sin base de datos real)

### Almacenamiento de precedentes
- Local filesystem (`./storage`)
- Opcional: Google Drive

### Otros
- Docker Compose para desarrollo
- Resend (email opcional, con fallback a consola)

## Project Structure
lol-ai-lo/
├── backend/              # FastAPI backend
│   ├── main.py
│   ├── api/              # Routers/endpoints
│   ├── services/         # Lógica de negocio (RAG, generación, etc.)
│   ├── models/
│   └── tests/
├── frontend/             # Next.js 14 (App Router)
│   ├── app/
│   ├── components/
│   └── lib/
├── supabase/migrations/  # Migraciones SQL
├── docs/                 # Documentación técnica importante
│   ├── LOCAL_MODELS.md
│   ├── SPEC.md
│   ├── SECURITY.md
│   └── GDPR.md
├── storage/              # Precedentes almacenados localmente (se crea en runtime)
├── docker-compose.yml
└── CLAUDE.md


## Key Commands

### Ejecución local (recomendada para desarrollo)
```bash
# 1. Ollama (debe estar corriendo)
ollama serve
ollama pull qwen2.5:14b-instruct
ollama pull bge-m3

# 2. Backend
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# 3. Frontend
cd frontend
npm install
npm run dev

Important Rules & Conventions

Local-first first: Por defecto todo debe intentar ejecutarse localmente con Ollama. Los proveedores cloud (Anthropic/OpenAI) son opt-in.
Aislamiento por gestora: Nunca mezclar datos entre diferentes gestora_id. Usar siempre filtros + RLS.
Graceful degradation: El sistema debe seguir funcionando (aunque con funcionalidad reducida) si Ollama, Supabase, email o almacenamiento externo no están disponibles.
Modo desarrollo: Usar DEV_AUTH_STUB=true para no depender de Supabase durante desarrollo.
Documentos: Se generan con python-docx. El autor de los redlines debe aparecer como "Lol-AI-lo AI".
No romper privacidad: Nunca enviar datos de una gestora a servicios cloud sin que sea explícitamente opt-in.

Architecture Highlights

Intake en lenguaje natural → parsing con LLM → RAG sobre precedentes de la gestora → generación de documento.
Flujo opcional de validación por counsel externo (con redline).
Dos salidas posibles: descarga directa o envío a counsel → validación → entrega final + incorporación del documento validado como nuevo precedente.
Fallbacks bien definidos cuando fallan componentes (embeddings, LLM, email, almacenamiento).

Environment & Providers
El comportamiento se controla principalmente desde backend/.env:

LLM_PROVIDER=ollama | anthropic
EMBEDDING_PROVIDER=ollama | openai
DEV_AUTH_STUB=true → desactiva Supabase para desarrollo rápido
LOCAL_STORAGE_DIR=./storage

Cuando se use Anthropic u OpenAI, deben estar configuradas las API keys correspondientes.
Notes for Claude

Este es un proyecto serio con fuerte enfoque en privacidad, cumplimiento normativo y fiabilidad.
Prefiero soluciones pragmáticas y mantenibles antes que sobre-ingeniería.
Cuando propongas cambios de arquitectura o refactoring, ten en cuenta el principio de "local-first" y graceful degradation.
Hay buena documentación en la carpeta docs/. Consúltala cuando sea relevante.
MANTÉN ACTUALIZADO docs/ARQUITECTURA.html: cada vez que cambies la arquitectura
(endpoints, servicios, proveedores, tablas, flujos), refleja el cambio en ese
HTML en el mismo commit. Es el mapa vivo de la plataforma para Antonio.