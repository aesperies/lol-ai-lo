"""Chat Q&A sobre el RAG de la gestora (021).

Cubre: retrieval sin doc_type con aislamiento duro por gestora (índice
persistido y fallback por ficheros), el flujo SSE completo del endpoint
(sources → delta* → done), la degradación sin fuentes (sin llamada al LLM),
el fallback de llm.stream para proveedores sin streaming, el grounding de la
verificación y el modelo de acceso no-leak de las conversaciones.
"""
from __future__ import annotations

import json
from typing import Any, Iterator

import pytest

from services import chat as chat_service
from services import db as dbmod
from services import llm, rag
from tests.conftest import auth, seed_precedent

DIM = 1024


def _vector(lead: float) -> list[float]:
    vector = [0.0] * DIM
    vector[0] = lead
    vector[1] = 1.0 - lead
    return vector


def _chunk_row(
    *,
    gestora_id: str | None,
    doc_type: str,
    text: str,
    embed_model: str,
    version_status: str = "active",
    lead: float = 1.0,
) -> dict[str, Any]:
    return {
        "precedent_version_id": f"v-{text}",
        "precedent_id": f"p-{text}",
        "gestora_id": gestora_id,
        "doc_type": doc_type,
        "language": "es",
        "source": "manual_upload",
        "version_status": version_status,
        "is_docx": True,
        "chunk_index": 0,
        "text": text,
        "embed_model": embed_model,
        "embedding": _vector(lead),
    }


def _sse_events(body: str) -> list[dict[str, Any]]:
    return [
        json.loads(line[len("data:"):].strip())
        for line in body.splitlines()
        if line.startswith("data:")
    ]


def _conversation(client, seed, user_key: str = "client_a") -> str:
    response = client.post(
        "/api/chat/conversations", json={}, headers=auth(seed[user_key])
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


# ---------------------------------------------------------------------------
# rag.search_silo — retrieval Q&A sin doc_type
# ---------------------------------------------------------------------------

class TestSearchSilo:
    def test_indexed_path_crosses_doc_types_within_the_silo_only(
        self, db: dbmod.DevStore, monkeypatch: pytest.MonkeyPatch
    ):
        """Sin doc_type: chunks de varios tipos del MISMO silo; jamás de otra
        gestora ni del pool global, y nunca versiones sustituidas."""
        config = llm.resolve_embedding_config(None)
        model = config.resolved_embed_model
        db.insert("precedent_chunks", _chunk_row(
            gestora_id="g-a", doc_type="Acta", text="acta alfa", embed_model=model))
        db.insert("precedent_chunks", _chunk_row(
            gestora_id="g-a", doc_type="Contrato", text="contrato alfa", embed_model=model))
        db.insert("precedent_chunks", _chunk_row(
            gestora_id="g-a", doc_type="Acta", text="acta vieja", embed_model=model,
            version_status="superseded"))
        db.insert("precedent_chunks", _chunk_row(
            gestora_id="g-b", doc_type="Acta", text="acta beta", embed_model=model))
        db.insert("precedent_chunks", _chunk_row(
            gestora_id=None, doc_type="Acta", text="plantilla global", embed_model=model))

        monkeypatch.setattr(rag, "_embed", lambda texts, config: [_vector(1.0)])
        hits = rag.search_silo(db, gestora_id="g-a", language="es", query_text="pregunta")

        texts = {hit.text for hit in hits}
        assert texts == {"acta alfa", "contrato alfa"}
        assert all(hit.precedent_id and hit.precedent_version_id for hit in hits)

    def test_file_fallback_stays_in_the_silo(self, db: dbmod.DevStore):
        """Embeddings caídos (conftest) y sin índice: fallback por ficheros,
        solo el silo de la gestora, con procedencia para las citas."""
        precedent_a, version_a = seed_precedent(
            db, gestora_id="g-a", doc_type="Acta",
            text="El quórum del consejo es de dos tercios.")
        seed_precedent(db, gestora_id="g-b", doc_type="Acta", text="Texto de beta.")

        hits = rag.search_silo(db, gestora_id="g-a", language="es", query_text="quórum")
        assert hits, "el fallback por ficheros debe devolver el precedente del silo"
        assert {hit.precedent_id for hit in hits} == {precedent_a["id"]}
        assert hits[0].precedent_version_id == version_a["id"]
        assert "quórum" in hits[0].text

    def test_empty_silo_returns_no_hits(self, db: dbmod.DevStore):
        assert rag.search_silo(db, gestora_id="g-a", language="es", query_text="x") == []


# ---------------------------------------------------------------------------
# llm.stream — fallback para proveedores sin streaming
# ---------------------------------------------------------------------------

class TestLlmStream:
    def test_provider_without_stream_degrades_to_single_yield(
        self, monkeypatch: pytest.MonkeyPatch
    ):
        class NoStreamProvider:
            name = "fake"

            def complete(self, prompt, *, max_tokens, json_schema, system, config):
                return "respuesta entera"

            def is_configured(self, settings):
                return True

        from services import providers

        monkeypatch.setattr(providers, "get_llm", lambda name: NoStreamProvider())
        assert list(llm.stream("hola")) == ["respuesta entera"]

    def test_streaming_provider_yields_deltas(self, monkeypatch: pytest.MonkeyPatch):
        class StreamingProvider:
            name = "fake"

            def complete(self, prompt, *, max_tokens, json_schema, system, config):
                raise AssertionError("stream() must be preferred")

            def stream(self, prompt, *, max_tokens, system, config) -> Iterator[str]:
                yield "ho"
                yield "la"

            def is_configured(self, settings):
                return True

        from services import providers

        monkeypatch.setattr(providers, "get_llm", lambda name: StreamingProvider())
        assert list(llm.stream("hola")) == ["ho", "la"]


# ---------------------------------------------------------------------------
# Endpoint SSE — flujo completo
# ---------------------------------------------------------------------------

class TestChatEndpoint:
    def test_full_turn_streams_sources_deltas_and_persists(
        self, client, seed, db: dbmod.DevStore, monkeypatch: pytest.MonkeyPatch
    ):
        seed_precedent(
            db, gestora_id=seed["gestora_a"]["id"], doc_type="Acta",
            text="La comisión de gestión es del 2 por ciento anual.")

        def fake_stream(prompt, **kwargs) -> Iterator[str]:
            assert "comisión" in prompt  # el extracto llega al prompt
            yield "La comisión "
            yield "es del 2% [1]."

        monkeypatch.setattr(llm, "stream", fake_stream)

        conversation_id = _conversation(client, seed)
        response = client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            json={"content": "¿Cuál es la comisión de gestión?"},
            headers=auth(seed["client_a"]),
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        events = _sse_events(response.text)
        kinds = [event["type"] for event in events]
        assert kinds[0] == "sources" and kinds[-1] == "done"
        assert kinds.count("delta") == 2
        assert events[0]["citations"], "las citas se emiten antes de generar"
        assert events[0]["citations"][0]["precedent_id"]

        messages = db.select("chat_messages", conversation_id=conversation_id)
        assert [m["role"] for m in messages] == ["user", "assistant"]
        assert messages[1]["content"] == "La comisión es del 2% [1]."
        assert messages[1]["citations"]
        # Auto-título desde la primera pregunta.
        row = db.get("chat_conversations", conversation_id)
        assert row["title"].startswith("¿Cuál es la comisión")

    def test_empty_library_answers_honestly_without_llm(
        self, client, seed, db: dbmod.DevStore, monkeypatch: pytest.MonkeyPatch
    ):
        def must_not_run(*args, **kwargs):
            raise AssertionError("sin fuentes no se llama al LLM")

        monkeypatch.setattr(llm, "stream", must_not_run)

        conversation_id = _conversation(client, seed)
        response = client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            json={"content": "¿Qué dice mi LPA?"},
            headers=auth(seed["client_a"]),
        )
        events = _sse_events(response.text)
        assert events[0] == {"type": "sources", "citations": []}
        assert events[1]["text"] == chat_service.NO_SOURCES_ANSWER
        assert events[-1]["type"] == "done"

    def test_provider_failure_arrives_as_error_event(
        self, client, seed, db: dbmod.DevStore, monkeypatch: pytest.MonkeyPatch
    ):
        seed_precedent(
            db, gestora_id=seed["gestora_a"]["id"], doc_type="Acta", text="Texto alfa.")

        from config import ServiceNotConfiguredError

        def broken_stream(prompt, **kwargs) -> Iterator[str]:
            raise ServiceNotConfiguredError("ollama", "daemon caído")
            yield  # pragma: no cover

        monkeypatch.setattr(llm, "stream", broken_stream)

        conversation_id = _conversation(client, seed)
        response = client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            json={"content": "¿Qué dice el acta?"},
            headers=auth(seed["client_a"]),
        )
        events = _sse_events(response.text)
        assert events[-1]["type"] == "error"
        # El mensaje del asistente NO se persiste en un turno fallido.
        messages = db.select("chat_messages", conversation_id=conversation_id)
        assert [m["role"] for m in messages] == ["user"]


# ---------------------------------------------------------------------------
# Aislamiento y acceso (no-leak)
# ---------------------------------------------------------------------------

class TestChatAccess:
    def test_conversations_are_private_to_their_owner(self, client, seed):
        conversation_id = _conversation(client, seed, "client_a")

        # Otro cliente (otra gestora): 404 no-leak en mensajes y borrado.
        for method, path in (
            ("get", f"/api/chat/conversations/{conversation_id}/messages"),
            ("delete", f"/api/chat/conversations/{conversation_id}"),
            ("post", f"/api/chat/conversations/{conversation_id}/messages"),
        ):
            kwargs: dict[str, Any] = {"headers": auth(seed["client_b"])}
            if method == "post":
                kwargs["json"] = {"content": "hola"}
            response = getattr(client, method)(path, **kwargs)
            assert response.status_code == 404, (method, path, response.text)

        # Y su listado no la incluye.
        listing = client.get("/api/chat/conversations", headers=auth(seed["client_b"]))
        assert listing.json() == []

    def test_counsel_and_admin_cannot_use_the_client_chat(self, client, seed):
        for user_key in ("counsel", "admin"):
            response = client.post(
                "/api/chat/conversations", json={}, headers=auth(seed[user_key])
            )
            assert response.status_code == 403

    def test_delete_removes_conversation_and_messages(
        self, client, seed, db: dbmod.DevStore, monkeypatch: pytest.MonkeyPatch
    ):
        monkeypatch.setattr(llm, "stream", lambda prompt, **kwargs: iter(["ok"]))
        seed_precedent(
            db, gestora_id=seed["gestora_a"]["id"], doc_type="Acta", text="Texto alfa.")
        conversation_id = _conversation(client, seed)
        client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            json={"content": "hola"},
            headers=auth(seed["client_a"]),
        )
        response = client.delete(
            f"/api/chat/conversations/{conversation_id}", headers=auth(seed["client_a"])
        )
        assert response.status_code == 204
        assert db.get("chat_conversations", conversation_id) is None
        assert db.select("chat_messages", conversation_id=conversation_id) == []


# ---------------------------------------------------------------------------
# Verificación de grounding
# ---------------------------------------------------------------------------

class TestChatVerification:
    def test_non_literal_quotes_are_discarded(
        self, db: dbmod.DevStore, monkeypatch: pytest.MonkeyPatch
    ):
        """El mismo mecanismo de autoinvalidación que el verificador (020):
        un hallazgo cuya cita no aparece literal en la respuesta se descarta."""
        import config as config_module

        monkeypatch.setattr(config_module.get_settings(), "verify_enabled", True)
        monkeypatch.setattr(llm, "complete_json", lambda *args, **kwargs: {
            "findings": [
                {"problem": "importe sin soporte", "quote": "el hurdle es del 8%"},
                {"problem": "alucinada", "quote": "esto no está en la respuesta"},
            ]
        })

        answer = "Según la documentación, el hurdle es del 8% anual."
        hits = [rag.ChatHit(
            precedent_id="p1", precedent_version_id="v1", doc_type="LPA",
            source="manual_upload", text="hurdle rate", similarity=0.9)]
        result = chat_service._verify_grounding(answer, hits, "g-a")
        assert result is not None
        assert [f["quote"] for f in result["findings"]] == ["el hurdle es del 8%"]
        assert result["findings"][0]["category"] == "afirmacion_sin_soporte"

    def test_verification_disabled_returns_none(self, db: dbmod.DevStore):
        # VERIFY_ENABLED=false (conftest): la capa se salta limpiamente.
        hits = [rag.ChatHit(
            precedent_id="p1", precedent_version_id="v1", doc_type="LPA",
            source="manual_upload", text="x", similarity=0.9)]
        assert chat_service._verify_grounding("respuesta", hits, "g-a") is None


# ---------------------------------------------------------------------------
# Búsqueda híbrida (022): semántica + léxica con RRF
# ---------------------------------------------------------------------------

class TestHybridSearch:
    def test_lexical_half_works_without_embeddings(self, db: dbmod.DevStore):
        """Chunks sin vectores (proveedor caído al indexar) y embeddings de la
        query caídos (conftest): la mitad léxica los encuentra igualmente."""
        row = _chunk_row(gestora_id="g-a", doc_type="LPA",
                         text="El hurdle rate del fondo es del 8 por ciento.",
                         embed_model="")
        row["embedding"] = None
        row["embed_model"] = None
        db.insert("precedent_chunks", row)

        hits = rag.search_silo(db, gestora_id="g-a", language="es",
                               query_text="hurdle rate fondo")
        assert len(hits) == 1
        assert "hurdle rate" in hits[0].text

    def test_rrf_prefers_chunks_found_by_both_halves(
        self, db: dbmod.DevStore, monkeypatch: pytest.MonkeyPatch
    ):
        config = llm.resolve_embedding_config(None)
        model = config.resolved_embed_model
        # "ambos": similar al vector de la query Y contiene sus términos.
        db.insert("precedent_chunks", _chunk_row(
            gestora_id="g-a", doc_type="LPA",
            text="comision de gestion del dos por ciento",
            embed_model=model, lead=0.9))
        # "solo semántico": vector muy similar, texto sin los términos.
        db.insert("precedent_chunks", _chunk_row(
            gestora_id="g-a", doc_type="LPA",
            text="honorarios anuales aplicables", embed_model=model, lead=1.0))

        monkeypatch.setattr(rag, "_embed", lambda texts, config: [_vector(1.0)])
        hits = rag.search_silo(db, gestora_id="g-a", language="es",
                               query_text="comision de gestion")
        assert hits[0].text.startswith("comision de gestion")

    def test_lexical_half_respects_gestora_isolation(self, db: dbmod.DevStore):
        for gestora in ("g-a", "g-b"):
            row = _chunk_row(gestora_id=gestora, doc_type="LPA",
                             text=f"clausula de exclusividad de {gestora}",
                             embed_model="")
            row["embedding"] = None
            db.insert("precedent_chunks", row)
        hits = rag.search_silo(db, gestora_id="g-a", language="es",
                               query_text="clausula exclusividad")
        assert {hit.text for hit in hits} == {"clausula de exclusividad de g-a"}


# ---------------------------------------------------------------------------
# Chunking estructural (022): secciones/cláusulas
# ---------------------------------------------------------------------------

class TestStructuralChunking:
    def test_split_sections_by_clause_headers(self):
        from services import docx_renderer

        text = (
            "CONTRATO DE SUSCRIPCIÓN\n"
            "Entre las partes abajo firmantes.\n"
            "CLÁUSULA 1 — OBJETO\n"
            "El objeto del presente contrato.\n"
            "CLÁUSULA 2 — COMISIONES\n"
            "La comisión de gestión será del 2%.\n"
        )
        sections = docx_renderer.split_sections(text)
        titles = [title for title, _ in sections]
        assert titles == ["CONTRATO DE SUSCRIPCIÓN", "CLÁUSULA 1 — OBJETO",
                          "CLÁUSULA 2 — COMISIONES"]
        assert "comisión de gestión" in sections[2][1]

    def test_indexer_persists_section_per_chunk(
        self, db: dbmod.DevStore, monkeypatch: pytest.MonkeyPatch
    ):
        from services import indexer

        precedent, version = seed_precedent(
            db, gestora_id="g-a", doc_type="LPA",
            text="CLÁUSULA 1 — OBJETO\nEl objeto.\nCLÁUSULA 2 — COMISIONES\nLa comisión.")
        monkeypatch.setattr(indexer, "_embed_batch", lambda texts, config: None)
        config = llm.resolve_embedding_config(None)
        indexer._index_version(db, precedent, version, config)

        rows = db.select("precedent_chunks", precedent_version_id=version["id"])
        assert {row["section"] for row in rows} == {
            "CLÁUSULA 1 — OBJETO", "CLÁUSULA 2 — COMISIONES"}


# ---------------------------------------------------------------------------
# Reformulación de seguimiento + citas usadas + feedback (022)
# ---------------------------------------------------------------------------

class TestFollowUpRewrite:
    def test_follow_up_is_rewritten_for_retrieval_only(
        self, client, seed, db: dbmod.DevStore, monkeypatch: pytest.MonkeyPatch
    ):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], doc_type="LPA",
                       text="El hurdle rate es del 8%.")
        monkeypatch.setattr(
            llm, "complete",
            lambda *args, **kwargs: "¿Cuál es el hurdle rate del fondo?")
        searched: dict[str, str] = {}
        original_search = rag.search_silo

        def spy_search(db_, **kwargs):
            searched["query"] = kwargs["query_text"]
            return original_search(db_, **kwargs)

        monkeypatch.setattr(rag, "search_silo", spy_search)

        prompts: dict[str, str] = {}

        def fake_stream(prompt, **kwargs):
            prompts["prompt"] = prompt
            yield "El hurdle es del 8% [1]."

        monkeypatch.setattr(llm, "stream", fake_stream)

        conversation_id = _conversation(client, seed)
        # Primer turno crea historial.
        db.insert("chat_messages", {"conversation_id": conversation_id,
                                    "gestora_id": seed["gestora_a"]["id"],
                                    "role": "user", "content": "¿Comisión de gestión?"})
        db.insert("chat_messages", {"conversation_id": conversation_id,
                                    "gestora_id": seed["gestora_a"]["id"],
                                    "role": "assistant", "content": "El 2% [1]."})
        response = client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            json={"content": "¿y el hurdle?"},
            headers=auth(seed["client_a"]),
        )
        assert response.status_code == 200
        # El retrieval usa la pregunta reescrita; el prompt, la original.
        assert searched["query"] == "¿Cuál es el hurdle rate del fondo?"
        assert "¿y el hurdle?" in prompts["prompt"]

    def test_rewrite_failure_falls_back_to_original(
        self, db: dbmod.DevStore, monkeypatch: pytest.MonkeyPatch
    ):
        from config import ServiceNotConfiguredError

        def broken(*args, **kwargs):
            raise ServiceNotConfiguredError("ollama", "caído")

        monkeypatch.setattr(llm, "complete", broken)
        history = [{"role": "user", "content": "hola"}]
        assert chat_service._standalone_question(history, "¿y el hurdle?", "g-a") == "¿y el hurdle?"

    def test_no_history_skips_the_llm(self, monkeypatch: pytest.MonkeyPatch):
        def must_not_run(*args, **kwargs):
            raise AssertionError("sin historial no se reformula")

        monkeypatch.setattr(llm, "complete", must_not_run)
        assert chat_service._standalone_question([], "pregunta", "g-a") == "pregunta"


class TestUsedCitationsAndFeedback:
    def test_done_event_marks_used_citations(
        self, client, seed, db: dbmod.DevStore, monkeypatch: pytest.MonkeyPatch
    ):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], doc_type="LPA",
                       text="La comisión es del 2%. El hurdle es del 8%.")
        monkeypatch.setattr(llm, "stream",
                            lambda prompt, **kwargs: iter(["La comisión es del 2% [1]."]))

        conversation_id = _conversation(client, seed)
        response = client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            json={"content": "¿Comisión?"},
            headers=auth(seed["client_a"]),
        )
        events = _sse_events(response.text)
        done = events[-1]
        assert done["type"] == "done"
        assert done["used_indexes"] == [1]
        messages = db.select("chat_messages", conversation_id=conversation_id)
        assert messages[-1]["citations"][0]["used"] is True

    def test_feedback_up_down_with_no_leak(
        self, client, seed, db: dbmod.DevStore, monkeypatch: pytest.MonkeyPatch
    ):
        seed_precedent(db, gestora_id=seed["gestora_a"]["id"], doc_type="LPA",
                       text="Texto alfa.")
        monkeypatch.setattr(llm, "stream", lambda prompt, **kwargs: iter(["ok [1]."]))
        conversation_id = _conversation(client, seed)
        client.post(
            f"/api/chat/conversations/{conversation_id}/messages",
            json={"content": "hola"}, headers=auth(seed["client_a"]),
        )
        message_id = db.select("chat_messages", conversation_id=conversation_id)[-1]["id"]

        response = client.post(
            f"/api/chat/messages/{message_id}/feedback",
            json={"feedback": "down"}, headers=auth(seed["client_a"]),
        )
        assert response.status_code == 200
        assert db.get("chat_messages", message_id)["feedback"] == "down"

        # Otro cliente: 404 no-leak. Mensaje de usuario: 404 también.
        response = client.post(
            f"/api/chat/messages/{message_id}/feedback",
            json={"feedback": "up"}, headers=auth(seed["client_b"]),
        )
        assert response.status_code == 404
        user_message_id = db.select("chat_messages", conversation_id=conversation_id)[0]["id"]
        response = client.post(
            f"/api/chat/messages/{user_message_id}/feedback",
            json={"feedback": "up"}, headers=auth(seed["client_a"]),
        )
        assert response.status_code == 404
