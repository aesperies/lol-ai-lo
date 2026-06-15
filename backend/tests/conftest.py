"""Test fixtures.

The suite runs WITHOUT heavy deps or external services:
- DEV_AUTH_STUB=true -> in-memory store + X-Dev-User auth
- LLM calls are monkeypatched (fake_llm fixture)
- storage goes to a temp directory
Environment is pinned BEFORE any backend module is imported.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

# --- environment must be set before backend imports -----------------------
os.environ["DEV_AUTH_STUB"] = "true"
os.environ["LOCAL_STORAGE_DIR"] = tempfile.mkdtemp(prefix="lolailo-test-storage-")
os.environ["JOB_BACKOFF_BASE"] = "0"  # instant generation-job retries in tests
for _var in (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "RESEND_API_KEY",
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "GOOGLE_SERVICE_ACCOUNT_FILE",
):
    os.environ[_var] = ""

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import pytest
from fastapi.testclient import TestClient

import config
from models.schema import LEVEL3_WARNING, SLP_DISCLAIMER, PrecedentVersionStatus
from services import db as dbmod
from services import docx_renderer, generator, intake_parser, llm, storage

config.get_settings.cache_clear()


@pytest.fixture(autouse=True)
def _no_llm_network(monkeypatch: pytest.MonkeyPatch):
    """Default test mode runs the local-first (ollama) provider, but no real
    daemon exists in CI. Simulate an unreachable daemon at the HTTP layer so:

    - RAG embeddings degrade to weight/recency ranking (the existing isolation
      invariant — never a wider candidate pool), exactly as they did when
      OpenAI was unconfigured before this refactor;
    - any unmocked text-generation call surfaces a ServiceNotConfiguredError
      (503) rather than silently reaching the network.

    Tests that exercise the seam (test_llm_provider) override ``httpx.post``
    per-test; the workflow tests mock the public ``generator``/``intake_parser``
    seams via ``fake_llm`` so they never reach this layer for generation.
    ``llm.httpx`` IS the httpx module, so this also covers rag.py's usage."""

    def _unreachable(*_args, **_kwargs):
        raise llm.httpx.ConnectError("no ollama daemon in tests")

    monkeypatch.setattr(llm.httpx, "post", _unreachable)

FREETEXT = (
    "Necesito un acta de reunión del consejo de administración aprobando una "
    "llamada de capital del fondo por importe de 500.000 euros con fecha 15 de julio de 2026."
)
DOC_TYPE = "Acta de Reunión del Consejo"


@pytest.fixture()
def db() -> dbmod.DevStore:
    return dbmod.reset_dev_store()


@pytest.fixture()
def client(db: dbmod.DevStore):
    from main import app

    # Context-managed so all requests share one event loop and in-process
    # generation jobs (asyncio tasks) keep running between requests.
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def seed(db: dbmod.DevStore) -> dict[str, Any]:
    """Two fully separate gestoras + shared counsel/admin users."""
    gestora_a = db.insert("gestoras", {"name": "Gestora Alfa", "subscription_tier": "growth"})
    gestora_b = db.insert("gestoras", {"name": "Gestora Beta", "subscription_tier": "starter"})
    fund_a = db.insert("funds", {"gestora_id": gestora_a["id"], "name": "Alfa Fund I", "jurisdiction": "España"})
    fund_b = db.insert("funds", {"gestora_id": gestora_b["id"], "name": "Beta Fund I", "jurisdiction": "España"})
    client_a = db.insert("users", {"email": "clienta@alfa.es", "role": "client", "gestora_id": gestora_a["id"]})
    client_b = db.insert("users", {"email": "clientb@beta.es", "role": "client", "gestora_id": gestora_b["id"]})
    counsel = db.insert("users", {"email": "abogado@lolailolegal.es", "role": "counsel", "gestora_id": None})
    admin = db.insert("users", {"email": "admin@lolailo.es", "role": "admin", "gestora_id": None})
    return {
        "gestora_a": gestora_a,
        "gestora_b": gestora_b,
        "fund_a": fund_a,
        "fund_b": fund_b,
        "client_a": client_a,
        "client_b": client_b,
        "counsel": counsel,
        "admin": admin,
    }


def auth(user: dict[str, Any]) -> dict[str, str]:
    return {"X-Dev-User": user["id"]}


@pytest.fixture()
def anthropic_on(monkeypatch: pytest.MonkeyPatch):
    """Make settings report Anthropic as configured (calls are monkeypatched)."""
    monkeypatch.setattr(config.get_settings(), "anthropic_api_key", "test-key-not-real")


@pytest.fixture()
def fake_llm(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Deterministic stand-ins for the Claude calls. Mutate the returned state
    dict to steer behavior (missing markers, low confidence...)."""
    state: dict[str, Any] = {"missing": False, "ready": True, "confidence": 0.95}

    def fake_parse(
        doc_type: str, freetext: str, structured_fields: dict | None = None
    ) -> dict[str, Any]:
        return {
            "language": "es",
            "doc_type_confirmed": doc_type,
            "parties": [{"role": "fondo", "name": "Alfa Fund I"}],
            "key_dates": [{"label": "fecha de reunión", "date": "2026-07-15"}],
            "jurisdiction": "España",
            "governing_law": "Derecho español",
            "key_terms": [{"field": "importe", "value": "500.000 EUR"}],
            "summary": "Acta de consejo aprobando una llamada de capital.",
            "confidence": state["confidence"],
            "unclear_fields": [] if state["ready"] else ["fecha"],
            "generation_ready": state["ready"],
        }

    def fake_generate(**kwargs: Any) -> str:
        lines = [
            "ACTA DE REUNIÓN DEL CONSEJO",
            f"Fondo: {kwargs['fund_name']}.",
            "Se aprueba la llamada de capital por importe de 500.000 euros.",
            "El consejo aprueba por unanimidad los acuerdos anteriores.",
        ]
        if state["missing"]:
            lines.append("Fecha de la reunión: [MISSING: fecha de la reunión]")
        return "\n".join(lines) + "\n\n" + SLP_DISCLAIMER

    monkeypatch.setattr(intake_parser, "parse_intake", fake_parse)
    monkeypatch.setattr(generator, "generate_document", fake_generate)
    return state


def seed_precedent(
    db: dbmod.DevStore,
    *,
    gestora_id: str | None,
    doc_type: str = DOC_TYPE,
    language: str = "es",
    text: str = "TEXTO DE PRECEDENTE",
    source: str = "manual_upload",
    status: str = PrecedentVersionStatus.active.value,
    extension: str = ".docx",
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Insert a precedent + stored version file, returning (precedent, version)."""
    precedent = db.insert(
        "precedents",
        {"gestora_id": gestora_id, "fund_id": None, "doc_type": doc_type, "language": language, "source": source},
    )
    data = docx_renderer.render_docx(text) if extension == ".docx" else text.encode("utf-8")
    prefix = f"gestoras/{gestora_id}/precedents" if gestora_id else f"lol-ai-lo-templates/{source}/{language}"
    key = storage.save(f"{prefix}/{precedent['id']}-v1{extension}", data)
    weight = {"active": 1.0, "superseded": 0.3}.get(status, 0.0)
    version = db.insert(
        "precedent_versions",
        {
            "precedent_id": precedent["id"],
            "version_number": 1,
            "file_path": key,
            "status": status,
            "rag_weight": weight,
            "activated_at": "2026-01-01T00:00:00+00:00" if status == "active" else None,
        },
    )
    return precedent, version


@pytest.fixture()
def wf(client: TestClient, seed: dict[str, Any], fake_llm: dict[str, Any], anthropic_on: None):
    """Workflow driver: runs a request through intake -> confirm -> generate."""

    class Workflow:
        def __init__(self) -> None:
            self.client = client
            self.seed = seed
            self.llm = fake_llm

        def create(
            self,
            user: dict | None = None,
            fund: dict | None = None,
            structured_fields: dict | None = None,
        ) -> str:
            payload: dict[str, Any] = {
                "fund_id": (fund or self.seed["fund_a"])["id"],
                "doc_type": DOC_TYPE,
                "freetext": FREETEXT,
            }
            if structured_fields is not None:
                payload["structured_fields"] = structured_fields
            response = self.client.post(
                "/api/requests",
                json=payload,
                headers=auth(user or self.seed["client_a"]),
            )
            assert response.status_code == 201, response.text
            return response.json()["id"]

        def parse(self, request_id: str, user: dict | None = None):
            return self.client.post(
                f"/api/requests/{request_id}/parse", headers=auth(user or self.seed["client_a"])
            )

        def confirm(self, request_id: str, user: dict | None = None, edited: dict | None = None):
            return self.client.post(
                f"/api/requests/{request_id}/confirm",
                json={"parsed_params": edited},
                headers=auth(user or self.seed["client_a"]),
            )

        def generate(self, request_id: str, user: dict | None = None):
            return self.client.post(
                f"/api/requests/{request_id}/generate", headers=auth(user or self.seed["client_a"])
            )

        def job_status(self, request_id: str, user: dict | None = None):
            return self.client.get(
                f"/api/requests/{request_id}/generation-job",
                headers=auth(user or self.seed["client_a"]),
            )

        def wait_for_job(self, request_id: str, user: dict | None = None, timeout: float = 5.0) -> dict:
            """Poll the generation job until it reaches a terminal state."""
            deadline = time.time() + timeout
            while time.time() < deadline:
                response = self.job_status(request_id, user)
                assert response.status_code == 200, response.text
                job = response.json()
                if job["status"] in ("succeeded", "failed"):
                    return job
                time.sleep(0.02)
            raise AssertionError(f"generation job for {request_id} did not finish in {timeout}s")

        def generation_summary(self, request_id: str) -> dict:
            """Mirror of the old synchronous /generate response payload,
            rebuilt from the store now that generation runs as an async job."""
            store = dbmod.get_db()
            row = store.get("requests", request_id)
            drafts = store.select("documents", request_id=request_id, version_type="draft")
            redlines = store.select("documents", request_id=request_id, version_type="redline")
            generated = [
                entry
                for entry in store.select("audit_log", action="document_generated")
                if (entry.get("metadata") or {}).get("request_id") == request_id
            ]
            rag_level = generated[-1]["metadata"]["rag_level"] if generated else None
            return {
                "request": row,
                "draft": drafts[-1] if drafts else None,
                "redline": redlines[-1] if redlines else None,
                "rag_level": rag_level,
                "requires_counsel": row.get("requires_counsel", False),
                "warning": LEVEL3_WARNING if rag_level == 3 else None,
            }

        def to_review_pending(self, user: dict | None = None, fund: dict | None = None) -> tuple[str, dict]:
            request_id = self.create(user, fund)
            assert self.parse(request_id, user).status_code == 200
            assert self.confirm(request_id, user).status_code == 200
            response = self.generate(request_id, user)
            assert response.status_code == 202, response.text
            job = self.wait_for_job(request_id, user)
            assert job["status"] == "succeeded", job
            return request_id, self.generation_summary(request_id)

    return Workflow()
