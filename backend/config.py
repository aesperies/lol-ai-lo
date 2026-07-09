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

    # ---------- LLM provider (local-first) ----------
    # Text generation + intake parsing route through a single seam
    # (services/llm.py). "ollama" (default) runs fully local; "anthropic"
    # falls back to the cloud Claude API.
    llm_provider: str = "ollama"
    # Embeddings provider for RAG (services/rag.py): "ollama" (default, local)
    # or "openai" (cloud, via LlamaIndex).
    embedding_provider: str = "ollama"

    # ---------- Ollama (local LLM + embeddings) ----------
    ollama_base_url: str = "http://localhost:11434"
    ollama_llm_model: str = "qwen2.5:14b-instruct"
    # Multilingual embeddings (docs are ES/EN/FR/DE).
    ollama_embed_model: str = "bge-m3"
    # Big legal generations can be slow on local hardware.
    ollama_timeout_seconds: float = 600.0
    # Transient-network retry attempts in the LLM seam (delays ~0 under pytest).
    llm_retry_attempts: int = 2

    # ---------- Anthropic Claude (optional cloud fallback) ----------
    # TODO: real credential required when LLM_PROVIDER=anthropic
    # (console.anthropic.com -> API Keys)
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"

    # ---------- Mistral (optional EU cloud fallback — data residency in Paris) ----------
    # GDPR-friendlier cloud alternative to Anthropic for gestoras that accept
    # cloud processing only within the EU. TODO: real credential required when
    # LLM_PROVIDER=mistral (console.mistral.ai -> API Keys).
    mistral_api_key: str = ""
    mistral_model: str = "mistral-large-latest"
    # Embeddings UE (EMBEDDING_PROVIDER=mistral): 1024 dims — igual que bge-m3,
    # así el índice pgvector (migración 018, vector(1024)) sirve para ambos.
    mistral_embed_model: str = "mistral-embed"

    # ---------- Grok / xAI (optional US cloud fallback) ----------
    # Generation-only: xAI publishes no embedding models (jul-2026), so the
    # RAG index keeps its own EMBEDDING_PROVIDER. TODO: real credential
    # required when LLM_PROVIDER=grok (console.x.ai -> API Keys).
    xai_api_key: str = ""
    grok_model: str = "grok-4.5"

    # ---------- OpenAI (optional cloud RAG embeddings) ----------
    # TODO: real credential required when EMBEDDING_PROVIDER=openai
    # (platform.openai.com)
    openai_api_key: str = ""
    embedding_model: str = "text-embedding-3-small"

    # ---------- Cost-aware model routing (services/model_router.py) ----------
    # The orchestrator picks a LIGHT model for cheap, high-volume workloads
    # (critic, evaluator gate, lessons, tabular cells, intake parse) and keeps
    # the provider's standard model for document generation/refinement. A
    # gestora that pins an explicit llm_model in its model-config override is
    # NEVER re-routed. Empty light model = routing is a no-op for that provider.
    model_routing_enabled: bool = True
    ollama_light_model: str = ""  # e.g. "qwen2.5:7b-instruct" once pulled
    anthropic_light_model: str = "claude-haiku-4-5-20251001"
    mistral_light_model: str = "mistral-small-latest"
    grok_light_model: str = "grok-4.3"
    # Intake-parse escalation: when the light-tier parse returns confidence
    # below this, retry ONCE on the heavy tier (skipped when both tiers
    # resolve to the same model).
    parse_escalation_confidence: float = 0.7

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

    # ---------- Document generation / redline (improvement #3) ----------
    # Upper bound on tokens for a full document generation (generator.py).
    # Long legal documents (long-form agreements, fund side letters) need
    # headroom beyond the LLM seam's per-call default; bump this — not the
    # provider settings — to allow longer outputs.
    max_generation_tokens: int = 8192
    # Above this paragraph count on either side, the redline engine drops the
    # expensive word-level intra-paragraph diff and falls back to a coarser
    # paragraph-level diff so very large documents never blow up or hang
    # (services/redline.py). Still produces a valid tracked-changes .docx.
    redline_max_paragraphs: int = 1200

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
    # Symmetric secret for encrypting per-gestora BYO API keys at rest
    # (services/secrets.py, gestora_model_config; account-security feature C).
    # TODO: real secret required for production (openssl rand -hex 32) — when
    # unset a process-stable random fallback is derived and a warning logged
    # (stored ciphertext stops decrypting across restarts/workers), the same
    # graceful-degradation pattern as url_signing_secret.
    secrets_encryption_key: str = ""
    # Public base URL of THIS backend, used to build signed download links.
    backend_url: str = "http://localhost:8000"
    # In-process sliding-window rate limiting (services/rate_limit.py);
    # disabled under pytest except in the dedicated rate-limit tests.
    # TODO: Redis-based limiter for multi-worker production deployments.
    rate_limit_enabled: bool = True
    # Max accepted upload size (counsel .docx, admin precedents), in MiB.
    max_upload_mb: int = 15

    # ---------- Specialized drafting agents + critic loop (drafting-agents) ----------
    # The critic/reviewer is an extra LLM pass after the first draft (services/
    # critic.py). When the LLM is unreachable the whole critic loop is SKIPPED
    # (graceful degradation) and the original draft proceeds unchanged.
    critic_enabled: bool = True
    # Max revision rounds after the first draft (critic round 0 reviews the
    # first draft; up to this many revise→re-review cycles follow).
    critic_max_rounds: int = 2
    # Lowest severity that triggers a revision: revise on this and anything
    # more severe, ignore everything below it ('blocking' > 'major' > 'minor').
    critic_min_severity_to_revise: str = "major"
    # Grounding verifier (lavern P1): an issue whose citation quote does NOT
    # appear in the draft is a hallucination — drop it instead of triggering a
    # useless (and expensive) revision round. Issues without a citation keep
    # their severity (local models often omit citations; dropping them would
    # neuter the critic).
    critic_grounding_enabled: bool = True
    # Evaluator gate (lavern P3, opt-in): one cheap light-tier LLM pass that
    # filters weak/speculative issues BEFORE an expensive revision round.
    critic_gate_enabled: bool = False
    # How many gestora-siloed lessons (services/lessons.py) the specialized
    # drafter injects into the generation context (top-K by weight*recency).
    drafting_lessons_top_k: int = 5
    # Below this draft↔final similarity there is something to learn; at or above
    # it the lesson-extraction pass short-circuits (little/nothing changed).
    lessons_similarity_skip_threshold: float = 0.985
    # Lessons reinforcement/decay (lavern P2): a re-extracted near-duplicate
    # lesson REINFORCES the stored one instead of piling up; at this many
    # occurrences it is promoted tentative -> confirmed.
    lessons_confirm_threshold: int = 2
    # Read-time exponential decay half-life (days since last reinforcement);
    # lessons whose effective weight falls below the floor stop being injected.
    lessons_half_life_days: float = 180.0
    lessons_min_effective_weight: float = 0.15

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
    def mistral_configured(self) -> bool:
        return bool(self.mistral_api_key)

    @property
    def grok_configured(self) -> bool:
        return bool(self.xai_api_key)

    @property
    def openai_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def llm_configured(self) -> bool:
        """Whether the SELECTED text-generation provider is usable.

        Delegates to the provider registry (services/providers) — each
        provider knows its own credential requirements. Reachability of a
        local Ollama is surfaced as a 503 at call time, not here.
        """
        from services import providers  # lazy: providers imports config

        return providers.llm_configured(self.llm_provider, self)

    @property
    def embeddings_configured(self) -> bool:
        """Whether the SELECTED embeddings provider is usable.

        Delegates to the provider registry (services/providers). When the
        provider is unreachable, RAG degrades to weight/recency ranking rather
        than failing (see services/rag.py).
        """
        from services import providers  # lazy: providers imports config

        return providers.embeddings_configured(self.embedding_provider, self)

    @property
    def drive_configured(self) -> bool:
        return bool(self.google_service_account_file)

    @property
    def resend_configured(self) -> bool:
        return bool(self.resend_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
