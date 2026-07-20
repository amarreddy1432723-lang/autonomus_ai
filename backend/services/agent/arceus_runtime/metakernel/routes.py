from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusEvent
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    KernelContractResponse,
    KernelEntityResponse,
    KernelEventResponse,
    KernelInvariantResponse,
    KernelReplayRequest,
    KernelReplayResponse,
    KernelValidationRequest,
    KernelValidationResponse,
)
from .service import canonical_contracts, canonical_entities, event_stream_health, kernel_invariants, replay_events, validate_kernel_payload


router = APIRouter(prefix="/api/v1/kernel", tags=["aios-meta-kernel"])


@router.get("/entities")
def list_kernel_entities(
    request: Request,
    entity_type: str | None = Query(default=None, max_length=120),
    context: RequestContext = Depends(require_permission("kernel.view")),
):
    rows = canonical_entities()
    if entity_type:
        rows = [row for row in rows if row["entity_type"] == entity_type.lower()]
    return collection_response([KernelEntityResponse(**row).model_dump(mode="json") for row in rows], request)


@router.get("/contracts")
def list_kernel_contracts(
    request: Request,
    contract_key: str | None = Query(default=None, max_length=120),
    context: RequestContext = Depends(require_permission("kernel.view")),
):
    rows = canonical_contracts()
    if contract_key:
        rows = [row for row in rows if row["contract_key"] == contract_key.lower()]
    return collection_response([KernelContractResponse(**row).model_dump(mode="json") for row in rows], request)


@router.get("/events")
def list_kernel_events(
    request: Request,
    aggregate_type: str | None = Query(default=None, max_length=120),
    limit: int = Query(default=100, ge=1, le=500),
    context: RequestContext = Depends(require_permission("kernel.events.view")),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusEvent).filter(ArceusEvent.tenant_id == context.tenant_id)
    if aggregate_type:
        query = query.filter(ArceusEvent.aggregate_type == aggregate_type)
    events = query.order_by(ArceusEvent.occurred_at.desc()).limit(limit).all()
    rows = [
        KernelEventResponse(
            event_id=event.id,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            aggregate_version=int(event.aggregate_version),
            event_type=event.event_type,
            actor_type=event.actor_type,
            actor_id=event.actor_id,
            payload=event.payload or {},
            metadata_json=event.metadata_json or {},
            occurred_at=event.occurred_at,
        ).model_dump(mode="json")
        for event in events
    ]
    return collection_response(rows, request, has_more=len(events) == limit)


@router.post("/validate")
def validate_against_meta_kernel(
    payload: KernelValidationRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("kernel.validate")),
    db: Session = Depends(get_db),
):
    result = validate_kernel_payload(entity_type=payload.entity_type, payload=payload.payload, intended_action=payload.intended_action)
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="CONTRACT_VALIDATED" if result["valid"] else "INVARIANT_VIOLATED",
        resource_type=payload.entity_type,
        resource_id=payload.payload.get("id") or payload.payload.get(f"{payload.entity_type}_id"),
        result=result["status"],
        metadata={
            "intended_action": payload.intended_action,
            "violations": result["violations"],
            "required_events": result["required_events"],
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    return api_response(KernelValidationResponse(**result).model_dump(mode="json"), request)


@router.post("/replay")
def replay_kernel_state(
    payload: KernelReplayRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("kernel.replay")),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusEvent).filter(
        ArceusEvent.tenant_id == context.tenant_id,
        ArceusEvent.aggregate_type == payload.aggregate_type,
        ArceusEvent.aggregate_id == payload.aggregate_id,
        ArceusEvent.aggregate_version >= payload.from_version,
    )
    if payload.to_version is not None:
        query = query.filter(ArceusEvent.aggregate_version <= payload.to_version)
    events = query.order_by(ArceusEvent.aggregate_version.asc()).all()
    result = replay_events(
        aggregate_type=payload.aggregate_type,
        aggregate_id=payload.aggregate_id,
        events=events,
        from_version=payload.from_version,
        to_version=payload.to_version,
    )
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="STATE_REPLAYED",
        resource_type=payload.aggregate_type,
        resource_id=payload.aggregate_id,
        result="replayable" if result["replayable"] else "violations_detected",
        metadata={"event_count": result["event_count"], "violations": result["violations"], "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    return api_response(KernelReplayResponse(**result).model_dump(mode="json"), request)


@router.get("/invariants")
def list_kernel_invariants(
    request: Request,
    context: RequestContext = Depends(require_permission("kernel.view")),
    db: Session = Depends(get_db),
):
    recent_events = db.query(ArceusEvent).filter(ArceusEvent.tenant_id == context.tenant_id).order_by(ArceusEvent.occurred_at.desc()).limit(500).all()
    health = event_stream_health(recent_events)
    rows = [KernelInvariantResponse(**row).model_dump(mode="json") for row in kernel_invariants()]
    return api_response({"invariants": rows, "event_stream_health": health}, request)
