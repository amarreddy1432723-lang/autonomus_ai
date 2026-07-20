from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    AgentHeartbeatRequest,
    AgentMessageResponse,
    AgentMetricsResponse,
    AgentStatusResponse,
    AssignTaskRequest,
    AssignTaskResponse,
    RegisterAgentRequest,
    SendAgentMessageRequest,
)
from .service import MultiAgentRuntimeService


router = APIRouter(tags=["multi-agent-runtime"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


@router.post("/api/v1/agents/register", status_code=status.HTTP_201_CREATED)
def register_agent(
    request_body: RegisterAgentRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("agent.register")),
    db: Session = Depends(get_db),
):
    service = MultiAgentRuntimeService(_uow(db))
    participant = service.register_agent(
        tenant_id=context.tenant_id,
        actor_id=str(context.user_id),
        name=request_body.name,
        role=request_body.role,
        participant_type=request_body.participant_type,
        organization_id=request_body.organization_id,
        organization_member_id=request_body.organization_member_id,
        specialist_profile_id=request_body.specialist_profile_id,
        capabilities=request_body.capabilities,
        model_profile=request_body.model_profile,
        version=request_body.version,
        authorities=request_body.authorities,
        active_mission_ids=request_body.active_mission_ids,
    )
    service.uow.commit()
    return api_response(service.response(participant).model_dump(mode="json"), request)


@router.get("/api/v1/agents")
def list_agents(
    request: Request,
    context: RequestContext = Depends(require_permission("agent.view")),
    status: str | None = Query(default=None),
    capability: str | None = Query(default=None),
    organization_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=250),
    db: Session = Depends(get_db),
):
    service = MultiAgentRuntimeService(_uow(db))
    rows = service.list_agents(tenant_id=context.tenant_id, status=status, capability=capability, organization_id=organization_id, limit=limit)
    return collection_response([service.response(row).model_dump(mode="json") for row in rows], request)


@router.get("/api/v1/agents/{agent_id}")
def get_agent(
    agent_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("agent.view")),
    db: Session = Depends(get_db),
):
    service = MultiAgentRuntimeService(_uow(db))
    return api_response(service.response(service.get_agent(tenant_id=context.tenant_id, agent_id=agent_id)).model_dump(mode="json"), request)


@router.post("/api/v1/agents/{agent_id}/pause")
def pause_agent(
    agent_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("agent.manage")),
    db: Session = Depends(get_db),
):
    service = MultiAgentRuntimeService(_uow(db))
    participant = service.set_status(tenant_id=context.tenant_id, agent_id=agent_id, status="paused", actor_id=str(context.user_id))
    service.uow.commit()
    return api_response(AgentStatusResponse(agent_id=participant.id, status=participant.status, version_number=participant.version_number).model_dump(mode="json"), request)


@router.post("/api/v1/agents/{agent_id}/resume")
def resume_agent(
    agent_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("agent.manage")),
    db: Session = Depends(get_db),
):
    service = MultiAgentRuntimeService(_uow(db))
    participant = service.set_status(tenant_id=context.tenant_id, agent_id=agent_id, status="available", actor_id=str(context.user_id))
    service.uow.commit()
    return api_response(AgentStatusResponse(agent_id=participant.id, status=participant.status, version_number=participant.version_number).model_dump(mode="json"), request)


@router.post("/api/v1/agents/{agent_id}/disable")
def disable_agent(
    agent_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("agent.manage")),
    db: Session = Depends(get_db),
):
    service = MultiAgentRuntimeService(_uow(db))
    participant = service.set_status(tenant_id=context.tenant_id, agent_id=agent_id, status="disabled", actor_id=str(context.user_id))
    service.uow.commit()
    return api_response(AgentStatusResponse(agent_id=participant.id, status="disabled", version_number=participant.version_number).model_dump(mode="json"), request)


@router.post("/api/v1/agents/{agent_id}/heartbeat")
def heartbeat_agent(
    agent_id: UUID,
    request_body: AgentHeartbeatRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("agent.heartbeat")),
    db: Session = Depends(get_db),
):
    service = MultiAgentRuntimeService(_uow(db))
    participant = service.heartbeat(tenant_id=context.tenant_id, agent_id=agent_id, **request_body.model_dump())
    service.uow.commit()
    return api_response(AgentStatusResponse(agent_id=participant.id, status=participant.status, version_number=participant.version_number).model_dump(mode="json"), request)


@router.get("/api/v1/agents/{agent_id}/metrics")
def get_agent_metrics(
    agent_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("agent.metrics.view")),
    db: Session = Depends(get_db),
):
    service = MultiAgentRuntimeService(_uow(db))
    metrics, observation_count, reputation_score = service.metrics(tenant_id=context.tenant_id, agent_id=agent_id)
    return api_response(AgentMetricsResponse(agent_id=agent_id, metrics=metrics, observation_count=observation_count, reputation_score=reputation_score).model_dump(mode="json"), request)


@router.post("/api/v1/agents/assign-task")
def assign_agent_to_task(
    request_body: AssignTaskRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("agent.assign")),
    db: Session = Depends(get_db),
):
    service = MultiAgentRuntimeService(_uow(db))
    selected, candidates, assigned = service.assign_task(
        tenant_id=context.tenant_id,
        actor_id=str(context.user_id),
        **request_body.model_dump(),
    )
    service.uow.commit()
    response = AssignTaskResponse(task_id=request_body.task_id, selected_agent=selected, candidates=candidates[:25], assigned=assigned)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/api/v1/agents/messages", status_code=status.HTTP_201_CREATED)
def send_agent_message(
    request_body: SendAgentMessageRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("agent.message")),
    db: Session = Depends(get_db),
):
    service = MultiAgentRuntimeService(_uow(db))
    message = service.send_agent_message(
        tenant_id=context.tenant_id,
        correlation_id=context.correlation_id,
        **request_body.model_dump(),
    )
    service.uow.commit()
    response = AgentMessageResponse(
        id=message.id,
        mission_id=message.mission_id,
        sender_agent_id=message.sender_participant_id,
        receiver_agent_ids=request_body.receiver_agent_ids,
        message_type=message.message_type,
        subject=message.subject,
        priority=message.priority,
        created_at=message.created_at,
    )
    return api_response(response.model_dump(mode="json"), request)
