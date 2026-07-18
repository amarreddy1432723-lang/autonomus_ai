from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_idempotency_key, require_permission
from ..api.responses import api_response, collection_response
from ..application.idempotency import calculate_request_hash
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import CreateMissionRequest, MissionTransitionRequest, SubmitClarificationsRequest
from .commands import CreateMissionCommand, MissionTransitionCommand, SubmitClarificationsCommand
from .handlers import CreateMissionHandler, MissionQueryHandler, SubmitClarificationsHandler, TransitionMissionHandler


router = APIRouter(prefix="/api/v1/missions", tags=["missions"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_mission(
    request_body: CreateMissionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("mission.create")),
    idempotency_key: str = Depends(require_idempotency_key),
    db: Session = Depends(get_db),
):
    payload = request_body.model_dump(mode="json")
    command = CreateMissionCommand(
        tenant_id=context.tenant_id,
        project_id=request_body.project_id,
        mission_owner_id=context.user_id,
        objective=request_body.objective,
        title=request_body.title,
        repository_ids=tuple(request_body.repository_ids),
        constraints=tuple(request_body.constraints),
        desired_outcomes=tuple(request_body.desired_outcomes),
        maximum_budget_amount=request_body.budget.maximum_amount,
        budget_currency=request_body.budget.currency,
        priority=request_body.priority,
        idempotency_key=idempotency_key,
        request_hash=calculate_request_hash("mission.create", payload),
        actor_id=context.user_id,
        correlation_id=context.correlation_id,
    )
    result = CreateMissionHandler(_uow(db)).handle(command)
    return api_response(result.model_dump(mode="json"), request)


@router.get("")
def list_missions(
    request: Request,
    context: RequestContext = Depends(require_permission("mission.view")),
    project_id: UUID | None = Query(default=None),
    mission_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    result = MissionQueryHandler(_uow(db)).list(
        tenant_id=context.tenant_id,
        project_id=project_id,
        status=mission_status,
        limit=limit,
    )
    return collection_response([item.model_dump(mode="json") for item in result], request)


@router.get("/{mission_id}")
def get_mission(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("mission.view")),
    db: Session = Depends(get_db),
):
    result = MissionQueryHandler(_uow(db)).get(tenant_id=context.tenant_id, mission_id=mission_id)
    return api_response(result.model_dump(mode="json"), request)


@router.get("/{mission_id}/clarifications")
def get_clarifications(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("mission.clarify")),
    db: Session = Depends(get_db),
):
    result = MissionQueryHandler(_uow(db)).clarifications(tenant_id=context.tenant_id, mission_id=mission_id)
    return collection_response([item.model_dump(mode="json") for item in result], request)


@router.get("/{mission_id}/events")
def get_mission_events(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("mission.view")),
    after_sequence: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    events = uow.events.list_for_mission_after(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        after_version=after_sequence,
        limit=limit,
    )
    return collection_response(
        [
            {
                "id": str(event.id),
                "sequence": event.aggregate_version,
                "event_type": event.event_type,
                "payload": event.payload,
                "occurred_at": event.occurred_at.isoformat(),
            }
            for event in events
        ],
        request,
        next_cursor=str(events[-1].aggregate_version) if events else None,
        has_more=len(events) == limit,
    )


@router.post("/{mission_id}/clarifications", status_code=status.HTTP_202_ACCEPTED)
def submit_clarifications(
    mission_id: UUID,
    request_body: SubmitClarificationsRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("mission.clarify")),
    idempotency_key: str = Depends(require_idempotency_key),
    db: Session = Depends(get_db),
):
    payload = {
        "mission_id": str(mission_id),
        "expected_version": request_body.expected_version,
        "answers": [item.model_dump(mode="json") for item in request_body.answers],
    }
    command = SubmitClarificationsCommand(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        expected_version=request_body.expected_version,
        answers=tuple((item.unknown_id, item.answer) for item in request_body.answers),
        actor_id=context.user_id,
        idempotency_key=idempotency_key,
        request_hash=calculate_request_hash("mission.clarify", payload),
        correlation_id=context.correlation_id,
    )
    result = SubmitClarificationsHandler(_uow(db)).handle(command)
    return api_response(result.model_dump(mode="json"), request)


def _transition_command(
    *,
    action: str,
    mission_id: UUID,
    request_body: MissionTransitionRequest,
    context: RequestContext,
    idempotency_key: str,
) -> MissionTransitionCommand:
    payload = {
        "mission_id": str(mission_id),
        "expected_version": request_body.expected_version,
        "reason": request_body.reason,
    }
    return MissionTransitionCommand(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        expected_version=request_body.expected_version,
        action=action,
        reason=request_body.reason,
        actor_id=context.user_id,
        idempotency_key=idempotency_key,
        request_hash=calculate_request_hash(f"mission.{action}", payload),
        correlation_id=context.correlation_id,
    )


def _transition_response(
    *,
    action: str,
    mission_id: UUID,
    request_body: MissionTransitionRequest,
    request: Request,
    context: RequestContext,
    idempotency_key: str,
    db: Session,
):
    command = _transition_command(
        action=action,
        mission_id=mission_id,
        request_body=request_body,
        context=context,
        idempotency_key=idempotency_key,
    )
    result = TransitionMissionHandler(_uow(db)).handle(command)
    return api_response(result.model_dump(mode="json"), request)


@router.post("/{mission_id}/compile", status_code=status.HTTP_202_ACCEPTED)
def compile_mission(
    mission_id: UUID,
    request_body: MissionTransitionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("mission.compile")),
    idempotency_key: str = Depends(require_idempotency_key),
    db: Session = Depends(get_db),
):
    return _transition_response(
        action="compile",
        mission_id=mission_id,
        request_body=request_body,
        request=request,
        context=context,
        idempotency_key=idempotency_key,
        db=db,
    )


@router.post("/{mission_id}/start", status_code=status.HTTP_202_ACCEPTED)
def start_mission(
    mission_id: UUID,
    request_body: MissionTransitionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("mission.start")),
    idempotency_key: str = Depends(require_idempotency_key),
    db: Session = Depends(get_db),
):
    return _transition_response(action="start", mission_id=mission_id, request_body=request_body, request=request, context=context, idempotency_key=idempotency_key, db=db)


@router.post("/{mission_id}/pause", status_code=status.HTTP_202_ACCEPTED)
def pause_mission(
    mission_id: UUID,
    request_body: MissionTransitionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("mission.pause")),
    idempotency_key: str = Depends(require_idempotency_key),
    db: Session = Depends(get_db),
):
    return _transition_response(action="pause", mission_id=mission_id, request_body=request_body, request=request, context=context, idempotency_key=idempotency_key, db=db)


@router.post("/{mission_id}/resume", status_code=status.HTTP_202_ACCEPTED)
def resume_mission(
    mission_id: UUID,
    request_body: MissionTransitionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("mission.resume")),
    idempotency_key: str = Depends(require_idempotency_key),
    db: Session = Depends(get_db),
):
    return _transition_response(action="resume", mission_id=mission_id, request_body=request_body, request=request, context=context, idempotency_key=idempotency_key, db=db)


@router.post("/{mission_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
def cancel_mission(
    mission_id: UUID,
    request_body: MissionTransitionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("mission.cancel")),
    idempotency_key: str = Depends(require_idempotency_key),
    db: Session = Depends(get_db),
):
    return _transition_response(action="cancel", mission_id=mission_id, request_body=request_body, request=request, context=context, idempotency_key=idempotency_key, db=db)
