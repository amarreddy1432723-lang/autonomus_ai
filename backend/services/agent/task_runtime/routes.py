from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusAgentRuntimeWorker, ArceusMission, ArceusMissionPathReservation, ArceusMissionTaskAssignment, ArceusTask
from services.shared.database import get_db

from ..arceus_runtime.api.dependencies import RequestContext, require_permission
from .dispatcher import DispatchSummary, append_runtime_event, dispatch_mission, utc_now
from .observability import build_mission_observability
from .scheduler import ACTIVE_ASSIGNMENT_STATUSES, ASSIGNMENT_ACCEPTANCE_TIMEOUT_SECONDS, ScheduleSummary, schedule_ready_tasks


router = APIRouter(prefix="/api/v1/task-runtime", tags=["task-runtime"])


class DispatchMissionResponse(BaseModel):
    mission_id: str
    mission_status: str
    expired_leases: list[str] = Field(default_factory=list)
    requeued_tasks: list[str] = Field(default_factory=list)
    ready_tasks: list[str] = Field(default_factory=list)
    blocked_tasks: list[str] = Field(default_factory=list)
    completed_tasks: list[str] = Field(default_factory=list)
    failed_tasks: list[str] = Field(default_factory=list)
    events: list[str] = Field(default_factory=list)


class AgentWorkerResponse(BaseModel):
    id: str
    role: str
    provider: str
    model: str
    status: str
    current_task: str | None = None
    member_id: str | None = None
    can_implement: bool = False
    can_review: bool = False
    can_approve: bool = False


class ScheduledAssignmentResponse(BaseModel):
    task_id: str
    task_key: str
    task_type: str
    agent_id: str
    role: str
    assignment_id: str | None = None
    execution_class: str = "read_only"
    score: float = 0.0
    reserved_paths: list[str] = Field(default_factory=list)
    reason: str = ""
    reasons: list[str] = Field(default_factory=list)


class WaitingTaskResponse(BaseModel):
    task_id: str
    task_key: str
    reason: str
    blocked_by_task_id: str | None = None
    blocked_by_assignment_id: str | None = None


class CapacityResponse(BaseModel):
    active: int = 0
    limit: int = 3
    by_class: dict[str, int] = Field(default_factory=dict)
    limits: dict[str, int] = Field(default_factory=dict)


class ScheduleMissionResponse(BaseModel):
    mission_id: str
    mission_status: str
    agents: list[AgentWorkerResponse] = Field(default_factory=list)
    assignments: list[ScheduledAssignmentResponse] = Field(default_factory=list)
    ready_tasks: list[str] = Field(default_factory=list)
    waiting_tasks: list[str] = Field(default_factory=list)
    waiting: list[WaitingTaskResponse] = Field(default_factory=list)
    path_reservations: dict[str, str] = Field(default_factory=dict)
    capacity: CapacityResponse = Field(default_factory=CapacityResponse)
    dispatch_events: list[str] = Field(default_factory=list)


class AssignmentResponse(BaseModel):
    id: str
    mission_id: str
    task_id: str
    worker_id: str
    status: str
    assignment_reason: str | None = None
    score: float | None = None
    assigned_at: str | None = None
    started_at: str | None = None
    released_at: str | None = None
    completed_at: str | None = None
    lease_expires_at: str | None = None
    last_heartbeat_at: str | None = None
    metadata: dict = Field(default_factory=dict)


class ReservationResponse(BaseModel):
    id: str
    repository_id: str
    mission_id: str
    task_id: str
    assignment_id: str | None = None
    path_pattern: str
    reservation_mode: str
    status: str
    acquired_at: str | None = None
    expires_at: str | None = None
    released_at: str | None = None
    metadata: dict = Field(default_factory=dict)


class AcceptAssignmentRequest(BaseModel):
    worker_id: str
    expected_assignment_version: int | None = None


class HeartbeatAssignmentRequest(BaseModel):
    worker_id: str


class ReleaseAssignmentRequest(BaseModel):
    worker_id: str
    status: str = "released"


class CompleteAssignmentRequest(BaseModel):
    worker_id: str
    expected_version: int | None = None
    task_status: str = "completed"
    task_result_id: str | None = None
    evidence_count: int = 0
    change_set_id: str | None = None
    result: dict = Field(default_factory=dict)


class FailAssignmentRequest(BaseModel):
    worker_id: str
    error: dict = Field(default_factory=dict)


class RecoveryReportRequest(BaseModel):
    status: str
    local_stage: str
    repository_state: str
    recommended_action: str
    artifacts: dict = Field(default_factory=dict)
    reconciliation: dict = Field(default_factory=dict)
    report_id: str | None = None


class RecoveryReportResponse(BaseModel):
    assignment_id: str
    status: str
    local_stage: str
    repository_state: str
    recommended_action: str
    report_id: str
    idempotent: bool = False
    recorded_at: str | None = None


class AvailableAssignmentResponse(BaseModel):
    assignment_id: str
    mission_id: str
    task_id: str
    task_key: str
    task_type: str
    task_version: int
    worker_id: str
    execution_class: str
    required_capabilities: dict = Field(default_factory=dict)
    lease_expires_at: str | None = None
    metadata: dict = Field(default_factory=dict)


class AvailableAssignmentsResponse(BaseModel):
    assignments: list[AvailableAssignmentResponse] = Field(default_factory=list)


class MissionObservabilityResponse(BaseModel):
    mission_id: str
    mission: dict = Field(default_factory=dict)
    timeline: list[dict] = Field(default_factory=list)
    workers: list[dict] = Field(default_factory=list)
    reservations: list[dict] = Field(default_factory=list)
    dag: dict = Field(default_factory=dict)
    recovery: list[dict] = Field(default_factory=list)
    metrics: dict = Field(default_factory=dict)


def _response(summary: DispatchSummary) -> DispatchMissionResponse:
    return DispatchMissionResponse(**summary.__dict__)


def _schedule_response(summary: ScheduleSummary) -> ScheduleMissionResponse:
    return ScheduleMissionResponse(
        mission_id=summary.mission_id,
        mission_status=summary.mission_status,
        agents=[AgentWorkerResponse(**agent.__dict__) for agent in summary.agents],
        assignments=[ScheduledAssignmentResponse(**assignment.__dict__) for assignment in summary.assignments],
        ready_tasks=summary.ready_tasks,
        waiting_tasks=summary.waiting_tasks,
        waiting=[WaitingTaskResponse(**item.__dict__) for item in summary.waiting],
        path_reservations=summary.path_reservations,
        capacity=CapacityResponse(**summary.capacity.__dict__),
        dispatch_events=summary.dispatch_events,
    )


def _assignment_response(assignment: ArceusMissionTaskAssignment) -> AssignmentResponse:
    return AssignmentResponse(
        id=str(assignment.id),
        mission_id=str(assignment.mission_id),
        task_id=str(assignment.task_id),
        worker_id=str(assignment.worker_id),
        status=assignment.status,
        assignment_reason=assignment.assignment_reason,
        score=float(assignment.score) if assignment.score is not None else None,
        assigned_at=assignment.assigned_at.isoformat() if assignment.assigned_at else None,
        started_at=assignment.started_at.isoformat() if assignment.started_at else None,
        released_at=assignment.released_at.isoformat() if assignment.released_at else None,
        completed_at=assignment.completed_at.isoformat() if assignment.completed_at else None,
        lease_expires_at=assignment.lease_expires_at.isoformat() if assignment.lease_expires_at else None,
        last_heartbeat_at=assignment.last_heartbeat_at.isoformat() if assignment.last_heartbeat_at else None,
        metadata=assignment.metadata_json or {},
    )


def _reservation_response(reservation: ArceusMissionPathReservation) -> ReservationResponse:
    return ReservationResponse(
        id=str(reservation.id),
        repository_id=str(reservation.repository_id),
        mission_id=str(reservation.mission_id),
        task_id=str(reservation.task_id),
        assignment_id=str(reservation.assignment_id) if reservation.assignment_id else None,
        path_pattern=reservation.path_pattern,
        reservation_mode=reservation.reservation_mode,
        status=reservation.status,
        acquired_at=reservation.acquired_at.isoformat() if reservation.acquired_at else None,
        expires_at=reservation.expires_at.isoformat() if reservation.expires_at else None,
        released_at=reservation.released_at.isoformat() if reservation.released_at else None,
        metadata=reservation.metadata_json or {},
    )


def _assignment_or_404(db: Session, *, tenant_id: UUID, assignment_id: UUID) -> ArceusMissionTaskAssignment:
    assignment = db.query(ArceusMissionTaskAssignment).filter(ArceusMissionTaskAssignment.tenant_id == tenant_id, ArceusMissionTaskAssignment.id == assignment_id).first()
    if assignment is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "ASSIGNMENT_NOT_FOUND", "message": "Assignment not found.", "retryable": False}})
    return assignment


def _worker_or_403(db: Session, *, tenant_id: UUID, worker_id: str, assignment: ArceusMissionTaskAssignment) -> ArceusAgentRuntimeWorker:
    try:
        worker_uuid = UUID(worker_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_WORKER_ID", "message": "Worker id must be a UUID.", "retryable": False}}) from exc
    worker = db.query(ArceusAgentRuntimeWorker).filter(ArceusAgentRuntimeWorker.tenant_id == tenant_id, ArceusAgentRuntimeWorker.id == worker_uuid).first()
    if worker is None or worker.id != assignment.worker_id:
        raise HTTPException(status_code=403, detail={"error": {"code": "WORKER_MISMATCH", "message": "Worker does not own this assignment.", "retryable": False}})
    return worker


def _release_reservations(db: Session, *, tenant_id: UUID, assignment_id: UUID):
    now = utc_now()
    reservations = (
        db.query(ArceusMissionPathReservation)
        .filter(ArceusMissionPathReservation.tenant_id == tenant_id, ArceusMissionPathReservation.assignment_id == assignment_id, ArceusMissionPathReservation.status == "active")
        .all()
    )
    for reservation in reservations:
        reservation.status = "released"
        reservation.released_at = now
        reservation.version_number = int(reservation.version_number or 1) + 1
    return reservations


def _mark_worker_idle(worker: ArceusAgentRuntimeWorker) -> None:
    worker.status = "idle"
    worker.current_task_id = None
    worker.last_heartbeat_at = utc_now()
    worker.version_number = int(worker.version_number or 1) + 1


def _task_for_assignment(db: Session, *, tenant_id: UUID, assignment: ArceusMissionTaskAssignment) -> ArceusTask | None:
    return db.query(ArceusTask).filter(ArceusTask.tenant_id == tenant_id, ArceusTask.id == assignment.task_id, ArceusTask.mission_id == assignment.mission_id).first()


def _stable_json_hash(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@router.post("/missions/{mission_id}/dispatch", response_model=DispatchMissionResponse)
def dispatch_mission_endpoint(
    mission_id: UUID,
    context: RequestContext = Depends(require_permission("runtime.schedule")),
    db: Session = Depends(get_db),
):
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.id == mission_id).first()
    if mission is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MISSION_NOT_FOUND", "message": "Mission not found.", "retryable": False}})
    summary = dispatch_mission(db, tenant_id=context.tenant_id, mission_id=mission.id, correlation_id=context.correlation_id)
    db.commit()
    return _response(summary)


@router.post("/missions/{mission_id}/schedule", response_model=ScheduleMissionResponse)
def schedule_mission_endpoint(
    mission_id: UUID,
    context: RequestContext = Depends(require_permission("runtime.schedule")),
    db: Session = Depends(get_db),
):
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.id == mission_id).first()
    if mission is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MISSION_NOT_FOUND", "message": "Mission not found.", "retryable": False}})
    summary = schedule_ready_tasks(db, tenant_id=context.tenant_id, mission_id=mission.id, correlation_id=context.correlation_id)
    db.commit()
    return _schedule_response(summary)


@router.get("/assignments/available", response_model=AvailableAssignmentsResponse)
def available_assignments_endpoint(
    desktop_session_id: UUID | None = Query(default=None),
    repository_id: UUID | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    context: RequestContext = Depends(require_permission("runtime.execute")),
    db: Session = Depends(get_db),
):
    query = (
        db.query(ArceusMissionTaskAssignment, ArceusTask)
        .join(ArceusTask, ArceusTask.id == ArceusMissionTaskAssignment.task_id)
        .filter(
            ArceusMissionTaskAssignment.tenant_id == context.tenant_id,
            ArceusMissionTaskAssignment.status == "assigned",
            ArceusMissionTaskAssignment.lease_expires_at > utc_now(),
            ArceusTask.status == "ready",
        )
        .order_by(ArceusMissionTaskAssignment.assigned_at.asc(), ArceusMissionTaskAssignment.id.asc())
        .limit(limit)
    )
    rows = query.all()
    assignments: list[AvailableAssignmentResponse] = []
    for assignment, task in rows:
        metadata = assignment.metadata_json or {}
        task_input = task.input_contract or {}
        if repository_id:
            task_repository_id = task_input.get("repository_id")
            if task_repository_id and str(task_repository_id) != str(repository_id):
                continue
        assignments.append(
            AvailableAssignmentResponse(
                assignment_id=str(assignment.id),
                mission_id=str(assignment.mission_id),
                task_id=str(assignment.task_id),
                task_key=task.task_key,
                task_type=task.task_type,
                task_version=int(task.version_number or 1),
                worker_id=str(assignment.worker_id),
                execution_class=str(metadata.get("execution_class") or "read_only"),
                required_capabilities=task_input.get("required_capabilities") or {},
                lease_expires_at=assignment.lease_expires_at.isoformat() if assignment.lease_expires_at else None,
                metadata={**metadata, "desktop_session_id": str(desktop_session_id) if desktop_session_id else None},
            )
        )
    return AvailableAssignmentsResponse(assignments=assignments)


@router.get("/missions/{mission_id}/assignments", response_model=list[AssignmentResponse])
def list_mission_assignments_endpoint(
    mission_id: UUID,
    context: RequestContext = Depends(require_permission("runtime.schedule")),
    db: Session = Depends(get_db),
):
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.id == mission_id).first()
    if mission is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MISSION_NOT_FOUND", "message": "Mission not found.", "retryable": False}})
    assignments = (
        db.query(ArceusMissionTaskAssignment)
        .filter(ArceusMissionTaskAssignment.tenant_id == context.tenant_id, ArceusMissionTaskAssignment.mission_id == mission.id)
        .order_by(ArceusMissionTaskAssignment.assigned_at.desc(), ArceusMissionTaskAssignment.id.desc())
        .all()
    )
    return [_assignment_response(assignment) for assignment in assignments]


@router.get("/missions/{mission_id}/reservations", response_model=list[ReservationResponse])
def list_mission_reservations_endpoint(
    mission_id: UUID,
    context: RequestContext = Depends(require_permission("runtime.schedule")),
    db: Session = Depends(get_db),
):
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.id == mission_id).first()
    if mission is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MISSION_NOT_FOUND", "message": "Mission not found.", "retryable": False}})
    reservations = (
        db.query(ArceusMissionPathReservation)
        .filter(ArceusMissionPathReservation.tenant_id == context.tenant_id, ArceusMissionPathReservation.mission_id == mission.id)
        .order_by(ArceusMissionPathReservation.acquired_at.desc(), ArceusMissionPathReservation.id.desc())
        .all()
    )
    return [_reservation_response(reservation) for reservation in reservations]


@router.get("/missions/{mission_id}/state", response_model=ScheduleMissionResponse)
def get_mission_scheduler_state_endpoint(
    mission_id: UUID,
    context: RequestContext = Depends(require_permission("runtime.schedule")),
    db: Session = Depends(get_db),
):
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.id == mission_id).first()
    if mission is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MISSION_NOT_FOUND", "message": "Mission not found.", "retryable": False}})
    summary = schedule_ready_tasks(db, tenant_id=context.tenant_id, mission_id=mission.id, correlation_id=context.correlation_id, max_assignments=0)
    db.commit()
    return _schedule_response(summary)


@router.get("/missions/{mission_id}/observability", response_model=MissionObservabilityResponse)
def get_mission_observability_endpoint(
    mission_id: UUID,
    event_limit: int = Query(default=80, ge=1, le=500),
    context: RequestContext = Depends(require_permission("runtime.schedule")),
    db: Session = Depends(get_db),
):
    try:
        return MissionObservabilityResponse(**build_mission_observability(db, tenant_id=context.tenant_id, mission_id=mission_id, event_limit=event_limit))
    except ValueError as exc:
        if str(exc) == "MISSION_NOT_FOUND":
            raise HTTPException(status_code=404, detail={"error": {"code": "MISSION_NOT_FOUND", "message": "Mission not found.", "retryable": False}}) from exc
        raise


@router.post("/assignments/{assignment_id}/accept", response_model=AssignmentResponse)
def accept_assignment_endpoint(
    assignment_id: UUID,
    payload: AcceptAssignmentRequest,
    context: RequestContext = Depends(require_permission("runtime.execute")),
    db: Session = Depends(get_db),
):
    assignment = _assignment_or_404(db, tenant_id=context.tenant_id, assignment_id=assignment_id)
    worker = _worker_or_403(db, tenant_id=context.tenant_id, worker_id=payload.worker_id, assignment=assignment)
    if assignment.status != "assigned":
        raise HTTPException(status_code=409, detail={"error": {"code": "ASSIGNMENT_NOT_ASSIGNED", "message": f"Assignment is {assignment.status}.", "retryable": False}})
    if payload.expected_assignment_version is not None and int(assignment.version_number or 1) != payload.expected_assignment_version:
        raise HTTPException(status_code=409, detail={"error": {"code": "ASSIGNMENT_VERSION_CONFLICT", "message": "Assignment version changed.", "retryable": True}})
    now = utc_now()
    if assignment.lease_expires_at and assignment.lease_expires_at <= now:
        assignment.status = "expired"
        assignment.released_at = now
        assignment.version_number = int(assignment.version_number or 1) + 1
        worker.status = "idle"
        worker.current_task_id = None
        db.commit()
        raise HTTPException(status_code=409, detail={"error": {"code": "ASSIGNMENT_EXPIRED", "message": "Assignment expired before acceptance.", "retryable": True}})
    assignment.status = "accepted"
    assignment.started_at = now
    assignment.last_heartbeat_at = now
    assignment.lease_expires_at = now + timedelta(seconds=ASSIGNMENT_ACCEPTANCE_TIMEOUT_SECONDS * 3)
    assignment.version_number = int(assignment.version_number or 1) + 1
    worker.status = "busy"
    worker.last_heartbeat_at = now
    worker.version_number = int(worker.version_number or 1) + 1
    append_runtime_event(
        db,
        tenant_id=context.tenant_id,
        mission_id=assignment.mission_id,
        event_type="task.assignment.accepted",
        actor_type="worker",
        actor_id=str(worker.id),
        payload={"assignment_id": str(assignment.id), "task_id": str(assignment.task_id), "worker_id": str(worker.id)},
        correlation_id=context.correlation_id,
        idempotency_key=f"task.assignment.accepted:{assignment.id}:{assignment.version_number}",
        outbox_topic="arceus.task.assignment.accepted",
    )
    db.commit()
    return _assignment_response(assignment)


@router.post("/assignments/{assignment_id}/heartbeat", response_model=AssignmentResponse)
def heartbeat_assignment_endpoint(
    assignment_id: UUID,
    payload: HeartbeatAssignmentRequest,
    context: RequestContext = Depends(require_permission("runtime.execute")),
    db: Session = Depends(get_db),
):
    assignment = _assignment_or_404(db, tenant_id=context.tenant_id, assignment_id=assignment_id)
    worker = _worker_or_403(db, tenant_id=context.tenant_id, worker_id=payload.worker_id, assignment=assignment)
    if assignment.status not in ACTIVE_ASSIGNMENT_STATUSES:
        raise HTTPException(status_code=409, detail={"error": {"code": "ASSIGNMENT_NOT_ACTIVE", "message": f"Assignment is {assignment.status}.", "retryable": False}})
    now = utc_now()
    assignment.last_heartbeat_at = now
    assignment.lease_expires_at = now + timedelta(seconds=ASSIGNMENT_ACCEPTANCE_TIMEOUT_SECONDS * 3)
    assignment.version_number = int(assignment.version_number or 1) + 1
    worker.last_heartbeat_at = now
    worker.version_number = int(worker.version_number or 1) + 1
    db.commit()
    return _assignment_response(assignment)


@router.post("/assignments/{assignment_id}/release", response_model=AssignmentResponse)
def release_assignment_endpoint(
    assignment_id: UUID,
    payload: ReleaseAssignmentRequest,
    context: RequestContext = Depends(require_permission("runtime.execute")),
    db: Session = Depends(get_db),
):
    assignment = _assignment_or_404(db, tenant_id=context.tenant_id, assignment_id=assignment_id)
    worker = _worker_or_403(db, tenant_id=context.tenant_id, worker_id=payload.worker_id, assignment=assignment)
    if assignment.status == payload.status:
        return _assignment_response(assignment)
    if payload.status not in {"released", "completed", "failed"}:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_RELEASE_STATUS", "message": "Release status must be released, completed, or failed.", "retryable": False}})
    now = utc_now()
    assignment.status = payload.status
    assignment.released_at = now
    assignment.completed_at = now if payload.status == "completed" else assignment.completed_at
    assignment.version_number = int(assignment.version_number or 1) + 1
    _mark_worker_idle(worker)
    _release_reservations(db, tenant_id=context.tenant_id, assignment_id=assignment.id)
    append_runtime_event(
        db,
        tenant_id=context.tenant_id,
        mission_id=assignment.mission_id,
        event_type="task.assignment.released",
        actor_type="worker",
        actor_id=str(worker.id),
        payload={"assignment_id": str(assignment.id), "task_id": str(assignment.task_id), "worker_id": str(worker.id), "status": assignment.status},
        correlation_id=context.correlation_id,
        idempotency_key=f"task.assignment.released:{assignment.id}:{assignment.version_number}",
        outbox_topic="arceus.task.assignment.released",
    )
    db.commit()
    return _assignment_response(assignment)


@router.post("/assignments/{assignment_id}/complete", response_model=AssignmentResponse)
def complete_assignment_endpoint(
    assignment_id: UUID,
    payload: CompleteAssignmentRequest,
    context: RequestContext = Depends(require_permission("runtime.execute")),
    db: Session = Depends(get_db),
):
    assignment = _assignment_or_404(db, tenant_id=context.tenant_id, assignment_id=assignment_id)
    worker = _worker_or_403(db, tenant_id=context.tenant_id, worker_id=payload.worker_id, assignment=assignment)
    if assignment.status == "completed":
        return _assignment_response(assignment)
    if assignment.status not in ACTIVE_ASSIGNMENT_STATUSES:
        raise HTTPException(status_code=409, detail={"error": {"code": "ASSIGNMENT_NOT_ACTIVE", "message": f"Assignment is {assignment.status}.", "retryable": False}})
    if payload.expected_version is not None and int(assignment.version_number or 1) != payload.expected_version:
        raise HTTPException(status_code=409, detail={"error": {"code": "ASSIGNMENT_VERSION_CONFLICT", "message": "Assignment version changed.", "retryable": True}})
    task = _task_for_assignment(db, tenant_id=context.tenant_id, assignment=assignment)
    now = utc_now()
    assignment.status = "completed"
    assignment.completed_at = now
    assignment.released_at = now
    assignment.metadata_json = {
        **(assignment.metadata_json or {}),
        "task_status": payload.task_status,
        "task_result_id": payload.task_result_id,
        "evidence_count": payload.evidence_count,
        "change_set_id": payload.change_set_id,
        "result": payload.result,
    }
    assignment.version_number = int(assignment.version_number or 1) + 1
    if task is not None and task.status == "running":
        task.status = "completed" if payload.task_status == "completed" else payload.task_status
        task.completed_at = now if task.status == "completed" else task.completed_at
        task.version_number = int(task.version_number or 1) + 1
    _mark_worker_idle(worker)
    _release_reservations(db, tenant_id=context.tenant_id, assignment_id=assignment.id)
    append_runtime_event(
        db,
        tenant_id=context.tenant_id,
        mission_id=assignment.mission_id,
        event_type="assignment.completed",
        actor_type="worker",
        actor_id=str(worker.id),
        payload={"assignment_id": str(assignment.id), "task_id": str(assignment.task_id), "worker_id": str(worker.id), "evidence_count": payload.evidence_count, "change_set_id": payload.change_set_id},
        correlation_id=context.correlation_id,
        idempotency_key=f"assignment.completed:{assignment.id}:{assignment.version_number}",
        outbox_topic="arceus.assignment.completed",
    )
    schedule_ready_tasks(db, tenant_id=context.tenant_id, mission_id=assignment.mission_id, correlation_id=context.correlation_id)
    db.commit()
    return _assignment_response(assignment)


@router.post("/assignments/{assignment_id}/fail", response_model=AssignmentResponse)
def fail_assignment_endpoint(
    assignment_id: UUID,
    payload: FailAssignmentRequest,
    context: RequestContext = Depends(require_permission("runtime.execute")),
    db: Session = Depends(get_db),
):
    assignment = _assignment_or_404(db, tenant_id=context.tenant_id, assignment_id=assignment_id)
    worker = _worker_or_403(db, tenant_id=context.tenant_id, worker_id=payload.worker_id, assignment=assignment)
    if assignment.status == "failed":
        return _assignment_response(assignment)
    if assignment.status not in ACTIVE_ASSIGNMENT_STATUSES:
        raise HTTPException(status_code=409, detail={"error": {"code": "ASSIGNMENT_NOT_ACTIVE", "message": f"Assignment is {assignment.status}.", "retryable": False}})
    task = _task_for_assignment(db, tenant_id=context.tenant_id, assignment=assignment)
    now = utc_now()
    retryable = bool((payload.error or {}).get("retryable", False))
    assignment.status = "failed"
    assignment.released_at = now
    assignment.metadata_json = {**(assignment.metadata_json or {}), "error": payload.error}
    assignment.version_number = int(assignment.version_number or 1) + 1
    if task is not None:
        task.status = "ready" if retryable else "failed"
        task.failure_reason = str((payload.error or {}).get("message") or (payload.error or {}).get("code") or "Assignment failed.")
        task.version_number = int(task.version_number or 1) + 1
    _mark_worker_idle(worker)
    _release_reservations(db, tenant_id=context.tenant_id, assignment_id=assignment.id)
    append_runtime_event(
        db,
        tenant_id=context.tenant_id,
        mission_id=assignment.mission_id,
        event_type="assignment.failed",
        actor_type="worker",
        actor_id=str(worker.id),
        payload={"assignment_id": str(assignment.id), "task_id": str(assignment.task_id), "worker_id": str(worker.id), "error": payload.error},
        correlation_id=context.correlation_id,
        idempotency_key=f"assignment.failed:{assignment.id}:{assignment.version_number}",
        outbox_topic="arceus.assignment.failed",
    )
    schedule_ready_tasks(db, tenant_id=context.tenant_id, mission_id=assignment.mission_id, correlation_id=context.correlation_id)
    db.commit()
    return _assignment_response(assignment)


@router.post("/assignments/{assignment_id}/recovery", response_model=RecoveryReportResponse)
def report_assignment_recovery_endpoint(
    assignment_id: UUID,
    payload: RecoveryReportRequest,
    context: RequestContext = Depends(require_permission("runtime.execute")),
    db: Session = Depends(get_db),
):
    allowed_statuses = {"reconciled", "recovered", "rollback_required", "manual_review_required", "abandoned"}
    if payload.status not in allowed_statuses:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_RECOVERY_STATUS", "message": "Recovery status is not supported.", "retryable": False}})
    assignment = _assignment_or_404(db, tenant_id=context.tenant_id, assignment_id=assignment_id)
    report_payload = payload.model_dump(mode="json")
    report_key = payload.report_id or _stable_json_hash(
        {
            "assignment_id": str(assignment.id),
            "local_stage": payload.local_stage,
            "repository_state": payload.repository_state,
            "recommended_action": payload.recommended_action,
            "artifacts": payload.artifacts,
        }
    )[:24]
    request_hash = _stable_json_hash(report_payload)
    metadata = dict(assignment.metadata_json or {})
    recovery_reports = dict(metadata.get("recovery_reports") or {})
    existing = recovery_reports.get(report_key)
    if existing and existing.get("request_hash") == request_hash:
        return RecoveryReportResponse(
            assignment_id=str(assignment.id),
            status=existing.get("status") or payload.status,
            local_stage=existing.get("local_stage") or payload.local_stage,
            repository_state=existing.get("repository_state") or payload.repository_state,
            recommended_action=existing.get("recommended_action") or payload.recommended_action,
            report_id=report_key,
            idempotent=True,
            recorded_at=existing.get("recorded_at"),
        )

    now = utc_now()
    record = {
        **report_payload,
        "report_id": report_key,
        "request_hash": request_hash,
        "recorded_at": now.isoformat(),
        "assignment_status": assignment.status,
    }
    recovery_reports[report_key] = record
    metadata["recovery_reports"] = recovery_reports
    metadata["latest_recovery_report"] = record
    assignment.metadata_json = metadata
    assignment.last_heartbeat_at = now
    assignment.version_number = int(assignment.version_number or 1) + 1
    append_runtime_event(
        db,
        tenant_id=context.tenant_id,
        mission_id=assignment.mission_id,
        event_type="assignment.recovery.reported",
        actor_type="worker",
        actor_id="desktop-recovery",
        payload={
            "assignment_id": str(assignment.id),
            "task_id": str(assignment.task_id),
            "report_id": report_key,
            "status": payload.status,
            "local_stage": payload.local_stage,
            "repository_state": payload.repository_state,
            "recommended_action": payload.recommended_action,
        },
        correlation_id=context.correlation_id,
        idempotency_key=f"assignment.recovery.reported:{assignment.id}:{report_key}:{assignment.version_number}",
        outbox_topic="arceus.assignment.recovery.reported",
    )
    db.commit()
    return RecoveryReportResponse(
        assignment_id=str(assignment.id),
        status=payload.status,
        local_stage=payload.local_stage,
        repository_state=payload.repository_state,
        recommended_action=payload.recommended_action,
        report_id=report_key,
        idempotent=False,
        recorded_at=record["recorded_at"],
    )
