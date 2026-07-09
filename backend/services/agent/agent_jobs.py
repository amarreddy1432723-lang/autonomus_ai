from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from services.shared.models import AgentJob


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _log(kind: str, message: str, detail: str | None = None) -> dict:
    entry = {"kind": kind, "message": message, "timestamp": _now().isoformat()}
    if detail:
        entry["detail"] = detail
    return entry


def serialize_job(job: AgentJob) -> dict:
    return {
        "id": str(job.id),
        "code_session_id": str(job.code_session_id) if job.code_session_id else None,
        "mode": job.mode,
        "prompt": job.prompt,
        "status": job.status,
        "approval_state": job.approval_state,
        "logs": job.logs or [],
        "files_touched": job.files_touched or [],
        "commands_run": job.commands_run or [],
        "result": job.result or {},
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
) -> AgentJob:
    job = AgentJob(
        user_id=user_id,
        code_session_id=code_session_id,
        mode=mode or "code",
        prompt=prompt,
        status="running",
        approval_state=approval_state,
        started_at=_now(),
        logs=[_log("start", f"{(mode or 'code').title()} job started", prompt[:220])],
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


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


def mark_stale_agent_jobs(db: Session, user_id: UUID, code_session_id: UUID | None = None, stale_after_minutes: int = 45) -> int:
    cutoff = _now() - timedelta(minutes=stale_after_minutes)
    query = db.query(AgentJob).filter(
        AgentJob.user_id == user_id,
        AgentJob.status.in_(["running", "queued"]),
        AgentJob.started_at.isnot(None),
        AgentJob.started_at < cutoff,
    )
    if code_session_id:
        query = query.filter(AgentJob.code_session_id == code_session_id)
    jobs = query.all()
    for job in jobs:
        job.status = "interrupted"
        job.completed_at = _now()
        logs = list(job.logs or [])
        logs.append(_log("error", "Job interrupted", "Marked stale because no progress was recorded for too long."))
        job.logs = logs[-300:]
    if jobs:
        db.commit()
    return len(jobs)


def cancel_agent_job(db: Session, user_id: UUID, job_id: UUID) -> AgentJob:
    job = get_agent_job(db, user_id, job_id)
    if job.status in {"completed", "failed", "cancelled", "blocked", "timeout"}:
        return job
    job.status = "cancelled"
    job.completed_at = _now()
    logs = list(job.logs or [])
    logs.append(_log("error", "Job cancelled by user"))
    job.logs = logs[-300:]
    db.commit()
    db.refresh(job)
    return job


def reset_background_job_for_retry(db: Session, user_id: UUID, job_id: UUID) -> AgentJob:
    job = get_agent_job(db, user_id, job_id)
    if not str(job.mode or "").startswith("background_") or not job.code_session_id:
        raise HTTPException(status_code=400, detail="Only background Code jobs can be retried.")
    if job.status in {"running", "queued"}:
        raise HTTPException(status_code=409, detail="Job is already running.")
    job.status = "running"
    job.started_at = _now()
    job.completed_at = None
    job.result = {}
    job.files_touched = []
    job.commands_run = []
    logs = list(job.logs or [])
    logs.append(_log("start", "Job retried", (job.prompt or "")[:220]))
    job.logs = logs[-300:]
    db.commit()
    db.refresh(job)
    return job


def append_job_log(db: Session, job: AgentJob | None, kind: str, message: str, detail: str | None = None) -> None:
    if not job:
        return
    logs = list(job.logs or [])
    logs.append(_log(kind, message, detail))
    job.logs = logs[-300:]
    db.commit()


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
    append_job_log(db, job, "done" if status == "completed" else "error", f"Job {status}")
    db.commit()
