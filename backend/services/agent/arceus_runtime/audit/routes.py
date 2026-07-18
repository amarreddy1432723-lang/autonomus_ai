from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import AuditEventResponse, MissionReplayResponse, ReplayEventResponse


router = APIRouter(tags=["audit"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _replay_event_response(event) -> ReplayEventResponse:
    return ReplayEventResponse(
        id=event.id,
        aggregate_type=event.aggregate_type,
        aggregate_id=event.aggregate_id,
        aggregate_version=int(event.aggregate_version),
        event_type=event.event_type,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        payload=event.payload or {},
        metadata_json=event.metadata_json or {},
        occurred_at=event.occurred_at,
    )


def _audit_event_response(event) -> AuditEventResponse:
    return AuditEventResponse(
        id=event.id,
        actor_type=event.actor_type,
        actor_id=event.actor_id,
        action=event.action,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        result=event.result,
        ip_address=event.ip_address,
        user_agent=event.user_agent,
        metadata_json=event.metadata_json or {},
        occurred_at=event.occurred_at,
    )


@router.get("/api/v1/missions/{mission_id}/replay")
def replay_mission_events(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("event.replay")),
    from_version: int = Query(default=1, ge=1),
    to_version: int | None = Query(default=None, ge=1),
    limit: int = Query(default=500, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    events = uow.events.replay_for_mission(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        from_version=from_version,
        to_version=to_version,
        limit=limit,
    )
    replay_events = [_replay_event_response(event) for event in events]
    cursor = max((event.aggregate_version for event in replay_events), default=from_version - 1)
    response = MissionReplayResponse(
        mission_id=mission_id,
        from_version=from_version,
        to_version=to_version,
        event_count=len(replay_events),
        replay_cursor=cursor,
        events=replay_events,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/api/v1/audit-events")
def list_audit_events(
    request: Request,
    context: RequestContext = Depends(require_permission("audit.view")),
    actor_type: str | None = Query(default=None, max_length=80),
    actor_id: str | None = Query(default=None, max_length=160),
    action: str | None = Query(default=None, max_length=160),
    resource_type: str | None = Query(default=None, max_length=120),
    resource_id: str | None = Query(default=None, max_length=160),
    result: str | None = Query(default=None, max_length=60),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    events = _uow(db).audit.list(
        tenant_id=context.tenant_id,
        actor_type=actor_type,
        actor_id=actor_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        limit=limit,
    )
    return collection_response([_audit_event_response(event).model_dump(mode="json") for event in events], request)


@router.get("/api/v1/audit-events/{audit_event_id}")
def get_audit_event(
    audit_event_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("audit.view")),
    db: Session = Depends(get_db),
):
    event = _uow(db).audit.get(tenant_id=context.tenant_id, audit_event_id=audit_event_id)
    return api_response(_audit_event_response(event).model_dump(mode="json"), request)
