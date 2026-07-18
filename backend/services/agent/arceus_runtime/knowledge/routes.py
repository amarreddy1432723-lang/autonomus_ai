from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    KnowledgeGraphResponse,
    KnowledgeImpactResponse,
    KnowledgeIndexRequest,
    KnowledgeIndexResponse,
    KnowledgeNodeResponse,
    KnowledgeSearchResponse,
)
from .service import MEMORY_LAYERS, analyze_impact, base_knowledge_graph, get_node, index_repository, search_graph


router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge-graph"])


@router.get("/search")
def search_knowledge(
    request: Request,
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=10, ge=1, le=50),
    context: RequestContext = Depends(require_permission("knowledge.search")),
):
    result = search_graph(q, limit=limit)
    response = KnowledgeSearchResponse(
        query=result["query"],
        strategy=result["strategy"],
        results=[KnowledgeNodeResponse(**item) for item in result["results"]],
        related_edges=result["related_edges"],
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/node/{node_id}")
def get_knowledge_node(
    node_id: str,
    request: Request,
    context: RequestContext = Depends(require_permission("knowledge.view")),
):
    node = get_node(node_id)
    response = KnowledgeNodeResponse(**node) if node else KnowledgeNodeResponse(
        node_id=node_id,
        type="documentation",
        name="Unknown knowledge node",
        ontology="Knowledge",
        metadata={"status": "not_found", "message": "Persistent graph storage is not connected for this node."},
        confidence="hypothesized",
        evidence=[],
        created_at=base_knowledge_graph()["indexed_at"],
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/graph")
def get_knowledge_graph(
    request: Request,
    context: RequestContext = Depends(require_permission("knowledge.view")),
):
    graph = base_knowledge_graph()
    response = KnowledgeGraphResponse(
        graph_id="arceus-reference",
        graph_hash=graph["graph_hash"],
        nodes=[KnowledgeNodeResponse(**item) for item in graph["nodes"]],
        edges=graph["edges"],
        generated_at=graph["indexed_at"],
        memory_layers=MEMORY_LAYERS,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.post("/index")
def index_knowledge(
    payload: KnowledgeIndexRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("knowledge.index")),
    db: Session = Depends(get_db),
):
    result = index_repository(payload.model_dump(mode="json"))
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="REPOSITORY_INDEXED",
        resource_type="knowledge_graph",
        resource_id=payload.repository_id,
        result="completed",
        metadata={
            "repository_name": payload.repository_name,
            "node_count": result["node_count"],
            "edge_count": result["edge_count"],
            "graph_hash": result["graph_hash"],
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    response = KnowledgeIndexResponse(**result)
    return api_response(response.model_dump(mode="json"), request)


@router.get("/impact")
def get_knowledge_impact(
    request: Request,
    changed_entity: str = Query(min_length=1, max_length=500),
    context: RequestContext = Depends(require_permission("knowledge.impact")),
    db: Session = Depends(get_db),
):
    result = analyze_impact(changed_entity)
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="IMPACT_ANALYSIS_COMPLETED",
        resource_type="knowledge_graph",
        resource_id=changed_entity,
        result=result["risk_level"],
        metadata={"affected_nodes": len(result["affected_nodes"]), "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    response = KnowledgeImpactResponse(**result)
    return api_response(response.model_dump(mode="json"), request)
