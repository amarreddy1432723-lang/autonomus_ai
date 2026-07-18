from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusCollaborationMessage, ArceusMemoryItem, ArceusParticipantInboxItem
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    CollaborationDecisionResponse,
    CollaborationMessageResponse,
    CompleteReviewRequest,
    CreateDecisionRequest,
    CreateReviewRequest,
    InboxItemResponse,
    MemoryItemResponse,
    MemoryProposalRequest,
    ResolveDecisionRequest,
    ReviewResponse,
    SendCollaborationMessageRequest,
)
from .service import CollaborationService


router = APIRouter(tags=["collaboration"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _message_response(message) -> CollaborationMessageResponse:
    return CollaborationMessageResponse(
        id=message.id,
        mission_id=message.mission_id,
        task_id=message.task_id,
        decision_id=message.decision_id,
        message_type=message.message_type,
        sender_participant_id=message.sender_participant_id,
        subject=message.subject,
        body=message.body,
        structured_payload=message.structured_payload or {},
        priority=message.priority,
        confidentiality=message.confidentiality,
        requires_acknowledgement=message.requires_acknowledgement,
        body_hash=message.body_hash,
        created_at=message.created_at,
        version_number=message.version_number,
    )


def _inbox_response(item) -> InboxItemResponse:
    return InboxItemResponse(
        id=item.id,
        participant_id=item.participant_id,
        message_id=item.message_id,
        delivery_status=item.delivery_status,
        relevance_score=item.relevance_score,
        delivered_at=item.delivered_at,
        acknowledged_at=item.acknowledged_at,
    )


def _decision_response(decision) -> CollaborationDecisionResponse:
    return CollaborationDecisionResponse(
        id=decision.id,
        mission_id=decision.mission_id,
        decision_key=decision.decision_key,
        title=decision.title,
        summary=decision.summary,
        selected_option=decision.selected_option or {},
        alternatives=decision.alternatives or [],
        rationale=decision.rationale,
        status=decision.status,
        version_number=decision.version_number,
    )


def _review_response(review) -> ReviewResponse:
    return ReviewResponse(
        id=review.id,
        mission_id=review.mission_id,
        task_id=review.task_id,
        review_type=review.review_type,
        target_type=review.target_type,
        target_id=review.target_id,
        target_hash=review.target_hash,
        requester_participant_id=review.requester_participant_id,
        reviewer_participant_id=review.reviewer_participant_id,
        status=review.status,
        verdict=review.verdict,
    )


def _memory_response(item) -> MemoryItemResponse:
    return MemoryItemResponse(
        id=item.id,
        memory_scope=item.memory_scope,
        scope_reference_id=item.scope_reference_id,
        title=item.title,
        content=item.content,
        lifecycle_status=item.lifecycle_status,
        trust_level=item.trust_level,
        confidence=item.confidence,
        content_hash=item.content_hash,
        created_at=item.created_at,
    )


@router.post("/api/v1/missions/{mission_id}/messages", status_code=status.HTTP_201_CREATED)
def send_message(
    mission_id: UUID,
    request_body: SendCollaborationMessageRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("collaboration.message")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    message = CollaborationService(uow).send_message(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        sender_participant_id=request_body.sender_participant_id,
        message_type=request_body.message_type,
        subject=request_body.subject,
        body=request_body.body,
        structured_payload=request_body.structured_payload,
        recipient_participant_ids=request_body.recipient_participant_ids,
        topic_keys=request_body.topic_keys,
        workflow_id=request_body.workflow_id,
        task_id=request_body.task_id,
        decision_id=request_body.decision_id,
        priority=request_body.priority,
        confidentiality=request_body.confidentiality,
        requires_acknowledgement=request_body.requires_acknowledgement,
        response_required_by=request_body.response_required_by,
        correlation_id=context.correlation_id,
        causation_id=request_body.causation_id,
    )
    uow.commit()
    return api_response(_message_response(message).model_dump(mode="json"), request)


@router.get("/api/v1/missions/{mission_id}/messages")
def list_messages(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("collaboration.view")),
    task_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusCollaborationMessage).filter(
        ArceusCollaborationMessage.tenant_id == context.tenant_id,
        ArceusCollaborationMessage.mission_id == mission_id,
    )
    if task_id:
        query = query.filter(ArceusCollaborationMessage.task_id == task_id)
    rows = query.order_by(ArceusCollaborationMessage.created_at.desc()).limit(limit).all()
    return collection_response([_message_response(item).model_dump(mode="json") for item in rows], request)


@router.get("/api/v1/participants/{participant_id}/inbox")
def list_participant_inbox(
    participant_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("collaboration.view")),
    delivery_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusParticipantInboxItem).filter(
        ArceusParticipantInboxItem.tenant_id == context.tenant_id,
        ArceusParticipantInboxItem.participant_id == participant_id,
    )
    if delivery_status:
        query = query.filter(ArceusParticipantInboxItem.delivery_status == delivery_status)
    rows = query.order_by(ArceusParticipantInboxItem.delivered_at.desc()).limit(limit).all()
    return collection_response([_inbox_response(item).model_dump(mode="json") for item in rows], request)


@router.post("/api/v1/inbox/{item_id}/acknowledge")
def acknowledge_inbox_item(
    item_id: UUID,
    request: Request,
    participant_id: UUID = Query(),
    context: RequestContext = Depends(require_permission("collaboration.message")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    item = CollaborationService(uow).acknowledge_inbox_item(tenant_id=context.tenant_id, item_id=item_id, participant_id=participant_id)
    uow.commit()
    return api_response(_inbox_response(item).model_dump(mode="json"), request)


@router.post("/api/v1/missions/{mission_id}/collaboration-decisions", status_code=status.HTTP_201_CREATED)
def create_decision(
    mission_id: UUID,
    request_body: CreateDecisionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("decision.create")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    decision = CollaborationService(uow).create_decision(tenant_id=context.tenant_id, mission_id=mission_id, **request_body.model_dump())
    uow.commit()
    return api_response(_decision_response(decision).model_dump(mode="json"), request)


@router.post("/api/v1/collaboration-decisions/{decision_id}/resolve")
def resolve_decision(
    decision_id: UUID,
    request_body: ResolveDecisionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("decision.approve")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    decision = CollaborationService(uow).resolve_decision(tenant_id=context.tenant_id, decision_id=decision_id, **request_body.model_dump())
    uow.commit()
    return api_response(_decision_response(decision).model_dump(mode="json"), request)


@router.post("/api/v1/reviews", status_code=status.HTTP_201_CREATED)
def request_review(
    request_body: CreateReviewRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("review.create")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    payload = request_body.model_dump()
    mission_id = payload.pop("mission_id")
    review = CollaborationService(uow).request_review(tenant_id=context.tenant_id, mission_id=mission_id, **payload)
    uow.commit()
    return api_response(_review_response(review).model_dump(mode="json"), request)


@router.post("/api/v1/reviews/{review_id}/complete")
def complete_review(
    review_id: UUID,
    request_body: CompleteReviewRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("review.complete")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    review = CollaborationService(uow).complete_review(tenant_id=context.tenant_id, review_id=review_id, **request_body.model_dump())
    uow.commit()
    return api_response(_review_response(review).model_dump(mode="json"), request)


@router.post("/api/v1/memory/proposals", status_code=status.HTTP_201_CREATED)
def propose_memory(
    request_body: MemoryProposalRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("memory.create")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    item = CollaborationService(uow).propose_memory(tenant_id=context.tenant_id, **request_body.model_dump())
    uow.commit()
    return api_response(_memory_response(item).model_dump(mode="json"), request)


@router.post("/api/v1/memory/{memory_id}/approve")
def approve_memory(
    memory_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("memory.approve")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    item = CollaborationService(uow).approve_memory(tenant_id=context.tenant_id, memory_id=memory_id)
    uow.commit()
    return api_response(_memory_response(item).model_dump(mode="json"), request)


@router.get("/api/v1/memory/search")
def search_memory(
    request: Request,
    context: RequestContext = Depends(require_permission("memory.view")),
    q: str = Query(default="", max_length=240),
    memory_scope: str | None = Query(default=None),
    authoritative_only: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusMemoryItem).filter(ArceusMemoryItem.tenant_id == context.tenant_id)
    if memory_scope:
        query = query.filter(ArceusMemoryItem.memory_scope == memory_scope)
    if authoritative_only:
        query = query.filter(ArceusMemoryItem.lifecycle_status == "approved")
    if q:
        query = query.filter(ArceusMemoryItem.title.ilike(f"%{q}%"))
    rows = query.order_by(ArceusMemoryItem.created_at.desc()).limit(limit).all()
    return collection_response([_memory_response(item).model_dump(mode="json") for item in rows], request)
