from __future__ import annotations

from datetime import datetime
from statistics import mean
from uuid import UUID

from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusAgentRuntimeWorker,
    ArceusEvent,
    ArceusMission,
    ArceusMissionPathReservation,
    ArceusMissionTaskAssignment,
    ArceusTask,
    ArceusTaskDependency,
)

from .dispatcher import utc_now


ACTIVE_ASSIGNMENT_STATES = {"assigned", "accepted", "running"}
TERMINAL_TASK_STATES = {"completed", "failed", "cancelled"}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _seconds_between(start: datetime | None, end: datetime | None) -> float | None:
    if not start or not end:
        return None
    return max(0.0, (end - start).total_seconds())


def _age_seconds(value: datetime | None, *, now: datetime) -> float | None:
    return _seconds_between(value, now)


def _avg(values: list[float]) -> float | None:
    return round(mean(values), 3) if values else None


def _dependency_blocked_reason(task: ArceusTask, dependencies_by_task: dict[UUID, list[UUID]], tasks_by_id: dict[UUID, ArceusTask]) -> str | None:
    if task.status in TERMINAL_TASK_STATES:
        return None
    blockers = []
    for blocker_id in dependencies_by_task.get(task.id, []):
        blocker = tasks_by_id.get(blocker_id)
        if blocker and blocker.status != "completed":
            blockers.append(f"{blocker.task_key}:{blocker.status}")
    if blockers:
        return "waiting_for_dependencies:" + ",".join(blockers)
    if task.failure_reason:
        return task.failure_reason
    scheduler = (task.output_contract or {}).get("scheduler") if isinstance(task.output_contract, dict) else None
    if isinstance(scheduler, dict):
        reason = scheduler.get("last_wait_reason") or scheduler.get("blocked_reason")
        if reason:
            return str(reason)
    return None


def _recovery_reports(assignments: list[ArceusMissionTaskAssignment], tasks_by_id: dict[UUID, ArceusTask]) -> list[dict]:
    reports: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for assignment in assignments:
        metadata = assignment.metadata_json or {}
        raw_reports = metadata.get("recovery_reports") or {}
        if isinstance(raw_reports, dict):
            iterable = raw_reports.values()
        elif isinstance(raw_reports, list):
            iterable = raw_reports
        else:
            iterable = []
        latest = metadata.get("latest_recovery_report")
        if isinstance(latest, dict):
            iterable = [*iterable, latest]
        task = tasks_by_id.get(assignment.task_id)
        for report in iterable:
            if not isinstance(report, dict):
                continue
            report_id = str(report.get("report_id") or report.get("request_hash") or "unknown")
            key = (str(assignment.id), report_id)
            if key in seen:
                continue
            seen.add(key)
            reports.append(
                {
                    "assignment_id": str(assignment.id),
                    "task_id": str(assignment.task_id),
                    "task_key": task.task_key if task else None,
                    "status": report.get("status"),
                    "local_stage": report.get("local_stage"),
                    "repository_state": report.get("repository_state"),
                    "recommended_action": report.get("recommended_action"),
                    "report_id": report_id,
                    "recorded_at": report.get("recorded_at"),
                    "artifacts": report.get("artifacts") or {},
                    "reconciliation": report.get("reconciliation") or {},
                }
            )
    return sorted(reports, key=lambda item: str(item.get("recorded_at") or ""), reverse=True)


def build_mission_observability(db: Session, *, tenant_id: UUID, mission_id: UUID, event_limit: int = 80) -> dict:
    now = utc_now()
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == tenant_id, ArceusMission.id == mission_id).first()
    if mission is None:
        raise ValueError("MISSION_NOT_FOUND")

    tasks = (
        db.query(ArceusTask)
        .filter(ArceusTask.tenant_id == tenant_id, ArceusTask.mission_id == mission.id)
        .order_by(ArceusTask.created_at.asc(), ArceusTask.id.asc())
        .all()
    )
    tasks_by_id = {task.id: task for task in tasks}
    dependencies = (
        db.query(ArceusTaskDependency)
        .filter(ArceusTaskDependency.tenant_id == tenant_id, ArceusTaskDependency.task_id.in_([task.id for task in tasks] or [UUID(int=0)]))
        .all()
    )
    dependencies_by_task: dict[UUID, list[UUID]] = {}
    for dependency in dependencies:
        dependencies_by_task.setdefault(dependency.task_id, []).append(dependency.depends_on_task_id)

    assignments = (
        db.query(ArceusMissionTaskAssignment)
        .filter(ArceusMissionTaskAssignment.tenant_id == tenant_id, ArceusMissionTaskAssignment.mission_id == mission.id)
        .order_by(ArceusMissionTaskAssignment.assigned_at.desc(), ArceusMissionTaskAssignment.id.desc())
        .all()
    )
    active_assignments_by_worker = {assignment.worker_id: assignment for assignment in assignments if assignment.status in ACTIVE_ASSIGNMENT_STATES}
    latest_assignment_by_task: dict[UUID, ArceusMissionTaskAssignment] = {}
    for assignment in assignments:
        latest_assignment_by_task.setdefault(assignment.task_id, assignment)

    workers = (
        db.query(ArceusAgentRuntimeWorker)
        .filter(ArceusAgentRuntimeWorker.tenant_id == tenant_id, ArceusAgentRuntimeWorker.current_mission_id == mission.id)
        .order_by(ArceusAgentRuntimeWorker.role.asc(), ArceusAgentRuntimeWorker.id.asc())
        .all()
    )
    reservations = (
        db.query(ArceusMissionPathReservation)
        .filter(ArceusMissionPathReservation.tenant_id == tenant_id, ArceusMissionPathReservation.mission_id == mission.id)
        .order_by(ArceusMissionPathReservation.acquired_at.desc(), ArceusMissionPathReservation.id.desc())
        .all()
    )
    events = (
        db.query(ArceusEvent)
        .filter(ArceusEvent.tenant_id == tenant_id, ArceusEvent.aggregate_type == "mission", ArceusEvent.aggregate_id == mission.id)
        .order_by(ArceusEvent.occurred_at.desc(), ArceusEvent.aggregate_version.desc())
        .limit(max(1, min(event_limit, 500)))
        .all()
    )

    queue_durations = [
        duration
        for assignment in assignments
        if (duration := _seconds_between(tasks_by_id.get(assignment.task_id).created_at if tasks_by_id.get(assignment.task_id) else None, assignment.assigned_at)) is not None
    ]
    assignment_durations = [
        duration
        for assignment in assignments
        if (duration := _seconds_between(assignment.started_at or assignment.assigned_at, assignment.completed_at or assignment.released_at)) is not None
    ]
    recovery = _recovery_reports(assignments, tasks_by_id)
    event_types = [event.event_type for event in events]

    dag_nodes = []
    for task in tasks:
        assignment = latest_assignment_by_task.get(task.id)
        dag_nodes.append(
            {
                "task_id": str(task.id),
                "task_key": task.task_key,
                "title": task.title,
                "task_type": task.task_type,
                "status": task.status,
                "owner_member_id": str(task.owner_member_id) if task.owner_member_id else None,
                "blocked_reason": _dependency_blocked_reason(task, dependencies_by_task, tasks_by_id),
                "assignment_id": str(assignment.id) if assignment else None,
                "assignment_status": assignment.status if assignment else None,
                "started_at": _iso(task.started_at),
                "completed_at": _iso(task.completed_at),
            }
        )

    return {
        "mission_id": str(mission.id),
        "mission": {
            "id": str(mission.id),
            "title": mission.title,
            "status": mission.status,
            "risk_level": mission.risk_level,
            "priority": mission.priority,
            "created_at": _iso(mission.created_at),
            "completed_at": _iso(mission.completed_at),
            "failed_at": _iso(mission.failed_at),
            "duration_seconds": _seconds_between(mission.created_at, mission.completed_at or mission.failed_at or now),
        },
        "timeline": [
            {
                "event_id": str(event.id),
                "sequence": int(event.aggregate_version),
                "event_type": event.event_type,
                "actor_type": event.actor_type,
                "actor_id": event.actor_id,
                "payload": event.payload or {},
                "metadata": event.metadata_json or {},
                "occurred_at": _iso(event.occurred_at),
            }
            for event in reversed(events)
        ],
        "workers": [
            {
                "worker_id": str(worker.id),
                "role": worker.role,
                "provider": worker.provider,
                "model": worker.model,
                "status": worker.status,
                "current_task_id": str(worker.current_task_id) if worker.current_task_id else None,
                "current_task_key": tasks_by_id.get(worker.current_task_id).task_key if worker.current_task_id in tasks_by_id else None,
                "current_assignment_id": str(active_assignments_by_worker[worker.id].id) if worker.id in active_assignments_by_worker else None,
                "assignment_status": active_assignments_by_worker[worker.id].status if worker.id in active_assignments_by_worker else None,
                "lease_expires_at": _iso(active_assignments_by_worker[worker.id].lease_expires_at) if worker.id in active_assignments_by_worker else None,
                "last_heartbeat_at": _iso(worker.last_heartbeat_at),
                "heartbeat_age_seconds": _age_seconds(worker.last_heartbeat_at, now=now),
                "capabilities": worker.capabilities or {},
                "metadata": worker.metadata_json or {},
            }
            for worker in workers
        ],
        "reservations": [
            {
                "reservation_id": str(reservation.id),
                "repository_id": str(reservation.repository_id),
                "task_id": str(reservation.task_id),
                "task_key": tasks_by_id.get(reservation.task_id).task_key if reservation.task_id in tasks_by_id else None,
                "assignment_id": str(reservation.assignment_id) if reservation.assignment_id else None,
                "path_pattern": reservation.path_pattern,
                "reservation_mode": reservation.reservation_mode,
                "status": reservation.status,
                "acquired_at": _iso(reservation.acquired_at),
                "expires_at": _iso(reservation.expires_at),
                "released_at": _iso(reservation.released_at),
                "metadata": reservation.metadata_json or {},
            }
            for reservation in reservations
        ],
        "dag": {
            "nodes": dag_nodes,
            "edges": [
                {
                    "from_task_id": str(dependency.depends_on_task_id),
                    "to_task_id": str(dependency.task_id),
                    "dependency_type": dependency.dependency_type,
                    "from_task_key": tasks_by_id.get(dependency.depends_on_task_id).task_key if dependency.depends_on_task_id in tasks_by_id else None,
                    "to_task_key": tasks_by_id.get(dependency.task_id).task_key if dependency.task_id in tasks_by_id else None,
                }
                for dependency in dependencies
            ],
        },
        "recovery": recovery,
        "metrics": {
            "task_count": len(tasks),
            "ready_tasks": sum(1 for task in tasks if task.status == "ready"),
            "running_tasks": sum(1 for task in tasks if task.status == "running"),
            "blocked_tasks": sum(1 for task in tasks if task.status == "blocked" or _dependency_blocked_reason(task, dependencies_by_task, tasks_by_id)),
            "completed_tasks": sum(1 for task in tasks if task.status == "completed"),
            "failed_tasks": sum(1 for task in tasks if task.status == "failed"),
            "assignment_count": len(assignments),
            "active_assignments": sum(1 for assignment in assignments if assignment.status in ACTIVE_ASSIGNMENT_STATES),
            "active_reservations": sum(1 for reservation in reservations if reservation.status == "active"),
            "recovery_reports": len(recovery),
            "manual_review_required": sum(1 for report in recovery if report.get("status") == "manual_review_required" or report.get("recommended_action") == "manual_review_required"),
            "lease_renewals": sum(1 for event_type in event_types if "lease" in event_type and ("renew" in event_type or "heartbeat" in event_type)),
            "rollbacks": sum(1 for event_type in event_types if "rollback" in event_type),
            "verification_events": sum(1 for event_type in event_types if "verification" in event_type or "evidence" in event_type),
            "failed_assignments": sum(1 for assignment in assignments if assignment.status == "failed"),
            "expired_assignments": sum(1 for assignment in assignments if assignment.status == "expired"),
            "average_queue_seconds": _avg(queue_durations),
            "average_assignment_duration_seconds": _avg(assignment_durations),
            "mission_duration_seconds": _seconds_between(mission.created_at, mission.completed_at or mission.failed_at or now),
        },
    }
