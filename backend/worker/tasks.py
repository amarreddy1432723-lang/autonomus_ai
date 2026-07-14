from __future__ import annotations

import socket
from datetime import datetime, timezone
from uuid import UUID

from celery.exceptions import Ignore

from worker.celery_app import celery_app
from services.agent.agent_jobs import append_job_log, complete_job, heartbeat_job, update_job_metadata
from services.agent.config import settings
from services.agent.worker import AgentWorkerQueue
from services.shared.database import SessionLocal
from services.shared.models import AgentJob


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _worker_id() -> str:
    return f"celery:{socket.gethostname()}"


def _claim_job(db, job_id: str) -> AgentJob:
    job = db.query(AgentJob).filter(AgentJob.id == UUID(str(job_id))).with_for_update().first()
    if not job:
        raise Ignore()
    if job.status in {"completed", "cancelled", "failed", "timeout", "dead_letter", "blocked"}:
        raise Ignore()
    if job.status == "paused":
        append_job_log(db, job, "info", "Job is paused; worker skipped execution.")
        raise Ignore()
    if job.status == "cancel_requested":
        complete_job(db, job, "cancelled", {"reason": "Cancelled before worker claim."})
        raise Ignore()
    job.status = "claimed"
    job.started_at = _now()
    metadata = dict(job.metadata_json or {})
    metadata["worker_id"] = _worker_id()
    metadata["worker_backend"] = "celery"
    metadata["heartbeat_at"] = _now().isoformat()
    metadata["progress"] = {
        "stage": "claimed",
        "detail": "Celery worker claimed the job.",
        "percent": 5,
        "updated_at": _now().isoformat(),
    }
    job.metadata_json = metadata
    db.commit()
    db.refresh(job)
    append_job_log(db, job, "start", "Celery worker claimed job", metadata["worker_id"])
    return job


def _record_task_id(db, job: AgentJob, task_request) -> None:
    metadata = dict(job.metadata_json or {})
    metadata["celery_task_id"] = getattr(task_request, "id", None)
    metadata["worker_backend"] = "celery"
    job.metadata_json = metadata
    db.commit()


def _run_job(job_id: str) -> dict:
    db = SessionLocal()
    try:
        job = _claim_job(db, job_id)
        worker = AgentWorkerQueue()
        worker.worker_id = _worker_id()
        worker._execute_job(db, job)
        db.refresh(job)
        return {"job_id": str(job.id), "status": job.status}
    finally:
        db.close()


def _handle_task_failure(job_id: str, exc: Exception, task_request) -> None:
    db = SessionLocal()
    try:
        job = db.query(AgentJob).filter(AgentJob.id == UUID(str(job_id))).first()
        if not job:
            return
        metadata = dict(job.metadata_json or {})
        retry_count = int(metadata.get("retry_count") or 0)
        metadata["retry_count"] = retry_count + 1
        metadata["last_error"] = str(exc)
        metadata["heartbeat_at"] = _now().isoformat()
        metadata["celery_task_id"] = getattr(task_request, "id", None)
        update_job_metadata(db, job, metadata)
        if retry_count + 1 >= int(settings.AGENT_JOB_MAX_RETRIES):
            complete_job(db, job, "dead_letter", {
                "error": str(exc),
                "retry_count": retry_count + 1,
                "max_retries": settings.AGENT_JOB_MAX_RETRIES,
                "worker_backend": "celery",
            })
        else:
            job.status = "retrying"
            job.started_at = None
            job.completed_at = None
            db.commit()
            append_job_log(db, job, "error", "Celery task failed; retry scheduled", str(exc))
    finally:
        db.close()


@celery_app.task(bind=True, name="worker.tasks.run_agent_task", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def run_agent_task(self, job_id: str) -> dict:
    try:
        db = SessionLocal()
        try:
            job = db.query(AgentJob).filter(AgentJob.id == UUID(str(job_id))).first()
            if job:
                _record_task_id(db, job, self.request)
        finally:
            db.close()
        return _run_job(job_id)
    except Ignore:
        raise
    except Exception as exc:
        _handle_task_failure(job_id, exc, self.request)
        raise


@celery_app.task(bind=True, name="worker.tasks.run_workspace_checks", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def run_workspace_checks(self, job_id: str) -> dict:
    db = SessionLocal()
    try:
        job = _claim_job(db, job_id)
        _record_task_id(db, job, self.request)
        heartbeat_job(db, job, "checks", "Workspace check job queued for execution.", 20)
        from services.agent.code_workspace import get_code_session, run_workspace_checks as run_checks

        session = get_code_session(db, job.user_id, job.code_session_id)
        result = run_checks(db, job.user_id, session, job=job)
        db.refresh(job)
        return {"job_id": str(job.id), "status": job.status, "result": result}
    except Ignore:
        raise
    except Exception as exc:
        _handle_task_failure(job_id, exc, self.request)
        raise
    finally:
        db.close()


@celery_app.task(bind=True, name="worker.tasks.run_install_deps", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def run_install_deps(self, job_id: str) -> dict:
    db = SessionLocal()
    try:
        job = _claim_job(db, job_id)
        _record_task_id(db, job, self.request)
        heartbeat_job(db, job, "install", "Dependency install job queued for execution.", 20)
        from services.agent.code_workspace import get_code_session, install_workspace_dependencies

        session = get_code_session(db, job.user_id, job.code_session_id)
        metadata = job.metadata_json or {}
        result = install_workspace_dependencies(
            db,
            job.user_id,
            session,
            metadata.get("install_command"),
            bool(metadata.get("approved")),
            int(metadata.get("timeout_seconds") or 180),
            job,
        )
        db.refresh(job)
        return {"job_id": str(job.id), "status": job.status, "result": result}
    except Ignore:
        raise
    except Exception as exc:
        _handle_task_failure(job_id, exc, self.request)
        raise
    finally:
        db.close()


@celery_app.task(bind=True, name="worker.tasks.run_preview_check", autoretry_for=(Exception,), retry_backoff=True, retry_kwargs={"max_retries": 3})
def run_preview_check(self, job_id: str) -> dict:
    db = SessionLocal()
    try:
        job = _claim_job(db, job_id)
        _record_task_id(db, job, self.request)
        heartbeat_job(db, job, "preview", "Preview verification job queued for execution.", 20)
        from services.agent.code_workspace import check_preview_url, get_code_session

        session = get_code_session(db, job.user_id, job.code_session_id)
        metadata = job.metadata_json or {}
        url = metadata.get("preview_url") or job.prompt
        result = check_preview_url(db, session, url, job)
        db.refresh(job)
        return {"job_id": str(job.id), "status": job.status, "result": result}
    except Ignore:
        raise
    except Exception as exc:
        _handle_task_failure(job_id, exc, self.request)
        raise
    finally:
        db.close()


@celery_app.task(name="worker.tasks.recover_stale_jobs")
def recover_stale_jobs() -> dict:
    from services.agent.agent_jobs import recover_stale_agent_jobs

    db = SessionLocal()
    try:
        recovered = recover_stale_agent_jobs(db, stale_after_minutes=10)
        return {"recovered": recovered}
    finally:
        db.close()
