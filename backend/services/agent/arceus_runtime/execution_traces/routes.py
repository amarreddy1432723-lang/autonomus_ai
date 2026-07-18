from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    ContextPackageResponse,
    ModelExecutionResponse,
    PolicyEvaluationResponse,
    ToolDefinitionResponse,
    ToolExecutionResponse,
)


router = APIRouter(tags=["execution-traces"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _context_package_response(item) -> ContextPackageResponse:
    return ContextPackageResponse(
        id=item.id,
        mission_id=item.mission_id,
        task_id=item.task_id,
        recipient_member_id=item.recipient_member_id,
        purpose=item.purpose,
        selected_items=item.selected_items or [],
        excluded_items=item.excluded_items or [],
        token_budget=item.token_budget,
        content_hash=item.content_hash,
        created_at=item.created_at,
        updated_at=item.updated_at,
        version_number=item.version_number,
    )


def _model_execution_response(item) -> ModelExecutionResponse:
    return ModelExecutionResponse(
        id=item.id,
        mission_id=item.mission_id,
        task_id=item.task_id,
        member_id=item.member_id,
        provider=item.provider,
        model=item.model,
        purpose=item.purpose,
        prompt_hash=item.prompt_hash,
        input_tokens=item.input_tokens,
        output_tokens=item.output_tokens,
        cost_usd=item.cost_usd,
        latency_ms=item.latency_ms,
        status=item.status,
        error=item.error or {},
        created_at=item.created_at,
        updated_at=item.updated_at,
        version_number=item.version_number,
    )


def _tool_definition_response(item) -> ToolDefinitionResponse | None:
    if item is None:
        return None
    return ToolDefinitionResponse(
        id=item.id,
        tool_key=item.tool_key,
        display_name=item.display_name,
        tool_type=item.tool_type,
        permission_requirements=item.permission_requirements or {},
        active=item.active,
        created_at=item.created_at,
        updated_at=item.updated_at,
        version_number=item.version_number,
    )


def _tool_execution_response(item, definition=None) -> ToolExecutionResponse:
    return ToolExecutionResponse(
        id=item.id,
        mission_id=item.mission_id,
        task_id=item.task_id,
        member_id=item.member_id,
        tool_definition_id=item.tool_definition_id,
        tool_definition=_tool_definition_response(definition),
        action=item.action,
        target=item.target,
        status=item.status,
        input_payload=item.input_payload or {},
        output_payload=item.output_payload or {},
        error=item.error or {},
        started_at=item.started_at,
        finished_at=item.finished_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
        version_number=item.version_number,
    )


def _policy_evaluation_response(item) -> PolicyEvaluationResponse:
    return PolicyEvaluationResponse(
        id=item.id,
        mission_id=item.mission_id,
        task_id=item.task_id,
        policy_key=item.policy_key,
        subject=item.subject or {},
        action=item.action,
        resource=item.resource or {},
        decision=item.decision,
        reason=item.reason,
        created_at=item.created_at,
        updated_at=item.updated_at,
        version_number=item.version_number,
    )


@router.get("/api/v1/missions/{mission_id}/context-packages")
def list_mission_context_packages(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("context.view")),
    task_id: UUID | None = Query(default=None),
    recipient_member_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    rows = uow.execution_traces.context_packages(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        task_id=task_id,
        recipient_member_id=recipient_member_id,
        limit=limit,
    )
    return collection_response([_context_package_response(item).model_dump(mode="json") for item in rows], request)


@router.get("/api/v1/context-packages/{context_package_id}")
def get_context_package(
    context_package_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("context.view")),
    db: Session = Depends(get_db),
):
    item = _uow(db).execution_traces.context_package(tenant_id=context.tenant_id, context_package_id=context_package_id)
    return api_response(_context_package_response(item).model_dump(mode="json"), request)


@router.get("/api/v1/model-executions")
def list_model_executions(
    request: Request,
    context: RequestContext = Depends(require_permission("model_execution.view")),
    mission_id: UUID | None = Query(default=None),
    task_id: UUID | None = Query(default=None),
    member_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None, max_length=60),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    rows = _uow(db).execution_traces.model_executions(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        task_id=task_id,
        member_id=member_id,
        status=status,
        limit=limit,
    )
    return collection_response([_model_execution_response(item).model_dump(mode="json") for item in rows], request)


@router.get("/api/v1/model-executions/{model_execution_id}")
def get_model_execution(
    model_execution_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("model_execution.view")),
    db: Session = Depends(get_db),
):
    item = _uow(db).execution_traces.model_execution(tenant_id=context.tenant_id, model_execution_id=model_execution_id)
    return api_response(_model_execution_response(item).model_dump(mode="json"), request)


@router.get("/api/v1/tool-definitions")
def list_tool_definitions(
    request: Request,
    context: RequestContext = Depends(require_permission("tool_execution.view")),
    active: bool | None = Query(default=True),
    limit: int = Query(default=100, ge=1, le=250),
    db: Session = Depends(get_db),
):
    rows = _uow(db).execution_traces.tool_definitions(active=active, limit=limit)
    return collection_response([_tool_definition_response(item).model_dump(mode="json") for item in rows if item is not None], request)


@router.get("/api/v1/tool-executions")
def list_tool_executions(
    request: Request,
    context: RequestContext = Depends(require_permission("tool_execution.view")),
    mission_id: UUID | None = Query(default=None),
    task_id: UUID | None = Query(default=None),
    member_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None, max_length=60),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    rows = []
    for item in uow.execution_traces.tool_executions(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        task_id=task_id,
        member_id=member_id,
        status=status,
        limit=limit,
    ):
        definition = uow.execution_traces.tool_definition(tool_definition_id=item.tool_definition_id)
        rows.append(_tool_execution_response(item, definition).model_dump(mode="json"))
    return collection_response(rows, request)


@router.get("/api/v1/tool-executions/{tool_execution_id}")
def get_tool_execution(
    tool_execution_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("tool_execution.view")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    item = uow.execution_traces.tool_execution(tenant_id=context.tenant_id, tool_execution_id=tool_execution_id)
    definition = uow.execution_traces.tool_definition(tool_definition_id=item.tool_definition_id)
    return api_response(_tool_execution_response(item, definition).model_dump(mode="json"), request)


@router.get("/api/v1/policy-evaluations")
def list_policy_evaluations(
    request: Request,
    context: RequestContext = Depends(require_permission("policy_evaluation.view")),
    mission_id: UUID | None = Query(default=None),
    task_id: UUID | None = Query(default=None),
    decision: str | None = Query(default=None, max_length=60),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    rows = _uow(db).execution_traces.policy_evaluations(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        task_id=task_id,
        decision=decision,
        limit=limit,
    )
    return collection_response([_policy_evaluation_response(item).model_dump(mode="json") for item in rows], request)


@router.get("/api/v1/policy-evaluations/{policy_evaluation_id}")
def get_policy_evaluation(
    policy_evaluation_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("policy_evaluation.view")),
    db: Session = Depends(get_db),
):
    item = _uow(db).execution_traces.policy_evaluation(tenant_id=context.tenant_id, policy_evaluation_id=policy_evaluation_id)
    return api_response(_policy_evaluation_response(item).model_dump(mode="json"), request)
