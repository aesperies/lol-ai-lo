"""Per-gestora model configuration + secrets encryption (feature C).

Covers: the stdlib secrets round-trip (ciphertext != plaintext, tamper-proof),
per-gestora override of the global LLM resolution, fallback to global when no
config row exists, the admin-only endpoint never returning plaintext keys, and
cross-gestora config isolation.
"""
from __future__ import annotations

import pytest

from services import db as dbmod, llm, secrets
from tests.conftest import auth


# ---------------------------------------------------------------------------
# 1. Secrets encryption round-trip
# ---------------------------------------------------------------------------

class TestSecrets:
    def test_round_trip(self):
        plaintext = "sk-ant-super-secret-key-12345"
        token = secrets.encrypt(plaintext)
        assert secrets.decrypt(token) == plaintext

    def test_ciphertext_differs_from_plaintext(self):
        plaintext = "sk-openai-abcdef"
        token = secrets.encrypt(plaintext)
        assert plaintext not in token
        assert token != plaintext

    def test_each_encryption_is_nondeterministic(self):
        plaintext = "same-key"
        assert secrets.encrypt(plaintext) != secrets.encrypt(plaintext)
        # ...but both still decrypt back to the original.
        assert secrets.decrypt(secrets.encrypt(plaintext)) == plaintext

    def test_tampered_ciphertext_rejected(self):
        token = secrets.encrypt("secret")
        # Flip a character in the middle of the token.
        tampered = token[:-4] + ("A" if token[-4] != "A" else "B") + token[-3:]
        with pytest.raises(secrets.DecryptionError):
            secrets.decrypt(tampered)

    def test_garbage_token_rejected(self):
        with pytest.raises(secrets.DecryptionError):
            secrets.decrypt("not-a-real-token!!!")

    def test_unicode_round_trip(self):
        plaintext = "clé-secrète-€-日本語"
        assert secrets.decrypt(secrets.encrypt(plaintext)) == plaintext


# ---------------------------------------------------------------------------
# 2. Per-gestora LLM resolution (override vs global fallback)
# ---------------------------------------------------------------------------

class TestResolution:
    def test_no_gestora_uses_global(self, db, seed):
        config = llm.resolve_config(None)
        # Conftest pins the default provider to ollama (local-first).
        assert config.llm_provider == "ollama"

    def test_gestora_without_config_uses_global(self, db, seed):
        config = llm.resolve_config(seed["gestora_a"]["id"])
        assert config.llm_provider == "ollama"
        assert config.anthropic_api_key == ""  # conftest clears it

    def test_gestora_config_overrides_provider_model_and_key(self, db, seed):
        db.insert(
            "gestora_model_config",
            {
                "gestora_id": seed["gestora_a"]["id"],
                "llm_provider": "anthropic",
                "llm_model": "claude-custom-model",
                "anthropic_api_key_enc": secrets.encrypt("sk-ant-gestora-a"),
            },
        )
        config = llm.resolve_config(seed["gestora_a"]["id"])
        assert config.llm_provider == "anthropic"
        assert config.claude_model == "claude-custom-model"
        assert config.anthropic_api_key == "sk-ant-gestora-a"

    def test_override_captured_by_complete_call(self, db, seed, monkeypatch):
        """The effective provider/model/key reach the actual provider call."""
        db.insert(
            "gestora_model_config",
            {
                "gestora_id": seed["gestora_a"]["id"],
                "llm_provider": "anthropic",
                "llm_model": "claude-xyz",
                "anthropic_api_key_enc": secrets.encrypt("sk-ant-captured"),
            },
        )
        captured: dict = {}

        def fake_anthropic(prompt, *, max_tokens, json_schema, system, config):
            captured["provider"] = config.llm_provider
            captured["model"] = config.claude_model
            captured["key"] = config.anthropic_api_key
            return "ok"

        monkeypatch.setattr(llm, "_complete_anthropic", fake_anthropic)
        out = llm.complete("hi", gestora_id=seed["gestora_a"]["id"])
        assert out == "ok"
        assert captured == {
            "provider": "anthropic",
            "model": "claude-xyz",
            "key": "sk-ant-captured",
        }

    def test_undecryptable_key_degrades_to_global(self, db, seed):
        db.insert(
            "gestora_model_config",
            {
                "gestora_id": seed["gestora_a"]["id"],
                "llm_provider": "anthropic",
                "anthropic_api_key_enc": "garbage-not-a-token",
            },
        )
        config = llm.resolve_config(seed["gestora_a"]["id"])
        # Provider override still applied; the broken key falls back to global "".
        assert config.llm_provider == "anthropic"
        assert config.anthropic_api_key == ""


# ---------------------------------------------------------------------------
# 3. Admin endpoint — no plaintext keys, admin-only, isolation
# ---------------------------------------------------------------------------

class TestModelConfigApi:
    def _put(self, client, seed, gestora, body, user=None):
        return client.put(
            f"/api/admin/gestoras/{gestora['id']}/model-config",
            json=body,
            headers=auth(user or seed["admin"]),
        )

    def test_default_when_unset(self, client, seed):
        res = client.get(
            f"/api/admin/gestoras/{seed['gestora_a']['id']}/model-config",
            headers=auth(seed["admin"]),
        )
        assert res.status_code == 200
        body = res.json()
        assert body["is_default"] is True
        assert body["anthropic_key_set"] is False
        assert body["openai_key_set"] is False

    def test_put_sets_provider_and_keys_without_returning_plaintext(self, client, seed, db):
        res = self._put(
            client,
            seed,
            seed["gestora_a"],
            {
                "llm_provider": "anthropic",
                "llm_model": "claude-custom",
                "anthropic_api_key": "sk-ant-plaintext-never-leaks",
                "openai_api_key": "sk-openai-plaintext-never-leaks",
            },
        )
        assert res.status_code == 200
        body = res.json()
        assert body["llm_provider"] == "anthropic"
        assert body["llm_model"] == "claude-custom"
        assert body["anthropic_key_set"] is True
        assert body["openai_key_set"] is True
        assert body["is_default"] is False
        # The plaintext key must NEVER appear anywhere in the response.
        assert "sk-ant-plaintext-never-leaks" not in res.text
        assert "sk-openai-plaintext-never-leaks" not in res.text
        # ...and it must be stored ENCRYPTED, not as plaintext, in the DB.
        rows = db.select("gestora_model_config", gestora_id=seed["gestora_a"]["id"])
        stored = rows[-1]
        assert stored["anthropic_api_key_enc"] != "sk-ant-plaintext-never-leaks"
        assert secrets.decrypt(stored["anthropic_api_key_enc"]) == "sk-ant-plaintext-never-leaks"

    def test_get_never_returns_plaintext_keys(self, client, seed):
        self._put(
            client,
            seed,
            seed["gestora_a"],
            {"anthropic_api_key": "sk-ant-top-secret"},
        )
        res = client.get(
            f"/api/admin/gestoras/{seed['gestora_a']['id']}/model-config",
            headers=auth(seed["admin"]),
        )
        assert "sk-ant-top-secret" not in res.text
        assert res.json()["anthropic_key_set"] is True

    def test_empty_string_clears_key_and_provider(self, client, seed, db):
        self._put(
            client,
            seed,
            seed["gestora_a"],
            {"llm_provider": "anthropic", "anthropic_api_key": "sk-to-clear"},
        )
        # Now clear them.
        res = self._put(
            client,
            seed,
            seed["gestora_a"],
            {"llm_provider": "", "anthropic_api_key": ""},
        )
        body = res.json()
        assert body["llm_provider"] is None
        assert body["anthropic_key_set"] is False

    def test_omitted_key_left_unchanged(self, client, seed):
        self._put(
            client, seed, seed["gestora_a"], {"anthropic_api_key": "sk-keep-me"}
        )
        # A later PUT that omits the key field must not wipe it.
        res = self._put(client, seed, seed["gestora_a"], {"llm_model": "m2"})
        body = res.json()
        assert body["anthropic_key_set"] is True
        assert body["llm_model"] == "m2"

    def test_client_and_counsel_forbidden(self, client, seed):
        for user in (seed["client_a"], seed["counsel"]):
            res = client.get(
                f"/api/admin/gestoras/{seed['gestora_a']['id']}/model-config",
                headers=auth(user),
            )
            assert res.status_code == 403
            res_put = self._put(
                client, seed, seed["gestora_a"], {"llm_provider": "anthropic"}, user=user
            )
            assert res_put.status_code == 403

    def test_unknown_gestora_404(self, client, seed):
        res = client.get(
            "/api/admin/gestoras/does-not-exist/model-config",
            headers=auth(seed["admin"]),
        )
        assert res.status_code == 404

    def test_cross_gestora_config_isolation(self, client, seed, db):
        """Gestora A's config never bleeds into gestora B's resolution/endpoint."""
        self._put(
            client,
            seed,
            seed["gestora_a"],
            {"llm_provider": "anthropic", "anthropic_api_key": "sk-only-for-a"},
        )
        # B's endpoint still reports default (no config of its own).
        res_b = client.get(
            f"/api/admin/gestoras/{seed['gestora_b']['id']}/model-config",
            headers=auth(seed["admin"]),
        )
        assert res_b.json()["is_default"] is True
        # B's LLM resolution uses the global default, never A's key/provider.
        config_b = llm.resolve_config(seed["gestora_b"]["id"])
        assert config_b.llm_provider == "ollama"
        assert config_b.anthropic_api_key == ""
        # A's resolution does use A's override.
        config_a = llm.resolve_config(seed["gestora_a"]["id"])
        assert config_a.llm_provider == "anthropic"
        assert config_a.anthropic_api_key == "sk-only-for-a"
