from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID
import json
import os

from fastapi import HTTPException
from sqlalchemy.orm import Session

from services.shared.models import AgentJob, AgentJobArtifact, AgentJobLog


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _log(kind: str, message: str, detail: str | None = None) -> dict:
    entry = {"kind": kind, "message": message, "timestamp": _now().isoformat()}
    if detail:
        entry["detail"] = detail
    return entry


def _publish_job_event(job: AgentJob | None, event: str, payload: dict) -> None:
    if not job:
        return
    try:
        import redis

        redis_url = os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL") or "redis://localhost:6379/0"
        client = redis.Redis.from_url(redis_url, decode_responses=True)
        client.publish(f"job:{job.id}:logs", json.dumps({"event": event, "payload": payload}, default=str))
    except Exception:
        # DB logs are the durable source of truth; Redis pub/sub is best-effort live transport.
        pass


def serialize_job(job: AgentJob) -> dict:
    metadata = job.metadata_json or {}
    table_logs = [
        {
            "id": str(entry.id),
            "kind": entry.kind,
            "message": entry.message,
            "detail": entry.detail,
            "timestamp": entry.created_at.isoformat() if entry.created_at else None,
            "metadata": entry.metadata_json or {},
        }
        for entry in sorted(job.job_logs or [], key=lambda item: item.created_at or _now())
    ]
    table_artifacts = [
        {
            "id": str(item.id),
            "type": item.artifact_type,
            "name": item.name,
            "uri": item.uri,
            "size_bytes": item.size_bytes,
            "metadata": item.metadata_json or {},
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in sorted(job.artifacts or [], key=lambda artifact: artifact.created_at or _now())
    ]
    return {
        "id": str(job.id),
        "code_session_id": str(job.code_session_id) if job.code_session_id else None,
        "mode": job.mode,
        "prompt": job.prompt,
        "status": job.status,
        "approval_state": job.approval_state,
        "logs": table_logs or (job.logs or []),
        "artifacts": table_artifacts,
        "files_touched": job.files_touched or [],
        "commands_run": job.commands_run or [],
        "result": job.result or {},
        "metadata": metadata,
        "progress": metadata.get("progress") or {},
        "heartbeat_at": metadata.get("heartbeat_at"),
        "retry_count": int(metadata.get("retry_count") or 0),
        "worker_id": metadata.get("worker_id"),
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def create_agent_job(
    db: Session,
    user_id: UUID,
    code_session_id: UUID | None,
    mode: str,
    prompt: str,
    approval_state: str = "none",
    status: str = "running",
    metadata_json: dict | None = None,
) -> AgentJob:
    job = AgentJob(
        user_id=user_id,
        code_session_id=code_session_id,
        mode=mode or "code",
        prompt=prompt,
        status=status,
        approval_state=approval_state,
        started_at=_now() if status == "running" else None,
        metadata_json=metadata_json or {},
        logs=[_log("start", f"{(mode or 'code').title()} job started", prompt[:220])],
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    _append_job_log_row(db, job, "start", f"{(mode or 'code').title()} job started", prompt[:220])
    db.commit()
    return job


def update_job_metadata(db: Session, job: AgentJob | None, updates: dict) -> None:
    if not job:
        return
    metadata = dict(job.metadata_json or {})
    metadata.update(updates)
    job.metadata_json = metadata
    db.commit()
    _publish_job_event(job, "status", {"status": job.status, "progress": metadata.get("progress") or {}})


def heartbeat_job(db: Session, job: AgentJob | None, stage: str, detail: str | None = None, percent: int | None = None) -> None:
    if not job:
        return
    metadata = dict(job.metadata_json or {})
    progress = dict(metadata.get("progress") or {})
    progress["stage"] = stage
    progress["updated_at"] = _now().isoformat()
    if detail:
        progress["detail"] = detail
    if percent is not None:
        progress["percent"] = max(0, min(100, int(percent)))
    metadata["progress"] = progress
    metadata["heartbeat_at"] = _now().isoformat()
    job.metadata_json = metadata
    db.commit()
    _publish_job_event(job, "status", {"status": job.status, "progress": progress})


def get_agent_job(db: Session, user_id: UUID, job_id: UUID) -> AgentJob:
    job = db.query(AgentJob).filter(AgentJob.id == job_id, AgentJob.user_id == user_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Agent job not found")
    return job


def list_agent_jobs(db: Session, user_id: UUID, code_session_id: UUID | None = None, limit: int = 30) -> list[AgentJob]:
    mark_stale_agent_jobs(db, user_id, code_session_id)
    query = db.query(AgentJob).filter(AgentJob.user_id == user_id)
    if code_session_id:
        query = query.filter(AgentJob.code_session_id == code_session_id)
    return query.order_by(AgentJob.created_at.desc()).limit(limit).all()


def mark_stale_agent_jobs(db: Session, user_id: UUID, code_session_id: UUID | None = None, stale_after_minutes: int = 10) -> int:
    from .config import settings

    cutoff = _now() - timedelta(minutes=stale_after_minutes)
    query = db.query(AgentJob).filter(
        AgentJob.user_id == user_id,
        AgentJob.status.in_(["claimed", "running", "queued", "retrying", "cancel_requested"]),
    )
    if code_session_id:
        query = query.filter(AgentJob.code_session_id == code_session_id)
    jobs = query.all()
    changed = 0
    for job in jobs:
        metadata = dict(job.metadata_json or {})
        heartbeat_raw = metadata.get("heartbeat_at")
        heartbeat_at = None
        if heartbeat_raw:
            try:
                heartbeat_at = datetime.fromisoformat(str(heartbeat_raw))
                if heartbeat_at.tzinfo is None:
                    heartbeat_at = heartbeat_at.replace(tzinfo=timezone.utc)
            except ValueError:
                heartbeat_at = None
        started_at = job.started_at or job.created_at
        is_stale = (heartbeat_at and heartbeat_at < cutoff) or (started_at and started_at < cutoff)
        if not is_stale:
            continue
        changed += 1
        retry_count = int(metadata.get("retry_count") or 0)
        if retry_count >= int(settings.AGENT_JOB_MAX_RETRIES):
            job.status = "dead_letter"
            detail = "Moved to dead letter after retry limit and stale heartbeat."
        elif job.status in {"queued", "retrying"}:
            metadata["retry_count"] = retry_count + 1
            metadata["retry_queued_at"] = _now().isoformat()
            job.status = "retrying"
            job.started_at = None
            detail = "Requeued stale job for retry."
        elif job.status == "cancel_requested":
            job.status = "cancelled"
            detail = "Cancelled after stale cancellation request."
        else:
            job.status = "failed"
            detail = "job_timeout: no progress was recorded for 10 minutes."
            job.result = {"error": "job_timeout", "detail": detail}
        if job.status in {"retrying", "queued"}:
            job.completed_at = None
        else:
            job.completed_at = _now()
        metadata["heartbeat_at"] = _now().isoformat()
        metadata["progress"] = {
            **(metadata.get("progress") or {}),
            "stage": job.status,
            "detail": detail,
            "updated_at": _now().isoformat(),
        }
        job.metadata_json = metadata
        logs = list(job.logs or [])
        logs.append(_log("error", f"Job {job.status}", detail))
        job.logs = logs[-300:]
        _append_job_log_row(db, job, "error", f"Job {job.status}", detail, {"retry_count": metadata.get("retry_count", retry_count)})
    if changed:
        db.commit()
    return changed


def recover_stale_agent_jobs(db: Session, stale_after_minutes: int = 10) -> int:
    from services.shared.models import User

    total = 0
    user_ids = [
        row[0]
        for row in db.query(AgentJob.user_id)
        .filter(AgentJob.status.in_(["claimed", "running", "queued", "retrying", "cancel_requested"]))
        .distinct()
        .all()
    ]
    for user_id in user_ids:
        # Keep the user-scoped helper as the single source of lifecycle rules.
        if db.query(User.id).filter(User.id == user_id).first():
            total += mark_stale_agent_jobs(db, user_id, stale_after_minutes=stale_after_minutes)
    return total


def _revoke_celery_task(job: AgentJob, terminate: bool = False) -> None:
    task_id = (job.metadata_json or {}).get("celery_task_id")
    if not task_id:
        return
    try:
        from worker.celery_app import celery_app

        celery_app.control.revoke(str(task_id), terminate=terminate)
    except Exception:
        pass


def cancel_agent_job(db: Session, user_id: UUID, job_id: UUID) -> AgentJob:
    job = get_agent_job(db, user_id, job_id)
    if job.status in {"completed", "failed", "cancelled", "blocked", "timeout", "dead_letter"}:
        return job
    if job.status in {"claimed", "running", "retrying"}:
        job.status = "cancel_requested"
        _revoke_celery_task(job, terminate=True)
    else:
        job.status = "cancelled"
        job.completed_at = _now()
        _revoke_celery_task(job, terminate=True)
    metadata = dict(job.metadata_json or {})
    metadata["cancel_requested_at"] = _now().isoformat()
    metadata["progress"] = {
        **(metadata.get("progress") or {}),
        "stage": job.status,
        "detail": "Cancellation requested by user." if job.status == "cancel_requested" else "Cancelled by user.",
        "updated_at": _now().isoformat(),
    }
    job.metadata_json = metadata
    logs = list(job.logs or [])
    logs.append(_log("error", "Job cancellation requested" if job.status == "cancel_requested" else "Job cancelled by user"))
    job.logs = logs[-300:]
    _append_job_log_row(db, job, "error", "Job cancellation requested" if job.status == "cancel_requested" else "Job cancelled by user")
    db.commit()
    db.refresh(job)
    _publish_job_event(job, "status", serialize_job(job))
    return job


def pause_agent_job(db: Session, user_id: UUID, job_id: UUID) -> AgentJob:
    job = get_agent_job(db, user_id, job_id)
    if job.status in {"completed", "failed", "cancelled", "blocked", "timeout", "dead_letter"}:
        return job
    _revoke_celery_task(job, terminate=False)
    job.status = "paused"
    metadata = dict(job.metadata_json or {})
    metadata["paused_at"] = _now().isoformat()
    metadata["progress"] = {
        **(metadata.get("progress") or {}),
        "stage": "paused",
        "detail": "Paused by user.",
        "updated_at": _now().isoformat(),
    }
    job.metadata_json = metadata
    logs = list(job.logs or [])
    logs.append(_log("info", "Job paused by user"))
    job.logs = logs[-300:]
    _append_job_log_row(db, job, "info", "Job paused by user")
    db.commit()
    db.refresh(job)
    _publish_job_event(job, "status", serialize_job(job))
    return job


def resume_agent_job(db: Session, user_id: UUID, job_id: UUID) -> AgentJob:
    job = get_agent_job(db, user_id, job_id)
    if job.status != "paused":
        return job
    metadata = dict(job.metadata_json or {})
    metadata["resumed_at"] = _now().isoformat()
    metadata["progress"] = {
        **(metadata.get("progress") or {}),
        "stage": "queued",
        "detail": "Resumed and waiting for worker.",
        "updated_at": _now().isoformat(),
    }
    job.status = "queued"
    job.started_at = None
    job.metadata_json = metadata
    logs = list(job.logs or [])
    logs.append(_log("start", "Job resumed"))
    job.logs = logs[-300:]
    _append_job_log_row(db, job, "start", "Job resumed")
    db.commit()
    db.refresh(job)
    _publish_job_event(job, "status", serialize_job(job))
    return job


def reset_background_job_for_retry(db: Session, user_id: UUID, job_id: UUID) -> AgentJob:
    from .config import settings

    job = get_agent_job(db, user_id, job_id)
    if not str(job.mode or "").startswith("background_") or not job.code_session_id:
        raise HTTPException(status_code=400, detail="Only background Code jobs can be retried.")
    if job.status in {"running", "queued"}:
        raise HTTPException(status_code=409, detail="Job is already running.")
    metadata = dict(job.metadata_json or {})
    retry_count = int(metadata.get("retry_count") or 0)
    if retry_count >= int(settings.AGENT_JOB_MAX_RETRIES):
        raise HTTPException(status_code=409, detail="Retry limit reached for this job.")
    metadata["retry_count"] = retry_count + 1
    metadata["retry_requested_at"] = _now().isoformat()
    metadata["progress"] = {"stage": "retrying", "detail": "Retry accepted; waiting for worker.", "percent": 0, "updated_at": _now().isoformat()}
    metadata["heartbeat_at"] = None
    job.status = "retrying"
    job.started_at = None
    job.completed_at = None
    job.result = {}
    job.files_touched = []
    job.commands_run = []
    job.metadata_json = metadata
    logs = list(job.logs or [])
    logs.append(_log("start", "Job retried", (job.prompt or "")[:220]))
    job.logs = logs[-300:]
    _append_job_log_row(db, job, "start", "Job retry requested", (job.prompt or "")[:220], {"retry_count": retry_count + 1})
    db.commit()
    db.refresh(job)
    _publish_job_event(job, "status", serialize_job(job))
    return job


def append_job_log(db: Session, job: AgentJob | None, kind: str, message: str, detail: str | None = None) -> None:
    if not job:
        return
    logs = list(job.logs or [])
    logs.append(_log(kind, message, detail))
    job.logs = logs[-300:]
    _append_job_log_row(db, job, kind, message, detail)
    db.commit()
    _publish_job_event(job, "log", logs[-1])


def _append_job_log_row(db: Session, job: AgentJob | None, kind: str, message: str, detail: str | None = None, metadata: dict | None = None) -> None:
    if not job:
        return
    try:
        db.add(
            AgentJobLog(
                job_id=job.id,
                user_id=job.user_id,
                code_session_id=job.code_session_id,
                kind=kind or "info",
                message=message,
                detail=detail,
                metadata_json=metadata or {},
            )
        )
    except Exception:
        # JSON logs remain the compatibility fallback if the log table is not migrated yet.
        pass


def list_job_logs(db: Session, user_id: UUID, job_id: UUID) -> list[dict]:
    job = get_agent_job(db, user_id, job_id)
    logs = (
        db.query(AgentJobLog)
        .filter(AgentJobLog.job_id == job.id, AgentJobLog.user_id == user_id)
        .order_by(AgentJobLog.created_at.asc())
        .all()
    )
    if not logs:
        return job.logs or []
    return [
        {
            "id": str(item.id),
            "kind": item.kind,
            "message": item.message,
            "detail": item.detail,
            "timestamp": item.created_at.isoformat() if item.created_at else None,
            "metadata": item.metadata_json or {},
        }
        for item in logs
    ]


def add_job_artifact(
    db: Session,
    job: AgentJob | None,
    name: str,
    uri: str,
    artifact_type: str = "file",
    size_bytes: int | None = None,
    metadata: dict | None = None,
) -> None:
    if not job:
        return
    db.add(
        AgentJobArtifact(
            job_id=job.id,
            user_id=job.user_id,
            code_session_id=job.code_session_id,
            artifact_type=artifact_type,
            name=name,
            uri=uri,
            size_bytes=size_bytes,
            metadata_json=metadata or {},
        )
    )
    db.commit()


def list_job_artifacts(db: Session, user_id: UUID, job_id: UUID) -> list[dict]:
    job = get_agent_job(db, user_id, job_id)
    artifacts = (
        db.query(AgentJobArtifact)
        .filter(AgentJobArtifact.job_id == job.id, AgentJobArtifact.user_id == user_id)
        .order_by(AgentJobArtifact.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(item.id),
            "type": item.artifact_type,
            "name": item.name,
            "uri": item.uri,
            "size_bytes": item.size_bytes,
            "metadata": item.metadata_json or {},
            "created_at": item.created_at.isoformat() if item.created_at else None,
        }
        for item in artifacts
    ]


def complete_job(
    db: Session,
    job: AgentJob | None,
    status: str = "completed",
    result: dict | None = None,
    files_touched: list | None = None,
    commands_run: list | None = None,
    approval_state: str | None = None,
) -> None:
    if not job:
        return
    job.status = status
    job.completed_at = _now()
    if result is not None:
        job.result = result
    if files_touched is not None:
        job.files_touched = files_touched
    if commands_run is not None:
        job.commands_run = commands_run
    if approval_state is not None:
        job.approval_state = approval_state
    metadata = dict(job.metadata_json or {})
    progress = dict(metadata.get("progress") or {})
    progress["stage"] = status
    progress["percent"] = 100 if status == "completed" else progress.get("percent", 0)
    progress["updated_at"] = _now().isoformat()
    metadata["progress"] = progress
    metadata["heartbeat_at"] = _now().isoformat()
    job.metadata_json = metadata
    append_job_log(db, job, "done" if status == "completed" else "error", f"Job {status}")
    db.commit()
    _publish_job_event(job, "done" if status in {"completed", "failed", "cancelled", "timeout", "dead_letter", "blocked"} else "status", serialize_job(job))
