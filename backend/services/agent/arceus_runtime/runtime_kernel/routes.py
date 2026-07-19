from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusEvent,
    ArceusMission,
    ArceusProject,
    ArceusRuntimeCheckpoint,
    ArceusTask,
    ArceusTaskDependency,
    ArceusWorkerLease,
)
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    CheckpointRequest,
    CheckpointResponse,
    LeaseRequest,
    LeaseResponse,
    RuntimeActionResponse,
    RuntimeEventResponse,
    RuntimeMetricsResponse,
    RuntimeMissionRequest,
    RuntimeMissionResponse,
    RuntimeReplayResponse,
)
from .service import compile_mission_graph, create_checkpoint, grant_lease, replay_mission, runtime_metrics, sanitize_cognitive_state


router = APIRouter(prefix="/api/v1/runtime", tags=["runtime-kernel"])


SYSTEM_PROJECT_SLUG = "runtime-kernel"
RUNTIME_RETRY_POLICY = {"strategy": "exponential_backoff", "max_attempts": 3, "base_delay_seconds": 5, "jitter": True}
RUNTIME_EXECUTION_POLICY = {
    "isolated_workspace": True,
    "scoped_credentials": True,
    "sandboxed_network": True,
    "capability_token_required": True,
}


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _priority_0_to_5(priority: int) -> int:
    return max(0, min(5, round(priority / 20)))


def _runtime_status_from_mission(status: str) -> str:
    return {
        "draft": "created",
        "compiling": "planned",
        "compiled": "planned",
        "organizing": "planned",
        "plan_pending": "planned",
        "awaiting_plan_approval": "planned",
        "ready": "ready",
        "running": "running",
        "paused": "paused",
        "blocked": "blocked",
        "reviewing": "review",
        "verifying": "verification",
        "completed": "completed",
        "failed": "blocked",
        "cancelled": "cancelled",
        "archived": "archived",
    }.get(status, "created")


def _runtime_status_from_task(status: str, active_lease: ArceusWorkerLease | None) -> str:
    if status == "pending":
        return "pending"
    if status == "ready":
        return "queued"
    if status == "running":
        return "leased" if active_lease else "running"
    if status == "completed":
        return "succeeded"
    if status == "failed":
        return "failed"
    if status == "cancelled":
        return "cancelled"
    if status in {"blocked", "reviewing", "verifying"}:
        return "retry"
    return "pending"


def _parse_uuid(value: str, resource: str) -> UUID:
    try:
        return UUID(value)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=f"{resource} not found.") from exc


def _runtime_project(db: Session, context: RequestContext) -> ArceusProject:
    project = (
        db.query(ArceusProject)
        .filter(ArceusProject.tenant_id == context.tenant_id, ArceusProject.slug == SYSTEM_PROJECT_SLUG)
        .first()
    )
    if project is not None:
        return project
    project = ArceusProject(
        tenant_id=context.tenant_id,
        name="Runtime Kernel",
        slug=SYSTEM_PROJECT_SLUG,
        description="System project for durable Arceus runtime kernel missions.",
        status="active",
        settings={"system": True, "runtime_kernel": True},
        created_by=context.user_id,
    )
    db.add(project)
    db.flush()
    return project


def _mission_or_404(db: Session, context: RequestContext, mission_id: UUID) -> ArceusMission:
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.id == mission_id).first()
    if mission is None:
        raise HTTPException(status_code=404, detail="Runtime mission not found.")
    return mission


def _task_or_404(db: Session, context: RequestContext, task_id: UUID) -> ArceusTask:
    task = db.query(ArceusTask).filter(ArceusTask.tenant_id == context.tenant_id, ArceusTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail="Runtime task not found.")
    return task


def _next_event_version(db: Session, tenant_id: UUID, aggregate_type: str, aggregate_id: UUID) -> int:
    current = (
        db.query(func.max(ArceusEvent.aggregate_version))
        .filter(ArceusEvent.tenant_id == tenant_id, ArceusEvent.aggregate_type == aggregate_type, ArceusEvent.aggregate_id == aggregate_id)
        .scalar()
        or 0
    )
    return int(current) + 1


def _append_runtime_event(
    db: Session,
    context: RequestContext,
    *,
    aggregate_type: str,
    aggregate_id: UUID,
    event_type: str,
    payload: dict[str, Any],
) -> ArceusEvent:
    version = _next_event_version(db, context.tenant_id, aggregate_type, aggregate_id)
    event = ArceusEvent(
        tenant_id=context.tenant_id,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        aggregate_version=version,
        event_type=event_type,
        actor_type="human",
        actor_id=str(context.user_id),
        payload=payload,
        metadata_json={"correlation_id": str(context.correlation_id), "source": "runtime_kernel"},
    )
    db.add(event)
    db.flush()
    return event


def _event_response(event: ArceusEvent) -> dict[str, Any]:
    return RuntimeEventResponse(
        event_id=str(event.id),
        sequence=int(event.aggregate_version),
        aggregate_type=event.aggregate_type,
        aggregate_id=str(event.aggregate_id),
        event_type=event.event_type,
        payload=event.payload or {},
        occurred_at=event.occurred_at,
    ).model_dump(mode="json")


def _checkpoint_response(checkpoint: ArceusRuntimeCheckpoint) -> dict[str, Any]:
    state = checkpoint.execution_state or {}
    return {
        "checkpoint_id": str(checkpoint.id),
        "task_id": str(checkpoint.task_id),
        "timestamp": checkpoint.created_at or datetime.now(timezone.utc),
        "state_hash": state.get("state_hash") or "",
        "artifacts": checkpoint.artifacts or [],
        "evidence": state.get("evidence") or [],
        "metadata": {
            "worker_id": checkpoint.created_by_worker_id,
            "progress": round(float(checkpoint.progress_percent or 0) / 100, 4),
            "resource_usage": state.get("resource_usage") or {},
            "cognitive_state": state.get("cognitive_state") or {},
        },
    }


def _active_lease(db: Session, tenant_id: UUID, task_id: UUID) -> ArceusWorkerLease | None:
    return (
        db.query(ArceusWorkerLease)
        .filter(ArceusWorkerLease.tenant_id == tenant_id, ArceusWorkerLease.task_id == task_id, ArceusWorkerLease.status == "active")
        .order_by(ArceusWorkerLease.expires_at.desc())
        .first()
    )


def _task_response(db: Session, context: RequestContext, task: ArceusTask) -> dict[str, Any]:
    input_contract = task.input_contract or {}
    output_contract = task.output_contract or {}
    active_lease = _active_lease(db, context.tenant_id, task.id)
    runtime_priority = input_contract.get("runtime_priority")
    return {
        "task_id": str(task.id),
        "task_key": task.task_key,
        "title": task.title,
        "task_type": task.task_type,
        "dependencies": input_contract.get("dependencies") or [],
        "required_capabilities": input_contract.get("required_capabilities") or [],
        "priority": int(runtime_priority if runtime_priority is not None else 50),
        "status": _runtime_status_from_task(task.status, active_lease),
        "assigned_worker": active_lease.worker_id if active_lease else None,
        "lease_id": str(active_lease.id) if active_lease else None,
        "retry_policy": output_contract.get("retry_policy") or RUNTIME_RETRY_POLICY,
        "execution_policy": output_contract.get("execution_policy") or RUNTIME_EXECUTION_POLICY,
    }


def _scheduler_summary(mission: ArceusMission, tasks: list[ArceusTask], graph: dict[str, Any]) -> dict[str, Any]:
    strategy = ((mission.metadata_json or {}).get("runtime_kernel") or {}).get("scheduling_strategy", "priority")
    return {
        "strategy": strategy,
        "ready_task_count": len([task for task in tasks if task.status == "ready"]),
        "dependency_resolved": True,
        "policy_aware": True,
        "cost_aware": True,
        "parallel_groups": graph.get("parallel_groups") or [],
    }


def _runtime_mission_payload(db: Session, context: RequestContext, mission: ArceusMission) -> dict[str, Any]:
    tasks = (
        db.query(ArceusTask)
        .filter(ArceusTask.tenant_id == context.tenant_id, ArceusTask.mission_id == mission.id)
        .order_by(ArceusTask.created_at.asc(), ArceusTask.id.asc())
        .all()
    )
    checkpoints = (
        db.query(ArceusRuntimeCheckpoint)
        .filter(ArceusRuntimeCheckpoint.tenant_id == context.tenant_id, ArceusRuntimeCheckpoint.mission_id == mission.id)
        .order_by(ArceusRuntimeCheckpoint.created_at.asc(), ArceusRuntimeCheckpoint.id.asc())
        .all()
    )
    events = (
        db.query(ArceusEvent)
        .filter(ArceusEvent.tenant_id == context.tenant_id, ArceusEvent.aggregate_type == "runtime_mission", ArceusEvent.aggregate_id == mission.id)
        .order_by(ArceusEvent.aggregate_version.asc())
        .all()
    )
    metadata = mission.metadata_json or {}
    runtime_metadata = metadata.get("runtime_kernel") or {}
    graph = runtime_metadata.get("graph") or {"nodes": [], "edges": [], "parallel_groups": [], "graph_hash": ""}
    workflow = runtime_metadata.get("workflow") or {
        "strategy": runtime_metadata.get("scheduling_strategy", "priority"),
        "resource_budget": runtime_metadata.get("resource_budget") or {},
    }
    return {
        "mission_id": str(mission.id),
        "title": mission.title,
        "objective": mission.objective,
        "priority": int(runtime_metadata.get("priority") or mission.priority * 20),
        "workflow": workflow,
        "graph": graph,
        "scheduler": _scheduler_summary(mission, tasks, graph),
        "checkpoints": [_checkpoint_response(item) for item in checkpoints],
        "runtime_state": _runtime_status_from_mission(mission.status),
        "tasks": [_task_response(db, context, task) for task in tasks],
        "events": [_event_response(item) for item in events],
        "created_at": mission.created_at,
    }


def _refresh_ready_tasks(db: Session, context: RequestContext, mission_id: UUID) -> None:
    tasks = (
        db.query(ArceusTask)
        .filter(ArceusTask.tenant_id == context.tenant_id, ArceusTask.mission_id == mission_id)
        .order_by(ArceusTask.created_at.asc(), ArceusTask.id.asc())
        .all()
    )
    completed_keys = {task.task_key for task in tasks if task.status == "completed"}
    by_key = {task.task_key: task for task in tasks}
    for task in tasks:
        dependencies = set((task.input_contract or {}).get("dependencies") or [])
        if task.status == "pending" and dependencies.issubset(completed_keys):
            task.status = "ready"
            task.version_number = int(task.version_number or 1) + 1
            _append_runtime_event(
                db,
                context,
                aggregate_type="runtime_mission",
                aggregate_id=mission_id,
                event_type="runtime.task.ready",
                payload={"task_id": str(task.id), "task_key": task.task_key},
            )
        elif task.status == "ready" and any(by_key.get(dep) and by_key[dep].status != "completed" for dep in dependencies):
            task.status = "pending"
            task.version_number = int(task.version_number or 1) + 1


@router.post("/missions")
def create_mission_runtime(
    payload: RuntimeMissionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.manage")),
    db: Session = Depends(get_db),
):
    payload_dict = payload.model_dump(mode="json")
    graph = compile_mission_graph(payload_dict)
    project = _runtime_project(db, context)
    ready_keys = set(graph["parallel_groups"][0]) if graph["parallel_groups"] else set()
    mission = ArceusMission(
        tenant_id=context.tenant_id,
        project_id=project.id,
        created_by=context.user_id,
        title=payload.title,
        objective=payload.objective,
        status="ready" if ready_keys else "blocked",
        risk_level="medium",
        priority=_priority_0_to_5(payload.priority),
        maximum_budget_amount=(payload.resource_budget or {}).get("maximum_budget_amount"),
        metadata_json={
            "runtime_kernel": {
                "priority": payload.priority,
                "scheduling_strategy": payload.scheduling_strategy,
                "resource_budget": payload.resource_budget,
                "workflow": {"strategy": payload.scheduling_strategy, "resource_budget": payload.resource_budget},
                "graph": graph,
            }
        },
    )
    db.add(mission)
    db.flush()

    tasks_by_key: dict[str, ArceusTask] = {}
    for task_def in payload.tasks:
        task = ArceusTask(
            tenant_id=context.tenant_id,
            mission_id=mission.id,
            task_key=task_def.task_key,
            title=task_def.title,
            task_type=task_def.task_type,
            status="ready" if task_def.task_key in ready_keys else "pending",
            input_contract={
                "dependencies": task_def.dependencies,
                "required_capabilities": task_def.required_capabilities,
                "runtime_priority": task_def.priority,
                "estimated_cost": task_def.estimated_cost,
            },
            output_contract={"retry_policy": RUNTIME_RETRY_POLICY, "execution_policy": RUNTIME_EXECUTION_POLICY},
            acceptance_criteria=[],
        )
        db.add(task)
        tasks_by_key[task_def.task_key] = task
    db.flush()

    for task_def in payload.tasks:
        task = tasks_by_key[task_def.task_key]
        for dependency_key in task_def.dependencies:
            db.add(
                ArceusTaskDependency(
                    tenant_id=context.tenant_id,
                    task_id=task.id,
                    depends_on_task_id=tasks_by_key[dependency_key].id,
                    dependency_type="blocks",
                )
            )
    _append_runtime_event(
        db,
        context,
        aggregate_type="runtime_mission",
        aggregate_id=mission.id,
        event_type="runtime.mission.created",
        payload={"title": mission.title, "project_id": str(project.id)},
    )
    _append_runtime_event(
        db,
        context,
        aggregate_type="runtime_mission",
        aggregate_id=mission.id,
        event_type="runtime.mission.graph_compiled",
        payload={"graph_hash": graph["graph_hash"], "task_count": len(payload.tasks)},
    )
    for task_key in sorted(ready_keys):
        _append_runtime_event(
            db,
            context,
            aggregate_type="runtime_mission",
            aggregate_id=mission.id,
            event_type="runtime.task.ready",
            payload={"task_id": str(tasks_by_key[task_key].id), "task_key": task_key},
        )

    _uow(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="RUNTIME_MISSION_CREATED",
        resource_type="runtime_mission",
        resource_id=mission.id,
        result=mission.status,
        metadata={"graph_hash": graph["graph_hash"], "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    return api_response(RuntimeMissionResponse(**_runtime_mission_payload(db, context, mission)).model_dump(mode="json"), request)


@router.get("/missions/{mission_id}")
def get_runtime_mission(
    mission_id: str,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.view")),
    db: Session = Depends(get_db),
):
    mission = _mission_or_404(db, context, _parse_uuid(mission_id, "Runtime mission"))
    return api_response(RuntimeMissionResponse(**_runtime_mission_payload(db, context, mission)).model_dump(mode="json"), request)


@router.post("/tasks/{task_id}/lease")
def lease_runtime_task(
    task_id: str,
    payload: LeaseRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.lease")),
    db: Session = Depends(get_db),
):
    task = _task_or_404(db, context, _parse_uuid(task_id, "Runtime task"))
    mission = _mission_or_404(db, context, task.mission_id)
    if mission.status == "ready":
        mission.status = "running"
        mission.version_number = int(mission.version_number or 1) + 1
    if mission.status != "running":
        raise HTTPException(status_code=409, detail={"code": "MISSION_NOT_RUNNING", "status": mission.status})
    if task.status != "ready":
        raise HTTPException(status_code=409, detail={"code": "TASK_NOT_READY", "status": task.status})

    task_payload = {
        "task_id": str(task.id),
        "task_key": task.task_key,
        "title": task.title,
        "required_capabilities": (task.input_contract or {}).get("required_capabilities") or [],
    }
    lease_decision = grant_lease(task_payload, payload.model_dump(mode="json"))
    if lease_decision["status"] != "granted":
        return api_response(LeaseResponse(**lease_decision).model_dump(mode="json"), request)

    lease = ArceusWorkerLease(
        tenant_id=context.tenant_id,
        task_id=task.id,
        worker_id=payload.worker_id,
        lease_token=f"lease_{uuid.uuid4().hex}",
        status="active",
        heartbeat_at=datetime.now(timezone.utc),
        expires_at=lease_decision["expires_at"],
    )
    task.status = "running"
    task.started_at = task.started_at or datetime.now(timezone.utc)
    task.version_number = int(task.version_number or 1) + 1
    db.add(lease)
    db.flush()
    _append_runtime_event(
        db,
        context,
        aggregate_type="runtime_mission",
        aggregate_id=mission.id,
        event_type="runtime.lease.granted",
        payload={"task_id": str(task.id), "task_key": task.task_key, "lease_id": str(lease.id), "worker_id": lease.worker_id},
    )
    db.commit()
    response = {**lease_decision, "lease_id": str(lease.id), "task_id": str(task.id)}
    return api_response(LeaseResponse(**response).model_dump(mode="json"), request)


@router.post("/tasks/{task_id}/checkpoint")
def checkpoint_runtime_task(
    task_id: str,
    payload: CheckpointRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.checkpoint")),
    db: Session = Depends(get_db),
):
    task = _task_or_404(db, context, _parse_uuid(task_id, "Runtime task"))
    mission = _mission_or_404(db, context, task.mission_id)
    active_lease = (
        db.query(ArceusWorkerLease)
        .filter(
            ArceusWorkerLease.tenant_id == context.tenant_id,
            ArceusWorkerLease.task_id == task.id,
            ArceusWorkerLease.worker_id == payload.worker_id,
            ArceusWorkerLease.status == "active",
        )
        .order_by(ArceusWorkerLease.expires_at.desc())
        .first()
    )
    checkpoint = create_checkpoint(str(task.id), payload.model_dump(mode="json"))
    checkpoint_key = f"progress-{int(payload.progress * 100):03d}-{uuid.uuid4().hex[:8]}"
    row = ArceusRuntimeCheckpoint(
        tenant_id=context.tenant_id,
        mission_id=mission.id,
        task_id=task.id,
        workflow_id=mission.active_workflow_id,
        worker_lease_id=active_lease.id if active_lease else None,
        checkpoint_key=checkpoint_key,
        workflow_version=int(mission.version_number or 1),
        execution_state={
            "state_hash": checkpoint["state_hash"],
            "evidence": payload.evidence,
            "resource_usage": payload.resource_usage,
            "cognitive_state": sanitize_cognitive_state(payload.cognitive_state),
        },
        artifacts=checkpoint["artifacts"],
        model_calls=[],
        tool_calls=[],
        outputs=payload.outputs,
        progress_percent=int(payload.progress * 100),
        created_by_worker_id=payload.worker_id,
    )
    db.add(row)
    task.output_contract = {**(task.output_contract or {}), "latest_checkpoint_id": str(row.id), "latest_progress": payload.progress}
    task.version_number = int(task.version_number or 1) + 1
    db.flush()
    _append_runtime_event(
        db,
        context,
        aggregate_type="runtime_mission",
        aggregate_id=mission.id,
        event_type="runtime.checkpoint.created",
        payload={"task_id": str(task.id), "checkpoint_id": str(row.id), "state_hash": checkpoint["state_hash"], "progress": payload.progress},
    )
    _uow(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="CHECKPOINT_CREATED",
        resource_type="runtime_task",
        resource_id=task.id,
        result="checkpointed",
        metadata={"checkpoint_id": str(row.id), "state_hash": checkpoint["state_hash"], "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    response = {**checkpoint, "checkpoint_id": str(row.id), "task_id": str(task.id)}
    return api_response(CheckpointResponse(**response).model_dump(mode="json"), request)


@router.post("/tasks/{task_id}/cancel")
def cancel_runtime_task(
    task_id: str,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.manage")),
    db: Session = Depends(get_db),
):
    task = _task_or_404(db, context, _parse_uuid(task_id, "Runtime task"))
    previous = task.status
    task.status = "cancelled"
    task.completed_at = datetime.now(timezone.utc)
    task.failure_reason = "Cancelled by runtime kernel request."
    task.version_number = int(task.version_number or 1) + 1
    for lease in db.query(ArceusWorkerLease).filter(ArceusWorkerLease.tenant_id == context.tenant_id, ArceusWorkerLease.task_id == task.id, ArceusWorkerLease.status == "active").all():
        lease.status = "released"
        lease.version_number = int(lease.version_number or 1) + 1
    event = _append_runtime_event(
        db,
        context,
        aggregate_type="runtime_mission",
        aggregate_id=task.mission_id,
        event_type="runtime.task.cancelled",
        payload={"task_id": str(task.id), "task_key": task.task_key, "previous_status": previous, "resources_released": True},
    )
    db.commit()
    response = {
        "accepted": True,
        "status": "cancelled",
        "reason": "Task cancellation accepted; leases were released and partial results remain auditable.",
        "events": [_event_response(event)],
    }
    return api_response(RuntimeActionResponse(**response).model_dump(mode="json"), request)


@router.post("/missions/{mission_id}/pause")
def pause_runtime_mission(
    mission_id: str,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.manage")),
    db: Session = Depends(get_db),
):
    mission = _mission_or_404(db, context, _parse_uuid(mission_id, "Runtime mission"))
    mission.status = "paused"
    mission.paused_at = datetime.now(timezone.utc)
    mission.version_number = int(mission.version_number or 1) + 1
    for lease in (
        db.query(ArceusWorkerLease)
        .join(ArceusTask, ArceusTask.id == ArceusWorkerLease.task_id)
        .filter(ArceusWorkerLease.tenant_id == context.tenant_id, ArceusTask.mission_id == mission.id, ArceusWorkerLease.status == "active")
        .all()
    ):
        lease.status = "released"
        lease.version_number = int(lease.version_number or 1) + 1
    event = _append_runtime_event(
        db,
        context,
        aggregate_type="runtime_mission",
        aggregate_id=mission.id,
        event_type="runtime.mission.paused",
        payload={"leases_released": True, "checkpoints_preserved": True},
    )
    db.commit()
    response = {"accepted": True, "status": "paused", "reason": "Mission paused with checkpoints and evidence preserved.", "events": [_event_response(event)]}
    return api_response(RuntimeActionResponse(**response).model_dump(mode="json"), request)


@router.post("/missions/{mission_id}/resume")
def resume_runtime_mission(
    mission_id: str,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.manage")),
    db: Session = Depends(get_db),
):
    mission = _mission_or_404(db, context, _parse_uuid(mission_id, "Runtime mission"))
    mission.status = "ready"
    mission.paused_at = None
    mission.version_number = int(mission.version_number or 1) + 1
    _refresh_ready_tasks(db, context, mission.id)
    event = _append_runtime_event(
        db,
        context,
        aggregate_type="runtime_mission",
        aggregate_id=mission.id,
        event_type="runtime.mission.resumed",
        payload={"resume_from_latest_valid_checkpoint": True},
    )
    db.commit()
    response = {"accepted": True, "status": "ready", "reason": "Mission resumed from the latest valid checkpoint.", "events": [_event_response(event)]}
    return api_response(RuntimeActionResponse(**response).model_dump(mode="json"), request)


@router.get("/events")
def list_runtime_events(
    request: Request,
    mission_id: str | None = Query(default=None, max_length=160),
    context: RequestContext = Depends(require_permission("runtime.kernel.view")),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusEvent).filter(ArceusEvent.tenant_id == context.tenant_id, ArceusEvent.aggregate_type == "runtime_mission")
    if mission_id:
        query = query.filter(ArceusEvent.aggregate_id == _parse_uuid(mission_id, "Runtime mission"))
    rows = query.order_by(ArceusEvent.occurred_at.asc(), ArceusEvent.aggregate_version.asc()).limit(500).all()
    return collection_response([_event_response(item) for item in rows], request)


@router.post("/missions/{mission_id}/replay")
def replay_runtime_mission(
    mission_id: str,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.view")),
    db: Session = Depends(get_db),
):
    mission = _mission_or_404(db, context, _parse_uuid(mission_id, "Runtime mission"))
    runtime_payload = _runtime_mission_payload(db, context, mission)
    return api_response(RuntimeReplayResponse(**replay_mission(runtime_payload)).model_dump(mode="json"), request)


@router.get("/metrics")
def get_runtime_kernel_metrics(
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.view")),
    db: Session = Depends(get_db),
):
    statuses = Counter(
        _runtime_status_from_task(status, None)
        for (status,) in db.query(ArceusTask.status)
        .join(ArceusMission, ArceusMission.id == ArceusTask.mission_id)
        .filter(ArceusTask.tenant_id == context.tenant_id, ArceusMission.tenant_id == context.tenant_id)
        .all()
    )
    checkpoints = db.query(ArceusRuntimeCheckpoint).filter(ArceusRuntimeCheckpoint.tenant_id == context.tenant_id).count()
    lease_expirations = db.query(ArceusWorkerLease).filter(ArceusWorkerLease.tenant_id == context.tenant_id, ArceusWorkerLease.status == "expired").count()
    summary = {"task_statuses": dict(statuses), "checkpoints": checkpoints, "lease_expirations": lease_expirations}
    return api_response(RuntimeMetricsResponse(**runtime_metrics(summary)).model_dump(mode="json"), request)
