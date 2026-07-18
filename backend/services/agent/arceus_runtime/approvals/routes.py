from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_idempotency_key, require_permission
from ..api.responses import api_response, collection_response
from ..application.idempotency import calculate_request_hash
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import ApprovalDetailResponse, ApprovalSummaryResponse, ApprovalVoteRequest, ApprovalVoteResponse
from .service import required_human_votes, resolve_approval_if_ready, validate_vote_preconditions


router = APIRouter(prefix="/api/v1/approvals", tags=["approvals"])


def _summary(uow: SqlAlchemyUnitOfWork, approval) -> ApprovalSummaryResponse:
    votes = uow.approvals.votes(tenant_id=approval.tenant_id, approval_id=approval.id)
    return ApprovalSummaryResponse(
        id=approval.id,
        mission_id=approval.mission_id,
        approval_type=approval.approval_type,
        subject_type=approval.subject_type,
        subject_hash=approval.subject_hash,
        proposed_action=approval.proposed_action,
        risk_level=approval.risk_level,
        status=approval.status,
        required_human_votes=required_human_votes(approval),
        human_approvals=len([vote for vote in votes if vote.vote == "approve" and vote.is_human_vote]),
        expires_at=approval.expires_at,
        created_at=approval.created_at,
    )


@router.get("")
def list_approvals(
    request: Request,
    context: RequestContext = Depends(require_permission("approval.view")),
    mission_id: UUID | None = Query(default=None),
    approval_status: str | None = Query(default="pending", alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = SqlAlchemyUnitOfWork(db)
    approvals = uow.approvals.list(tenant_id=context.tenant_id, mission_id=mission_id, status=approval_status, limit=limit)
    return collection_response([_summary(uow, approval).model_dump(mode="json") for approval in approvals], request)


@router.get("/{approval_id}")
def get_approval(
    approval_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("approval.view")),
    db: Session = Depends(get_db),
):
    uow = SqlAlchemyUnitOfWork(db)
    approval = uow.approvals.get(tenant_id=context.tenant_id, approval_id=approval_id)
    summary = _summary(uow, approval).model_dump(mode="json")
    votes = uow.approvals.votes(tenant_id=context.tenant_id, approval_id=approval.id)
    summary["quorum_policy"] = approval.quorum_policy or {}
    summary["votes"] = [
        {
            "id": str(vote.id),
            "vote": vote.vote,
            "comment": vote.comment,
            "is_human_vote": vote.is_human_vote,
            "voter_user_id": str(vote.voter_user_id) if vote.voter_user_id else None,
            "created_at": vote.created_at.isoformat(),
        }
        for vote in votes
    ]
    return api_response(ApprovalDetailResponse(**summary).model_dump(mode="json"), request)


def _vote(
    *,
    approval_id: UUID,
    vote: str,
    request_body: ApprovalVoteRequest,
    request: Request,
    context: RequestContext,
    idempotency_key: str,
    db: Session,
):
    payload = {
        "approval_id": str(approval_id),
        "vote": vote,
        "expected_mission_version": request_body.expected_mission_version,
        "subject_hash": request_body.subject_hash,
        "rationale": request_body.rationale,
    }
    scope = f"approval.{vote}"
    uow = SqlAlchemyUnitOfWork(db)
    existing = uow.idempotency.get(tenant_id=context.tenant_id, scope=scope, idempotency_key=idempotency_key)
    request_hash = calculate_request_hash(scope, payload)
    if existing is not None:
        return api_response(uow.idempotency.resolve_existing(existing, request_hash), request)

    approval = uow.approvals.get(tenant_id=context.tenant_id, approval_id=approval_id)
    mission = uow.missions.get(tenant_id=context.tenant_id, mission_id=approval.mission_id)
    uow.missions.require_version(mission, request_body.expected_mission_version)
    validate_vote_preconditions(approval, subject_hash=request_body.subject_hash)
    uow.approvals.add_vote(
        tenant_id=context.tenant_id,
        approval_id=approval.id,
        voter_user_id=context.user_id,
        vote=vote,
        comment=request_body.rationale,
        is_human_vote=True,
    )
    votes = uow.approvals.votes(tenant_id=context.tenant_id, approval_id=approval.id)
    resolution = resolve_approval_if_ready(approval, mission, votes)
    if resolution == "approved" and approval.approval_type == "mission_plan":
        uow.workflows.activate_for_mission(tenant_id=context.tenant_id, mission_id=mission.id)
    event = uow.events.append(
        tenant_id=context.tenant_id,
        aggregate_type="mission",
        aggregate_id=mission.id,
        aggregate_version=mission.version_number,
        event_type="APPROVAL_RESOLVED" if resolution in {"approved", "rejected"} else "APPROVAL_VOTED",
        actor_type="human",
        actor_id=str(context.user_id),
        payload={
            "approval_id": str(approval.id),
            "vote": vote,
            "approval_status": approval.status,
            "mission_status": mission.status,
        },
        correlation_id=context.correlation_id,
        idempotency_key=idempotency_key,
    )
    uow.outbox.add_from_event(event, topic="arceus.approval.resolved" if resolution in {"approved", "rejected"} else "arceus.approval.requested")
    response = ApprovalVoteResponse(
        approval_id=approval.id,
        mission_id=mission.id,
        status=approval.status,
        mission_status=mission.status,
        mission_version=mission.version_number,
        vote=vote,
    )
    uow.idempotency.complete(
        tenant_id=context.tenant_id,
        scope=scope,
        idempotency_key=idempotency_key,
        request_hash=request_hash,
        response_payload=response.model_dump(mode="json"),
    )
    uow.audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action=scope,
        resource_type="approval",
        resource_id=approval.id,
        result="success",
        metadata={"mission_id": str(mission.id), "approval_status": approval.status},
    )
    uow.commit()
    return api_response(response.model_dump(mode="json"), request)


@router.post("/{approval_id}/approve", status_code=status.HTTP_202_ACCEPTED)
def approve(
    approval_id: UUID,
    request_body: ApprovalVoteRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("approval.vote")),
    idempotency_key: str = Depends(require_idempotency_key),
    db: Session = Depends(get_db),
):
    return _vote(approval_id=approval_id, vote="approve", request_body=request_body, request=request, context=context, idempotency_key=idempotency_key, db=db)


@router.post("/{approval_id}/reject", status_code=status.HTTP_202_ACCEPTED)
def reject(
    approval_id: UUID,
    request_body: ApprovalVoteRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("approval.vote")),
    idempotency_key: str = Depends(require_idempotency_key),
    db: Session = Depends(get_db),
):
    return _vote(approval_id=approval_id, vote="reject", request_body=request_body, request=request, context=context, idempotency_key=idempotency_key, db=db)
