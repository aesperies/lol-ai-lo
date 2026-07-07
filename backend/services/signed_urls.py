"""Signed, expiring download URLs (security hardening, improvement #9).

Download links embedded in EMAILS must not depend on a browser session and
must expire, so they carry an HMAC-SHA256 token instead of relying on the
Authorization header:

    token = base64url(json(payload)) + "." + base64url(hmac_sha256(body))
    payload = {"request_id": ..., "version_type": ..., "exp": epoch_seconds}

``verify`` uses a constant-time comparison (hmac.compare_digest) and rejects
expired or malformed tokens by returning None — callers translate that into a
404 so invalid links leak nothing (gestora-isolation 404 pattern).

Secret: URL_SIGNING_SECRET (config.py). When unset, a process-stable random
fallback is derived so dev keeps working (graceful degradation), with the
caveat that links break across restarts/workers.
TODO: real URL_SIGNING_SECRET required for production (openssl rand -hex 32).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from config import get_settings

logger = logging.getLogger("lolailo.signed_urls")

# Process-stable fallback secret, generated once per process when
# URL_SIGNING_SECRET is unset (see _secret()).
_fallback_secret: Optional[bytes] = None


def _secret() -> bytes:
    settings = get_settings()
    if settings.url_signing_secret:
        return settings.url_signing_secret.encode("utf-8")
    global _fallback_secret
    if _fallback_secret is None:
        _fallback_secret = secrets.token_bytes(32)
        logger.warning(
            "URL_SIGNING_SECRET is unset; using a process-stable random fallback. "
            "Signed download links will stop working on restart and across "
            "workers. TODO: set URL_SIGNING_SECRET in production."
        )
    return _fallback_secret


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _signature(body: str) -> bytes:
    return hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest()


def default_expiry() -> datetime:
    """Now + SIGNED_URL_TTL_HOURS (default 72h)."""
    return datetime.now(timezone.utc) + timedelta(hours=get_settings().signed_url_ttl_hours)


def sign_download(request_id: str, version_type: str, expires_at: datetime) -> str:
    """Build a signed download token for one request/version pair."""
    payload = {
        "request_id": request_id,
        "version_type": version_type,
        "exp": int(expires_at.timestamp()),
    }
    body = _b64encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    return f"{body}.{_b64encode(_signature(body))}"


def verify(token: str) -> Optional[dict[str, Any]]:
    """Validate a token; returns the payload, or None when invalid/expired.

    Constant-time signature comparison; any structural problem (bad base64,
    bad JSON, missing fields) also yields None — never an exception.
    """
    try:
        body, signature = token.split(".", 1)
        # Compare the CANONICAL encoding, not decoded bytes: unpadded
        # base64url of 32 bytes leaves 2 trailing bits the decoder ignores,
        # so several distinct strings decode to the same signature. String
        # comparison rejects every textual variant of a valid token.
        if not hmac.compare_digest(_b64encode(_signature(body)), signature):
            return None
        payload = json.loads(_b64decode(body))
    except (ValueError, TypeError, binascii.Error):
        return None
    if not isinstance(payload, dict):
        return None
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return None
    if datetime.now(timezone.utc).timestamp() > exp:
        return None
    if not payload.get("request_id") or not payload.get("version_type"):
        return None
    return payload


def signed_download_url(request_id: str, version_type: str) -> str:
    """Absolute backend URL serving this document via GET /api/download/{token}."""
    token = sign_download(request_id, version_type, default_expiry())
    return f"{get_settings().backend_url}/api/download/{token}"
