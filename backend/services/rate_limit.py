"""In-process sliding-window rate limiter (security hardening, improvement #9).

No new dependencies: a dict of deques of monotonic timestamps, keyed by
"{scope}:{user-or-ip}". Thread-safe enough for the single-process asyncio
deployment this app uses (one lock around the window bookkeeping).
TODO: Redis-based limiter for multi-worker production deployments — this
implementation is per-process, so N workers multiply every limit by N.

Usage (FastAPI):

    @router.post("/...", dependencies=[Depends(rate_limit("generation", 6))])

``per="user"`` keys by the caller identity (X-Dev-User header in dev-stub
mode, otherwise a hash of the Authorization header, falling back to the
client IP); ``per="ip"`` keys by client IP — used for auth-free endpoints
such as the signed download link.

Disabled under pytest (so the 124-test suite is unaffected) except when the
dedicated rate-limit tests flip ``enable_under_pytest``; disabled entirely
when RATE_LIMIT_ENABLED=false.
"""
from __future__ import annotations

import hashlib
import math
import sys
import threading
import time
from collections import deque
from typing import Callable, Coroutine, Optional

from fastapi import HTTPException, Request

from config import get_settings

WINDOW_SECONDS = 60.0

# Flipped (via monkeypatch) by tests/test_security.py to exercise the limiter;
# everywhere else the limiter is a no-op under pytest.
enable_under_pytest = False

# Test hook: override a scope's max_per_minute without touching the endpoints.
limit_overrides: dict[str, int] = {}

_lock = threading.Lock()
_windows: dict[str, deque[float]] = {}


def reset() -> None:
    """Clear all windows (test isolation helper)."""
    with _lock:
        _windows.clear()


def _enabled() -> bool:
    if not get_settings().rate_limit_enabled:
        return False
    if "pytest" in sys.modules and not enable_under_pytest:
        return False
    return True


def check(key: str, max_per_window: int, window_seconds: float = WINDOW_SECONDS) -> Optional[float]:
    """Record one hit for ``key``; returns None when allowed, or the seconds
    until the oldest hit leaves the window (the Retry-After value)."""
    now = time.monotonic()
    with _lock:
        window = _windows.setdefault(key, deque())
        cutoff = now - window_seconds
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= max_per_window:
            return window[0] + window_seconds - now
        window.append(now)
        return None


def _identity(http_request: Request, per: str) -> str:
    ip = http_request.client.host if http_request.client else "unknown"
    if per == "ip":
        return ip
    dev_user = http_request.headers.get("x-dev-user")
    if dev_user:
        return f"user:{dev_user}"
    authorization = http_request.headers.get("authorization")
    if authorization:
        # The token itself never lands in the key dict.
        return "tok:" + hashlib.sha256(authorization.encode("utf-8")).hexdigest()[:32]
    return ip


def rate_limit(
    scope: str, max_per_minute: int, per: str = "user"
) -> Callable[[Request], Coroutine[None, None, None]]:
    """FastAPI dependency: 429 + Retry-After once the caller exceeds
    ``max_per_minute`` requests in the sliding window for ``scope``."""

    async def dependency(http_request: Request) -> None:
        if not _enabled():
            return
        limit = limit_overrides.get(scope, max_per_minute)
        retry_after = check(f"{scope}:{_identity(http_request, per)}", limit)
        if retry_after is not None:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded for {scope} ({limit}/min). Try again later.",
                headers={"Retry-After": str(max(1, math.ceil(retry_after)))},
            )

    return dependency
