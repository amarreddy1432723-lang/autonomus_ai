from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

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
from .service import cancel_task, create_checkpoint, create_runtime_mission, grant_lease, pause_mission, replay_mission, resume_mission, runtime_events, runtime_metrics


router = APIRouter(prefix="/api/v1/runtime", tags=["runtime-kernel"])


@router.post("/missions")
def create_mission_runtime(
    payload: RuntimeMissionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.manage")),
    db: Session = Depends(get_db),
):
    result = create_runtime_mission(payload.model_dump(mode="json"))
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="RUNTIME_MISSION_CREATED",
        resource_type="runtime_mission",
        resource_id=result["mission_id"],
        result=result["runtime_state"],
        metadata={"graph_hash": result["graph"]["graph_hash"], "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    return api_response(RuntimeMissionResponse(**result).model_dump(mode="json"), request)


@router.get("/missions/{mission_id}")
def get_runtime_mission(
    mission_id: str,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.view")),
):
    sample = create_runtime_mission(
        {
            "title": "Runtime mission snapshot",
            "objective": f"Inspect runtime mission {mission_id}",
            "priority": 50,
            "scheduling_strategy": "priority",
            "tasks": [{"task_key": "inspect", "title": "Inspect mission", "dependencies": [], "required_capabilities": [], "priority": 50}],
            "resource_budget": {},
        }
    )
    sample["mission_id"] = mission_id
    return api_response(RuntimeMissionResponse(**sample).model_dump(mode="json"), request)


@router.post("/tasks/{task_id}/lease")
def lease_runtime_task(
    task_id: str,
    payload: LeaseRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.lease")),
):
    task = {
        "task_id": task_id,
        "task_key": task_id,
        "title": "Runtime task",
        "required_capabilities": payload.worker_capabilities,
    }
    response = grant_lease(task, payload.model_dump(mode="json"))
    return api_response(LeaseResponse(**response).model_dump(mode="json"), request)


@router.post("/tasks/{task_id}/checkpoint")
def checkpoint_runtime_task(
    task_id: str,
    payload: CheckpointRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.checkpoint")),
    db: Session = Depends(get_db),
):
    checkpoint = create_checkpoint(task_id, payload.model_dump(mode="json"))
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="CHECKPOINT_CREATED",
        resource_type="runtime_task",
        resource_id=task_id,
        result="checkpointed",
        metadata={"checkpoint_id": checkpoint["checkpoint_id"], "state_hash": checkpoint["state_hash"], "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    return api_response(CheckpointResponse(**checkpoint).model_dump(mode="json"), request)


@router.post("/tasks/{task_id}/cancel")
def cancel_runtime_task(
    task_id: str,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.manage")),
):
    return api_response(RuntimeActionResponse(**cancel_task(task_id)).model_dump(mode="json"), request)


@router.post("/missions/{mission_id}/pause")
def pause_runtime_mission(
    mission_id: str,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.manage")),
):
    return api_response(RuntimeActionResponse(**pause_mission(mission_id)).model_dump(mode="json"), request)


@router.post("/missions/{mission_id}/resume")
def resume_runtime_mission(
    mission_id: str,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.manage")),
):
    return api_response(RuntimeActionResponse(**resume_mission(mission_id)).model_dump(mode="json"), request)


@router.get("/events")
def list_runtime_events(
    request: Request,
    mission_id: str | None = Query(default=None, max_length=160),
    context: RequestContext = Depends(require_permission("runtime.kernel.view")),
):
    rows = [RuntimeEventResponse(**item).model_dump(mode="json") for item in runtime_events(mission_id)]
    return collection_response(rows, request)


@router.post("/missions/{mission_id}/replay")
def replay_runtime_mission(
    mission_id: str,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.view")),
):
    mission = create_runtime_mission(
        {
            "title": "Replay target",
            "objective": f"Replay {mission_id}",
            "priority": 50,
            "scheduling_strategy": "priority",
            "tasks": [{"task_key": "replay", "title": "Replay mission", "dependencies": [], "required_capabilities": [], "priority": 50}],
            "resource_budget": {},
        }
    )
    mission["mission_id"] = mission_id
    return api_response(RuntimeReplayResponse(**replay_mission(mission)).model_dump(mode="json"), request)


@router.get("/metrics")
def get_runtime_kernel_metrics(
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.kernel.view")),
):
    return api_response(RuntimeMetricsResponse(**runtime_metrics()).model_dump(mode="json"), request)
