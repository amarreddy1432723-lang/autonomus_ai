from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_idempotency_key, require_permission
from ..api.responses import api_response, collection_response
from ..application.idempotency import calculate_request_hash
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    TaskAttemptResponse,
    TaskDependencyResponse,
    TaskDetailResponse,
    TaskOperationRequest,
    TaskOperationResponse,
    TaskSummaryResponse,
    WorkerLeaseResponse,
)


router = APIRouter(tags=["tasks"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _task_summary(task) -> TaskSummaryResponse:
    return TaskSummaryResponse(
        id=task.id,
        mission_id=task.mission_id,
        workflow_node_id=task.workflow_node_id,
        task_key=task.task_key,
        title=task.title,
        task_type=task.task_type,
        status=task.status,
        owner_member_id=task.owner_member_id,
        acceptance_criteria=task.acceptance_criteria or [],
        started_at=task.started_at,
        completed_at=task.completed_at,
        failure_reason=task.failure_reason,
        created_at=task.created_at,
        updated_at=task.updated_at,
        version_number=task.version_number,
    )


def _task_attempt(attempt) -> TaskAttemptResponse:
    return TaskAttemptResponse(
        id=attempt.id,
        task_id=attempt.task_id,
        attempt_number=attempt.attempt_number,
        status=attempt.status,
        started_at=attempt.started_at,
        finished_at=attempt.finished_at,
        worker_id=attempt.worker_id,
        result=attempt.result or {},
        error=attempt.error or {},
        version_number=attempt.version_number,
    )


@router.get("/api/v1/missions/{mission_id}/tasks")
def list_mission_tasks(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("task.view")),
    task_status: str | None = Query(default=None, alias="status", max_length=60),
    owner_member_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=250),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    tasks = uow.tasks.list_for_mission(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        status=task_status,
        owner_member_id=owner_member_id,
        limit=limit,
    )
    return collection_response([_task_summary(item).model_dump(mode="json") for item in tasks], request)


@router.get("/api/v1/tasks/{task_id}")
def get_task(
    task_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("task.view")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    task = uow.tasks.get(tenant_id=context.tenant_id, task_id=task_id)
    dependencies = [
        TaskDependencyResponse(
            id=item.id,
            depends_on_task_id=item.depends_on_task_id,
            dependency_type=item.dependency_type,
        )
        for item in uow.tasks.dependencies(tenant_id=context.tenant_id, task_id=task_id)
    ]
    active_leases = [
        WorkerLeaseResponse(
            id=item.id,
            task_id=item.task_id,
            worker_id=item.worker_id,
            status=item.status,
            expires_at=item.expires_at,
            version_number=item.version_number,
        )
        for item in uow.tasks.active_leases(tenant_id=context.tenant_id, task_id=task_id)
    ]
    response = TaskDetailResponse(
        **_task_summary(task).model_dump(),
        input_contract=task.input_contract or {},
        output_contract=task.output_contract or {},
        dependencies=dependencies,
        attempts=[_task_attempt(item) for item in uow.tasks.attempts(tenant_id=context.tenant_id, task_id=task_id)],
        active_leases=active_leases,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/api/v1/tasks/{task_id}/attempts")
def list_task_attempts(
    task_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("task.view")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.tasks.get(tenant_id=context.tenant_id, task_id=task_id)
    attempts = uow.tasks.attempts(tenant_id=context.tenant_id, task_id=task_id)
    return collection_response([_task_attempt(item).model_dump(mode="json") for item in attempts], request)


def _change_task_status(
    *,
    task_id: UUID,
    request_body: TaskOperationRequest,
    request: Request,
    context: RequestContext,
    idempotency_key: str,
    db: Session,
    operation: str,
):
    uow = _uow(db)
    payload = request_body.model_dump(mode="json")
    request_hash = calculate_request_hash(f"task.{operation}", {"task_id": str(task_id), **payload})
    existing = uow.idempotency.get(tenant_id=context.tenant_id, scope=f"task.{operation}", idempotency_key=idempotency_key)
    if existing:
        return api_response(uow.idempotency.resolve_existing(existing, request_hash), request)

    task = uow.tasks.get(tenant_id=context.tenant_id, task_id=task_id)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=task.mission_id)
    if int(task.version_number) != int(request_body.expected_version):
        from ..application.errors import TaskStateConflict

        raise TaskStateConflict(
            "The task changed after this page was loaded.",
            details={"expected_version": request_body.expected_version, "current_version": task.version_number},
        )

    previous_status = task.status
    if operation == "retry":
        uow.tasks.retry(task, reason=request_body.reason)
        event_type = "arceus.task.retry.requested"
    else:
        uow.tasks.skip(task, reason=request_body.reason)
        event_type = "arceus.task.skipped"

    operation_id = uow.new_id()
    event = uow.events.append(
        tenant_id=context.tenant_id,
        aggregate_type="task",
        aggregate_id=task.id,
        aggregate_version=task.version_number,
        event_type=event_type,
        actor_type="human",
        actor_id=str(context.user_id),
        payload={
            "task_id": str(task.id),
            "mission_id": str(task.mission_id),
            "previous_status": previous_status,
            "status": task.status,
            "reason": request_body.reason,
            "operation_id": str(operation_id),
        },
        correlation_id=context.correlation_id,
        idempotency_key=idempotency_key,
    )
    uow.outbox.add_from_event(event, topic=event_type)
    response = TaskOperationResponse(
        task_id=task.id,
        mission_id=task.mission_id,
        previous_status=previous_status,
        status=task.status,
        version_number=task.version_number,
        operation_id=operation_id,
    ).model_dump(mode="json")
    uow.idempotency.complete(
        tenant_id=context.tenant_id,
        scope=f"task.{operation}",
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_payload=response,
    )
    uow.audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action=f"task.{operation}",
        resource_type="task",
        resource_id=task.id,
        result="success",
        metadata={"previous_status": previous_status, "status": task.status, "operation_id": str(operation_id)},
    )
    uow.commit()
    return api_response(response, request)


@router.post("/api/v1/tasks/{task_id}/retry")
def retry_task(
    task_id: UUID,
    request_body: TaskOperationRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("task.retry")),
    idempotency_key: str = Depends(require_idempotency_key),
    db: Session = Depends(get_db),
):
    return _change_task_status(
        task_id=task_id,
        request_body=request_body,
        request=request,
        context=context,
        idempotency_key=idempotency_key,
        db=db,
        operation="retry",
    )


@router.post("/api/v1/tasks/{task_id}/skip")
def skip_task(
    task_id: UUID,
    request_body: TaskOperationRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("task.skip")),
    idempotency_key: str = Depends(require_idempotency_key),
    db: Session = Depends(get_db),
):
    return _change_task_status(
        task_id=task_id,
        request_body=request_body,
        request=request,
        context=context,
        idempotency_key=idempotency_key,
        db=db,
        operation="skip",
    )
