# Lol-AI-lo

Document generation and review platform for European VC *fund servicers*. Fund clients (in-house counsel / fund managers) request corporate and fund documents in natural language; the platform generates them from each gestora's own precedents (RAG) and, optionally, routes them to external counsel for validation before delivery.

**Local-first by default.** The LLM and embeddings run *on your machine* via [Ollama](https://ollama.com) — no precedent text or client data leaves the host. Cloud providers (Anthropic / OpenAI) are available as an opt-in fallback. This matters for legal work: confidentiality and the project's GDPR posture both favour keeping documents local. See [docs/LOCAL_MODELS.md](docs/LOCAL_MODELS.md).

> Full product spec: [docs/SPEC.md](docs/SPEC.md) · Security: [docs/SECURITY.md](docs/SECURITY.md) · GDPR: [docs/GDPR.md](docs/GDPR.md)

## Architecture

| Layer | Default (local-first) | Cloud option |
|------|------------------------|--------------|
| Frontend | Next.js 14 (App Router) + Tailwind CSS | — |
| Backend | Python + FastAPI (`uvicorn main:app`) | — |
| **LLM** (intake parsing + generation) | **Ollama, local** — `qwen2.5:14b-instruct` | Anthropic Claude |
| **Embeddings** (RAG) | **Ollama, local** — `bge-m3` (multilingual) | OpenAI `text-embedding-3-small` |
| Auth / DB | Supabase (PostgreSQL) — *or* dev-stub, no DB | — |
| Precedent storage | Local filesystem (`./storage`) | Google Drive |
| Doc generation / redline | python-docx (redline author: "Lol-AI-lo AI") | — |
| Email | Console log (fallback) | Resend |

## Golden rule

**Per-gestora isolation is inviolable.** Precedents, documents and data are siloed by `gestora_id` on every query (Supabase RLS + a hard pre-filter in the RAG layer). The audit log is append-only at the database level.

---

## Quick start — fully local on a Mac (the headline path)

Runs the whole platform on your machine with **no cloud keys and no database**.

**1. Install and start Ollama** (native — never in Docker on macOS, see [below](#run-with-docker-compose)):

```bash
brew install ollama        # or download the app from ollama.com
ollama serve               # leave this running (or use the menu-bar app)
```

**2. Pull the local models** (generation + embeddings):

```bash
ollama pull qwen2.5:14b-instruct   # ~9 GB. On a tight 16 GB box, qwen2.5:7b-instruct is the safe default.
ollama pull bge-m3                 # multilingual embeddings (ES/EN/FR/DE)
```

**3. Configure env** — copy `.env.example` to both locations and enable the no-database demo mode:

```bash
cp .env.example backend/.env
cp .env.example frontend/.env.local
```

In `backend/.env` make sure these are set (they are the defaults the backend ships with):

```dotenv
LLM_PROVIDER=ollama
EMBEDDING_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_LLM_MODEL=qwen2.5:14b-instruct
OLLAMA_EMBED_MODEL=bge-m3
OLLAMA_TIMEOUT_SECONDS=600
DEV_AUTH_STUB=true          # no Supabase needed; auth runs in dev-stub mode
LOCAL_STORAGE_DIR=./storage # precedents on local disk (no Google Drive needed)
```

`frontend/.env.local` only needs `NEXT_PUBLIC_API_URL=http://localhost:8000`.

**4. Backend** (FastAPI):

```bash
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**5. Frontend** (Next.js):

```bash
cd frontend
npm install
npm run dev
```

**6. Open** http://localhost:3000. Check service readiness any time at http://localhost:8000/health.

That's it — generation runs against your local Ollama, RAG embeds with `bge-m3`, documents are written to `./storage`, emails are logged to the console, and no Supabase project is required.

---

## Run with Docker Compose

The stack (`backend` + `frontend`, optional `db`) builds from [`docker-compose.yml`](docker-compose.yml) and reads a root-level `.env`.

> **Apple Silicon caveat — keep Ollama OUT of Docker.** Containers on macOS run in a Linux VM with **no access to the Metal GPU**, so an Ollama container would be CPU-only and unusably slow. Run Ollama **natively** on the host (steps 1–2 above). The backend container reaches it through `host.docker.internal` — the compose file already sets `OLLAMA_BASE_URL=http://host.docker.internal:11434` and `extra_hosts: ["host.docker.internal:host-gateway"]` for you.

```bash
cp .env.example .env       # root .env consumed by docker compose (set DEV_AUTH_STUB=true for the no-DB demo)
# make sure native Ollama is running:  ollama serve

docker compose up --build  # backend on :8000, frontend on :3000
```

Optional local Postgres (only if you want a real database instead of `DEV_AUTH_STUB`):

```bash
docker compose --profile supabase up --build
```

The `db` service is a **minimal `postgres:16`** that applies the SQL in `supabase/migrations/` on first start — it is *not* full Supabase (no Auth/Storage/Realtime). For the complete local Supabase, use the official CLI instead: `supabase start`.

---

## Switching to cloud providers

Local-first is the default, but you can flip either half to the cloud independently. Set these in `backend/.env`:

```dotenv
# Generation / intake parsing via Anthropic Claude:
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-sonnet-4-20250514

# RAG embeddings via OpenAI:
EMBEDDING_PROVIDER=openai
OPENAI_API_KEY=sk-...
EMBEDDING_MODEL=text-embedding-3-small
```

You can mix and match (e.g. local LLM + OpenAI embeddings, or vice-versa).

---

## Graceful degradation

Every external service is independently toggleable. When something isn't configured, the platform degrades predictably rather than crashing:

| Missing / not configured | Behaviour |
|--------------------------|-----------|
| Ollama not running (and no cloud LLM) | Generation endpoints return **503** with a clear "service not configured/unavailable" message; the rest of the app stays up |
| No embeddings (Ollama down / no OpenAI) | RAG **degrades to deterministic `rag_weight` + recency ranking** — still fully gestora-isolated, never a wider candidate pool |
| No Resend (`RESEND_API_KEY` unset) | Emails are **logged to the console** instead of sent |
| No Google Drive | Precedents use the **local filesystem** (`./storage` / `LOCAL_STORAGE_DIR`) |
| `DEV_AUTH_STUB=true` | **No Supabase needed** — auth runs in dev-stub mode (`X-Dev-User` header) |

## Master workflow

```
Client → Intake form → Parser (LLM) → Parameter confirmation
       → Generation (RAG + LLM + python-docx) → Draft + Redline
       → EXIT A: direct download (mandatory liability checkbox)
       → EXIT B: counsel validation → review → final delivery
                 (validated doc automatically enters the precedent library)
```

With no precedent available (Level 3 fallback), counsel validation is **mandatory** — Exit A is disabled.

## Tests

```bash
cd backend && .venv/bin/pytest tests/
```

Includes the cross-gestora isolation suite (zero-leakage is a hard guardrail).

## Corporate structure

- **Lol-AI-lo SL** — technology entity: operates the platform and bills gestora subscriptions. Never signs legal-services contracts with funds.
- **Lol-AI-lo Legal SLP** — legal entity: signs the legal-services contracts, employs the counsel, and is responsible for delivered documents. All client-facing email is sent from its domain.

## Deployment

- Frontend → Vercel (`frontend/`) or the `frontend` container.
- Backend → Railway / Render or the `backend` container (`uvicorn main:app`). For local LLM in production, point `OLLAMA_BASE_URL` at a GPU host running Ollama.
- DB / Auth → Supabase.

## More docs

- [docs/LOCAL_MODELS.md](docs/LOCAL_MODELS.md) — model recommendations, RAM budgeting, performance tips for Apple Silicon.
- [docs/SPEC.md](docs/SPEC.md) — full product specification.
- [docs/SECURITY.md](docs/SECURITY.md) — security hardening.
- [docs/GDPR.md](docs/GDPR.md) — data-protection posture.
