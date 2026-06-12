"""Iterative refinement tests: happy path with version history, the
max_refinements limit, status gating, the [REFINEMENT-UNCLEAR] path,
cross-gestora isolation and the Exit A [MISSING] re-check on the LATEST
iteration."""
from __future__ import annotations

from typing import Any

import pytest

from services import docx_renderer, generator, storage
from tests.conftest import auth, seed_precedent

INSTRUCTION = "Cambia el plazo de preaviso a 15 días naturales."


@pytest.fixture()
def fake_refine(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Deterministic stand-in for the refinement Claude call. Steer via the
    returned state: 'unclear' returns the verbatim marker; 'transform' maps
    (current_text, instruction) -> revised text."""
    state: dict[str, Any] = {
        "unclear": None,
        "transform": lambda text, instruction: f"{text}\nAJUSTE APLICADO: {instruction}",
        "calls": 0,
    }

    def fake(*, current_text: str, instruction: str) -> str:
        state["calls"] += 1
        if state["unclear"]:
            return f"[REFINEMENT-UNCLEAR: {state['unclear']}]"
        return state["transform"](current_text, instruction)

    monkeypatch.setattr(generator, "refine_document", fake)
    return state


def refine(wf, request_id: str, instruction: str = INSTRUCTION, user: dict | None = None):
    return wf.client.post(
        f"/api/requests/{request_id}/refinements",
        json={"instruction": instruction},
        headers=auth(user or wf.seed["client_a"]),
    )


def history(wf, request_id: str, user: dict | None = None):
    return wf.client.get(
        f"/api/requests/{request_id}/refinements",
        headers=auth(user or wf.seed["client_a"]),
    )


def download_text(wf, request_id: str, version_type: str = "draft", iteration: int | None = None) -> str:
    url = f"/api/requests/{request_id}/documents/{version_type}/download"
    if iteration is not None:
        url += f"?iteration={iteration}"
    response = wf.client.get(url, headers=auth(wf.seed["client_a"]))
    assert response.status_code == 200, response.text
    return docx_renderer.extract_text(response.content)


class TestHappyPath:
    def test_refine_creates_new_iteration_with_history(self, wf, client, db, seed, fake_refine):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA ACTA")
        request_id, _ = wf.to_review_pending()

        response = refine(wf, request_id)
        assert response.status_code == 202, response.text
        body = response.json()
        assert body["refinement_id"] and body["job_id"]
        assert body["iteration"] == 1
        # Refinement runs as an async generation job: status flips synchronously.
        assert db.get("requests", request_id)["status"] in ("generating", "review_pending")

        job = wf.wait_for_job(request_id)
        assert job["status"] == "succeeded"
        assert db.get("requests", request_id)["status"] == "review_pending"

        # New draft + redline documents exist at iteration 1; iteration 0 intact.
        drafts = db.select("documents", request_id=request_id, version_type="draft")
        redlines = db.select("documents", request_id=request_id, version_type="redline")
        assert sorted(d["iteration"] for d in drafts) == [0, 1]
        assert sorted(r["iteration"] for r in redlines) == [0, 1]
        # Redline vs the SAME original precedent base.
        base_id = drafts[0]["precedent_version_id"]
        assert base_id is not None
        assert all(d["precedent_version_id"] == base_id for d in drafts + redlines)

        # History shows the applied refinement.
        rows = history(wf, request_id).json()
        assert len(rows) == 1
        assert rows[0]["status"] == "applied"
        assert rows[0]["iteration"] == 1
        assert rows[0]["instruction"] == INSTRUCTION
        assert rows[0]["applied_at"] is not None
        assert rows[0]["error"] is None

        # Downloads serve the LATEST iteration by default; ?iteration=0 the original.
        assert "AJUSTE APLICADO" in download_text(wf, request_id)
        assert "AJUSTE APLICADO" not in download_text(wf, request_id, iteration=0)
        # HTML viewer follows the same contract.
        html_latest = client.get(
            f"/api/requests/{request_id}/documents/draft/html", headers=auth(seed["client_a"])
        )
        html_v0 = client.get(
            f"/api/requests/{request_id}/documents/draft/html?iteration=0",
            headers=auth(seed["client_a"]),
        )
        assert "AJUSTE APLICADO" in html_latest.json()["html"]
        assert "AJUSTE APLICADO" not in html_v0.json()["html"]

        # Audit: document_generated/redline_generated with refinement metadata.
        generated = [
            row
            for row in db.select("audit_log", action="document_generated")
            if (row.get("metadata") or {}).get("refinement")
        ]
        assert len(generated) == 1
        assert generated[0]["metadata"]["iteration"] == 1
        assert generated[0]["metadata"]["instruction"] == INSTRUCTION
        redlined = [
            row
            for row in db.select("audit_log", action="redline_generated")
            if (row.get("metadata") or {}).get("refinement")
        ]
        assert len(redlined) == 1
        # Usage: original generation + one billable refinement generation.
        generated_events = db.select("usage_events", event_type="document_generated")
        assert len(generated_events) == 2

    def test_failed_job_keeps_previous_draft_and_reverts_to_review_pending(
        self, wf, client, db, seed, fake_refine, monkeypatch
    ):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        request_id, _ = wf.to_review_pending()

        def always_fails(**kwargs):
            raise RuntimeError("anthropic permanently down (simulated)")

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(generator, "refine_document", always_fails)
            assert refine(wf, request_id).status_code == 202
            job = wf.wait_for_job(request_id)

        assert job["status"] == "failed"
        # NOT 'confirmed': the previous draft is still valid.
        assert db.get("requests", request_id)["status"] == "review_pending"
        rows = history(wf, request_id).json()
        assert rows[0]["status"] == "failed"
        assert "simulated" in rows[0]["error"]
        # No new iteration was created.
        drafts = db.select("documents", request_id=request_id, version_type="draft")
        assert [d["iteration"] for d in drafts] == [0]


class TestLimitAndStatusGating:
    def test_limit_of_three_refinements_enforced(self, wf, client, db, seed, fake_refine):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        request_id, _ = wf.to_review_pending()

        for n in (1, 2, 3):
            response = refine(wf, request_id, f"Ajuste número {n} del documento.")
            assert response.status_code == 202, response.text
            assert wf.wait_for_job(request_id)["status"] == "succeeded"

        fourth = refine(wf, request_id, "Un cuarto ajuste que debe ser rechazado.")
        assert fourth.status_code == 409
        detail = fourth.json()["detail"]
        assert "3" in detail
        assert "Solicitar Validación" in detail  # directs the client to Exit B

        rows = history(wf, request_id).json()
        assert [r["iteration"] for r in rows] == [1, 2, 3]
        assert all(r["status"] == "applied" for r in rows)

    def test_only_allowed_in_review_pending(self, wf, client, db, seed, fake_refine):
        # Before generation.
        request_id = wf.create()
        assert refine(wf, request_id).status_code == 409
        # After Exit B (counsel review).
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        request_id, _ = wf.to_review_pending()
        client.post(f"/api/requests/{request_id}/exit-b", headers=auth(seed["client_a"]))
        assert refine(wf, request_id).status_code == 409

    def test_instruction_length_validated(self, wf, client, db, seed, fake_refine):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        request_id, _ = wf.to_review_pending()
        assert refine(wf, request_id, "abc").status_code == 422
        assert refine(wf, request_id, "x" * 1001).status_code == 422

    def test_503_when_anthropic_unconfigured_leaves_request_untouched(
        self, wf, client, db, seed, fake_refine, monkeypatch
    ):
        import config

        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        request_id, _ = wf.to_review_pending()
        monkeypatch.setattr(config.get_settings(), "anthropic_api_key", "")
        assert refine(wf, request_id).status_code == 503
        assert db.get("requests", request_id)["status"] == "review_pending"
        assert history(wf, request_id).json() == []


class TestUnclearInstruction:
    def test_unclear_leaves_previous_draft_intact_and_surfaces_reason(
        self, wf, client, db, seed, fake_refine
    ):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        request_id, _ = wf.to_review_pending()
        original_text = download_text(wf, request_id)

        fake_refine["unclear"] = "No queda claro qué plazo debe modificarse"
        assert refine(wf, request_id, "Cambia el plazo a lo que sea razonable.").status_code == 202
        # Handled outcome, not a pipeline error: the job itself succeeds.
        assert wf.wait_for_job(request_id)["status"] == "succeeded"

        # Refinement failed with the surfaced reason; request stays review_pending.
        rows = history(wf, request_id).json()
        assert rows[0]["status"] == "failed"
        assert rows[0]["error"] == "No queda claro qué plazo debe modificarse"
        assert db.get("requests", request_id)["status"] == "review_pending"

        # NO new documents: the previous iteration is intact and still served.
        drafts = db.select("documents", request_id=request_id, version_type="draft")
        assert [d["iteration"] for d in drafts] == [0]
        assert download_text(wf, request_id) == original_text

        # Audit trail records the unclear failure; usage is NOT billed.
        failed = [
            row
            for row in db.select("audit_log", action="document_generated")
            if (row.get("metadata") or {}).get("refinement_failed")
        ]
        assert len(failed) == 1
        assert failed[0]["metadata"]["refinement_failed"] == rows[0]["error"]
        assert len(db.select("usage_events", event_type="document_generated")) == 1

        # A failed refinement does not consume the quota: retry is allowed
        # and gets the next iteration number (numbering gaps by design).
        fake_refine["unclear"] = None
        retry = refine(wf, request_id, "Cambia el plazo de preaviso a 15 días.")
        assert retry.status_code == 202
        assert retry.json()["iteration"] == 2
        assert wf.wait_for_job(request_id)["status"] == "succeeded"
        assert history(wf, request_id).json()[-1]["status"] == "applied"


class TestIsolation:
    def test_cross_gestora_blocked_on_both_endpoints(self, wf, client, db, seed, fake_refine):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        request_id, _ = wf.to_review_pending()
        headers_b = auth(seed["client_b"])
        assert (
            client.post(
                f"/api/requests/{request_id}/refinements",
                json={"instruction": INSTRUCTION},
                headers=headers_b,
            ).status_code
            == 404
        )
        assert (
            client.get(f"/api/requests/{request_id}/refinements", headers=headers_b).status_code
            == 404
        )
        # Counsel/admin read the history cross-gestora by design; refinements
        # themselves are a client action.
        assert history(wf, request_id, seed["counsel"]).status_code == 200
        assert (
            client.post(
                f"/api/requests/{request_id}/refinements",
                json={"instruction": INSTRUCTION},
                headers=auth(seed["counsel"]),
            ).status_code
            == 403
        )

    def test_versioned_downloads_are_siloed(self, wf, client, db, seed, fake_refine):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        request_id, _ = wf.to_review_pending()
        assert refine(wf, request_id).status_code == 202
        wf.wait_for_job(request_id)
        url = f"/api/requests/{request_id}/documents/draft/download?iteration=1"
        assert client.get(url, headers=auth(seed["client_b"])).status_code == 404
        assert client.get(url, headers=auth(seed["client_a"])).status_code == 200


class TestExitAOnLatestIteration:
    def test_missing_check_runs_against_latest_iteration(self, wf, client, db, seed, fake_refine):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        # Original generation carries a [MISSING] marker -> Exit A blocked.
        wf.llm["missing"] = True
        request_id, _ = wf.to_review_pending()
        headers = auth(seed["client_a"])
        blocked = client.post(
            f"/api/requests/{request_id}/exit-a/acknowledge",
            json={"acknowledged": True},
            headers=headers,
        )
        assert blocked.status_code == 409

        # The refinement resolves the [MISSING] field (rule 3 of the prompt).
        fake_refine["transform"] = lambda text, instruction: text.replace(
            "[MISSING: fecha de la reunión]", "15 de julio de 2026"
        )
        assert refine(wf, request_id, "La fecha de la reunión es el 15 de julio de 2026.").status_code == 202
        assert wf.wait_for_job(request_id)["status"] == "succeeded"
        assert "[MISSING:" not in download_text(wf, request_id)

        # Exit A re-check reads the LATEST iteration: now unblocked.
        acknowledged = client.post(
            f"/api/requests/{request_id}/exit-a/acknowledge",
            json={"acknowledged": True},
            headers=headers,
        )
        assert acknowledged.status_code == 200
        download = client.post(f"/api/requests/{request_id}/exit-a/download", headers=headers)
        assert download.status_code == 200
        # The delivered final is the refined iteration.
        finals = db.select("documents", request_id=request_id, version_type="final")
        assert finals[-1]["iteration"] == 1

    def test_refinement_introducing_missing_blocks_exit_a(self, wf, client, db, seed, fake_refine):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        request_id, _ = wf.to_review_pending()
        headers = auth(seed["client_a"])

        fake_refine["transform"] = (
            lambda text, instruction: f"{text}\nNuevo importe: [MISSING: importe revisado]"
        )
        assert refine(wf, request_id, "Actualiza el importe de la llamada de capital.").status_code == 202
        assert wf.wait_for_job(request_id)["status"] == "succeeded"

        blocked = client.post(
            f"/api/requests/{request_id}/exit-a/acknowledge",
            json={"acknowledged": True},
            headers=headers,
        )
        assert blocked.status_code == 409

    def test_counsel_validates_latest_iteration(self, wf, client, db, seed, fake_refine):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA")
        request_id, _ = wf.to_review_pending()
        assert refine(wf, request_id).status_code == 202
        assert wf.wait_for_job(request_id)["status"] == "succeeded"

        client.post(f"/api/requests/{request_id}/exit-b", headers=auth(seed["client_a"]))
        validated = client.post(
            f"/api/requests/{request_id}/validate", headers=auth(seed["counsel"])
        )
        assert validated.status_code == 200
        # The validated final comes from the LATEST draft iteration.
        finals = db.select("documents", request_id=request_id, version_type="final")
        assert finals[-1]["iteration"] == 1
        final_text = docx_renderer.extract_text(storage.read(finals[-1]["file_path"]))
        assert "AJUSTE APLICADO" in final_text
