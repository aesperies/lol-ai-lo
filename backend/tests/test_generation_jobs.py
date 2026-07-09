"""Async generation job tests: 202 + poll-until-done flow, retry with
backoff, final-failure revert, gestora isolation, synchronous guardrails,
startup sweep for jobs orphaned by a deploy/restart."""
from __future__ import annotations

import pytest

from services import generator, jobs
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


class TestStartupSweep:
    """Orphaned-job recovery (docs/ESCALADO.md §3): a Railway deploy/restart
    mid-generation must not leave the request stuck in 'generating'."""

    def _strand(self, wf, db, user=None, fund=None, job_status: str = "running") -> str:
        """Simulate a process killed mid-generation: request in 'generating'
        with a queued/running job row and no live asyncio task."""
        request_id = wf.create(user, fund)
        wf.parse(request_id, user)
        wf.confirm(request_id, user)
        db.update("requests", request_id, {"status": "generating"})
        db.insert(
            "generation_jobs",
            {
                "request_id": request_id,
                "status": job_status,
                "attempts": 1,
                "max_attempts": 3,
                "last_error": None,
                "started_at": "2026-07-09T00:00:00+00:00",
                "finished_at": None,
            },
        )
        return request_id

    def test_sweep_recovers_stuck_request(self, wf, client, db, seed):
        request_id = self._strand(wf, db)

        assert jobs.sweep_orphaned_jobs(db) == 1

        job = jobs_for(db, request_id)[-1]
        assert job["status"] == "failed"
        assert "reinició" in job["last_error"]
        assert job["finished_at"] is not None
        assert request_status(db, request_id) == "confirmed"

        # Owner notified in-app (kind generation_failed), gestora-scoped.
        notes = db.select("notifications", user_id=seed["client_a"]["id"])
        assert [n["kind"] for n in notes] == ["generation_failed"]
        assert notes[0]["request_id"] == request_id
        assert notes[0]["gestora_id"] == seed["gestora_a"]["id"]

        # Audited as a failed generation by the system (no acting user).
        orphaned = [
            row
            for row in db.unscoped_select("audit_log", action="document_generated")
            if (row.get("metadata") or {}).get("orphaned")
        ]
        assert len(orphaned) == 1
        assert orphaned[0]["resource_id"] == request_id
        assert orphaned[0]["user_id"] is None
        assert orphaned[0]["gestora_id"] == seed["gestora_a"]["id"]

        # And the request is re-runnable end to end.
        assert wf.generate(request_id).status_code == 202
        assert wf.wait_for_job(request_id)["status"] == "succeeded"
        assert request_status(db, request_id) == "review_pending"

    def test_sweep_runs_on_app_startup(self, wf, client, db, seed):
        from fastapi.testclient import TestClient

        from main import app

        request_id = self._strand(wf, db)
        with TestClient(app):  # lifespan startup runs the sweep
            pass
        assert jobs_for(db, request_id)[-1]["status"] == "failed"
        assert request_status(db, request_id) == "confirmed"

    def test_sweep_skips_finished_jobs_and_isolates_notifications(self, wf, client, db, seed):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        done_id, _ = wf.to_review_pending()
        stuck_b = self._strand(wf, db, seed["client_b"], seed["fund_b"], job_status="queued")

        assert jobs.sweep_orphaned_jobs(db) == 1

        # The finished job/request are untouched.
        assert jobs_for(db, done_id)[-1]["status"] == "succeeded"
        assert request_status(db, done_id) == "review_pending"
        assert request_status(db, stuck_b) == "confirmed"
        # Only gestora B's owner is notified, under gestora B's id.
        assert db.select("notifications", user_id=seed["client_a"]["id"]) == []
        notes_b = db.select("notifications", user_id=seed["client_b"]["id"])
        assert [n["kind"] for n in notes_b] == ["generation_failed"]
        assert notes_b[0]["gestora_id"] == seed["gestora_b"]["id"]


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
