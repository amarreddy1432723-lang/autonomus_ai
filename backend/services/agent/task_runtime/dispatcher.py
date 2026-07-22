from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusEvent,
    ArceusMission,
    ArceusOutboxMessage,
    ArceusTask,
    ArceusTaskDependency,
    ArceusWorkerLease,
)


TERMINAL_TASK_STATUSES = {"completed", "failed", "cancelled"}
RUNNABLE_MISSION_STATUSES = {"ready", "running"}


@dataclass
class DispatchSummary:
    mission_id: str
    mission_status: str
    expired_leases: list[str] = field(default_factory=list)
    requeued_tasks: list[str] = field(default_factory=list)
    ready_tasks: list[str] = field(default_factory=list)
    blocked_tasks: list[str] = field(default_factory=list)
    completed_tasks: list[str] = field(default_factory=list)
    failed_tasks: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def next_event_sequence(db: Session, *, tenant_id: UUID, aggregate_type: str, aggregate_id: UUID) -> int:
    current = (
        db.query(func.max(ArceusEvent.aggregate_version))
        .filter(
            ArceusEvent.tenant_id == tenant_id,
            ArceusEvent.aggregate_type == aggregate_type,
            ArceusEvent.aggregate_id == aggregate_id,
        )
        .scalar()
        or 0
    )
    return int(current) + 1


def append_runtime_event(
    db: Session,
    *,
    tenant_id: UUID,
    mission_id: UUID,
    event_type: str,
    actor_type: str,
    actor_id: str,
    payload: dict,
    correlation_id: UUID,
    idempotency_key: str,
    outbox_topic: str | None = None,
) -> ArceusEvent:
    event = ArceusEvent(
        tenant_id=tenant_id,
        aggregate_type="mission",
        aggregate_id=mission_id,
        aggregate_version=next_event_sequence(db, tenant_id=tenant_id, aggregate_type="mission", aggregate_id=mission_id),
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
                payload={"event_id": str(event.id), "mission_id": str(mission_id), "event_type": event_type, **payload},
            )
        )
    return event


def tasks_for_mission(db: Session, *, tenant_id: UUID, mission_id: UUID) -> list[ArceusTask]:
    return (
        db.query(ArceusTask)
        .filter(ArceusTask.tenant_id == tenant_id, ArceusTask.mission_id == mission_id)
        .order_by(ArceusTask.created_at.asc(), ArceusTask.id.asc())
        .all()
    )


def dependencies_for_tasks(db: Session, *, tenant_id: UUID, tasks: list[ArceusTask]) -> list[ArceusTaskDependency]:
    task_ids = [task.id for task in tasks]
    if not task_ids:
        return []
    return (
        db.query(ArceusTaskDependency)
        .filter(ArceusTaskDependency.tenant_id == tenant_id, ArceusTaskDependency.task_id.in_(task_ids))
        .all()
    )


def expire_stale_leases(
    db: Session,
    *,
    tenant_id: UUID,
    mission_id: UUID,
    correlation_id: UUID,
    actor_id: str,
) -> tuple[list[str], list[str]]:
    now = utc_now()
    expired = (
        db.query(ArceusWorkerLease)
        .join(ArceusTask, ArceusTask.id == ArceusWorkerLease.task_id)
        .filter(
            ArceusWorkerLease.tenant_id == tenant_id,
            ArceusWorkerLease.status == "active",
            ArceusWorkerLease.expires_at <= now,
            ArceusTask.mission_id == mission_id,
        )
        .all()
    )
    expired_lease_ids: list[str] = []
    requeued_task_keys: list[str] = []
    for lease in expired:
        task = db.query(ArceusTask).filter(ArceusTask.tenant_id == tenant_id, ArceusTask.id == lease.task_id).first()
        lease.status = "expired"
        lease.version_number = int(lease.version_number or 1) + 1
        expired_lease_ids.append(str(lease.id))
        if task is not None and task.status == "running":
            task.status = "ready"
            task.failure_reason = None
            task.version_number = int(task.version_number or 1) + 1
            requeued_task_keys.append(task.task_key)
            append_runtime_event(
                db,
                tenant_id=tenant_id,
                mission_id=mission_id,
                event_type="task.lease.expired",
                actor_type="runtime",
                actor_id=actor_id,
                payload={"task_id": str(task.id), "task_key": task.task_key, "lease_id": str(lease.id)},
                correlation_id=correlation_id,
                idempotency_key=f"task.lease.expired:{lease.id}:{lease.version_number}",
                outbox_topic="arceus.task.ready",
            )
    return expired_lease_ids, requeued_task_keys


def release_dependency_unblocked_tasks(
    db: Session,
    *,
    tenant_id: UUID,
    mission_id: UUID,
    correlation_id: UUID,
    actor_id: str,
) -> tuple[list[str], list[str]]:
    tasks = tasks_for_mission(db, tenant_id=tenant_id, mission_id=mission_id)
    deps = dependencies_for_tasks(db, tenant_id=tenant_id, tasks=tasks)
    by_id = {task.id: task for task in tasks}
    completed_ids = {task.id for task in tasks if task.status == "completed"}
    deps_by_task: dict[UUID, set[UUID]] = {}
    for dep in deps:
        deps_by_task.setdefault(dep.task_id, set()).add(dep.depends_on_task_id)

    ready: list[str] = []
    blocked: list[str] = []
    for task in tasks:
        dependencies = deps_by_task.get(task.id, set())
        dependency_statuses = [by_id[dep_id].status for dep_id in dependencies if dep_id in by_id]
        if any(status in {"failed", "cancelled"} for status in dependency_statuses):
            if task.status in {"pending", "ready", "blocked"}:
                task.status = "blocked"
                task.version_number = int(task.version_number or 1) + 1
                blocked.append(task.task_key)
                append_runtime_event(
                    db,
                    tenant_id=tenant_id,
                    mission_id=mission_id,
                    event_type="task.blocked_by_dependency",
                    actor_type="runtime",
                    actor_id=actor_id,
                    payload={"task_id": str(task.id), "task_key": task.task_key},
                    correlation_id=correlation_id,
                    idempotency_key=f"task.blocked_by_dependency:{task.id}:{task.version_number}",
                )
            continue
        if task.status in {"pending", "blocked"} and dependencies.issubset(completed_ids):
            task.status = "ready"
            task.version_number = int(task.version_number or 1) + 1
            ready.append(task.task_key)
            append_runtime_event(
                db,
                tenant_id=tenant_id,
                mission_id=mission_id,
                event_type="task.ready",
                actor_type="runtime",
                actor_id=actor_id,
                payload={"task_id": str(task.id), "task_key": task.task_key},
                correlation_id=correlation_id,
                idempotency_key=f"task.ready:{task.id}:{task.version_number}",
                outbox_topic="arceus.task.ready",
            )
    return ready, blocked


def update_mission_completion(
    db: Session,
    *,
    tenant_id: UUID,
    mission: ArceusMission,
    correlation_id: UUID,
    actor_id: str,
) -> tuple[str, list[str], list[str]]:
    tasks = tasks_for_mission(db, tenant_id=tenant_id, mission_id=mission.id)
    completed = [task.task_key for task in tasks if task.status == "completed"]
    failed = [task.task_key for task in tasks if task.status == "failed"]
    blocked = [task.task_key for task in tasks if task.status == "blocked"]
    active = [task for task in tasks if task.status not in TERMINAL_TASK_STATUSES and task.status != "blocked"]

    if failed:
        if mission.status != "failed":
            mission.status = "failed"
            mission.failure_reason = f"{len(failed)} task(s) failed: {', '.join(failed[:5])}"
            mission.version_number = int(mission.version_number or 1) + 1
            append_runtime_event(
                db,
                tenant_id=tenant_id,
                mission_id=mission.id,
                event_type="mission.failed",
                actor_type="runtime",
                actor_id=actor_id,
                payload={"failed_tasks": failed, "completed_tasks": completed},
                correlation_id=correlation_id,
                idempotency_key=f"mission.failed:{mission.id}:{mission.version_number}",
            )
        return mission.status, completed, failed

    if tasks and not active and not blocked:
        if mission.status != "completed":
            mission.status = "completed"
            mission.completed_at = utc_now()
            mission.version_number = int(mission.version_number or 1) + 1
            append_runtime_event(
                db,
                tenant_id=tenant_id,
                mission_id=mission.id,
                event_type="mission.completed",
                actor_type="runtime",
                actor_id=actor_id,
                payload={"completed_tasks": completed, "task_count": len(tasks)},
                correlation_id=correlation_id,
                idempotency_key=f"mission.completed:{mission.id}:{mission.version_number}",
                outbox_topic="arceus.mission.completed",
            )
        return mission.status, completed, failed

    if blocked and not active:
        if mission.status != "blocked":
            mission.status = "blocked"
            mission.failure_reason = f"{len(blocked)} task(s) blocked by dependency or policy."
            mission.version_number = int(mission.version_number or 1) + 1
            append_runtime_event(
                db,
                tenant_id=tenant_id,
                mission_id=mission.id,
                event_type="mission.blocked",
                actor_type="runtime",
                actor_id=actor_id,
                payload={"blocked_tasks": blocked, "completed_tasks": completed},
                correlation_id=correlation_id,
                idempotency_key=f"mission.blocked:{mission.id}:{mission.version_number}",
            )
    return mission.status, completed, failed


def dispatch_mission(
    db: Session,
    *,
    tenant_id: UUID,
    mission_id: UUID,
    correlation_id: UUID,
    actor_id: str = "task-dispatcher",
) -> DispatchSummary:
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == tenant_id, ArceusMission.id == mission_id).first()
    if mission is None:
        raise ValueError("Mission not found.")
    if mission.status not in RUNNABLE_MISSION_STATUSES | {"completed", "failed", "blocked"}:
        return DispatchSummary(mission_id=str(mission.id), mission_status=mission.status)

    expired, requeued = expire_stale_leases(db, tenant_id=tenant_id, mission_id=mission.id, correlation_id=correlation_id, actor_id=actor_id)
    ready, blocked = release_dependency_unblocked_tasks(db, tenant_id=tenant_id, mission_id=mission.id, correlation_id=correlation_id, actor_id=actor_id)
    status, completed, failed = update_mission_completion(db, tenant_id=tenant_id, mission=mission, correlation_id=correlation_id, actor_id=actor_id)
    db.flush()
    events = [*([f"expired:{item}" for item in expired]), *([f"ready:{item}" for item in ready]), *([f"blocked:{item}" for item in blocked])]
    return DispatchSummary(
        mission_id=str(mission.id),
        mission_status=status,
        expired_leases=expired,
        requeued_tasks=requeued,
        ready_tasks=ready,
        blocked_tasks=blocked,
        completed_tasks=completed,
        failed_tasks=failed,
        events=events,
    )
