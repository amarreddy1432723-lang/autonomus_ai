from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_idempotency_key, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    AcquireLeaseRequest,
    CompleteTaskRequest,
    FailTaskRequest,
    HeartbeatRequest,
    LeaseResponse,
    RuntimeCheckpointResponse,
    RuntimeTaskResultResponse,
    ScheduleMissionRequest,
    ScheduleMissionResponse,
    ScheduledTaskResponse,
)
from .service import RuntimeSchedulerService, RuntimeWorkerService


router = APIRouter(tags=["execution-runtime"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _lease_response(lease) -> LeaseResponse:
    return LeaseResponse(
        id=lease.id,
        task_id=lease.task_id,
        worker_id=lease.worker_id,
        lease_token=lease.lease_token,
        status=lease.status,
        heartbeat_at=lease.heartbeat_at,
        expires_at=lease.expires_at,
        version_number=lease.version_number,
    )


def _checkpoint_response(checkpoint) -> RuntimeCheckpointResponse:
    return RuntimeCheckpointResponse(
        id=checkpoint.id,
        mission_id=checkpoint.mission_id,
        task_id=checkpoint.task_id,
        workflow_id=checkpoint.workflow_id,
        worker_lease_id=checkpoint.worker_lease_id,
        checkpoint_key=checkpoint.checkpoint_key,
        workflow_version=checkpoint.workflow_version,
        execution_state=checkpoint.execution_state or {},
        outputs=checkpoint.outputs or {},
        progress_percent=checkpoint.progress_percent,
        created_by_worker_id=checkpoint.created_by_worker_id,
        created_at=checkpoint.created_at,
        version_number=checkpoint.version_number,
    )


@router.post("/api/v1/missions/{mission_id}/runtime/schedule")
def schedule_mission(
    mission_id: UUID,
    request_body: ScheduleMissionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.schedule")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    result = RuntimeSchedulerService(uow).schedule(tenant_id=context.tenant_id, mission_id=mission_id, limit=request_body.limit)
    uow.commit()
    response = ScheduleMissionResponse(
        mission_id=mission_id,
        mission_status=result["mission"].status,
        ready_count=len(result["ready_tasks"]),
        completed_count=result["completed_count"],
        total_count=result["total_count"],
        expired_leases=result["expired_leases"],
        ready_tasks=[
            ScheduledTaskResponse(
                id=task.id,
                task_key=task.task_key,
                title=task.title,
                status=task.status,
                owner_member_id=task.owner_member_id,
                priority_score=uow.tasks.priority_score(task),
            )
            for task in result["ready_tasks"]
        ],
    )
    return api_response(response.model_dump(mode="json"), request)


@router.post("/api/v1/tasks/{task_id}/leases", status_code=status.HTTP_201_CREATED)
def acquire_task_lease(
    task_id: UUID,
    request_body: AcquireLeaseRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.lease")),
    idempotency_key: str = Depends(require_idempotency_key),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    task, _mission, lease = RuntimeWorkerService(uow).acquire(
        tenant_id=context.tenant_id,
        task_id=task_id,
        worker_id=request_body.worker_id,
        ttl_seconds=request_body.ttl_seconds,
    )
    uow.commit()
    return api_response({"task_id": str(task.id), "lease": _lease_response(lease).model_dump(mode="json"), "idempotency_key": idempotency_key}, request)


@router.post("/api/v1/worker-leases/{lease_id}/heartbeat")
def heartbeat_worker_lease(
    lease_id: UUID,
    request_body: HeartbeatRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.lease")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    task, mission, lease, checkpoint = RuntimeWorkerService(uow).heartbeat(
        tenant_id=context.tenant_id,
        lease_id=lease_id,
        worker_id=request_body.worker_id,
        ttl_seconds=request_body.ttl_seconds,
        progress_percent=request_body.progress_percent,
        checkpoint=request_body.checkpoint,
        current_operation=request_body.current_operation,
    )
    uow.commit()
    response = RuntimeTaskResultResponse(
        task_id=task.id,
        mission_id=mission.id,
        status=task.status,
        lease_status=lease.status,
        checkpoint_id=checkpoint.id,
        version_number=task.version_number,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.post("/api/v1/worker-leases/{lease_id}/complete")
def complete_worker_lease(
    lease_id: UUID,
    request_body: CompleteTaskRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.lease")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    task, mission, lease, checkpoint = RuntimeWorkerService(uow).complete(
        tenant_id=context.tenant_id,
        lease_id=lease_id,
        worker_id=request_body.worker_id,
        outputs=request_body.outputs,
        progress_percent=request_body.progress_percent,
    )
    uow.commit()
    response = RuntimeTaskResultResponse(
        task_id=task.id,
        mission_id=mission.id,
        status=task.status,
        lease_status=lease.status,
        checkpoint_id=checkpoint.id,
        version_number=task.version_number,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.post("/api/v1/worker-leases/{lease_id}/fail")
def fail_worker_lease(
    lease_id: UUID,
    request_body: FailTaskRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.lease")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    task, mission, lease, checkpoint = RuntimeWorkerService(uow).fail(
        tenant_id=context.tenant_id,
        lease_id=lease_id,
        worker_id=request_body.worker_id,
        error=request_body.error,
        retryable=request_body.retryable,
    )
    uow.commit()
    response = RuntimeTaskResultResponse(
        task_id=task.id,
        mission_id=mission.id,
        status=task.status,
        lease_status=lease.status,
        checkpoint_id=checkpoint.id,
        version_number=task.version_number,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/api/v1/tasks/{task_id}/checkpoints")
def list_task_checkpoints(
    task_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.checkpoint")),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.tasks.get(tenant_id=context.tenant_id, task_id=task_id)
    checkpoints = uow.runtime_execution.checkpoints_for_task(tenant_id=context.tenant_id, task_id=task_id, limit=limit)
    return collection_response([_checkpoint_response(item).model_dump(mode="json") for item in checkpoints], request)
