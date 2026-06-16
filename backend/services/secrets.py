"""Symmetric encryption for secrets at rest (account-security feature C).

Per-gestora BYO API keys (gestora_model_config.{anthropic,openai}_api_key_enc)
must never be stored in plaintext. This module provides a tiny, dependency-light
authenticated symmetric scheme built on the standard library only (``hashlib`` +
``hmac``), so the app keeps its "importable with zero optional deps" property.

Scheme (clean-room, encrypt-then-MAC):

    salt  = 16 random bytes (per message)
    enc_k = HMAC-SHA256(master, b"enc" + salt)        # encryption sub-key
    mac_k = HMAC-SHA256(master, b"mac" + salt)         # authentication sub-key
    keystream_i = HMAC-SHA256(enc_k, counter_i)        # CTR-style keystream
    ciphertext  = plaintext XOR keystream
    tag   = HMAC-SHA256(mac_k, salt + ciphertext)      # authenticates both
    token = base64url( b"v1" + salt + tag + ciphertext )

Decryption recomputes the sub-keys from the embedded salt, verifies ``tag`` with
a constant-time comparison (``hmac.compare_digest``) BEFORE decrypting, and
rejects any tampered/short/garbage token by raising :class:`DecryptionError`.

The master key is ``SECRETS_ENCRYPTION_KEY`` (config.py). When unset a
process-stable random fallback is derived and a warning logged — dev keeps
working, with the caveat that stored ciphertext stops decrypting across restarts
and workers (same trade-off as ``URL_SIGNING_SECRET``).

If the ``cryptography`` package is ever installed it is NOT used here on purpose:
keeping a single stdlib path means the suite and the import stay dependency-free
and the round-trip is deterministic across environments.

NEVER log plaintext keys (or this module's inputs/outputs at INFO+).
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import logging
import secrets as _secrets
from typing import Optional

from config import get_settings

logger = logging.getLogger("lolailo.secrets")

# Token version prefix (lets the format evolve without ambiguity).
_VERSION = b"v1"
_SALT_LEN = 16
_TAG_LEN = 32  # HMAC-SHA256 digest size

# Process-stable fallback master key, generated once when
# SECRETS_ENCRYPTION_KEY is unset (see _master()).
_fallback_master: Optional[bytes] = None


class DecryptionError(ValueError):
    """Raised when a ciphertext is malformed, truncated, or fails its MAC."""


def _master() -> bytes:
    settings = get_settings()
    if settings.secrets_encryption_key:
        return settings.secrets_encryption_key.encode("utf-8")
    global _fallback_master
    if _fallback_master is None:
        _fallback_master = _secrets.token_bytes(32)
        logger.warning(
            "SECRETS_ENCRYPTION_KEY is unset; using a process-stable random "
            "fallback. Encrypted secrets (per-gestora BYO API keys) will stop "
            "decrypting on restart and across workers. TODO: set "
            "SECRETS_ENCRYPTION_KEY in production."
        )
    return _fallback_master


def _subkey(master: bytes, label: bytes, salt: bytes) -> bytes:
    return hmac.new(master, label + salt, hashlib.sha256).digest()


def _keystream(enc_key: bytes, length: int) -> bytes:
    """CTR-style keystream: HMAC-SHA256(enc_key, counter) blocks concatenated."""
    out = bytearray()
    counter = 0
    while len(out) < length:
        block = hmac.new(enc_key, counter.to_bytes(8, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:length])


def _xor(data: bytes, keystream: bytes) -> bytes:
    return bytes(a ^ b for a, b in zip(data, keystream))


def encrypt(plaintext: str) -> str:
    """Encrypt ``plaintext`` into an authenticated, URL-safe base64 token.

    A fresh random salt makes the ciphertext non-deterministic (the same key
    encrypts to a different token each call). Never logs the plaintext.
    """
    master = _master()
    salt = _secrets.token_bytes(_SALT_LEN)
    enc_key = _subkey(master, b"enc", salt)
    mac_key = _subkey(master, b"mac", salt)
    raw = plaintext.encode("utf-8")
    ciphertext = _xor(raw, _keystream(enc_key, len(raw)))
    tag = hmac.new(mac_key, salt + ciphertext, hashlib.sha256).digest()
    token = _VERSION + salt + tag + ciphertext
    return base64.urlsafe_b64encode(token).decode("ascii")


def decrypt(token: str) -> str:
    """Decrypt a token produced by :func:`encrypt`.

    Verifies the MAC with a constant-time comparison BEFORE decrypting. Raises
    :class:`DecryptionError` on any tampering, truncation, wrong key, or garbage
    input (never leaks why beyond "could not decrypt").
    """
    try:
        blob = base64.urlsafe_b64decode(token.encode("ascii"))
    except (binascii.Error, ValueError) as exc:
        raise DecryptionError("invalid secret token encoding") from exc
    header = len(_VERSION) + _SALT_LEN + _TAG_LEN
    if len(blob) < header or blob[: len(_VERSION)] != _VERSION:
        raise DecryptionError("invalid or truncated secret token")
    salt = blob[len(_VERSION) : len(_VERSION) + _SALT_LEN]
    tag = blob[len(_VERSION) + _SALT_LEN : header]
    ciphertext = blob[header:]
    master = _master()
    mac_key = _subkey(master, b"mac", salt)
    expected = hmac.new(mac_key, salt + ciphertext, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, expected):
        raise DecryptionError("secret token failed authentication")
    enc_key = _subkey(master, b"enc", salt)
    plaintext = _xor(ciphertext, _keystream(enc_key, len(ciphertext)))
    try:
        return plaintext.decode("utf-8")
    except UnicodeDecodeError as exc:  # pragma: no cover — MAC already guards this
        raise DecryptionError("decrypted secret is not valid UTF-8") from exc
