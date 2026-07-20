from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusMemoryItem
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    MemoryArchiveRequest,
    MemoryConflictResponse,
    MemoryExtractRequest,
    MemoryExtractResponse,
    MemoryFact,
    MemoryFeedbackRequest,
    MemoryFeedbackResponse,
    MemoryGraphProjectionResponse,
    MemoryItemResponse,
    MemoryLifecycleResponse,
    MemoryRetentionPolicyResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    MemoryStoreRequest,
    MemorySummarizeRequest,
    MemorySummarizeResponse,
)
from .service import (
    build_memory_payload,
    can_forget,
    encode_content,
    apply_memory_feedback,
    detect_memory_conflicts,
    extract_memory_facts,
    graph_projection_for_memory,
    memory_response_payload,
    RETENTION_POLICIES,
    search_memories,
    summarize_memories,
)


router = APIRouter(prefix="/api/v1/memory", tags=["enterprise-memory-fabric"])


def _memory_or_404(db: Session, tenant_id: UUID, memory_id: UUID) -> ArceusMemoryItem:
    item = db.query(ArceusMemoryItem).filter(ArceusMemoryItem.tenant_id == tenant_id, ArceusMemoryItem.id == memory_id).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Memory not found.")
    return item


def _tenant_memories(db: Session, tenant_id: UUID, *, include_archived: bool = False) -> list[ArceusMemoryItem]:
    query = db.query(ArceusMemoryItem).filter(ArceusMemoryItem.tenant_id == tenant_id)
    if not include_archived:
        query = query.filter(ArceusMemoryItem.lifecycle_status != "archived")
    return query.order_by(ArceusMemoryItem.created_at.desc()).limit(500).all()


@router.post("/store", status_code=status.HTTP_201_CREATED)
def store_memory(
    payload: MemoryStoreRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("memory.store")),
    db: Session = Depends(get_db),
):
    built = build_memory_payload(payload.model_dump(mode="json"), owner_id=str(context.user_id))
    existing = (
        db.query(ArceusMemoryItem)
        .filter(
            ArceusMemoryItem.tenant_id == context.tenant_id,
            ArceusMemoryItem.memory_scope == built["memory_scope"],
            ArceusMemoryItem.scope_reference_id == payload.scope_reference_id,
            ArceusMemoryItem.content_hash == built["content_hash"],
        )
        .first()
    )
    if existing:
        return api_response(MemoryItemResponse(**memory_response_payload(existing)).model_dump(mode="json"), request, deduplicated=True)
    item = ArceusMemoryItem(
        tenant_id=context.tenant_id,
        memory_scope=built["memory_scope"],
        scope_reference_id=payload.scope_reference_id,
        title=built["title"],
        content=encode_content(built["content"], built["metadata"]),
        content_type=built["content_type"],
        source_type=built["source_type"],
        source_ids=built["source_ids"],
        evidence_ids=built["evidence_ids"],
        lifecycle_status=built["lifecycle_status"],
        trust_level=built["trust_level"],
        confidence=built["confidence"],
        sensitivity=built["sensitivity"],
        content_hash=built["content_hash"],
        valid_until=built["valid_until"],
    )
    db.add(item)
    db.flush()
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="MEMORY_CREATED",
        resource_type="memory",
        resource_id=item.id,
        result=item.lifecycle_status,
        metadata={"memory_type": item.content_type, "importance": built["metadata"]["importance"], "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    db.refresh(item)
    return api_response(MemoryItemResponse(**memory_response_payload(item)).model_dump(mode="json"), request)


@router.post("/extract")
def extract_memory(
    payload: MemoryExtractRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("memory.store")),
    db: Session = Depends(get_db),
):
    extracted = extract_memory_facts(payload.content)
    stored_memory = None
    if payload.store:
        store_payload = MemoryStoreRequest(
            memory_type="semantic",
            memory_scope=payload.memory_scope,
            scope_reference_id=payload.scope_reference_id,
            title=payload.title,
            content=payload.content,
            source_type=payload.source_type,
            source_ids=payload.source_ids,
            evidence_ids=payload.evidence_ids,
            relationships=[{"type": fact["relation"], "from": fact["subject"], "to": fact["object"], "confidence": fact["confidence"]} for fact in extracted["facts"]],
            tags=[entity["label"] for entity in extracted["entities"][:20]],
            confidence=max([fact["confidence"] for fact in extracted["facts"]] or [0.62]),
            sensitivity="project",
            retention_policy="standard",
        )
        built = build_memory_payload(store_payload.model_dump(mode="json"), owner_id=str(context.user_id))
        item = ArceusMemoryItem(
            tenant_id=context.tenant_id,
            memory_scope=built["memory_scope"],
            scope_reference_id=payload.scope_reference_id,
            title=built["title"],
            content=encode_content(built["content"], built["metadata"]),
            content_type=built["content_type"],
            source_type=built["source_type"],
            source_ids=built["source_ids"],
            evidence_ids=built["evidence_ids"],
            lifecycle_status=built["lifecycle_status"],
            trust_level=built["trust_level"],
            confidence=built["confidence"],
            sensitivity=built["sensitivity"],
            content_hash=built["content_hash"],
            valid_until=built["valid_until"],
        )
        db.add(item)
        db.flush()
        stored_memory = MemoryItemResponse(**memory_response_payload(item))
        SqlAlchemyUnitOfWork(db).audit.record(
            tenant_id=context.tenant_id,
            actor_id=context.user_id,
            action="MEMORY_EXTRACTED",
            resource_type="memory",
            resource_id=item.id,
            result="stored",
            metadata={"fact_count": len(extracted["facts"]), "correlation_id": str(context.correlation_id)},
        )
        db.commit()
    response = MemoryExtractResponse(
        facts=[MemoryFact(**fact) for fact in extracted["facts"]],
        entities=extracted["entities"],
        relationships=extracted["relationships"],
        stored_memory=stored_memory,
        events=["FACTS_EXTRACTED", "MEMORY_STORED"] if stored_memory else ["FACTS_EXTRACTED"],
    )
    return api_response(response.model_dump(mode="json"), request)


@router.post("/search")
def search_memory_fabric(
    payload: MemorySearchRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("memory.search")),
    db: Session = Depends(get_db),
):
    rows = _tenant_memories(db, context.tenant_id, include_archived=payload.include_archived)
    if payload.scope_reference_id:
        rows = [item for item in rows if item.scope_reference_id == payload.scope_reference_id]
    result = search_memories(rows, payload.model_dump(mode="json"))
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="MEMORY_RECALLED",
        resource_type="memory_search",
        resource_id=payload.query[:160],
        result="completed",
        metadata={"returned": len(result["results"]), "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    return api_response(MemorySearchResponse(**result).model_dump(mode="json"), request)


@router.post("/summarize")
def summarize_memory(
    payload: MemorySummarizeRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("memory.summarize")),
    db: Session = Depends(get_db),
):
    if payload.memory_ids:
        rows = [_memory_or_404(db, context.tenant_id, memory_id) for memory_id in payload.memory_ids]
    else:
        rows = _tenant_memories(db, context.tenant_id)
        if payload.query:
            rows = search_memories(rows, {"query": payload.query, "limit": 20, "authorized_sensitivities": ["public", "mission", "project", "organization"], "mission_context": {}})["results"]
            rows = [_memory_or_404(db, context.tenant_id, item["memory"]["id"]) for item in rows]
    summary = summarize_memories(rows, query=payload.query)
    summary_item = None
    if rows:
        store_payload = {
            "memory_type": "semantic",
            "memory_scope": payload.target_scope,
            "title": payload.summary_title or "Consolidated memory summary",
            "content": summary["summary"],
            "source_type": "memory_consolidation",
            "source_ids": [str(memory_id) for memory_id in summary["source_memory_ids"]],
            "evidence_ids": summary["evidence_ids"] if payload.preserve_evidence else [],
            "relationships": [{"type": "summarizes", "memory_id": str(memory_id)} for memory_id in summary["source_memory_ids"]],
            "tags": summary["themes"],
            "importance": "high" if "high_importance_recall" in summary["patterns"] else "medium",
            "confidence": 0.82,
            "sensitivity": "organization",
            "retention_policy": "standard",
        }
        built = build_memory_payload(store_payload, owner_id=str(context.user_id))
        item = ArceusMemoryItem(
            tenant_id=context.tenant_id,
            memory_scope=built["memory_scope"],
            title=built["title"],
            content=encode_content(built["content"], built["metadata"]),
            content_type=built["content_type"],
            source_type=built["source_type"],
            source_ids=built["source_ids"],
            evidence_ids=built["evidence_ids"],
            lifecycle_status="verified",
            trust_level="governed",
            confidence=built["confidence"],
            sensitivity=built["sensitivity"],
            content_hash=built["content_hash"],
        )
        db.add(item)
        db.flush()
        summary_item = MemoryItemResponse(**memory_response_payload(item))
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="MEMORY_SUMMARIZED",
        resource_type="memory",
        resource_id=str(summary["source_memory_ids"][0]) if summary["source_memory_ids"] else "none",
        result="completed",
        metadata={"source_count": len(summary["source_memory_ids"]), "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    response = MemorySummarizeResponse(summary_memory=summary_item, **summary)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/consolidate")
def consolidate_memory(
    payload: MemorySummarizeRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("memory.summarize")),
    db: Session = Depends(get_db),
):
    return summarize_memory(payload, request, context, db)


@router.get("/conflicts")
def list_memory_conflicts(
    request: Request,
    include_archived: bool = False,
    context: RequestContext = Depends(require_permission("memory.view")),
    db: Session = Depends(get_db),
):
    rows = _tenant_memories(db, context.tenant_id, include_archived=include_archived)
    conflicts = [MemoryConflictResponse(**item).model_dump(mode="json") for item in detect_memory_conflicts(rows)]
    return api_response(conflicts, request)


@router.post("/{memory_id}/feedback")
def record_memory_feedback(
    memory_id: UUID,
    payload: MemoryFeedbackRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("memory.store")),
    db: Session = Depends(get_db),
):
    item = _memory_or_404(db, context.tenant_id, memory_id)
    result = apply_memory_feedback(item, rating=payload.rating, confidence_delta=payload.confidence_delta)
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="MEMORY_FEEDBACK_RECORDED",
        resource_type="memory",
        resource_id=item.id,
        result=payload.rating,
        metadata={"comment": payload.comment, "correlation_id": str(context.correlation_id), **result},
    )
    db.commit()
    response = MemoryFeedbackResponse(memory_id=item.id, rating=payload.rating, event_type="MEMORY_FEEDBACK_RECORDED", **result)
    return api_response(response.model_dump(mode="json"), request)


@router.get("/{memory_id}/graph")
def project_memory_graph(
    memory_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("memory.view")),
    db: Session = Depends(get_db),
):
    item = _memory_or_404(db, context.tenant_id, memory_id)
    response = MemoryGraphProjectionResponse(**graph_projection_for_memory(item))
    return api_response(response.model_dump(mode="json"), request)


@router.get("/retention/policies")
def get_retention_policies(
    request: Request,
    context: RequestContext = Depends(require_permission("memory.view")),
):
    rows = [
        MemoryRetentionPolicyResponse(memory_type=memory_type, **policy).model_dump(mode="json")
        for memory_type, policy in sorted(RETENTION_POLICIES.items())
    ]
    return api_response(rows, request)


@router.get("/{memory_id}")
def get_memory(
    memory_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("memory.view")),
    db: Session = Depends(get_db),
):
    item = _memory_or_404(db, context.tenant_id, memory_id)
    return api_response(MemoryItemResponse(**memory_response_payload(item)).model_dump(mode="json"), request)


@router.post("/archive/{memory_id}")
def archive_memory(
    memory_id: UUID,
    payload: MemoryArchiveRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("memory.archive")),
    db: Session = Depends(get_db),
):
    item = _memory_or_404(db, context.tenant_id, memory_id)
    item.lifecycle_status = "archived"
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="MEMORY_ARCHIVED",
        resource_type="memory",
        resource_id=item.id,
        result="archived",
        metadata={"reason": payload.reason, "retain_evidence": payload.retain_evidence, "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    return api_response(MemoryLifecycleResponse(memory_id=item.id, action="archive", lifecycle_status=item.lifecycle_status, event_type="MEMORY_ARCHIVED", audit_recorded=True).model_dump(mode="json"), request)


@router.delete("/{memory_id}")
def forget_memory(
    memory_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("memory.delete")),
    db: Session = Depends(get_db),
):
    item = _memory_or_404(db, context.tenant_id, memory_id)
    allowed, reason = can_forget(item)
    if not allowed:
        raise HTTPException(status_code=409, detail={"code": "MEMORY_RETENTION_BLOCKED", "message": reason})
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="MEMORY_FORGOTTEN",
        resource_type="memory",
        resource_id=item.id,
        result="deleted",
        metadata={"reason": reason, "content_hash": item.content_hash, "correlation_id": str(context.correlation_id)},
    )
    db.delete(item)
    db.commit()
    return api_response(MemoryLifecycleResponse(memory_id=memory_id, action="forget", lifecycle_status="forgotten", event_type="MEMORY_FORGOTTEN", audit_recorded=True).model_dump(mode="json"), request)
