"""Application settings.

All external services are independently toggleable: each `*_configured`
property answers whether the corresponding credential is present. Code paths
MUST consult these properties (or catch ServiceNotConfiguredError) instead of
assuming a service exists.
"""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class ServiceNotConfiguredError(RuntimeError):
    """Raised when an endpoint needs an external service that has no credentials.

    API layers translate this into HTTP 503.
    """

    def __init__(self, service: str, hint: str = "") -> None:
        self.service = service
        detail = f"Service not configured: {service}."
        if hint:
            detail += f" {hint}"
        super().__init__(detail)


class Settings(BaseSettings):
    """Environment-driven configuration (see /.env.example)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # ---------- Supabase (Database + Auth) ----------
    # TODO: real credentials required for production (Supabase dashboard -> Settings -> API)
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    database_url: str = ""

    # ---------- Anthropic Claude ----------
    # TODO: real credential required (console.anthropic.com -> API Keys)
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # ---------- OpenAI (RAG embeddings) ----------
    # TODO: real credential required (platform.openai.com)
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"

    # ---------- Google Drive ----------
    # TODO: real service-account JSON required for Drive storage
    google_service_account_file: str = ""
    drive_templates_folder_id: str = ""
    drive_gestoras_folder_id: str = ""

    # ---------- Resend ----------
    # TODO: real credential required (resend.com) — console fallback otherwise
    resend_api_key: str = ""
    email_from: str = "notificaciones@lolailolegal.es"

    # ---------- App ----------
    frontend_url: str = "http://localhost:3000"
    local_storage_dir: str = "./storage"
    dev_auth_stub: bool = False
    # Generation-job retry backoff base in seconds (delays: base*1, base*4).
    # The test suite pins JOB_BACKOFF_BASE=0 so retries are instant.
    job_backoff_base: float = 1.0
    # Max iterative refinements per request; beyond this the client is
    # directed to Exit B (counsel validation).
    max_refinements: int = 3

    # ---------- Billing (improvement #7) ----------
    # Per-doc overage prices in EUR once the tier's monthly doc allowance is
    # exhausted (SPEC PRICING STRUCTURE: Exit A €X < Exit B €Y).
    # TODO: tiers/prices TBD per SPEC — 0 = TBD, estimated overage stays €0.
    price_exit_a_eur: float = 0.0
    price_exit_b_eur: float = 0.0

    # ---------- Security hardening (improvement #9) ----------
    # HMAC secret for signed, expiring download links (services/signed_urls.py).
    # TODO: real secret required for production (openssl rand -hex 32) — when
    # unset a process-stable random fallback is derived and a warning logged
    # (links stop working across restarts/workers).
    url_signing_secret: str = ""
    # Lifetime of signed download links embedded in emails (hours).
    signed_url_ttl_hours: float = 72.0
    # Public base URL of THIS backend, used to build signed download links.
    backend_url: str = "http://localhost:8000"
    # In-process sliding-window rate limiting (services/rate_limit.py);
    # disabled under pytest except in the dedicated rate-limit tests.
    # TODO: Redis-based limiter for multi-worker production deployments.
    rate_limit_enabled: bool = True
    # Max accepted upload size (counsel .docx, admin precedents), in MiB.
    max_upload_mb: int = 15

    # ---------- Counsel SLA (Exit B turnaround, improvement #8) ----------
    # Promised review turnaround for counsel validation (hours).
    sla_review_hours: float = 48.0
    # Reminder to the assigned counsel when half the SLA has elapsed.
    sla_reminder_hours: float = 24.0
    # Escalation to the BACKUP counsel after SLA + 8h grace.
    sla_escalation_hours: float = 56.0
    # In-process periodic sweep (services/sla.py); disabled under pytest.
    sla_sweep_enabled: bool = True
    sla_sweep_interval_minutes: float = 30.0

    # -- readiness flags ---------------------------------------------------
    @property
    def supabase_configured(self) -> bool:
        return bool(self.supabase_url and self.supabase_service_role_key)

    @property
    def anthropic_configured(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def drive_configured(self) -> bool:
        return bool(self.google_service_account_file)

    @property
    def resend_configured(self) -> bool:
        return bool(self.resend_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
