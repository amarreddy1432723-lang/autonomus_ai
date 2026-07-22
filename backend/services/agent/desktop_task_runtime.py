from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusDesktopSession,
    ArceusEvent,
    ArceusMission,
    ArceusOutboxMessage,
    ArceusTask,
    ArceusTaskAttempt,
    ArceusWorkerLease,
)
from services.shared.database import get_db

from .arceus_runtime.api.dependencies import RequestContext, require_permission
from .task_runtime.dispatcher import dispatch_mission


router = APIRouter(tags=["desktop-task-runtime"])

DEFAULT_HEARTBEAT_SECONDS = 30
DESKTOP_SESSION_TTL_SECONDS = 90
TASK_LEASE_SECONDS = 90


class DesktopCapabilities(BaseModel):
    filesystem_read: bool = False
    filesystem_write: bool = False
    terminal: bool = False
    git: bool = False
    docker: bool = False
    network: bool = False


class DesktopRuntimeInfo(BaseModel):
    platform: str = Field(min_length=2, max_length=80)
    architecture: str = Field(min_length=2, max_length=80)
    app_version: str = Field(min_length=1, max_length=80)


class DesktopSessionRegisterRequest(BaseModel):
    device_id: str = Field(min_length=2, max_length=160)
    workspace_id: str = Field(min_length=1, max_length=240)
    repository_id: str | None = Field(default=None, max_length=240)
    capabilities: DesktopCapabilities = Field(default_factory=DesktopCapabilities)
    runtime: DesktopRuntimeInfo


class DesktopSessionResponse(BaseModel):
    desktop_session_id: str
    status: str
    expires_at: str
    heartbeat_interval_seconds: int


class DesktopSessionHeartbeatRequest(BaseModel):
    active_mission_id: UUID | None = None
    active_task_id: UUID | None = None
    repository_available: bool = True


class DesktopSessionHeartbeatResponse(BaseModel):
    desktop_session_id: str
    status: str
    expires_at: str


class TaskClaimRequest(BaseModel):
    desktop_session_id: UUID
    expected_task_version: int = Field(ge=1)
    ttl_seconds: int = Field(default=TASK_LEASE_SECONDS, ge=30, le=300)


class TaskClaimResponse(BaseModel):
    task_id: str
    status: str
    lease_id: str
    lease_token: str
    lease_expires_at: str
    version: int


class TaskRenewLeaseRequest(BaseModel):
    lease_token: str = Field(min_length=10, max_length=255)
    ttl_seconds: int = Field(default=TASK_LEASE_SECONDS, ge=30, le=300)


class TaskContextResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    context_package_id: str
    mission_id: str
    task_id: str
    goal: str
    task: dict[str, Any]
    repository_context: dict[str, Any]
    constraints: list[str]
    permitted_tools: list[str]
    prohibited_paths: list[str]
    expected_output_schema: dict[str, Any]
    token_estimate: int
    created_at: str


class StructuredTaskResult(BaseModel):
    status: str = Field(pattern="^(completed|failed)$")
    summary: str = Field(min_length=1, max_length=4_000)
    files: list[str] = Field(default_factory=list, max_length=200)
    changes: list[dict[str, Any] | str] = Field(default_factory=list, max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=100)
    next_recommendations: list[str] = Field(default_factory=list, max_length=100)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskCompleteRequest(BaseModel):
    lease_token: str = Field(min_length=10, max_length=255)
    result: StructuredTaskResult


class TaskCompleteResponse(BaseModel):
    task_id: str
    task_key: str
    task_status: str
    mission_id: str
    mission_status: str
    released_tasks: list[str] = Field(default_factory=list)
    completed_tasks: list[str] = Field(default_factory=list)
    failed_tasks: list[str] = Field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _expires(seconds: int) -> datetime:
    return _now() + timedelta(seconds=seconds)


def _next_event_sequence(db: Session, *, tenant_id: UUID, aggregate_type: str, aggregate_id: UUID) -> int:
    current = (
        db.query(func.max(ArceusEvent.aggregate_version))
        .filter(ArceusEvent.tenant_id == tenant_id, ArceusEvent.aggregate_type == aggregate_type, ArceusEvent.aggregate_id == aggregate_id)
        .scalar()
        or 0
    )
    return int(current) + 1


def _append_event(
    db: Session,
    *,
    tenant_id: UUID,
    aggregate_type: str,
    aggregate_id: UUID,
    event_type: str,
    actor_type: str,
    actor_id: str,
    payload: dict[str, Any],
    correlation_id: UUID,
    idempotency_key: str,
    outbox_topic: str | None = None,
) -> ArceusEvent:
    event = ArceusEvent(
        tenant_id=tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=_next_event_sequence(db, tenant_id=tenant_id, aggregate_type=aggregate_type, aggregate_id=aggregate_id),
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        payload=payload,
        metadata_json={"correlation_id": str(correlation_id), "idempotency_key": idempotency_key},
    )
    db.add(event)
    db.flush()
    if outbox_topic:
        db.add(
            ArceusOutboxMessage(
                tenant_id=tenant_id,
                event_id=event.id,
                topic=outbox_topic,
                payload={"event_id": str(event.id), **payload},
            )
        )
    return event


def _session_response(session: ArceusDesktopSession) -> DesktopSessionResponse:
    return DesktopSessionResponse(
        desktop_session_id=str(session.id),
        status=session.status,
        expires_at=session.expires_at.isoformat(),
        heartbeat_interval_seconds=int(session.heartbeat_interval_seconds or DEFAULT_HEARTBEAT_SECONDS),
    )


def _get_desktop_session(db: Session, *, tenant_id: UUID, session_id: UUID) -> ArceusDesktopSession:
    session = (
        db.query(ArceusDesktopSession)
        .filter(ArceusDesktopSession.tenant_id == tenant_id, ArceusDesktopSession.id == session_id)
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "DESKTOP_SESSION_NOT_FOUND", "message": "Desktop session not found.", "retryable": False}})
    if session.status != "connected" or session.expires_at <= _now():
        session.status = "expired" if session.expires_at <= _now() else session.status
        raise HTTPException(status_code=409, detail={"error": {"code": "DESKTOP_SESSION_DISCONNECTED", "message": "Desktop session is not connected.", "retryable": True}})
    return session


def _active_lease(db: Session, *, tenant_id: UUID, task_id: UUID) -> ArceusWorkerLease | None:
    return (
        db.query(ArceusWorkerLease)
        .filter(
            ArceusWorkerLease.tenant_id == tenant_id,
            ArceusWorkerLease.task_id == task_id,
            ArceusWorkerLease.status == "active",
            ArceusWorkerLease.expires_at > _now(),
        )
        .first()
    )


def _required_capabilities(task: ArceusTask) -> dict[str, bool]:
    configured = ((task.input_contract or {}).get("required_capabilities") or {})
    required = {
        "filesystem_read": True,
        "filesystem_write": False,
        "terminal": False,
        "git": False,
        "docker": False,
        "network": False,
    }
    required.update({key: bool(value) for key, value in configured.items() if key in required})
    task_type = (task.task_type or "").lower()
    if task_type in {"implementation", "code_change", "frontend", "backend"}:
        required["filesystem_write"] = True
    if task_type in {"verification", "test", "build", "lint"}:
        required["terminal"] = True
    return required


def _ensure_capabilities(session: ArceusDesktopSession, task: ArceusTask) -> dict[str, bool]:
    required = _required_capabilities(task)
    available = session.capabilities or {}
    missing = [key for key, value in required.items() if value and not bool(available.get(key))]
    if missing:
        raise HTTPException(
            status_code=409,
            detail={"error": {"code": "DESKTOP_CAPABILITY_MISSING", "message": "Desktop session cannot execute this task.", "missing": missing, "retryable": False}},
        )
    return required


def _find_lease_by_token(db: Session, *, tenant_id: UUID, task_id: UUID, lease_token: str) -> ArceusWorkerLease:
    lease = (
        db.query(ArceusWorkerLease)
        .filter(
            ArceusWorkerLease.tenant_id == tenant_id,
            ArceusWorkerLease.task_id == task_id,
            ArceusWorkerLease.lease_token == lease_token,
        )
        .first()
    )
    if lease is None or lease.status != "active" or lease.expires_at <= _now():
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_TASK_LEASE", "message": "Task lease is invalid or expired.", "retryable": True}})
    return lease


def _next_attempt_number(db: Session, *, tenant_id: UUID, task_id: UUID) -> int:
    current = (
        db.query(func.max(ArceusTaskAttempt.attempt_number))
        .filter(ArceusTaskAttempt.tenant_id == tenant_id, ArceusTaskAttempt.task_id == task_id)
        .scalar()
        or 0
    )
    return int(current) + 1


@router.post("/api/v1/desktop-sessions", response_model=DesktopSessionResponse, status_code=status.HTTP_201_CREATED)
def register_desktop_session(
    payload: DesktopSessionRegisterRequest,
    context: RequestContext = Depends(require_permission("runtime.lease")),
    db: Session = Depends(get_db),
):
    now = _now()
    session = ArceusDesktopSession(
        tenant_id=context.tenant_id,
        device_id=payload.device_id,
        workspace_id=payload.workspace_id,
        repository_id=payload.repository_id,
        capabilities=payload.capabilities.model_dump(mode="json"),
        runtime=payload.runtime.model_dump(mode="json"),
        status="connected",
        heartbeat_interval_seconds=DEFAULT_HEARTBEAT_SECONDS,
        last_heartbeat_at=now,
        expires_at=now + timedelta(seconds=DESKTOP_SESSION_TTL_SECONDS),
        repository_available=True,
        connected_by=context.user_id,
    )
    db.add(session)
    db.flush()
    _append_event(
        db,
        tenant_id=context.tenant_id,
        aggregate_type="desktop_session",
        aggregate_id=session.id,
        event_type="desktop_session.connected",
        actor_type="desktop",
        actor_id=payload.device_id,
        payload={"desktop_session_id": str(session.id), "repository_id": payload.repository_id, "capabilities": session.capabilities},
        correlation_id=context.correlation_id,
        idempotency_key=f"desktop-session-connected:{session.id}",
    )
    db.commit()
    db.refresh(session)
    return _session_response(session)


@router.post("/api/v1/desktop-sessions/{session_id}/heartbeat", response_model=DesktopSessionHeartbeatResponse)
def heartbeat_desktop_session(
    session_id: UUID,
    payload: DesktopSessionHeartbeatRequest,
    context: RequestContext = Depends(require_permission("runtime.lease")),
    db: Session = Depends(get_db),
):
    session = _get_desktop_session(db, tenant_id=context.tenant_id, session_id=session_id)
    session.last_heartbeat_at = _now()
    session.expires_at = _expires(DESKTOP_SESSION_TTL_SECONDS)
    session.active_mission_id = payload.active_mission_id
    session.active_task_id = payload.active_task_id
    session.repository_available = payload.repository_available
    session.version_number = int(session.version_number or 1) + 1
    db.commit()
    db.refresh(session)
    return DesktopSessionHeartbeatResponse(desktop_session_id=str(session.id), status=session.status, expires_at=session.expires_at.isoformat())


@router.post("/api/v1/missions/{mission_id}/tasks/{task_id}/claim", response_model=TaskClaimResponse)
def claim_mission_task(
    mission_id: UUID,
    task_id: UUID,
    payload: TaskClaimRequest,
    context: RequestContext = Depends(require_permission("runtime.lease")),
    db: Session = Depends(get_db),
):
    session = _get_desktop_session(db, tenant_id=context.tenant_id, session_id=payload.desktop_session_id)
    if not session.repository_available:
        raise HTTPException(status_code=409, detail={"error": {"code": "REPOSITORY_UNAVAILABLE", "message": "Desktop repository is not available.", "retryable": True}})
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.id == mission_id).first()
    task = db.query(ArceusTask).filter(ArceusTask.tenant_id == context.tenant_id, ArceusTask.id == task_id, ArceusTask.mission_id == mission_id).first()
    if mission is None or task is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "TASK_NOT_FOUND", "message": "Mission task not found.", "retryable": False}})
    if int(task.version_number or 1) != payload.expected_task_version:
        raise HTTPException(status_code=409, detail={"error": {"code": "TASK_VERSION_CONFLICT", "message": "Task was updated by another actor.", "current_version": int(task.version_number or 1), "retryable": True}})
    if mission.status not in {"ready", "running"}:
        raise HTTPException(status_code=409, detail={"error": {"code": "MISSION_NOT_EXECUTABLE", "message": f"Mission is {mission.status}.", "retryable": False}})
    if task.status != "ready":
        raise HTTPException(status_code=409, detail={"error": {"code": "TASK_NOT_READY", "message": f"Task is {task.status}.", "retryable": True}})
    active = _active_lease(db, tenant_id=context.tenant_id, task_id=task.id)
    if active is not None:
        raise HTTPException(status_code=409, detail={"error": {"code": "TASK_ALREADY_CLAIMED", "message": "Task already has an active lease.", "lease_id": str(active.id), "retryable": True}})
    required = _ensure_capabilities(session, task)
    lease = ArceusWorkerLease(
        tenant_id=context.tenant_id,
        task_id=task.id,
        worker_id=f"desktop:{session.id}",
        lease_token=f"lease_{uuid.uuid4().hex}",
        status="active",
        heartbeat_at=_now(),
        expires_at=_expires(payload.ttl_seconds),
    )
    db.add(lease)
    mission.status = "running"
    mission.version_number = int(mission.version_number or 1) + 1
    task.status = "running"
    task.started_at = task.started_at or _now()
    task.input_contract = {**(task.input_contract or {}), "required_capabilities": required, "claimed_by_desktop_session_id": str(session.id)}
    task.version_number = int(task.version_number or 1) + 1
    session.active_mission_id = mission.id
    session.active_task_id = task.id
    session.last_heartbeat_at = _now()
    session.expires_at = _expires(DESKTOP_SESSION_TTL_SECONDS)
    session.version_number = int(session.version_number or 1) + 1
    db.flush()
    _append_event(
        db,
        tenant_id=context.tenant_id,
        aggregate_type="task",
        aggregate_id=task.id,
        event_type="task.claimed",
        actor_type="desktop",
        actor_id=str(session.id),
        payload={"mission_id": str(mission.id), "task_id": str(task.id), "lease_id": str(lease.id), "desktop_session_id": str(session.id)},
        correlation_id=context.correlation_id,
        idempotency_key=f"task.claimed:{task.id}:{task.version_number}:{session.id}",
        outbox_topic="arceus.task.claimed",
    )
    db.commit()
    db.refresh(task)
    db.refresh(lease)
    return TaskClaimResponse(task_id=str(task.id), status="claimed", lease_id=str(lease.id), lease_token=lease.lease_token, lease_expires_at=lease.expires_at.isoformat(), version=int(task.version_number or 1))


@router.post("/api/v1/missions/{mission_id}/tasks/{task_id}/renew-lease", response_model=TaskClaimResponse)
def renew_task_lease(
    mission_id: UUID,
    task_id: UUID,
    payload: TaskRenewLeaseRequest,
    context: RequestContext = Depends(require_permission("runtime.lease")),
    db: Session = Depends(get_db),
):
    task = db.query(ArceusTask).filter(ArceusTask.tenant_id == context.tenant_id, ArceusTask.id == task_id, ArceusTask.mission_id == mission_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "TASK_NOT_FOUND", "message": "Mission task not found.", "retryable": False}})
    lease = _find_lease_by_token(db, tenant_id=context.tenant_id, task_id=task.id, lease_token=payload.lease_token)
    lease.heartbeat_at = _now()
    lease.expires_at = _expires(payload.ttl_seconds)
    lease.version_number = int(lease.version_number or 1) + 1
    task.version_number = int(task.version_number or 1) + 1
    _append_event(
        db,
        tenant_id=context.tenant_id,
        aggregate_type="task",
        aggregate_id=task.id,
        event_type="task.lease.renewed",
        actor_type="desktop",
        actor_id=lease.worker_id,
        payload={"mission_id": str(mission_id), "task_id": str(task.id), "lease_id": str(lease.id), "lease_expires_at": lease.expires_at.isoformat()},
        correlation_id=context.correlation_id,
        idempotency_key=f"task.lease.renewed:{lease.id}:{lease.version_number}",
    )
    db.commit()
    db.refresh(task)
    db.refresh(lease)
    return TaskClaimResponse(task_id=str(task.id), status="claimed", lease_id=str(lease.id), lease_token=lease.lease_token, lease_expires_at=lease.expires_at.isoformat(), version=int(task.version_number or 1))


@router.get("/api/v1/missions/{mission_id}/tasks/{task_id}/context", response_model=TaskContextResponse)
def get_task_context(
    mission_id: UUID,
    task_id: UUID,
    context: RequestContext = Depends(require_permission("context.build")),
    db: Session = Depends(get_db),
    lease_token: str | None = Header(default=None, alias="X-Task-Lease-Token"),
):
    if not lease_token:
        raise HTTPException(status_code=400, detail={"error": {"code": "LEASE_TOKEN_REQUIRED", "message": "X-Task-Lease-Token is required.", "retryable": False}})
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.id == mission_id).first()
    task = db.query(ArceusTask).filter(ArceusTask.tenant_id == context.tenant_id, ArceusTask.id == task_id, ArceusTask.mission_id == mission_id).first()
    if mission is None or task is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "TASK_NOT_FOUND", "message": "Mission task not found.", "retryable": False}})
    _find_lease_by_token(db, tenant_id=context.tenant_id, task_id=task.id, lease_token=lease_token)
    metadata = mission.metadata_json or {}
    compiled_plan = metadata.get("compiled_plan") or {}
    repository = metadata.get("repository") or {}
    task_input = task.input_contract or {}
    relevant_paths = list(dict.fromkeys([*(compiled_plan.get("understanding", {}).get("repository_scope") or []), *(repository.get("entry_points") or [])]))[:20]
    permitted_tools = ["read_file", "read_range", "search_repository", "list_directory"]
    if task_input.get("required_capabilities", {}).get("terminal"):
        permitted_tools.append("run_command")
    if task_input.get("required_capabilities", {}).get("filesystem_write"):
        permitted_tools.extend(["propose_patch", "propose_file"])
    package = TaskContextResponse(
        context_package_id=str(uuid.uuid4()),
        mission_id=str(mission.id),
        task_id=str(task.id),
        goal=mission.objective,
        task={
            "title": task.title,
            "task_key": task.task_key,
            "task_type": task.task_type,
            "agent_role": task_input.get("agent_role"),
            "model_hint": task_input.get("model_hint"),
            "acceptance_criteria": task.acceptance_criteria or [],
        },
        repository_context={
            "summary": repository.get("summary"),
            "frameworks": repository.get("frameworks") or [],
            "languages": repository.get("languages") or [],
            "root_path": repository.get("root_path"),
            "relevant_paths": relevant_paths,
        },
        constraints=[str(item) for item in (metadata.get("constraints") or {}).values() if item],
        permitted_tools=permitted_tools,
        prohibited_paths=[".git/**", "**/.env", "**/*.pem", "**/*secret*", "**/*token*"],
        expected_output_schema=task.output_contract or {},
        token_estimate=1800 + len(relevant_paths) * 120,
        created_at=_now().isoformat(),
    )
    _append_event(
        db,
        tenant_id=context.tenant_id,
        aggregate_type="task",
        aggregate_id=task.id,
        event_type="task.context.ready",
        actor_type="desktop",
        actor_id="context-builder",
        payload={"mission_id": str(mission.id), "task_id": str(task.id), "context_package_id": package.context_package_id, "relevant_path_count": len(relevant_paths)},
        correlation_id=context.correlation_id,
        idempotency_key=f"task.context.ready:{task.id}:{package.context_package_id}",
    )
    db.commit()
    return package


@router.post("/api/v1/missions/{mission_id}/tasks/{task_id}/complete", response_model=TaskCompleteResponse)
def complete_mission_task(
    mission_id: UUID,
    task_id: UUID,
    payload: TaskCompleteRequest,
    context: RequestContext = Depends(require_permission("runtime.execute")),
    db: Session = Depends(get_db),
):
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.id == mission_id).first()
    task = db.query(ArceusTask).filter(ArceusTask.tenant_id == context.tenant_id, ArceusTask.id == task_id, ArceusTask.mission_id == mission_id).first()
    if mission is None or task is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "TASK_NOT_FOUND", "message": "Mission task not found.", "retryable": False}})
    lease = _find_lease_by_token(db, tenant_id=context.tenant_id, task_id=task.id, lease_token=payload.lease_token)
    if task.status != "running":
        raise HTTPException(status_code=409, detail={"error": {"code": "TASK_NOT_RUNNING", "message": f"Task is {task.status}.", "retryable": True}})

    now = _now()
    result = payload.result.model_dump(mode="json")
    task.status = payload.result.status
    task.completed_at = now if payload.result.status == "completed" else None
    task.failure_reason = payload.result.summary if payload.result.status == "failed" else None
    task.output_contract = {**(task.output_contract or {}), "latest_result": result}
    task.version_number = int(task.version_number or 1) + 1
    lease.status = "released"
    lease.version_number = int(lease.version_number or 1) + 1
    attempt = ArceusTaskAttempt(
        tenant_id=context.tenant_id,
        task_id=task.id,
        attempt_number=_next_attempt_number(db, tenant_id=context.tenant_id, task_id=task.id),
        status="succeeded" if payload.result.status == "completed" else "failed",
        started_at=task.started_at or now,
        finished_at=now,
        worker_id=lease.worker_id,
        idempotency_key=f"task-result:{task.id}:{lease.id}",
        result=result if payload.result.status == "completed" else {},
        error=result if payload.result.status == "failed" else {},
    )
    db.add(attempt)
    session_id = (task.input_contract or {}).get("claimed_by_desktop_session_id")
    if session_id:
        session = db.query(ArceusDesktopSession).filter(ArceusDesktopSession.tenant_id == context.tenant_id, ArceusDesktopSession.id == UUID(session_id)).first()
        if session is not None and session.active_task_id == task.id:
            session.active_task_id = None
            session.active_mission_id = mission.id if mission.status in {"ready", "running"} else None
            session.version_number = int(session.version_number or 1) + 1
    _append_event(
        db,
        tenant_id=context.tenant_id,
        aggregate_type="task",
        aggregate_id=task.id,
        event_type="task.completed" if payload.result.status == "completed" else "task.failed",
        actor_type="desktop",
        actor_id=lease.worker_id,
        payload={"mission_id": str(mission.id), "task_id": str(task.id), "task_key": task.task_key, "result": result},
        correlation_id=context.correlation_id,
        idempotency_key=f"task.result:{task.id}:{lease.id}",
    )
    summary = dispatch_mission(db, tenant_id=context.tenant_id, mission_id=mission.id, correlation_id=context.correlation_id, actor_id="task-dispatcher")
    db.commit()
    db.refresh(task)
    db.refresh(mission)
    return TaskCompleteResponse(
        task_id=str(task.id),
        task_key=task.task_key,
        task_status=task.status,
        mission_id=str(mission.id),
        mission_status=mission.status,
        released_tasks=summary.ready_tasks,
        completed_tasks=summary.completed_tasks,
        failed_tasks=summary.failed_tasks,
    )
