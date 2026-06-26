"""imap-mcp-server module."""

# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

# Covers: FR-19

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import update

from cloud_dog_jobs import (
    FallbackAction,
    FallbackPolicy,
    FallbackPolicyManager,
    JobQueue,
    JobStatus,
    RedisQueueBackend,
    SQLQueueBackend,
    Worker,
)
from cloud_dog_jobs.backends.base import QueueBackend
from cloud_dog_jobs.domain.models import Job
from cloud_dog_jobs.maintenance.reaper import MaintenanceReaper
from cloud_dog_jobs.observability.audit import AuditEmitter
from cloud_dog_logging import get_audit_logger, get_logger, setup_logging
from cloud_dog_logging.audit_schema import Actor, Target

from imap_hub_core.audit.logger import default_app_log_path
from imap_hub_core.config.access import runtime_config_value
from imap_hub_core.jobs.models import JobEnvelope, JobStateRecord
from imap_hub_core.storage_paths import join_fs_path
from imap_hub_server.logging_runtime import ensure_runtime_log_permissions

JobHandler = Callable[[JobEnvelope], dict[str, Any] | None]


class _PlatformAuditEmitter(AuditEmitter):
    """Bridge cloud_dog_jobs AuditEmitter to cloud_dog_logging audit logger."""

    def __init__(self) -> None:
        super().__init__()
        self._audit_logger = get_audit_logger()

    def emit(self, action: str, outcome: str, *, service: str = "imap-mcp-server") -> dict:
        """Emit a PS-75 job audit event via cloud_dog_logging."""
        event = super().emit(action, outcome, service=service)
        actor = Actor(type="service", id=service)
        target = Target(type="queue", id="imap")
        self._audit_logger.log_crud(
            actor=actor, action=action, target=target, outcome=outcome,
        )
        return event


def _ts(value: Any) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    return value


_SQLITE_SCHEME = "sqlite"
_JOB_STATE_KEY = "_imap_mcp_job_state"


def _default_sql_url(config: Any) -> str:
    """Build SQL URL from config (PS-75 JQ5 — zero hardcoded backend URLs)."""
    configured = (config.jobs.backend.sql_url or "").strip()
    if configured:
        return configured
    data_dir = config.server.storage.data_dir
    return f"{_SQLITE_SCHEME}:///{join_fs_path(data_dir, 'imap_jobs.db')}"


def _build_backend(config: Any) -> tuple[str, QueueBackend]:
    preferred = config.jobs.backend.preferred
    if preferred == "memory":
        raise ValueError(
            "In-memory queue backend is not supported in production. "
            "Use jobs.backend.preferred=sql (default) or redis."
        )
    if preferred == "redis":
        redis_url = (config.jobs.backend.redis_url or "").strip()
        if not redis_url:
            raise ValueError("jobs_backend_redis_url_required")
        return preferred, RedisQueueBackend(redis_url)

    sql_url = _default_sql_url(config)
    return "sql", SQLQueueBackend(sql_url)


def _service_job_state(job: Job | None) -> dict[str, Any]:
    if job is None or not isinstance(job.payload, dict):
        return {}
    value = job.payload.get(_JOB_STATE_KEY)
    return dict(value) if isinstance(value, dict) else {}


@dataclass(slots=True)
class JobsRuntime:
    """Queue/worker runtime for the service."""

    backend_name: str
    backend: QueueBackend
    queue: JobQueue
    worker: Worker
    server_id: str
    worker_id: str
    retry_max_attempts: int
    maintenance: MaintenanceReaper
    claim_timeout_seconds: int
    max_age_seconds: int
    dead_letter_queue: str
    fallback_manager: FallbackPolicyManager | None
    logger: Any
    _audit_logger: Any = None

    def __post_init__(self) -> None:
        if self._audit_logger is None:
            object.__setattr__(self, "_audit_logger", get_audit_logger())

    # ------------------------------------------------------------------
    # PS-75 Audit (JQ15)
    # ------------------------------------------------------------------

    def _emit_audit(
        self, action: str, outcome: str, *, job_id: str = "", details: dict[str, Any] | None = None,
    ) -> None:
        """Emit a PS-75 compliant audit event for a job lifecycle action."""
        actor = Actor(type="service", id=self.server_id)
        target = Target(type="queue", id=str(job_id or "imap"))
        self._audit_logger.log_crud(
            actor=actor, action=action, target=target, outcome=outcome,
            **({"details": details} if details else {}),
        )

    # ------------------------------------------------------------------
    # Progress tracking (JQ12)
    # ------------------------------------------------------------------

    def update_progress(self, job_id: str, *, percentage: float, stage: str = "") -> None:
        """Update progress tracking for a job."""
        progress = {
            "percentage": round(min(100.0, max(0.0, float(percentage))), 1),
            "stage": stage,
            "updated_at_utc": _ts(datetime.now(timezone.utc)),
        }
        update_progress = getattr(self.backend, "update_progress", None)
        if callable(update_progress):
            update_progress(job_id, progress)
            return
        self._update_job_state(job_id, progress=progress)

    # ------------------------------------------------------------------
    # Cancellation (JQ8.4)
    # ------------------------------------------------------------------

    def cancel_job(self, job_id: str) -> bool:
        """Cancel a queued or running job."""
        ok = self.queue.cancel(job_id)
        if ok:
            self._emit_audit("job.cancel", "success", job_id=job_id)
        return ok

    def is_cancelled(self, job_id: str) -> bool:
        """Check if a job has been cancelled (cooperative cancellation)."""
        job = self.backend.get(job_id)
        if job is None:
            return False
        return job.status == JobStatus.CANCELLED or job.status.value == JobStatus.CANCELLED.value

    # ------------------------------------------------------------------
    # Dead-letter (JQ7.3)
    # ------------------------------------------------------------------

    def dead_letter_job(self, job_id: str, *, error: str) -> str | None:
        """Move an exhausted-retry job to the dead-letter queue."""
        job = self.backend.get(job_id)
        if job is None or self.fallback_manager is None:
            return None
        dl_policy = FallbackPolicy(
            action=FallbackAction.DEAD_LETTER,
            dead_letter_queue=self.dead_letter_queue,
        )
        self.fallback_manager.set_policy(f"__dl_{job.job_type}", dl_policy)
        job_copy = Job(
            job_id=job.job_id, job_type=f"__dl_{job.job_type}", queue_name=job.queue_name,
            payload=job.payload, status=job.status, priority=job.priority,
            created_at=job.created_at, updated_at=job.updated_at,
            app_id=job.app_id, host_id=job.host_id, worker_id=job.worker_id,
            correlation_id=job.correlation_id,
        )
        decision = self.fallback_manager.apply(self.backend, job_copy, RuntimeError(error))
        self._emit_audit(
            "job.dead_letter", "success", job_id=job_id,
            details={"error": error[:200], "dead_letter_job_id": decision.dead_letter_job_id},
        )
        return decision.dead_letter_job_id

    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        """Register a typed handler against the package worker runtime."""

        def _wrapped(context: Any) -> None:
            job = context.job
            attempt = int(_service_job_state(job).get("attempts") or job.attempt or 0) + 1
            self._update_job_state(
                job.job_id,
                attempts=attempt,
                last_error="",
                result={},
                started_at_utc=_ts(datetime.now(timezone.utc)),
            )
            self.logger.info(
                "job_started",
                event="job_started",
                component="imap_hub_core.jobs.runtime",
                source_identifier=self.worker_id,
                outcome="running",
                actor_id=self.worker_id,
                job_id=job.job_id,
                job_type=job.job_type,
                queue_name=job.queue_name,
                attempt=attempt,
                server_id=self.server_id,
                worker_id=self.worker_id,
            )
            self._emit_audit(
                "job.claim", "success", job_id=job.job_id,
                details={"job_type": job.job_type, "attempt": attempt},
            )
            self.update_progress(job.job_id, percentage=10.0, stage="started")
            try:
                result = handler(JobEnvelope.from_job(job))
            except Exception as exc:
                self._update_job_state(
                    job.job_id,
                    attempts=attempt,
                    last_error=str(exc),
                    finished_at_utc=_ts(datetime.now(timezone.utc)),
                )
                raise
            self.update_progress(job.job_id, percentage=100.0, stage="completed")
            self._update_job_state(
                job.job_id,
                attempts=attempt,
                last_error="",
                result=_json_safe(result) or {},
                finished_at_utc=_ts(datetime.now(timezone.utc)),
            )

        self.worker.register_handler(job_type, _wrapped)

    def submit(self, envelope: JobEnvelope) -> str:
        """Submit one job through the platform queue backend."""
        effective_envelope = envelope
        if effective_envelope.max_attempts is None:
            effective_envelope = envelope.model_copy(update={"max_attempts": self.retry_max_attempts})
        job_id = self.queue.submit(
            effective_envelope.to_job_request(
                server_id=self.server_id,
                default_max_attempts=self.retry_max_attempts,
            )
        )
        job = self.queue.get(job_id)
        if job is None:
            raise RuntimeError("submitted_job_not_found")
        self.logger.info(
            "job_submitted",
            event="job_submitted",
            component="imap_hub_core.jobs.runtime",
            source_identifier=self.worker_id,
            outcome="queued",
            actor_id=self.worker_id,
            job_id=job_id,
            job_type=effective_envelope.job_type,
            queue_name=effective_envelope.queue_name,
            server_id=self.server_id,
            worker_id=self.worker_id,
        )
        self._emit_audit(
            "job.submit", "success", job_id=job_id,
            details={"job_type": effective_envelope.job_type},
        )
        return job_id

    def get_job(self, job_id: str) -> Job | None:
        """Return one backend job."""
        return self.queue.get(job_id)

    def get_state(self, job_id: str) -> JobStateRecord | None:
        """Return one platform-derived state record."""
        job = self.backend.get(job_id)
        if job is None:
            return None
        return self._state_from_job(job)

    def get_job_record(self, job_id: str) -> dict[str, Any] | None:
        """Return one enriched job record for API/WebUI consumption."""
        job = self.get_job(job_id)
        state = self.get_state(job_id)
        if job is None and state is None:
            return None
        return self._job_record(job, state)

    def list_jobs(self) -> list[JobStateRecord]:
        """Return all platform-derived state records."""
        return sorted(
            (self._state_from_job(job) for job in self.backend.all_jobs()),
            key=lambda item: (item.created_at_utc, item.job_id),
        )

    def list_job_records(self) -> list[dict[str, Any]]:
        """Return enriched job records for all tracked jobs."""
        return [
            self._job_record(job, self._state_from_job(job))
            for job in sorted(self.backend.all_jobs(), key=lambda item: (item.created_at, item.job_id))
        ]

    def queue_status(self) -> dict[str, Any]:
        """Return queue and local state counters for health/reporting."""
        return {
            "backend": self.backend_name,
            "healthy": self.queue.health(),
            "counts": self.backend.get_queue_status(),
            "tracked_jobs": len(self.backend.all_jobs()),
            "server_id": self.server_id,
        }

    def retry_job(self, job_id: str) -> bool:
        """Return a terminal job to the queued state."""
        job = self.backend.get(job_id)
        if job is None:
            return False
        if job.status not in {
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.TIMEOUT,
            JobStatus.DEAD_LETTERED,
            JobStatus.TTL_EXPIRED,
        }:
            return False
        ok = self.backend.update_status(job_id, JobStatus.QUEUED.value)
        if ok:
            self._emit_audit("job.retry", "success", job_id=job_id)
        return ok

    def archive_job(self, job_id: str) -> bool:
        """Archive a terminal job while retaining its record."""
        job = self.backend.get(job_id)
        if job is None:
            return False
        if job.status not in {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
            JobStatus.CANCELLED,
            JobStatus.TIMEOUT,
            JobStatus.DEAD_LETTERED,
            JobStatus.TTL_EXPIRED,
            JobStatus.ARCHIVED,
        }:
            return False
        ok = self.backend.update_status(job_id, JobStatus.ARCHIVED.value)
        if ok:
            self._emit_audit("job.archive", "success", job_id=job_id)
        return ok

    def run_once(self) -> bool:
        """Process one queued job and apply configured retry behaviour."""
        seen_job_ids: set[str] = set()
        while True:
            queued = self.queue.list(limit=1)
            if not queued:
                return False
            job_id = queued[0].job_id
            if job_id in seen_job_ids:
                return False
            seen_job_ids.add(job_id)
            try:
                processed = self.worker.run_once()
            except Exception as exc:  # noqa: BLE001
                self._retry_or_finish(job_id, str(exc))
                return True

            if not processed:
                continue
            return True

    def recover_stale_jobs(self) -> dict[str, int]:
        """Run reaper maintenance and requeue retryable timed-out jobs."""
        summary = self.maintenance.run_sweep(
            ttl_seconds=self.max_age_seconds,
            retention_seconds=self.max_age_seconds,
        )
        requeued = 0
        for job in self.backend.all_jobs():
            if job.status not in {JobStatus.FAILED, JobStatus.TIMEOUT}:
                continue
            state = self._state_from_job(job)
            if state.attempts >= state.max_attempts:
                continue
            if self.backend.release(job.job_id):
                requeued += 1
        summary["requeued"] = requeued
        return summary

    def drain(self, *, max_jobs: int | None = None) -> int:
        """Run queued work until empty or until the optional cap is reached."""
        processed = 0
        while True:
            if max_jobs is not None and processed >= max_jobs:
                return processed
            if not self.run_once():
                return processed
            processed += 1

    def last_result(self, job_id: str) -> dict[str, Any] | None:
        """Return the persisted handler result for a job."""
        job = self.backend.get(job_id)
        result = self._result_from_job(job)
        return result if isinstance(result, dict) else None

    def close(self) -> None:
        """Dispose backend resources when supported."""
        close = getattr(self.backend, "close", None)
        if callable(close):
            close()

    def _state_from_job(self, job: Job) -> JobStateRecord:
        envelope = JobEnvelope.from_job(job)
        service_state = _service_job_state(job)
        progress = (
            dict(job.progress)
            if isinstance(job.progress, dict)
            else dict(service_state.get("progress") or {})
        )
        claimed_by = job.claimed_by or self._worker_claim_from_job(job)
        return JobStateRecord(
            job_id=job.job_id,
            job_type=job.job_type,
            queue_name=job.queue_name,
            profile_id=envelope.profile_id,
            status=job.status.value,
            claimed_by=claimed_by,
            attempts=int(service_state.get("attempts") or job.attempt or 0),
            max_attempts=envelope.max_attempts or job.max_attempts or self.retry_max_attempts,
            last_error=str(service_state.get("last_error") or self._error_from_job(job) or "") or None,
            progress_pct=float(progress.get("percentage") or 0.0),
            progress_stage=str(progress.get("stage") or ""),
            server_id=envelope.server_id or self.server_id,
            created_at_utc=_ts(job.created_at),
            updated_at_utc=_ts(job.updated_at),
        )

    @staticmethod
    def _worker_claim_from_job(job: Job | None) -> str | None:
        if job is None or not job.host_id or not job.worker_id:
            return None
        return f"{job.host_id}:{job.worker_id}"

    @staticmethod
    def _error_from_job(job: Job | None) -> str:
        if job is None or not job.last_error:
            return ""
        if isinstance(job.last_error, dict):
            return str(job.last_error.get("message") or job.last_error.get("error") or "").strip()
        return str(job.last_error).strip()

    @staticmethod
    def _result_from_job(job: Job | None) -> Any:
        if job is None:
            return None
        service_state = _service_job_state(job)
        if "result" in service_state:
            return service_state["result"]
        return getattr(job, "result_ref", None)

    def _update_job_state(self, job_id: str, **updates: Any) -> None:
        job = self.backend.get(job_id)
        if job is None:
            return
        payload = dict(job.payload) if isinstance(job.payload, dict) else {}
        service_state = dict(payload.get(_JOB_STATE_KEY) or {})
        service_state.update({key: _json_safe(value) for key, value in updates.items()})
        payload[_JOB_STATE_KEY] = service_state

        repo = getattr(self.backend, "_repo", None)
        jobs_table = getattr(repo, "jobs", None)
        engine = getattr(repo, "engine", None)
        if jobs_table is not None and engine is not None:
            with engine.begin() as conn:
                conn.execute(
                    update(jobs_table)
                    .where(jobs_table.c.job_id == job_id)
                    .values(payload=payload, updated_at=datetime.now(tz=timezone.utc))
                )
            return

        job.payload = payload
        job.updated_at = datetime.now(timezone.utc)

    def _job_record(self, job: Job | None, state: JobStateRecord | None) -> dict[str, Any]:
        payload = dict(job.payload) if job is not None and isinstance(job.payload, dict) else {}
        request_payload = (
            dict(payload.get("payload"))
            if isinstance(payload.get("payload"), dict)
            else payload
        )
        mailbox = str(
            request_payload.get("mailbox")
            or request_payload.get("folder")
            or request_payload.get("mailbox_pattern")
            or request_payload.get("mailbox_name")
            or ""
        ).strip()
        last_error = state.last_error if state is not None else ""
        if not last_error:
            last_error = self._error_from_job(job)
        service_state = _service_job_state(job)
        progress = (
            dict(job.progress)
            if job is not None and isinstance(job.progress, dict)
            else dict(service_state.get("progress") or {})
        )
        result = self._result_from_job(job)
        claimed_by = state.claimed_by if state is not None else None
        if claimed_by is None and job is not None:
            claimed_by = job.claimed_by or self._worker_claim_from_job(job)

        return {
            "job_id": state.job_id if state is not None else job.job_id if job is not None else "",
            "job_type": state.job_type if state is not None else job.job_type if job is not None else "",
            "queue_name": state.queue_name if state is not None else job.queue_name if job is not None else "",
            "profile_id": state.profile_id if state is not None else str(payload.get("profile_id") or request_payload.get("profile_id") or "").strip(),
            "mailbox": mailbox,
            "status": state.status if state is not None else job.status.value if job is not None else "",
            "claimed_by": claimed_by,
            "attempts": state.attempts if state is not None else job.attempt if job is not None else 0,
            "attempt": job.attempt if job is not None else state.attempts if state is not None else 0,
            "max_attempts": state.max_attempts if state is not None else job.max_attempts if job is not None else 0,
            "priority": job.priority if job is not None else 0,
            "last_error": last_error,
            "server_id": state.server_id if state is not None else self.server_id,
            "created_at_utc": state.created_at_utc if state is not None else _ts(job.created_at) if job is not None else "",
            "updated_at_utc": state.updated_at_utc if state is not None else _ts(job.updated_at) if job is not None else "",
            "started_at_utc": _ts(job.started_at) if job is not None and job.started_at is not None else "",
            "finished_at_utc": _ts(job.finished_at) if job is not None and job.finished_at is not None else "",
            "correlation_id": (
                (job.correlation_id if job is not None else "")
                or str(payload.get("correlation_id") or request_payload.get("correlation_id") or "").strip()
            ),
            "user_id": (
                (job.user_id if job is not None else "")
                or str(payload.get("user_id") or request_payload.get("user_id") or "").strip()
            ),
            "request_source": (
                (job.request_source if job is not None else "")
                or str(payload.get("request_source") or request_payload.get("request_source") or "").strip()
            ),
            "request_auth_method": (
                (job.request_auth_method if job is not None else "")
                or str(payload.get("request_auth_method") or request_payload.get("request_auth_method") or "").strip()
            ),
            "request_auth_identity": (
                (job.request_auth_identity if job is not None else "")
                or str(payload.get("request_auth_identity") or request_payload.get("request_auth_identity") or "").strip()
            ),
            "trace_id": (
                (job.trace_id if job is not None else "")
                or str(payload.get("trace_id") or request_payload.get("trace_id") or "").strip()
            ),
            "progress_pct": progress.get("percentage", state.progress_pct if state is not None else 0.0),
            "progress_stage": progress.get("stage", state.progress_stage if state is not None else ""),
            "payload": _json_safe(request_payload),
            "result": _json_safe(result),
        }

    def _retry_or_finish(self, job_id: str, last_error: str) -> None:
        job = self.backend.get(job_id)
        if job is None:
            return
        state = self._state_from_job(job)
        if job.status not in {JobStatus.RETRY_WAIT, JobStatus.TIMEOUT}:
            return
        if state.attempts >= state.max_attempts:
            self.backend.update_status(job_id, JobStatus.FAILED.value)
            self.logger.warning(
                "job_failed_final",
                event="job_failed_final",
                component="imap_hub_core.jobs.runtime",
                source_identifier=self.worker_id,
                outcome="failure",
                actor_id=self.worker_id,
                job_id=job_id,
                job_type=job.job_type,
                attempt=state.attempts,
                server_id=self.server_id,
                worker_id=self.worker_id,
                error=last_error,
            )
            self._emit_audit(
                "job.transition", "success", job_id=job_id,
                details={"from_state": "retry_wait", "to_state": "failed"},
            )
            # Dead-letter exhausted-retry jobs (PS-75 JQ7.3)
            dl_job_id = self.dead_letter_job(job_id, error=last_error)
            if dl_job_id:
                self.logger.info(
                    "job_dead_lettered",
                    event="job_dead_lettered",
                    component="imap_hub_core.jobs.runtime",
                    job_id=job_id,
                    dead_letter_job_id=dl_job_id,
                    dead_letter_queue=self.dead_letter_queue,
                )
            return
        self.backend.release(job_id)
        self.logger.warning(
            "job_requeued",
            event="job_requeued",
            component="imap_hub_core.jobs.runtime",
            source_identifier=self.worker_id,
            outcome="partial",
            actor_id=self.worker_id,
            job_id=job_id,
            job_type=job.job_type,
            attempt=state.attempts,
            server_id=self.server_id,
            worker_id=self.worker_id,
            error=last_error,
        )
        self._emit_audit(
            "job.transition", "success", job_id=job_id,
            details={"from_state": "retry_wait", "to_state": "queued", "attempt": state.attempts},
        )


def build_jobs_runtime(
    config: Any,
    *,
    worker_suffix: str = "main",
    app_log_path: str | None = None,
    audit_log_path: str | None = None,
    integrity_log_path: str | None = None,
    environment: str | None = None,
) -> JobsRuntime:
    """Construct the service job runtime using the configured backend."""
    backend_name, backend = _build_backend(config)
    server_id = config.server.server_id
    worker_id = f"{server_id}-{worker_suffix}"
    resolved_app_log_path = app_log_path or default_app_log_path(config.server.audit.log_path)
    setup_logging(
        {
            "service_name": "imap-mcp-server",
            "service_instance": server_id,
            "environment": environment
            or runtime_config_value(config, "log.environment", "CLOUD_DOG_ENVIRONMENT")
            or "unknown",
            "log": {
                "format": "json",
                "console": False,
                "app_log": resolved_app_log_path,
                **({"audit_log": audit_log_path} if audit_log_path else {}),
                **(
                    {"integrity": {"enabled": True, "log_file": integrity_log_path}}
                    if integrity_log_path
                    else {}
                ),
            },
        }
    )
    ensure_runtime_log_permissions(
        app_log_path=resolved_app_log_path,
        audit_log_path=audit_log_path,
        integrity_log_path=integrity_log_path,
    )
    logger = get_logger("imap.jobs")
    audit_emitter = _PlatformAuditEmitter()
    queue = JobQueue(
        backend,
        payload_max_bytes=config.jobs.payload_max_bytes,
        audit_emitter=audit_emitter,
    )
    dead_letter_queue_name = getattr(config.jobs, "dead_letter_queue", "imap_dead_letter")
    fallback = FallbackPolicyManager()
    def _set_fallback(job_type: str) -> None:
        if config.jobs.retry.max_attempts > 1:
            fallback.set_policy(job_type, FallbackPolicy(action=FallbackAction.RETRY))
        else:
            fallback.set_policy(job_type, FallbackPolicy(action=FallbackAction.DEAD_LETTER, dead_letter_queue=dead_letter_queue_name))
    job_type = "sync"; _set_fallback(job_type)
    job_type = "index"; _set_fallback(job_type)
    job_type = "archive"; _set_fallback(job_type)
    job_type = "mail"; _set_fallback(job_type)
    worker = Worker(
        backend,
        host_id=server_id,
        worker_id=worker_id,
        fallback_policies=fallback,
    )
    maintenance = MaintenanceReaper(
        backend,
        claim_timeout_seconds=config.jobs.maintenance.claim_timeout_seconds,
    )
    return JobsRuntime(
        backend_name=backend_name,
        backend=backend,
        queue=queue,
        worker=worker,
        server_id=server_id,
        worker_id=worker_id,
        retry_max_attempts=config.jobs.retry.max_attempts,
        maintenance=maintenance,
        claim_timeout_seconds=config.jobs.maintenance.claim_timeout_seconds,
        max_age_seconds=config.jobs.maintenance.max_age_seconds,
        dead_letter_queue=dead_letter_queue_name,
        fallback_manager=fallback,
        logger=logger,
    )
