from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import MissionBudgetSummaryResponse, UsageRecordResponse, UsageSummaryResponse, UsageTypeSummaryResponse


router = APIRouter(tags=["usage"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _usage_record_response(record) -> UsageRecordResponse:
    return UsageRecordResponse(
        id=record.id,
        user_id=record.user_id,
        mission_id=record.mission_id,
        usage_type=record.usage_type,
        quantity=record.quantity,
        unit=record.unit,
        cost_usd=record.cost_usd,
        metadata_json=record.metadata_json or {},
        occurred_at=record.occurred_at,
    )


def _summary_by_type(summary: dict) -> list[UsageTypeSummaryResponse]:
    return [
        UsageTypeSummaryResponse(
            usage_type=item["usage_type"],
            quantity=item["quantity"],
            unit=item["unit"],
            cost_usd=item["cost_usd"],
            record_count=item["record_count"],
        )
        for item in summary["by_type"]
    ]


@router.get("/api/v1/runtime/usage/records")
def list_usage_records(
    request: Request,
    context: RequestContext = Depends(require_permission("usage.view")),
    user_id: UUID | None = Query(default=None),
    mission_id: UUID | None = Query(default=None),
    usage_type: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    records = _uow(db).usage.list(
        tenant_id=context.tenant_id,
        user_id=user_id,
        mission_id=mission_id,
        usage_type=usage_type,
        limit=limit,
    )
    return collection_response([_usage_record_response(record).model_dump(mode="json") for record in records], request)


@router.get("/api/v1/runtime/usage/records/{usage_record_id}")
def get_usage_record(
    usage_record_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("usage.view")),
    db: Session = Depends(get_db),
):
    record = _uow(db).usage.get(tenant_id=context.tenant_id, usage_record_id=usage_record_id)
    return api_response(_usage_record_response(record).model_dump(mode="json"), request)


@router.get("/api/v1/runtime/usage/summary")
def get_usage_summary(
    request: Request,
    context: RequestContext = Depends(require_permission("usage.view")),
    user_id: UUID | None = Query(default=None),
    mission_id: UUID | None = Query(default=None),
    current_user_only: bool = Query(default=False),
    limit: int = Query(default=500, ge=1, le=500),
    db: Session = Depends(get_db),
):
    scoped_user_id = context.user_id if current_user_only else user_id
    summary = _uow(db).usage.summarize(
        tenant_id=context.tenant_id,
        user_id=scoped_user_id,
        mission_id=mission_id,
        limit=limit,
    )
    response = UsageSummaryResponse(
        tenant_id=context.tenant_id,
        user_id=scoped_user_id,
        mission_id=mission_id,
        record_count=summary["record_count"],
        cost_usd=summary["cost_usd"],
        by_type=_summary_by_type(summary),
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/api/v1/missions/{mission_id}/usage")
def get_mission_usage_summary(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("usage.view")),
    limit: int = Query(default=500, ge=1, le=500),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    mission = uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    summary = uow.usage.summarize(tenant_id=context.tenant_id, mission_id=mission_id, limit=limit)
    budget = mission.maximum_budget_amount
    actual = mission.actual_cost_amount or Decimal("0")
    response = MissionBudgetSummaryResponse(
        tenant_id=context.tenant_id,
        user_id=None,
        mission_id=mission_id,
        record_count=summary["record_count"],
        cost_usd=summary["cost_usd"],
        by_type=_summary_by_type(summary),
        mission_budget_amount=budget,
        mission_actual_cost_amount=actual,
        budget_currency=mission.budget_currency,
        budget_remaining_amount=(budget - actual) if budget is not None else None,
    )
    return api_response(response.model_dump(mode="json"), request)
