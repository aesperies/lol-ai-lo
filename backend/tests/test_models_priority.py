"""modelos in RAG: gestora master templates outrank precedents as the base.

A gestora_model (Level 0a) is chosen as the generation base over a regular
precedent (Level 0b) for the same gestora + doc_type, while precedents still
contribute as context. Both levels report level=0 (the silo level). Cross-gestora
isolation of models lives in test_gestora_isolation.py.
"""
from __future__ import annotations

from models.schema import PrecedentSource
from services import rag, storage
from tests.conftest import DOC_TYPE, seed_precedent


def test_model_is_preferred_base_over_precedent(db, seed):
    gestora_id = seed["gestora_a"]["id"]
    _, model_version = seed_precedent(
        db,
        gestora_id=gestora_id,
        source=PrecedentSource.gestora_model.value,
        text="MODELO MAESTRO DE GESTORA ALFA",
    )
    _, precedent_version = seed_precedent(
        db, gestora_id=gestora_id, text="PRECEDENTE NORMAL DE GESTORA ALFA"
    )

    result = rag.retrieve(
        db, gestora_id=gestora_id, doc_type=DOC_TYPE, language="es", query_text="acta"
    )
    # The model is the base; reported at the silo level (0).
    assert result.level == 0
    assert result.base_version_id == model_version["id"]
    assert result.base_version_id != precedent_version["id"]
    assert "MODELO MAESTRO" in result.base_text
    # The precedent still contributes as context (not discarded).
    assert any("PRECEDENTE NORMAL" in text for text in result.context_texts)


def test_model_stored_under_modelos_folder(db, seed):
    gestora_id = seed["gestora_a"]["id"]
    _, version = seed_precedent(
        db,
        gestora_id=gestora_id,
        source=PrecedentSource.gestora_model.value,
        text="MODELO",
    )
    assert version["file_path"].startswith(f"local:{storage.modelos_path(gestora_id, '')}")


def test_precedent_still_used_when_no_model(db, seed):
    gestora_id = seed["gestora_a"]["id"]
    _, precedent_version = seed_precedent(
        db, gestora_id=gestora_id, text="PRECEDENTE SIN MODELO"
    )
    result = rag.retrieve(
        db, gestora_id=gestora_id, doc_type=DOC_TYPE, language="es", query_text="acta"
    )
    assert result.level == 0
    assert result.base_version_id == precedent_version["id"]
    assert "PRECEDENTE SIN MODELO" in result.base_text


def test_admin_can_upload_gestora_model(client, seed):
    from tests.conftest import auth

    docx = b"PK\x03\x04" + b"0" * 64  # passes the magic-byte check
    response = client.post(
        "/api/precedents",
        data={
            "doc_type": DOC_TYPE,
            "language": "es",
            "source": PrecedentSource.gestora_model.value,
            "gestora_id": seed["gestora_a"]["id"],
        },
        files={"file": ("modelo.docx", docx, "application/octet-stream")},
        headers=auth(seed["admin"]),
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["precedent"]["source"] == PrecedentSource.gestora_model.value
    assert body["precedent"]["gestora_id"] == seed["gestora_a"]["id"]
    # Routed to the modelos/ folder.
    assert "/modelos/" in body["version"]["file_path"]


def test_gestora_model_requires_gestora_id(client, seed):
    from tests.conftest import auth

    docx = b"PK\x03\x04" + b"0" * 64
    response = client.post(
        "/api/precedents",
        data={
            "doc_type": DOC_TYPE,
            "language": "es",
            "source": PrecedentSource.gestora_model.value,
        },
        files={"file": ("modelo.docx", docx, "application/octet-stream")},
        headers=auth(seed["admin"]),
    )
    assert response.status_code == 422
