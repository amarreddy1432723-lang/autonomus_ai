from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    RunNextTaskRequest,
    RunNextTaskResponse,
    RuntimePlanValidationRequest,
    TaskContextBuildRequest,
)
from .service import MissionRuntimeService, validate_task_dag


router = APIRouter(prefix="/api/v1/mission-runtime", tags=["mission-runtime"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


@router.post("/plans/validate")
def validate_runtime_plan(
    request_body: RuntimePlanValidationRequest,
    request: Request,
    _context: RequestContext = Depends(require_permission("runtime.report")),
):
    response = validate_task_dag(request_body.tasks)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/tasks/{task_id}/context")
def build_task_context(
    task_id: UUID,
    request_body: TaskContextBuildRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("context.build")),
    db: Session = Depends(get_db),
):
    service = MissionRuntimeService(_uow(db))
    response = service.build_task_context(
        tenant_id=context.tenant_id,
        task_id=task_id,
        model=request_body.model,
        root_path=request_body.root_path,
        repository_id=request_body.repository_id,
        force_rebuild=request_body.force_rebuild,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/{mission_id}/snapshot")
def get_mission_runtime_snapshot(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.report")),
    db: Session = Depends(get_db),
):
    response = MissionRuntimeService(_uow(db)).snapshot(tenant_id=context.tenant_id, mission_id=mission_id)
    return api_response(response.model_dump(mode="json"), request)


@router.get("/{mission_id}/report")
def get_mission_runtime_report(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.report")),
    db: Session = Depends(get_db),
):
    response = MissionRuntimeService(_uow(db)).report(tenant_id=context.tenant_id, mission_id=mission_id)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/{mission_id}/run-next")
def run_next_mission_task(
    mission_id: UUID,
    request_body: RunNextTaskRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("runtime.execute")),
    db: Session = Depends(get_db),
):
    result = MissionRuntimeService(_uow(db)).run_next(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        worker_id=request_body.worker_id,
        ttl_seconds=request_body.ttl_seconds,
    )
    response = RunNextTaskResponse(**result)
    return api_response(response.model_dump(mode="json"), request)
