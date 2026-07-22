from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from uuid import UUID

from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusAgentRuntimeWorker,
    ArceusMission,
    ArceusMissionOrganization,
    ArceusMissionPathReservation,
    ArceusMissionRepositoryScope,
    ArceusMissionTaskAssignment,
    ArceusOrganizationMember,
    ArceusTask,
    ArceusWorkerLease,
)

from .dispatcher import append_runtime_event, dispatch_mission
from .path_policy import PathPolicyError, normalize_repository_paths, path_patterns_overlap, reservation_modes_conflict


READ_ONLY_TASK_TYPES = {"analysis", "research", "planning"}
REVIEW_TASK_TYPES = {"review"}
VERIFICATION_TASK_TYPES = {"verification", "test", "build", "lint"}
INTEGRATION_TASK_TYPES = {"integration", "deploy", "preview"}
WRITE_TASK_TYPES = {"implementation", "code_change", "frontend", "backend", "database", "migration"}
ACTIVE_ASSIGNMENT_STATUSES = {"assigned", "accepted", "running"}
TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled"}
ASSIGNMENT_ACCEPTANCE_TIMEOUT_SECONDS = 30


class TaskExecutionClass(str, Enum):
    READ_ONLY = "read_only"
    WRITE_SENSITIVE = "write_sensitive"
    VERIFICATION = "verification"
    INTEGRATION = "integration"
    REVIEW = "review"


DEFAULT_LIMITS = {
    "total": 3,
    TaskExecutionClass.READ_ONLY.value: 2,
    TaskExecutionClass.WRITE_SENSITIVE.value: 1,
    TaskExecutionClass.VERIFICATION.value: 1,
    TaskExecutionClass.INTEGRATION.value: 1,
    TaskExecutionClass.REVIEW.value: 2,
}


@dataclass
class AgentTemplate:
    role: str
    provider: str
    model: str
    can_implement: bool
    can_review: bool
    can_approve: bool


DEFAULT_VIRTUAL_AGENTS = (
    AgentTemplate("mission_lead", "arceus-default", "auto", True, True, False),
    AgentTemplate("solution_architect", "arceus-default", "auto", False, True, False),
    AgentTemplate("backend_engineer", "arceus-default", "auto", True, False, False),
    AgentTemplate("frontend_engineer", "arceus-default", "auto", True, False, False),
    AgentTemplate("qa_reviewer", "arceus-default", "auto", False, True, False),
    AgentTemplate("security_reviewer", "arceus-default", "auto", False, True, False),
)


@dataclass
class AgentWorker:
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


@dataclass
class ScheduledAssignment:
    task_id: str
    task_key: str
    task_type: str
    agent_id: str
    role: str
    assignment_id: str | None = None
    execution_class: str = TaskExecutionClass.READ_ONLY.value
    score: float = 0.0
    reserved_paths: list[str] = field(default_factory=list)
    reason: str = ""
    reasons: list[str] = field(default_factory=list)


@dataclass
class WaitingTask:
    task_id: str
    task_key: str
    reason: str
    blocked_by_task_id: str | None = None
    blocked_by_assignment_id: str | None = None


@dataclass
class CapacityState:
    active: int = 0
    limit: int = DEFAULT_LIMITS["total"]
    by_class: dict[str, int] = field(default_factory=dict)
    limits: dict[str, int] = field(default_factory=lambda: dict(DEFAULT_LIMITS))


@dataclass
class ScheduleSummary:
    mission_id: str
    mission_status: str
    agents: list[AgentWorker] = field(default_factory=list)
    assignments: list[ScheduledAssignment] = field(default_factory=list)
    ready_tasks: list[str] = field(default_factory=list)
    waiting_tasks: list[str] = field(default_factory=list)
    waiting: list[WaitingTask] = field(default_factory=list)
    path_reservations: dict[str, str] = field(default_factory=dict)
    capacity: CapacityState = field(default_factory=CapacityState)
    dispatch_events: list[str] = field(default_factory=list)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _metadata_capabilities(can_implement: bool, can_review: bool, can_approve: bool) -> dict:
    return {"can_implement": can_implement, "can_review": can_review, "can_approve": can_approve}


def _repository_id(db: Session, *, tenant_id: UUID, mission: ArceusMission) -> UUID:
    scope = (
        db.query(ArceusMissionRepositoryScope)
        .filter(ArceusMissionRepositoryScope.tenant_id == tenant_id, ArceusMissionRepositoryScope.mission_id == mission.id)
        .order_by(ArceusMissionRepositoryScope.created_at.asc(), ArceusMissionRepositoryScope.id.asc())
        .first()
    )
    return scope.repository_id if scope is not None else mission.project_id


def _task_paths(task: ArceusTask) -> list[str]:
    contract = task.input_contract or {}
    candidates: list[str] = []
    for key in ("reserved_paths", "write_paths", "target_paths", "paths", "files", "relevant_paths", "likely_affected_paths"):
        value = contract.get(key)
        if isinstance(value, str):
            candidates.append(value)
        elif isinstance(value, list):
            candidates.extend(str(item) for item in value if item)
    return normalize_repository_paths(candidates)


def _execution_class(task: ArceusTask) -> TaskExecutionClass:
    task_type = (task.task_type or "").lower()
    required = (task.input_contract or {}).get("required_capabilities") or {}
    if task_type in WRITE_TASK_TYPES or bool(required.get("filesystem_write")):
        return TaskExecutionClass.WRITE_SENSITIVE
    if task_type in VERIFICATION_TASK_TYPES:
        return TaskExecutionClass.VERIFICATION
    if task_type in INTEGRATION_TASK_TYPES:
        return TaskExecutionClass.INTEGRATION
    if task_type in REVIEW_TASK_TYPES:
        return TaskExecutionClass.REVIEW
    return TaskExecutionClass.READ_ONLY


def _requires_write(task: ArceusTask) -> bool:
    return _execution_class(task) == TaskExecutionClass.WRITE_SENSITIVE


def _reservation_mode(task: ArceusTask) -> str:
    if _execution_class(task) == TaskExecutionClass.WRITE_SENSITIVE:
        return "write"
    return "read"


def _active_leases(db: Session, *, tenant_id: UUID, mission_id: UUID) -> dict[UUID, ArceusWorkerLease]:
    leases = (
        db.query(ArceusWorkerLease)
        .join(ArceusTask, ArceusTask.id == ArceusWorkerLease.task_id)
        .filter(
            ArceusWorkerLease.tenant_id == tenant_id,
            ArceusWorkerLease.status == "active",
            ArceusWorkerLease.expires_at > _now(),
            ArceusTask.mission_id == mission_id,
        )
        .all()
    )
    return {lease.task_id: lease for lease in leases}


def _active_assignments(db: Session, *, tenant_id: UUID, mission_id: UUID) -> list[ArceusMissionTaskAssignment]:
    return (
        db.query(ArceusMissionTaskAssignment)
        .filter(
            ArceusMissionTaskAssignment.tenant_id == tenant_id,
            ArceusMissionTaskAssignment.mission_id == mission_id,
            ArceusMissionTaskAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
        )
        .all()
    )


def _assignment_by_task(active_assignments: list[ArceusMissionTaskAssignment]) -> dict[UUID, ArceusMissionTaskAssignment]:
    return {assignment.task_id: assignment for assignment in active_assignments}


def _worker_to_agent(worker: ArceusAgentRuntimeWorker) -> AgentWorker:
    capabilities = worker.capabilities or {}
    return AgentWorker(
        id=str(worker.id),
        role=worker.role,
        provider=worker.provider or "arceus",
        model=worker.model or "auto",
        status=worker.status,
        current_task=str(worker.current_task_id) if worker.current_task_id else None,
        member_id=str(worker.organization_member_id) if worker.organization_member_id else None,
        can_implement=bool(capabilities.get("can_implement")),
        can_review=bool(capabilities.get("can_review")),
        can_approve=bool(capabilities.get("can_approve")),
    )


def _ensure_worker(
    db: Session,
    *,
    tenant_id: UUID,
    mission_id: UUID,
    role: str,
    provider: str,
    model: str,
    capabilities: dict,
    organization_member_id: UUID | None = None,
) -> ArceusAgentRuntimeWorker:
    query = db.query(ArceusAgentRuntimeWorker).filter(
        ArceusAgentRuntimeWorker.tenant_id == tenant_id,
        ArceusAgentRuntimeWorker.current_mission_id == mission_id,
        ArceusAgentRuntimeWorker.role == role,
    )
    if organization_member_id:
        query = query.filter(ArceusAgentRuntimeWorker.organization_member_id == organization_member_id)
    else:
        query = query.filter(ArceusAgentRuntimeWorker.organization_member_id.is_(None))
    worker = query.first()
    if worker is None:
        worker = ArceusAgentRuntimeWorker(
            tenant_id=tenant_id,
            organization_member_id=organization_member_id,
            role=role,
            provider=provider,
            model=model,
            status="idle",
            current_mission_id=mission_id,
            capabilities=capabilities,
            metadata_json={"source": "organization_member" if organization_member_id else "bootstrap_virtual"},
            last_heartbeat_at=_now(),
        )
        db.add(worker)
        db.flush()
    else:
        worker.provider = provider
        worker.model = model
        worker.capabilities = capabilities
        worker.last_heartbeat_at = worker.last_heartbeat_at or _now()
    return worker


def _load_agents(db: Session, *, tenant_id: UUID, mission_id: UUID) -> list[AgentWorker]:
    organization = (
        db.query(ArceusMissionOrganization)
        .filter(ArceusMissionOrganization.tenant_id == tenant_id, ArceusMissionOrganization.mission_id == mission_id)
        .first()
    )
    workers: list[ArceusAgentRuntimeWorker] = []
    if organization is not None:
        members = (
            db.query(ArceusOrganizationMember)
            .filter(
                ArceusOrganizationMember.tenant_id == tenant_id,
                ArceusOrganizationMember.organization_id == organization.id,
                ArceusOrganizationMember.status == "active",
            )
            .order_by(ArceusOrganizationMember.created_at.asc(), ArceusOrganizationMember.id.asc())
            .all()
        )
        for member in members:
            policy = member.authority or {}
            workers.append(
                _ensure_worker(
                    db,
                    tenant_id=tenant_id,
                    mission_id=mission_id,
                    role=member.role_key,
                    provider=str(policy.get("provider") or "arceus"),
                    model=str(policy.get("model") or policy.get("model_profile") or "auto"),
                    organization_member_id=member.id,
                    capabilities=_metadata_capabilities(bool(member.can_implement), bool(member.can_review), bool(member.can_approve)),
                )
            )

    if not workers:
        for template in DEFAULT_VIRTUAL_AGENTS:
            workers.append(
                _ensure_worker(
                    db,
                    tenant_id=tenant_id,
                    mission_id=mission_id,
                    role=template.role,
                    provider=template.provider,
                    model=template.model,
                    capabilities=_metadata_capabilities(template.can_implement, template.can_review, template.can_approve),
                )
            )
    return [_worker_to_agent(worker) for worker in workers]


def _member_by_id(db: Session, *, tenant_id: UUID, member_id: str | None) -> ArceusOrganizationMember | None:
    if not member_id:
        return None
    try:
        member_uuid = UUID(member_id)
    except ValueError:
        return None
    return db.query(ArceusOrganizationMember).filter(ArceusOrganizationMember.tenant_id == tenant_id, ArceusOrganizationMember.id == member_uuid).first()


def _agent_match(task: ArceusTask, agent: AgentWorker) -> tuple[float, list[str]]:
    task_type = (task.task_type or "").lower()
    role = agent.role.lower()
    reasons: list[str] = []
    if agent.status != "idle":
        return -10_000.0, ["Worker is not idle."]
    if task.owner_member_id and str(task.owner_member_id) != agent.member_id:
        return -100.0, ["Task is already owned by another member."]

    execution_class = _execution_class(task)
    if execution_class == TaskExecutionClass.WRITE_SENSITIVE and not agent.can_implement:
        return -1_000.0, ["Write-sensitive task requires implementation authority."]

    score = 0.25
    if task_type and task_type in role:
        score += 0.25
        reasons.append(f"Role matches task type {task_type}.")
    if "backend" in task_type and "backend" in role:
        score += 0.30
        reasons.append("Backend role matches backend task.")
    if "frontend" in task_type and "frontend" in role:
        score += 0.30
        reasons.append("Frontend role matches frontend task.")
    if execution_class in {TaskExecutionClass.REVIEW, TaskExecutionClass.VERIFICATION} and (agent.can_review or "review" in role or "qa" in role or "test" in role):
        score += 0.30
        reasons.append("Reviewer capability matches verification/review work.")
    if agent.can_implement and execution_class == TaskExecutionClass.WRITE_SENSITIVE:
        score += 0.20
        reasons.append("Worker can implement write-sensitive changes.")
    if agent.can_review and execution_class != TaskExecutionClass.WRITE_SENSITIVE:
        score += 0.10
        reasons.append("Worker has review authority.")
    if task.owner_member_id and str(task.owner_member_id) == agent.member_id:
        score += 0.40
        reasons.append("Exact owner member match.")
    reasons.append("Worker currently idle.")
    return min(score, 0.99), reasons


def _choose_agent(task: ArceusTask, agents: list[AgentWorker]) -> tuple[AgentWorker | None, float, list[str]]:
    ranked = sorted(((agent, *_agent_match(task, agent)) for agent in agents), key=lambda item: (item[1], item[0].role), reverse=True)
    if not ranked or ranked[0][1] <= -1_000:
        return None, 0.0, []
    return ranked[0]


def _active_path_reservations(db: Session, *, tenant_id: UUID, mission_id: UUID) -> list[ArceusMissionPathReservation]:
    return (
        db.query(ArceusMissionPathReservation)
        .filter(
            ArceusMissionPathReservation.tenant_id == tenant_id,
            ArceusMissionPathReservation.mission_id == mission_id,
            ArceusMissionPathReservation.status == "active",
        )
        .order_by(ArceusMissionPathReservation.acquired_at.asc(), ArceusMissionPathReservation.id.asc())
        .all()
    )


def _reservation_owner_task_key(db: Session, reservation: ArceusMissionPathReservation) -> str | None:
    task = db.query(ArceusTask).filter(ArceusTask.tenant_id == reservation.tenant_id, ArceusTask.id == reservation.task_id).first()
    return task.task_key if task else None


def _find_path_conflict(
    db: Session,
    *,
    requested_paths: list[str],
    requested_mode: str,
    active_reservations: list[ArceusMissionPathReservation],
) -> ArceusMissionPathReservation | None:
    for reservation in active_reservations:
        if reservation_modes_conflict(reservation.reservation_mode, requested_mode):
            for path in requested_paths:
                if path_patterns_overlap(reservation.path_pattern, path):
                    return reservation
    return None


def _release_completed_runtime_state(db: Session, *, tenant_id: UUID, mission_id: UUID, correlation_id: UUID, actor_id: str) -> None:
    terminal_tasks = (
        db.query(ArceusTask)
        .filter(ArceusTask.tenant_id == tenant_id, ArceusTask.mission_id == mission_id, ArceusTask.status.in_(TERMINAL_TASK_STATUSES))
        .all()
    )
    terminal_by_id = {task.id: task for task in terminal_tasks}
    if not terminal_by_id:
        return

    active_assignments = (
        db.query(ArceusMissionTaskAssignment)
        .filter(
            ArceusMissionTaskAssignment.tenant_id == tenant_id,
            ArceusMissionTaskAssignment.mission_id == mission_id,
            ArceusMissionTaskAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
            ArceusMissionTaskAssignment.task_id.in_(terminal_by_id.keys()),
        )
        .all()
    )
    now = _now()
    for assignment in active_assignments:
        task = terminal_by_id.get(assignment.task_id)
        assignment.status = "completed" if task and task.status == "completed" else "failed"
        assignment.completed_at = now if assignment.status == "completed" else assignment.completed_at
        assignment.released_at = now
        assignment.version_number = int(assignment.version_number or 1) + 1
        worker = db.query(ArceusAgentRuntimeWorker).filter(ArceusAgentRuntimeWorker.tenant_id == tenant_id, ArceusAgentRuntimeWorker.id == assignment.worker_id).first()
        if worker is not None:
            worker.status = "idle"
            worker.current_task_id = None
            worker.last_heartbeat_at = now
            worker.version_number = int(worker.version_number or 1) + 1
        append_runtime_event(
            db,
            tenant_id=tenant_id,
            mission_id=mission_id,
            event_type="task.assignment.released",
            actor_type="runtime",
            actor_id=actor_id,
            payload={"assignment_id": str(assignment.id), "task_id": str(assignment.task_id), "status": assignment.status},
            correlation_id=correlation_id,
            idempotency_key=f"task.assignment.released:{assignment.id}:{assignment.version_number}",
            outbox_topic="arceus.task.assignment.released",
        )

    reservations = (
        db.query(ArceusMissionPathReservation)
        .filter(
            ArceusMissionPathReservation.tenant_id == tenant_id,
            ArceusMissionPathReservation.mission_id == mission_id,
            ArceusMissionPathReservation.status == "active",
            ArceusMissionPathReservation.task_id.in_(terminal_by_id.keys()),
        )
        .all()
    )
    for reservation in reservations:
        reservation.status = "released"
        reservation.released_at = now
        reservation.version_number = int(reservation.version_number or 1) + 1
        append_runtime_event(
            db,
            tenant_id=tenant_id,
            mission_id=mission_id,
            event_type="path.reservation.released",
            actor_type="runtime",
            actor_id=actor_id,
            payload={"reservation_id": str(reservation.id), "task_id": str(reservation.task_id), "path_pattern": reservation.path_pattern},
            correlation_id=correlation_id,
            idempotency_key=f"path.reservation.released:{reservation.id}:{reservation.version_number}",
            outbox_topic="arceus.path.reservation.released",
        )


def _expire_stale_assignments(db: Session, *, tenant_id: UUID, mission_id: UUID, correlation_id: UUID, actor_id: str) -> None:
    now = _now()
    expired = (
        db.query(ArceusMissionTaskAssignment)
        .filter(
            ArceusMissionTaskAssignment.tenant_id == tenant_id,
            ArceusMissionTaskAssignment.mission_id == mission_id,
            ArceusMissionTaskAssignment.status.in_(ACTIVE_ASSIGNMENT_STATUSES),
            ArceusMissionTaskAssignment.lease_expires_at.isnot(None),
            ArceusMissionTaskAssignment.lease_expires_at <= now,
        )
        .all()
    )
    for assignment in expired:
        previous_status = assignment.status
        assignment.status = "expired"
        assignment.released_at = now
        assignment.version_number = int(assignment.version_number or 1) + 1
        task = db.query(ArceusTask).filter(ArceusTask.tenant_id == tenant_id, ArceusTask.id == assignment.task_id).first()
        task_requeued = False
        if task is not None and task.status == "running":
            task.status = "ready"
            task.failure_reason = None
            task.version_number = int(task.version_number or 1) + 1
            task_requeued = True
        worker = db.query(ArceusAgentRuntimeWorker).filter(ArceusAgentRuntimeWorker.tenant_id == tenant_id, ArceusAgentRuntimeWorker.id == assignment.worker_id).first()
        if worker is not None:
            worker.status = "idle"
            worker.current_task_id = None
            worker.last_heartbeat_at = now
            worker.version_number = int(worker.version_number or 1) + 1
        reservations = (
            db.query(ArceusMissionPathReservation)
            .filter(
                ArceusMissionPathReservation.tenant_id == tenant_id,
                ArceusMissionPathReservation.assignment_id == assignment.id,
                ArceusMissionPathReservation.status == "active",
            )
            .all()
        )
        for reservation in reservations:
            reservation.status = "expired"
            reservation.released_at = now
            reservation.version_number = int(reservation.version_number or 1) + 1
        append_runtime_event(
            db,
            tenant_id=tenant_id,
            mission_id=mission_id,
            event_type="task.assignment.expired",
            actor_type="runtime",
            actor_id=actor_id,
            payload={
                "assignment_id": str(assignment.id),
                "task_id": str(assignment.task_id),
                "previous_status": previous_status,
                "task_requeued": task_requeued,
            },
            correlation_id=correlation_id,
            idempotency_key=f"task.assignment.expired:{assignment.id}:{assignment.version_number}",
            outbox_topic="arceus.task.assignment.expired",
        )


def _capacity_state(active_assignments: list[ArceusMissionTaskAssignment], limits: dict[str, int]) -> CapacityState:
    by_class: dict[str, int] = {}
    for assignment in active_assignments:
        execution_class = str((assignment.metadata_json or {}).get("execution_class") or TaskExecutionClass.READ_ONLY.value)
        by_class[execution_class] = by_class.get(execution_class, 0) + 1
    return CapacityState(active=len(active_assignments), limit=int(limits["total"]), by_class=by_class, limits=dict(limits))


def _capacity_allows(capacity: CapacityState, execution_class: TaskExecutionClass) -> bool:
    if capacity.active >= capacity.limit:
        return False
    limit = capacity.limits.get(execution_class.value)
    if limit is None:
        return True
    return capacity.by_class.get(execution_class.value, 0) < int(limit)


def _consume_capacity(capacity: CapacityState, execution_class: TaskExecutionClass) -> None:
    capacity.active += 1
    capacity.by_class[execution_class.value] = capacity.by_class.get(execution_class.value, 0) + 1


class MissionScheduler:
    def __init__(self, db: Session, *, tenant_id: UUID, mission_id: UUID, correlation_id: UUID, actor_id: str = "mission-scheduler"):
        self.db = db
        self.tenant_id = tenant_id
        self.mission_id = mission_id
        self.correlation_id = correlation_id
        self.actor_id = actor_id

    def schedule_ready_tasks(self, *, max_assignments: int = 4) -> ScheduleSummary:
        mission = self.db.query(ArceusMission).filter(ArceusMission.tenant_id == self.tenant_id, ArceusMission.id == self.mission_id).first()
        if mission is None:
            raise ValueError("Mission not found.")

        dispatch = dispatch_mission(self.db, tenant_id=self.tenant_id, mission_id=self.mission_id, correlation_id=self.correlation_id, actor_id=self.actor_id)
        _release_completed_runtime_state(self.db, tenant_id=self.tenant_id, mission_id=mission.id, correlation_id=self.correlation_id, actor_id=self.actor_id)
        _expire_stale_assignments(self.db, tenant_id=self.tenant_id, mission_id=mission.id, correlation_id=self.correlation_id, actor_id=self.actor_id)

        active_leases = _active_leases(self.db, tenant_id=self.tenant_id, mission_id=mission.id)
        agents = _load_agents(self.db, tenant_id=self.tenant_id, mission_id=mission.id)
        active_assignments = _active_assignments(self.db, tenant_id=self.tenant_id, mission_id=mission.id)
        assigned_by_task = _assignment_by_task(active_assignments)
        active_reservations = _active_path_reservations(self.db, tenant_id=self.tenant_id, mission_id=mission.id)
        limits = dict(DEFAULT_LIMITS)
        limits.update(((mission.metadata_json or {}).get("scheduler_limits") or {}))
        capacity = _capacity_state(active_assignments, limits)
        repository_id = _repository_id(self.db, tenant_id=self.tenant_id, mission=mission)

        ready_tasks = (
            self.db.query(ArceusTask)
            .filter(ArceusTask.tenant_id == self.tenant_id, ArceusTask.mission_id == mission.id, ArceusTask.status == "ready")
            .order_by(ArceusTask.priority.desc() if hasattr(ArceusTask, "priority") else ArceusTask.created_at.asc(), ArceusTask.created_at.asc(), ArceusTask.id.asc())
            .all()
        )

        assignments: list[ScheduledAssignment] = []
        waiting: list[WaitingTask] = []
        for task in ready_tasks:
            if len(assignments) >= max_assignments:
                break
            if task.id in active_leases:
                waiting.append(WaitingTask(task_id=str(task.id), task_key=task.task_key, reason="desktop_lease_active"))
                continue
            if task.id in assigned_by_task:
                existing = assigned_by_task[task.id]
                waiting.append(WaitingTask(task_id=str(task.id), task_key=task.task_key, reason="assignment_active", blocked_by_assignment_id=str(existing.id)))
                continue

            execution_class = _execution_class(task)
            if not _capacity_allows(capacity, execution_class):
                waiting.append(WaitingTask(task_id=str(task.id), task_key=task.task_key, reason="capacity"))
                append_runtime_event(
                    self.db,
                    tenant_id=self.tenant_id,
                    mission_id=mission.id,
                    event_type="task.waiting.capacity",
                    actor_type="runtime",
                    actor_id=self.actor_id,
                    payload={"task_id": str(task.id), "task_key": task.task_key, "execution_class": execution_class.value},
                    correlation_id=self.correlation_id,
                    idempotency_key=f"task.waiting.capacity:{task.id}:{task.version_number}",
                )
                continue

            try:
                reserved_paths = _task_paths(task) if _requires_write(task) else []
            except PathPolicyError as exc:
                waiting.append(WaitingTask(task_id=str(task.id), task_key=task.task_key, reason=f"path_policy:{exc}"))
                continue
            reservation_mode = _reservation_mode(task)
            conflict = _find_path_conflict(self.db, requested_paths=reserved_paths, requested_mode=reservation_mode, active_reservations=active_reservations)
            if conflict is not None:
                waiting.append(
                    WaitingTask(
                        task_id=str(task.id),
                        task_key=task.task_key,
                        reason="path_conflict",
                        blocked_by_task_id=str(conflict.task_id),
                        blocked_by_assignment_id=str(conflict.assignment_id) if conflict.assignment_id else None,
                    )
                )
                append_runtime_event(
                    self.db,
                    tenant_id=self.tenant_id,
                    mission_id=mission.id,
                    event_type="task.waiting.path_conflict",
                    actor_type="runtime",
                    actor_id=self.actor_id,
                    payload={"task_id": str(task.id), "task_key": task.task_key, "blocked_by_task_id": str(conflict.task_id), "path_pattern": conflict.path_pattern},
                    correlation_id=self.correlation_id,
                    idempotency_key=f"task.waiting.path_conflict:{task.id}:{task.version_number}",
                )
                continue

            agent, score, reasons = _choose_agent(task, agents)
            if agent is None:
                waiting.append(WaitingTask(task_id=str(task.id), task_key=task.task_key, reason="no_matching_worker"))
                append_runtime_event(
                    self.db,
                    tenant_id=self.tenant_id,
                    mission_id=mission.id,
                    event_type="task.waiting.no_worker",
                    actor_type="runtime",
                    actor_id=self.actor_id,
                    payload={"task_id": str(task.id), "task_key": task.task_key, "execution_class": execution_class.value},
                    correlation_id=self.correlation_id,
                    idempotency_key=f"task.waiting.no_worker:{task.id}:{task.version_number}",
                )
                continue

            worker = self.db.query(ArceusAgentRuntimeWorker).filter(ArceusAgentRuntimeWorker.tenant_id == self.tenant_id, ArceusAgentRuntimeWorker.id == UUID(agent.id)).first()
            if worker is None:
                waiting.append(WaitingTask(task_id=str(task.id), task_key=task.task_key, reason="worker_missing"))
                continue
            member = _member_by_id(self.db, tenant_id=self.tenant_id, member_id=agent.member_id)
            had_owner = bool(task.owner_member_id)
            if member is not None:
                task.owner_member_id = member.id

            now = _now()
            assignment = ArceusMissionTaskAssignment(
                tenant_id=self.tenant_id,
                mission_id=mission.id,
                task_id=task.id,
                worker_id=worker.id,
                status="assigned",
                assignment_reason="; ".join(reasons),
                score=score,
                lease_expires_at=now + timedelta(seconds=ASSIGNMENT_ACCEPTANCE_TIMEOUT_SECONDS),
                last_heartbeat_at=now,
                metadata_json={"execution_class": execution_class.value, "reasons": reasons},
            )
            self.db.add(assignment)
            self.db.flush()

            for path in reserved_paths:
                reservation = ArceusMissionPathReservation(
                    tenant_id=self.tenant_id,
                    repository_id=repository_id,
                    mission_id=mission.id,
                    task_id=task.id,
                    assignment_id=assignment.id,
                    path_pattern=path,
                    reservation_mode=reservation_mode,
                    status="active",
                    expires_at=assignment.lease_expires_at,
                    metadata_json={"execution_class": execution_class.value},
                )
                self.db.add(reservation)
                self.db.flush()
                active_reservations.append(reservation)
                append_runtime_event(
                    self.db,
                    tenant_id=self.tenant_id,
                    mission_id=mission.id,
                    event_type="path.reservation.acquired",
                    actor_type="runtime",
                    actor_id=self.actor_id,
                    payload={"reservation_id": str(reservation.id), "assignment_id": str(assignment.id), "task_id": str(task.id), "path_pattern": path, "mode": reservation_mode},
                    correlation_id=self.correlation_id,
                    idempotency_key=f"path.reservation.acquired:{reservation.id}:{reservation.version_number}",
                    outbox_topic="arceus.path.reservation.acquired",
                )

            scheduler_state = dict((task.output_contract or {}).get("scheduler") or {})
            scheduler_state.update(
                {
                    "assignment_id": str(assignment.id),
                    "assigned_agent_id": agent.id,
                    "assigned_role": agent.role,
                    "execution_class": execution_class.value,
                    "reserved_paths": reserved_paths,
                    "scheduled_at": now.isoformat(),
                    "parallel_safe": not bool(reserved_paths),
                    "score": score,
                }
            )
            output_contract = dict(task.output_contract or {})
            output_contract["scheduler"] = scheduler_state
            task.output_contract = output_contract
            task.version_number = int(task.version_number or 1) + 1

            worker.status = "reserved"
            worker.current_task_id = task.id
            worker.last_heartbeat_at = now
            worker.version_number = int(worker.version_number or 1) + 1
            agent.status = "reserved"
            agent.current_task = task.task_key
            _consume_capacity(capacity, execution_class)

            scheduled = ScheduledAssignment(
                task_id=str(task.id),
                task_key=task.task_key,
                task_type=task.task_type,
                assignment_id=str(assignment.id),
                agent_id=agent.id,
                role=agent.role,
                execution_class=execution_class.value,
                score=float(score),
                reserved_paths=reserved_paths,
                reason="owner match" if had_owner else "best available specialist",
                reasons=reasons,
            )
            assignments.append(scheduled)
            append_runtime_event(
                self.db,
                tenant_id=self.tenant_id,
                mission_id=mission.id,
                event_type="task.assignment.created",
                actor_type="runtime",
                actor_id=self.actor_id,
                payload={
                    "assignment_id": scheduled.assignment_id,
                    "task_id": scheduled.task_id,
                    "task_key": scheduled.task_key,
                    "agent_id": scheduled.agent_id,
                    "role": scheduled.role,
                    "execution_class": scheduled.execution_class,
                    "reserved_paths": scheduled.reserved_paths,
                    "score": scheduled.score,
                    "reasons": scheduled.reasons,
                },
                correlation_id=self.correlation_id,
                idempotency_key=f"task.assignment.created:{assignment.id}:{assignment.version_number}",
                outbox_topic="arceus.task.assignment.created",
            )

        self.db.flush()
        active_reservation_map = {reservation.path_pattern: _reservation_owner_task_key(self.db, reservation) or str(reservation.task_id) for reservation in active_reservations if reservation.status == "active"}
        return ScheduleSummary(
            mission_id=str(mission.id),
            mission_status=mission.status,
            agents=agents,
            assignments=assignments,
            ready_tasks=[task.task_key for task in ready_tasks],
            waiting_tasks=[item.task_key for item in waiting],
            waiting=waiting,
            path_reservations=active_reservation_map,
            capacity=capacity,
            dispatch_events=dispatch.events,
        )


def schedule_ready_tasks(
    db: Session,
    *,
    tenant_id: UUID,
    mission_id: UUID,
    correlation_id: UUID,
    actor_id: str = "mission-scheduler",
    max_assignments: int = 4,
) -> ScheduleSummary:
    scheduler = MissionScheduler(db, tenant_id=tenant_id, mission_id=mission_id, correlation_id=correlation_id, actor_id=actor_id)
    return scheduler.schedule_ready_tasks(max_assignments=max_assignments)
