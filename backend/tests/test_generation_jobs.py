"""Async generation job tests: 202 + poll-until-done flow, retry with
backoff, final-failure revert, gestora isolation, synchronous guardrails."""
from __future__ import annotations

import pytest

from services import generator
from tests.conftest import auth, seed_precedent


def jobs_for(db, request_id: str) -> list[dict]:
    return db.select("generation_jobs", request_id=request_id)


def request_status(db, request_id: str) -> str:
    return db.get("requests", request_id)["status"]


class TestHappyPath:
    def test_generate_enqueues_and_succeeds(self, wf, client, db, seed):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA ACTA")
        request_id = wf.create()
        wf.parse(request_id)
        wf.confirm(request_id)

        response = wf.generate(request_id)
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["status"] == "queued"
        assert body["job_id"]
        # Status flips to 'generating' synchronously, before the job runs.
        assert request_status(db, request_id) in ("generating", "review_pending")

        job = wf.wait_for_job(request_id)
        assert job["status"] == "succeeded"
        assert job["attempts"] == 1
        assert job["last_error"] is None

        # Pipeline continued exactly as before: documents + status.
        assert request_status(db, request_id) == "review_pending"
        assert db.select("documents", request_id=request_id, version_type="draft")
        assert db.select("documents", request_id=request_id, version_type="redline")
        persisted = jobs_for(db, request_id)[-1]
        assert persisted["started_at"] is not None
        assert persisted["finished_at"] is not None


class TestRetries:
    def test_transient_failure_then_success(self, wf, client, db, seed, monkeypatch):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        original = generator.generate_document
        calls = {"n": 0}

        def flaky(**kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("anthropic timeout (simulated)")
            return original(**kwargs)

        monkeypatch.setattr(generator, "generate_document", flaky)

        request_id = wf.create()
        wf.parse(request_id)
        wf.confirm(request_id)
        assert wf.generate(request_id).status_code == 202

        job = wf.wait_for_job(request_id)
        assert job["status"] == "succeeded"
        assert job["attempts"] == 2
        assert "simulated" in job["last_error"]
        assert request_status(db, request_id) == "review_pending"

    def test_final_failure_reverts_to_confirmed(self, wf, client, db, seed):
        def always_fails(**kwargs):
            raise RuntimeError("permanent failure (simulated)")

        request_id = wf.create()
        wf.parse(request_id)
        wf.confirm(request_id)

        # Dedicated patch context so undoing it keeps the fake_llm patches.
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(generator, "generate_document", always_fails)
            assert wf.generate(request_id).status_code == 202
            job = wf.wait_for_job(request_id)

        assert job["status"] == "failed"
        assert job["attempts"] == 3  # max_attempts
        assert "permanent failure" in job["last_error"]

        # Request reverted so the client can retry generation.
        assert request_status(db, request_id) == "confirmed"
        # Audit trail: document_generated with failed=true metadata.
        failures = [
            row
            for row in db.unscoped_select("audit_log", action="document_generated")
            if (row.get("metadata") or {}).get("failed")
        ]
        assert len(failures) == 1
        assert "permanent failure" in failures[0]["metadata"]["error"]
        assert failures[0]["resource_id"] == request_id

        # And the request is re-runnable: a new job succeeds.
        assert wf.generate(request_id).status_code == 202
        assert wf.wait_for_job(request_id)["status"] == "succeeded"
        assert request_status(db, request_id) == "review_pending"


class TestIsolationAndGuardrails:
    def test_job_status_blocked_cross_gestora(self, wf, client, db, seed):
        request_id, _ = wf.to_review_pending()
        response = client.get(
            f"/api/requests/{request_id}/generation-job", headers=auth(seed["client_b"])
        )
        assert response.status_code == 404
        assert wf.job_status(request_id).status_code == 200
        # Counsel/admin are cross-gestora by design.
        assert wf.job_status(request_id, seed["counsel"]).status_code == 200

    def test_guardrails_rejected_synchronously_before_any_job(self, wf, client, db, seed, monkeypatch):
        import config

        # Unconfirmed request -> 409, no job row created.
        request_id = wf.create()
        assert wf.generate(request_id).status_code == 409
        wf.parse(request_id)
        assert wf.generate(request_id).status_code == 409
        assert jobs_for(db, request_id) == []

        # Selected LLM provider unconfigured -> 503, status untouched, no job
        # row. (Default ollama is always configured; switch to the cloud
        # provider with no key to exercise the fail-fast gate.)
        wf.confirm(request_id)
        monkeypatch.setattr(config.get_settings(), "llm_provider", "anthropic")
        monkeypatch.setattr(config.get_settings(), "anthropic_api_key", "")
        assert wf.generate(request_id).status_code == 503
        assert request_status(db, request_id) == "confirmed"
        assert jobs_for(db, request_id) == []

    def test_no_job_yet_returns_404(self, wf, client, db, seed):
        request_id = wf.create()
        assert wf.job_status(request_id).status_code == 404
