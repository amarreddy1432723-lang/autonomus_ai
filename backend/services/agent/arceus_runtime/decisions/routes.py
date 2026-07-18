from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import DecisionResponse


router = APIRouter(tags=["decisions"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _decision_response(decision) -> DecisionResponse:
    return DecisionResponse(
        id=decision.id,
        mission_id=decision.mission_id,
        task_id=decision.task_id,
        decision_key=decision.decision_key,
        title=decision.title,
        summary=decision.summary,
        selected_option=decision.selected_option or {},
        alternatives=decision.alternatives or [],
        rationale=decision.rationale,
        status=decision.status,
        decided_by_member_id=decision.decided_by_member_id,
        created_at=decision.created_at,
        updated_at=decision.updated_at,
        version_number=decision.version_number,
    )


@router.get("/api/v1/missions/{mission_id}/decisions")
def list_mission_decisions(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("decision.view")),
    decision_status: str | None = Query(default=None, alias="status", max_length=60),
    current_only: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    decisions = uow.decisions.list_for_mission(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        status=decision_status,
        current_only=current_only,
        limit=limit,
    )
    return collection_response([_decision_response(item).model_dump(mode="json") for item in decisions], request)


@router.get("/api/v1/missions/{mission_id}/decisions/current")
def list_current_mission_decisions(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("decision.view")),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    decisions = uow.decisions.list_for_mission(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        current_only=True,
        limit=limit,
    )
    return collection_response([_decision_response(item).model_dump(mode="json") for item in decisions], request)


@router.get("/api/v1/decisions/{decision_id}")
def get_decision(
    decision_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("decision.view")),
    db: Session = Depends(get_db),
):
    decision = _uow(db).decisions.get(tenant_id=context.tenant_id, decision_id=decision_id)
    return api_response(_decision_response(decision).model_dump(mode="json"), request)
