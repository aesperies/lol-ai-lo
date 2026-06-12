"""Security hardening tests (improvement #9): signed download URLs, the
auth-free signed endpoint, rate limiting, upload hardening, security headers."""
from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone

import config
from services import docx_renderer, rate_limit, signed_urls
from services import db as dbmod
from tests.conftest import DOC_TYPE, auth


def _expiry(hours: float = 1.0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


# ---------------------------------------------------------------------------
# Signed URL tokens (services/signed_urls.py)
# ---------------------------------------------------------------------------

class TestSignedTokens:
    def test_roundtrip(self):
        token = signed_urls.sign_download("req-1", "draft", _expiry())
        payload = signed_urls.verify(token)
        assert payload is not None
        assert payload["request_id"] == "req-1"
        assert payload["version_type"] == "draft"

    def test_expired_token_rejected(self):
        token = signed_urls.sign_download("req-1", "draft", _expiry(hours=-1))
        assert signed_urls.verify(token) is None

    def test_tampered_token_rejected(self):
        token = signed_urls.sign_download("req-1", "draft", _expiry())
        body, signature = token.split(".", 1)
        # Re-encode a different request id with the ORIGINAL signature.
        other = signed_urls.sign_download("req-2", "draft", _expiry()).split(".", 1)[0]
        assert signed_urls.verify(f"{other}.{signature}") is None
        # Bit-flip in the signature.
        flipped = signature[:-1] + ("A" if signature[-1] != "A" else "B")
        assert signed_urls.verify(f"{body}.{flipped}") is None
        # Garbage tokens never raise.
        assert signed_urls.verify("not-a-token") is None
        assert signed_urls.verify("a.b") is None
        assert signed_urls.verify("") is None

    def test_wrong_secret_rejected(self, monkeypatch):
        monkeypatch.setattr(config.get_settings(), "url_signing_secret", "secret-one")
        token = signed_urls.sign_download("req-1", "draft", _expiry())
        assert signed_urls.verify(token) is not None
        monkeypatch.setattr(config.get_settings(), "url_signing_secret", "secret-two")
        assert signed_urls.verify(token) is None


# ---------------------------------------------------------------------------
# Signed download endpoint (GET /api/download/{token}, no auth dependency)
# ---------------------------------------------------------------------------

class TestSignedDownloadEndpoint:
    def test_serves_file_without_auth_and_audits_signed_link(self, wf, client, db):
        request_id, _ = wf.to_review_pending()
        token = signed_urls.sign_download(request_id, "draft", _expiry())

        response = client.get(f"/api/download/{token}")  # NO auth headers
        assert response.status_code == 200, response.text
        assert "wordprocessingml" in response.headers["content-type"]
        assert response.content[:4] == b"PK\x03\x04"

        entries = [
            e
            for e in db.select("audit_log", action="draft_downloaded")
            if (e.get("metadata") or {}).get("request_id") == request_id
        ]
        assert entries, "signed download must be audited as draft_downloaded"
        assert entries[-1]["metadata"]["mode"] == "signed_link"
        assert entries[-1]["user_id"] is None  # token is the credential

    def test_expired_and_tampered_links_404(self, wf, client):
        request_id, _ = wf.to_review_pending()
        expired = signed_urls.sign_download(request_id, "draft", _expiry(hours=-1))
        assert client.get(f"/api/download/{expired}").status_code == 404

        valid = signed_urls.sign_download(request_id, "draft", _expiry())
        body, signature = valid.split(".", 1)
        flipped = signature[:-2] + ("AA" if not signature.endswith("AA") else "BB")
        assert client.get(f"/api/download/{body}.{flipped}").status_code == 404
        assert client.get("/api/download/garbage").status_code == 404

    def test_final_link_requires_validated_status(self, wf, client):
        request_id, _ = wf.to_review_pending()
        token = signed_urls.sign_download(request_id, "final", _expiry())
        # No final document / status yet: 409 (status guard) — never the file.
        assert client.get(f"/api/download/{token}").status_code == 409


# ---------------------------------------------------------------------------
# Rate limiting (services/rate_limit.py)
# ---------------------------------------------------------------------------

class TestRateLimiting:
    def test_endpoint_returns_429_with_retry_after(self, wf, client, monkeypatch):
        request_id, _ = wf.to_review_pending()
        token = signed_urls.sign_download(request_id, "draft", _expiry())

        monkeypatch.setattr(rate_limit, "enable_under_pytest", True)
        monkeypatch.setitem(rate_limit.limit_overrides, "signed_download", 3)
        rate_limit.reset()
        try:
            for _ in range(3):
                assert client.get(f"/api/download/{token}").status_code == 200
            blocked = client.get(f"/api/download/{token}")
            assert blocked.status_code == 429
            assert int(blocked.headers["Retry-After"]) >= 1
        finally:
            rate_limit.reset()

    def test_window_recovers(self):
        # Pure limiter check with a tiny window: blocked, then allowed again.
        rate_limit.reset()
        try:
            assert rate_limit.check("t:recover", 2, window_seconds=0.05) is None
            assert rate_limit.check("t:recover", 2, window_seconds=0.05) is None
            assert rate_limit.check("t:recover", 2, window_seconds=0.05) is not None
            time.sleep(0.06)
            assert rate_limit.check("t:recover", 2, window_seconds=0.05) is None
        finally:
            rate_limit.reset()

    def test_keys_are_isolated_per_identity(self):
        rate_limit.reset()
        try:
            assert rate_limit.check("t:a", 1) is None
            assert rate_limit.check("t:a", 1) is not None
            assert rate_limit.check("t:b", 1) is None  # other identity unaffected
        finally:
            rate_limit.reset()

    def test_disabled_under_pytest_by_default(self, wf, client):
        # 10 generations in a row: with the limiter implicitly off under
        # pytest, none of the (guardrail-rejected) calls ever sees a 429.
        request_id, _ = wf.to_review_pending()
        for _ in range(10):
            response = wf.generate(request_id)
            assert response.status_code != 429


# ---------------------------------------------------------------------------
# Upload hardening (extension + size + magic bytes)
# ---------------------------------------------------------------------------

def _upload_precedent(client, seed, filename, content):
    return client.post(
        "/api/precedents",
        data={"doc_type": DOC_TYPE, "language": "es", "gestora_id": seed["gestora_a"]["id"]},
        files={"file": (filename, content, "application/octet-stream")},
        headers=auth(seed["admin"]),
    )


class TestUploadHardening:
    def test_wrong_extension_rejected(self, client, seed):
        response = _upload_precedent(client, seed, "p.txt", b"PK\x03\x04whatever")
        assert response.status_code == 422

    def test_bad_magic_bytes_rejected(self, client, seed):
        assert _upload_precedent(client, seed, "p.docx", b"not a zip at all").status_code == 422
        assert _upload_precedent(client, seed, "p.pdf", b"not a pdf either").status_code == 422

    def test_oversize_rejected(self, client, seed, monkeypatch):
        monkeypatch.setattr(config.get_settings(), "max_upload_mb", 1)
        oversize = b"PK\x03\x04" + b"0" * (1024 * 1024 + 16)
        assert _upload_precedent(client, seed, "p.docx", oversize).status_code == 422

    def test_valid_docx_accepted(self, client, seed):
        response = _upload_precedent(
            client, seed, "p.docx", docx_renderer.render_docx("PRECEDENTE VÁLIDO")
        )
        assert response.status_code == 201, response.text

    def test_valid_pdf_accepted(self, client, seed):
        response = _upload_precedent(client, seed, "p.pdf", b"%PDF-1.7 minimal")
        assert response.status_code == 201, response.text

    def test_counsel_upload_bad_magic_rejected(self, wf, client, seed):
        request_id, _ = wf.to_review_pending()
        client.post(f"/api/requests/{request_id}/exit-b", headers=auth(seed["client_a"]))
        response = client.post(
            f"/api/requests/{request_id}/counsel/upload",
            files={"file": ("edited.docx", b"plain text, not a docx", "text/plain")},
            headers=auth(seed["counsel"]),
        )
        assert response.status_code == 422
        # No counsel_edit document was created.
        db = dbmod.get_db()
        assert db.select("documents", request_id=request_id, version_type="counsel_edit") == []


# ---------------------------------------------------------------------------
# Security headers (main.py middleware)
# ---------------------------------------------------------------------------

class TestSecurityHeaders:
    def test_headers_present_on_api_response(self, client, seed):
        response = client.get("/api/requests", headers=auth(seed["client_a"]))
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
        assert response.headers["Cache-Control"] == "no-store"

    def test_no_store_only_on_api_paths(self, client):
        response = client.get("/health")
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers.get("Cache-Control") != "no-store"
