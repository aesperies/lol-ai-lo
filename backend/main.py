"""Lol-AI-lo backend — FastAPI application entry point.

Starts with zero external services configured: every optional dependency is
lazy-imported and every unconfigured service degrades per the SPEC readiness
matrix (Resend -> console, Drive -> ./storage, LLM endpoints -> 503,
DB -> dev store when DEV_AUTH_STUB=true).
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.documents import router as documents_router
from api.notifications import router as notifications_router
from api.precedents import router as precedents_router
from api.requests import router as requests_router
from config import ServiceNotConfiguredError, get_settings

app = FastAPI(title="Lol-AI-lo API", version="1.0.0")

_settings = get_settings()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_settings.frontend_url, "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ServiceNotConfiguredError)
async def service_not_configured_handler(request: Request, exc: ServiceNotConfiguredError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


app.include_router(requests_router)
app.include_router(documents_router)
app.include_router(precedents_router)
app.include_router(notifications_router)


@app.get("/health")
async def health() -> dict:
    """Service readiness matrix (SPEC graceful degradation)."""
    settings = get_settings()
    from services import drive  # local import keeps startup dependency-free

    return {
        "status": "ok",
        "services": {
            "supabase": settings.supabase_configured,
            "anthropic": settings.anthropic_configured,
            "openai": settings.openai_configured,
            "google_drive": drive.is_configured(),
            "resend": settings.resend_configured,
        },
        "auth_mode": "dev-stub" if settings.dev_auth_stub else "supabase",
        "storage_mode": "drive" if drive.is_configured() else "local",
        "claude_model": settings.claude_model,
    }
