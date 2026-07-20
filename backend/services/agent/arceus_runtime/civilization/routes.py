from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusMemoryItem
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..compiler.utils import stable_hash
from .api_schemas import (
    CivilizationConstitutionResponse,
    CivilizationEvolveRequest,
    CivilizationEvolveResponse,
    CivilizationMetricsResponse,
    CivilizationProposalRequest,
    CivilizationProposalResponse,
    CivilizationSimulateRequest,
    CivilizationSimulateResponse,
    CivilizationStateResponse,
)
from .service import build_state, constitution, evolve_civilization, metrics, propose_organization, simulate_civilization


router = APIRouter(prefix="/api/v1/civilization", tags=["self-evolving-civilization"])


def _persist(
    db: Session,
    context: RequestContext,
    *,
    title: str,
    content_type: str,
    content: dict,
    event_type: str,
    lifecycle_status: str = "verified",
) -> ArceusMemoryItem:
    content_hash = stable_hash({"content_type": content_type, "title": title, "content": content})
    existing = (
        db.query(ArceusMemoryItem)
        .filter(
            ArceusMemoryItem.tenant_id == context.tenant_id,
            ArceusMemoryItem.memory_scope == "global",
            ArceusMemoryItem.content_hash == content_hash,
        )
        .first()
    )
    if existing:
        return existing
    row = ArceusMemoryItem(
        tenant_id=context.tenant_id,
        memory_scope="global",
        title=title,
        content=json.dumps(content, sort_keys=True, default=str),
        content_type=content_type,
        source_type="civilization_layer",
        source_ids=[
            str(
                content.get("civilization_id")
                or content.get("proposal_id")
                or content.get("evolution_id")
                or content.get("simulation_id")
                or title
            )
        ],
        evidence_ids=[str(item) for item in content.get("evidence_ids", [])],
        lifecycle_status=lifecycle_status,
        trust_level="governed",
        confidence=0.84,
        sensitivity="organization",
        content_hash=content_hash,
    )
    db.add(row)
    db.flush()
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action=event_type,
        resource_type=content_type,
        resource_id=row.id,
        result=lifecycle_status,
        metadata={"content_hash": content_hash, "correlation_id": str(context.correlation_id)},
    )
    return row


def _civilization_memories(db: Session, tenant_id: UUID, limit: int = 250) -> list[dict]:
    rows = (
        db.query(ArceusMemoryItem)
        .filter(
            ArceusMemoryItem.tenant_id == tenant_id,
            ArceusMemoryItem.content_type.like("civilization%"),
        )
        .order_by(ArceusMemoryItem.created_at.desc())
        .limit(limit)
        .all()
    )
    payloads = []
    for row in rows:
        try:
            content = json.loads(row.content)
        except (TypeError, json.JSONDecodeError):
            content = {}
        payloads.append({"id": str(row.id), "title": row.title, "content_type": row.content_type, "content": content})
    return payloads


@router.post("/evolve", status_code=status.HTTP_201_CREATED)
def evolve(
    payload: CivilizationEvolveRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("civilization.evolve")),
    db: Session = Depends(get_db),
):
    result = evolve_civilization(payload.model_dump(mode="json"))
    lifecycle = "approved" if result["promotion_ready"] else ("proposed" if result["status"] != "blocked" else "disputed")
    _persist(db, context, title=f"Civilization evolution: {payload.objective[:120]}", content_type="civilization_evolution", content={**payload.model_dump(mode="json"), **result}, event_type=result["events"][0], lifecycle_status=lifecycle)
    db.commit()
    return api_response(CivilizationEvolveResponse(**result).model_dump(mode="json"), request)


@router.get("/state")
def state(
    request: Request,
    context: RequestContext = Depends(require_permission("civilization.view")),
    db: Session = Depends(get_db),
):
    result = build_state(_civilization_memories(db, context.tenant_id), str(context.tenant_id))
    return api_response(CivilizationStateResponse(**result).model_dump(mode="json"), request)


@router.post("/propose", status_code=status.HTTP_201_CREATED)
def propose(
    payload: CivilizationProposalRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("civilization.propose")),
    db: Session = Depends(get_db),
):
    result = propose_organization(payload.model_dump(mode="json"))
    lifecycle = "proposed" if result["status"] != "blocked_by_budget" else "disputed"
    _persist(db, context, title=f"Civilization proposal: {payload.goal[:120]}", content_type="civilization_organization_proposal", content={**payload.model_dump(mode="json"), **result}, event_type=result["events"][0], lifecycle_status=lifecycle)
    db.commit()
    return api_response(CivilizationProposalResponse(**result).model_dump(mode="json"), request)


@router.get("/metrics")
def get_metrics(
    request: Request,
    context: RequestContext = Depends(require_permission("civilization.metrics.view")),
    db: Session = Depends(get_db),
):
    result = metrics(_civilization_memories(db, context.tenant_id))
    return api_response(CivilizationMetricsResponse(**result).model_dump(mode="json"), request)


@router.post("/simulate", status_code=status.HTTP_201_CREATED)
def simulate(
    payload: CivilizationSimulateRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("civilization.simulate")),
    db: Session = Depends(get_db),
):
    result = simulate_civilization(payload.model_dump(mode="json"))
    lifecycle = "verified" if result["status"] != "blocked" else "disputed"
    _persist(db, context, title=f"Civilization simulation: {payload.scenario[:120]}", content_type="civilization_simulation", content={**payload.model_dump(mode="json"), **result}, event_type=result["events"][0], lifecycle_status=lifecycle)
    db.commit()
    return api_response(CivilizationSimulateResponse(**result).model_dump(mode="json"), request)


@router.get("/constitution")
def get_constitution(
    request: Request,
    context: RequestContext = Depends(require_permission("civilization.constitution.view")),
):
    return api_response(CivilizationConstitutionResponse(**constitution()).model_dump(mode="json"), request)

