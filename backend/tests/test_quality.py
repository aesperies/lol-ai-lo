"""Quality metric tests (improvement #6): draft→validated edit distance,
Exit A/B persistence hooks, never-blocking failures and the admin report."""
from __future__ import annotations

from typing import Any

import pytest

from services import quality
from tests.conftest import DOC_TYPE, auth, seed_precedent


def to_counsel_review(wf, client, seed) -> str:
    request_id, _ = wf.to_review_pending()
    response = client.post(f"/api/requests/{request_id}/exit-b", headers=auth(seed["client_a"]))
    assert response.status_code == 200, response.text
    return request_id


class TestComputeQualityMetric:
    def test_identical_texts_score_one(self):
        # Whitespace and casing differences are normalized away.
        metric = quality.compute_quality_metric("Hola   mundo  legal\n", "hola mundo LEGAL")
        assert metric["similarity"] == 1.0
        assert metric["words_changed"] == 0
        assert metric["chars_draft"] == metric["chars_final"]

    def test_small_edit_in_expected_range(self):
        draft = (
            "El plazo de preaviso será de diez días naturales a contar desde "
            "la fecha de la notificación fehaciente a la otra parte."
        )
        final = draft.replace("diez", "quince")
        metric = quality.compute_quality_metric(draft, final)
        assert 0.8 < metric["similarity"] < 1.0
        assert metric["words_changed"] > 0
        assert metric["chars_draft"] != metric["chars_final"]


class TestExitBMetric:
    def test_validation_with_counsel_edit_creates_metric_row(self, wf, client, db, seed):
        request_id = to_counsel_review(wf, client, seed)
        edit = client.post(
            f"/api/requests/{request_id}/counsel/edit",
            json={"text": "ACTA DE REUNIÓN DEL CONSEJO\nTexto íntegramente revisado por el abogado."},
            headers=auth(seed["counsel"]),
        )
        assert edit.status_code == 200
        assert client.post(f"/api/requests/{request_id}/validate", headers=auth(seed["counsel"])).status_code == 200

        metrics = db.select("quality_metrics", request_id=request_id)
        assert len(metrics) == 1
        metric = metrics[0]
        assert metric["doc_type"] == DOC_TYPE
        assert metric["gestora_id"] == seed["gestora_a"]["id"]
        assert metric["language"] == "es"
        assert 0.0 <= metric["similarity"] < 1.0
        assert metric["words_changed"] > 0
        assert metric["refinements_used"] == 0
        assert metric["fallback_level"] == 3  # no precedents seeded -> Level 3
        assert metric["draft_iteration"] == 0

    def test_validation_without_edit_scores_one(self, wf, client, db, seed):
        # Counsel validated the AI draft untouched: the final IS the draft.
        request_id = to_counsel_review(wf, client, seed)
        assert client.post(f"/api/requests/{request_id}/validate", headers=auth(seed["counsel"])).status_code == 200
        metric = db.select("quality_metrics", request_id=request_id)[0]
        assert metric["similarity"] == 1.0
        assert metric["words_changed"] == 0

    def test_metric_failure_never_blocks_validation(self, wf, client, db, seed, monkeypatch):
        request_id = to_counsel_review(wf, client, seed)

        def boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
            raise RuntimeError("metric computation exploded")

        monkeypatch.setattr(quality, "compute_quality_metric", boom)
        response = client.post(f"/api/requests/{request_id}/validate", headers=auth(seed["counsel"]))
        assert response.status_code == 200
        assert response.json()["status"] == "validated"
        assert db.select("quality_metrics", request_id=request_id) == []


class TestExitAMetric:
    def test_exit_a_download_records_similarity_one(self, wf, client, db, seed):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], text="PRECEDENTE ALFA ACTA")
        request_id, _ = wf.to_review_pending()
        headers = auth(seed["client_a"])

        assert (
            client.post(
                f"/api/requests/{request_id}/exit-a/acknowledge", json={"acknowledged": True}, headers=headers
            ).status_code
            == 200
        )
        assert client.post(f"/api/requests/{request_id}/exit-a/download", headers=headers).status_code == 200

        metrics = db.select("quality_metrics", request_id=request_id)
        assert len(metrics) == 1
        metric = metrics[0]
        assert metric["similarity"] == 1.0
        assert metric["words_changed"] == 0
        assert metric["chars_draft"] == metric["chars_final"]
        assert metric["fallback_level"] == 0
        assert metric["doc_type"] == DOC_TYPE


class TestQualityEndpoint:
    def test_admin_only(self, client, seed):
        for user in (seed["client_a"], seed["counsel"]):
            assert client.get("/api/admin/quality", headers=auth(user)).status_code == 403
        assert client.get("/api/admin/quality", headers=auth(seed["admin"])).status_code == 200

    @pytest.fixture()
    def seeded_metrics(self, db, seed) -> dict[str, Any]:
        """Three metric rows: NDA exit A + NDA exit B (gestora A), Acta exit B
        (gestora B)."""

        def make_request(fund: dict, user: dict, doc_type: str, exit_a: bool) -> dict[str, Any]:
            return db.insert(
                "requests",
                {
                    "fund_id": fund["id"],
                    "user_id": user["id"],
                    "doc_type": doc_type,
                    "freetext": "x" * 60,
                    "language": "es",
                    "status": "delivered",
                    "requires_counsel": not exit_a,
                    "exit_a_acknowledged_at": "2026-06-01T10:00:00+00:00" if exit_a else None,
                },
            )

        def make_metric(request: dict, gestora: dict, similarity: float, refinements: int) -> dict[str, Any]:
            return db.insert(
                "quality_metrics",
                {
                    "request_id": request["id"],
                    "gestora_id": gestora["id"],
                    "doc_type": request["doc_type"],
                    "language": "es",
                    "draft_iteration": 0,
                    "similarity": similarity,
                    "chars_draft": 1000,
                    "chars_final": 1000,
                    "words_changed": 0,
                    "refinements_used": refinements,
                    "fallback_level": 0,
                },
            )

        nda = "NDA / Acuerdo de Confidencialidad"
        r1 = make_request(seed["fund_a"], seed["client_a"], nda, exit_a=True)
        r2 = make_request(seed["fund_a"], seed["client_a"], nda, exit_a=False)
        r3 = make_request(seed["fund_b"], seed["client_b"], DOC_TYPE, exit_a=False)
        make_metric(r1, seed["gestora_a"], 1.0, 0)
        make_metric(r2, seed["gestora_a"], 0.8, 2)
        make_metric(r3, seed["gestora_b"], 0.9, 1)
        return {"nda": nda}

    def test_aggregation_math(self, client, seed, seeded_metrics):
        report = client.get("/api/admin/quality", headers=auth(seed["admin"])).json()

        overall = report["overall"]
        assert overall["count"] == 3
        assert overall["avg_similarity"] == pytest.approx(0.9, abs=1e-3)
        assert overall["avg_refinements"] == pytest.approx(1.0)
        assert overall["pct_accepted_as_is"] == pytest.approx(1 / 3, abs=1e-3)
        assert overall["pct_validated"] == pytest.approx(2 / 3, abs=1e-3)

        nda_row = next(r for r in report["by_doc_type"] if r["doc_type"] == seeded_metrics["nda"])
        assert nda_row["count"] == 2
        assert nda_row["avg_similarity"] == pytest.approx(0.9, abs=1e-3)
        assert nda_row["pct_accepted_as_is"] == pytest.approx(0.5)

        gestora_a_row = next(
            r for r in report["by_gestora"] if r["gestora_id"] == seed["gestora_a"]["id"]
        )
        assert gestora_a_row["count"] == 2
        assert gestora_a_row["gestora_name"] == seed["gestora_a"]["name"]

    def test_filters(self, client, seed, seeded_metrics):
        headers = auth(seed["admin"])
        by_gestora = client.get(
            f"/api/admin/quality?gestora_id={seed['gestora_a']['id']}", headers=headers
        ).json()
        assert by_gestora["overall"]["count"] == 2

        by_doc_type = client.get(
            f"/api/admin/quality?doc_type={seeded_metrics['nda']}", headers=headers
        ).json()
        assert by_doc_type["overall"]["count"] == 2
        assert by_doc_type["by_gestora"][0]["gestora_id"] == seed["gestora_a"]["id"]
