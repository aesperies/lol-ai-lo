"""In-process asyncio job runner for document generation.

Jobs run as asyncio tasks inside the API process — no extra infrastructure —
while every state change (status, attempts, last_error, timestamps) is
persisted to the ``generation_jobs`` table through the db layer, so jobs are
pollable via the API and survive inspection across requests.

Retry policy: exponential backoff (base*1s, base*4s; max_attempts=3 by
default). The base is configurable via JOB_BACKOFF_BASE and pinned to ~0
under pytest so the suite stays fast.

TODO: single-worker by design. Swap this runner for Celery/Redis (or another
external queue) when scaling beyond one backend worker — the enqueue/poll
contract and the persisted job rows are queue-agnostic.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional

from config import get_settings
from models.schema import (
    AuditAction,
    AuditResourceType,
    GenerationJobStatus,
    RequestStatus,
)
from services import db as dbmod

logger = logging.getLogger("lolailo.jobs")

# Re-invoked on every retry: must return a FRESH awaitable each call.
CoroutineFactory = Callable[[], Awaitable[Any]]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobRunner:
    """Enqueue + execute generation jobs with retries and persisted state."""

    def __init__(self) -> None:
        self._tasks: dict[str, asyncio.Task] = {}

    def enqueue(
        self,
        db: dbmod.Database,
        *,
        request_id: str,
        factory: CoroutineFactory,
        on_final_failure: Optional[Callable[[Exception], None]] = None,
        max_attempts: int = 3,
    ) -> dict[str, Any]:
        """Create a 'queued' job row and start running it on the event loop."""
        job = db.insert(
            "generation_jobs",
            {
                "request_id": request_id,
                "status": GenerationJobStatus.queued.value,
                "attempts": 0,
                "max_attempts": max_attempts,
                "last_error": None,
                "started_at": None,
                "finished_at": None,
            },
        )
        task = asyncio.create_task(self._run(db, job["id"], factory, on_final_failure))
        self._tasks[job["id"]] = task
        task.add_done_callback(lambda _t: self._tasks.pop(job["id"], None))
        return job

    def enqueue_background(
        self,
        coro_factory: CoroutineFactory,
        *,
        label: str = "background",
    ) -> Optional[asyncio.Task]:
        """Fire-and-forget a best-effort async task on the event loop.

        Unlike :meth:`enqueue` this persists NO ``generation_jobs`` row and has
        no retries — it is for off-the-request-thread work that must NEVER block
        or affect delivery (e.g. lessons extraction, services/lessons.py). Any
        exception is swallowed + logged. Returns the task (or None when there is
        no running loop, in which case the work is silently skipped)."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("No running loop for background task %s; skipped.", label)
            return None

        async def _runner() -> None:
            try:
                await coro_factory()
            except Exception:  # noqa: BLE001 — best-effort, never propagate
                logger.exception("Background task %s failed (swallowed).", label)

        task = loop.create_task(_runner())
        key = f"bg:{label}:{id(task)}"
        self._tasks[key] = task
        task.add_done_callback(lambda _t: self._tasks.pop(key, None))
        return task

    async def _run(
        self,
        db: dbmod.Database,
        job_id: str,
        factory: CoroutineFactory,
        on_final_failure: Optional[Callable[[Exception], None]],
    ) -> None:
        settings = get_settings()
        max_attempts = (db.get("generation_jobs", job_id) or {}).get("max_attempts", 3)

        for attempt in range(1, max_attempts + 1):
            fields: dict[str, Any] = {
                "status": GenerationJobStatus.running.value,
                "attempts": attempt,
            }
            if attempt == 1:
                fields["started_at"] = _now()
            db.update("generation_jobs", job_id, fields)
            try:
                await factory()
            except Exception as exc:  # noqa: BLE001 — any pipeline error is retryable
                db.update("generation_jobs", job_id, {"last_error": str(exc)})
                if attempt >= max_attempts:
                    db.update(
                        "generation_jobs",
                        job_id,
                        {"status": GenerationJobStatus.failed.value, "finished_at": _now()},
                    )
                    logger.error("Generation job %s failed after %s attempts: %s", job_id, attempt, exc)
                    if on_final_failure is not None:
                        try:
                            on_final_failure(exc)
                        except Exception:  # noqa: BLE001
                            logger.exception("on_final_failure handler raised for job %s", job_id)
                    return
                # Exponential backoff: base*1s, base*4s (base ~0 under pytest).
                await asyncio.sleep(settings.job_backoff_base * (4 ** (attempt - 1)))
            else:
                db.update(
                    "generation_jobs",
                    job_id,
                    {"status": GenerationJobStatus.succeeded.value, "finished_at": _now()},
                )
                return


_ORPHAN_ERROR = (
    "El proceso se reinició durante la generación (deploy/restart) y el job "
    "quedó huérfano; marcado como failed en el arranque."
)


def sweep_orphaned_jobs(db: Optional[dbmod.Database] = None) -> int:
    """Startup sweep (docs/ESCALADO.md §3): fail every queued/running job.

    Jobs are in-process asyncio tasks, so a job still 'queued'/'running' when
    the process STARTS belongs to a previous process killed mid-generation
    (Railway deploy/restart) — without this, its request stays 'generating'
    forever. For each orphan, mirroring the on_final_failure path in
    api/documents.py: mark the job failed, revert the request 'generating' ->
    'confirmed' so the client can retry, audit the failure and notify the
    request owner. Returns the number of jobs swept.

    Single-worker by design, like the runner itself: a second worker booting
    while another is mid-generation would sweep the live job.
    """
    from auth import gestora_of_request
    from services import audit, notifications
    from services.workflow import transition

    db = db if db is not None else dbmod.get_db()
    swept = 0
    for status in (GenerationJobStatus.queued, GenerationJobStatus.running):
        for job in db.unscoped_select("generation_jobs", status=status.value):
            db.update(
                "generation_jobs",
                job["id"],
                {
                    "status": GenerationJobStatus.failed.value,
                    "last_error": _ORPHAN_ERROR,
                    "finished_at": _now(),
                },
            )
            swept += 1
            row = db.get("requests", job["request_id"])
            if row is None or row["status"] != RequestStatus.generating.value:
                continue  # nothing stuck to recover (e.g. refinement flows)
            gestora_id = gestora_of_request(db, row)
            transition(db, row, RequestStatus.confirmed)
            audit.log_action(
                db,
                user=None,  # system action (the sweep has no acting user)
                action=AuditAction.document_generated,
                resource_type=AuditResourceType.request,
                resource_id=row["id"],
                gestora_id=gestora_id,
                metadata={"failed": True, "orphaned": True, "job_id": job["id"], "error": _ORPHAN_ERROR},
            )
            if row.get("user_id"):
                notifications.notify(
                    db,
                    user_id=row["user_id"],
                    kind=notifications.KIND_GENERATION_FAILED,
                    title="La generación se interrumpió por un reinicio del servidor",
                    body="Puedes reintentarla desde la solicitud; el estado ha vuelto a 'confirmado'.",
                    request_id=row["id"],
                    gestora_id=gestora_id,
                )
    if swept:
        logger.warning("Startup sweep: %s orphaned generation job(s) marked failed.", swept)
    return swept


def latest_job(db: dbmod.Database, request_id: str) -> Optional[dict[str, Any]]:
    """Most recent generation job for a request (select() sorts by created_at)."""
    rows = db.select("generation_jobs", request_id=request_id)
    return rows[-1] if rows else None


_runner: Optional[JobRunner] = None


def get_runner() -> JobRunner:
    global _runner
    if _runner is None:
        _runner = JobRunner()
    return _runner
