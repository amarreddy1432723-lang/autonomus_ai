from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusMemoryItem
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..compiler.utils import stable_hash
from .api_schemas import (
    GraphEntityResponse,
    GraphHistoryResponse,
    GraphQueryRequest,
    GraphQueryResponse,
    GraphRelationshipResponse,
    GraphSearchRequest,
    GraphSearchResponse,
    GraphSyncRequest,
    GraphSyncResponse,
)
from .service import build_digital_twin_sync, graph_query, graph_search, history_from_snapshots


router = APIRouter(prefix="/api/v1/graph", tags=["universal-data-fabric"])


def _graph_snapshots(db: Session, tenant_id: UUID, limit: int = 100) -> list[dict]:
    rows = (
        db.query(ArceusMemoryItem)
        .filter(
            ArceusMemoryItem.tenant_id == tenant_id,
            ArceusMemoryItem.memory_scope == "organization",
            ArceusMemoryItem.content_type == "digital_twin_snapshot",
        )
        .order_by(ArceusMemoryItem.created_at.desc())
        .limit(limit)
        .all()
    )
    snapshots = []
    for row in rows:
        try:
            snapshots.append(json.loads(row.content))
        except (TypeError, json.JSONDecodeError):
            continue
    return snapshots


def _merged_graph(snapshots: list[dict]) -> tuple[list[dict], list[dict]]:
    entities: dict[str, dict] = {}
    relationships: dict[str, dict] = {}
    for snapshot in reversed(snapshots):
        for entity in snapshot.get("resolved_entities", []):
            entities[entity["entity_id"]] = entity
        for relationship in snapshot.get("relationships", []):
            relationships[relationship["relationship_id"]] = relationship
    return list(entities.values()), list(relationships.values())


def _persist_snapshot(db: Session, context: RequestContext, snapshot: dict) -> ArceusMemoryItem:
    content_hash = stable_hash(snapshot)
    existing = (
        db.query(ArceusMemoryItem)
        .filter(
            ArceusMemoryItem.tenant_id == context.tenant_id,
            ArceusMemoryItem.memory_scope == "organization",
            ArceusMemoryItem.scope_reference_id.is_(None),
            ArceusMemoryItem.content_hash == content_hash,
        )
        .first()
    )
    if existing:
        return existing
    row = ArceusMemoryItem(
        tenant_id=context.tenant_id,
        memory_scope="organization",
        title=f"Digital twin sync from {snapshot['source_system']}",
        content=json.dumps(snapshot, sort_keys=True, default=str),
        content_type="digital_twin_snapshot",
        source_type=snapshot["connector"],
        source_ids=[snapshot["source_system"]],
        evidence_ids=[],
        lifecycle_status="verified" if snapshot["consistency"]["valid"] else "proposed",
        trust_level="observed",
        confidence=0.82 if snapshot["consistency"]["valid"] else 0.52,
        sensitivity="organization",
        content_hash=content_hash,
    )
    db.add(row)
    db.flush()
    return row


@router.get("/entities")
def list_graph_entities(
    request: Request,
    entity_type: str | None = Query(default=None, max_length=120),
    context: RequestContext = Depends(require_permission("graph.view")),
    db: Session = Depends(get_db),
):
    entities, _ = _merged_graph(_graph_snapshots(db, context.tenant_id))
    if entity_type:
        entities = [item for item in entities if item["entity_type"] == entity_type.lower()]
    return collection_response([GraphEntityResponse(**item).model_dump(mode="json") for item in entities], request)


@router.get("/relationships")
def list_graph_relationships(
    request: Request,
    relationship_type: str | None = Query(default=None, max_length=120),
    context: RequestContext = Depends(require_permission("graph.view")),
    db: Session = Depends(get_db),
):
    _, relationships = _merged_graph(_graph_snapshots(db, context.tenant_id))
    if relationship_type:
        relationships = [item for item in relationships if item["relationship_type"] == relationship_type.lower()]
    return collection_response([GraphRelationshipResponse(**item).model_dump(mode="json") for item in relationships], request)


@router.post("/query")
def query_graph(
    payload: GraphQueryRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("graph.query")),
    db: Session = Depends(get_db),
):
    entities, relationships = _merged_graph(_graph_snapshots(db, context.tenant_id))
    result = graph_query(payload.model_dump(mode="json"), entities, relationships)
    return api_response(GraphQueryResponse(**result).model_dump(mode="json"), request)


@router.post("/search")
def search_graph_entities(
    payload: GraphSearchRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("graph.search")),
    db: Session = Depends(get_db),
):
    entities, relationships = _merged_graph(_graph_snapshots(db, context.tenant_id))
    result = graph_search(payload.query, entities, relationships, entity_types=payload.entity_types, limit=payload.limit)
    return api_response(GraphSearchResponse(**result).model_dump(mode="json"), request)


@router.post("/sync")
def sync_graph(
    payload: GraphSyncRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("graph.sync")),
    db: Session = Depends(get_db),
):
    snapshot = build_digital_twin_sync(payload.model_dump(mode="json"))
    row = _persist_snapshot(db, context, snapshot)
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="DIGITAL_TWIN_REFRESHED",
        resource_type="digital_twin_snapshot",
        resource_id=row.id,
        result="valid" if snapshot["consistency"]["valid"] else "violations",
        metadata={
            "events": snapshot["events"],
            "entity_count": snapshot["entity_count"],
            "relationship_count": snapshot["relationship_count"],
            "violations": snapshot["consistency"]["violations"],
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    return api_response(GraphSyncResponse(**snapshot).model_dump(mode="json"), request)


@router.get("/history")
def get_graph_history(
    request: Request,
    entity_id: str | None = Query(default=None, max_length=160),
    context: RequestContext = Depends(require_permission("graph.view")),
    db: Session = Depends(get_db),
):
    result = history_from_snapshots(entity_id, _graph_snapshots(db, context.tenant_id, limit=200))
    return api_response(GraphHistoryResponse(**result).model_dump(mode="json"), request)
