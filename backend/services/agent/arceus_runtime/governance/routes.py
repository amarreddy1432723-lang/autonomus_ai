from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusMemoryItem, ArceusModelProfile, ArceusPolicyEvaluation, ArceusProviderProfile
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..audit.routes import _audit_event_response
from .api_schemas import (
    GovernanceApprovalRequest,
    GovernanceApprovalResponse,
    GovernanceComplianceResponse,
    GovernanceDashboardResponse,
    GovernanceEvaluateRequest,
    GovernanceEvaluateResponse,
    GovernanceModelResponse,
    GovernancePolicyResponse,
)
from .service import (
    compliance_report,
    default_model_registry,
    evaluate_governance,
    governance_dashboard,
    governance_memory_payload,
    list_governance_policies,
    model_risk_profile,
)


router = APIRouter(prefix="/api/v1/governance", tags=["ai-governance-mesh"])


def _provider_map(db: Session) -> dict[str, ArceusProviderProfile]:
    return {item.provider_key: item for item in db.query(ArceusProviderProfile).all()}


def _governance_models(db: Session) -> list[dict]:
    providers = _provider_map(db)
    rows = db.query(ArceusModelProfile).order_by(ArceusModelProfile.model_key.asc()).all()
    if not rows:
        return default_model_registry()
    return [model_risk_profile(row, providers.get(row.provider_key)) for row in rows]


def _persist_memory(db: Session, context: RequestContext, *, kind: str, title: str, payload: dict, lifecycle_status: str = "verified") -> ArceusMemoryItem:
    item = governance_memory_payload(kind, payload)
    existing = (
        db.query(ArceusMemoryItem)
        .filter(
            ArceusMemoryItem.tenant_id == context.tenant_id,
            ArceusMemoryItem.memory_scope == "organization",
            ArceusMemoryItem.scope_reference_id.is_(None),
            ArceusMemoryItem.content_hash == item["content_hash"],
        )
        .first()
    )
    if existing:
        return existing
    row = ArceusMemoryItem(
        tenant_id=context.tenant_id,
        memory_scope="organization",
        title=title,
        content=json.dumps(payload, sort_keys=True, default=str),
        content_type=kind,
        source_type="governance_mesh",
        source_ids=[kind],
        evidence_ids=payload.get("evidence_ids") or [],
        lifecycle_status=lifecycle_status,
        trust_level="governed",
        confidence=0.9 if lifecycle_status == "verified" else 0.65,
        sensitivity="organization",
        content_hash=item["content_hash"],
    )
    db.add(row)
    db.flush()
    return row


@router.get("/models")
def list_models_under_governance(
    request: Request,
    context: RequestContext = Depends(require_permission("governance.model.view")),
    db: Session = Depends(get_db),
):
    rows = [GovernanceModelResponse(**item).model_dump(mode="json") for item in _governance_models(db)]
    return collection_response(rows, request)


@router.get("/policies")
def list_policies(
    request: Request,
    context: RequestContext = Depends(require_permission("governance.policy.view")),
):
    rows = [GovernancePolicyResponse(**item).model_dump(mode="json") for item in list_governance_policies()]
    return collection_response(rows, request)


@router.post("/evaluate")
def evaluate_governance_request(
    payload: GovernanceEvaluateRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("governance.evaluate")),
    db: Session = Depends(get_db),
):
    raw = payload.model_dump(mode="json")
    result = evaluate_governance(raw)
    resource = {
        "object_type": payload.object_type,
        "object_id": payload.object_id,
        "risk_level": result["risk_level"],
        "risk_score": result["risk_score"],
        "required_approvals": result["required_approvals"],
        "controls": result["controls"],
        "compliance": result["compliance"],
        "privacy": result["privacy"],
        "content_safety": result["content_safety"],
        "supply_chain": result["supply_chain"],
        "monitoring": result["monitoring"],
    }
    evaluation = ArceusPolicyEvaluation(
        tenant_id=context.tenant_id,
        mission_id=payload.mission_id,
        task_id=payload.task_id,
        policy_key=result["policy_key"],
        subject={
            "actor_id": str(context.user_id),
            "actor_type": payload.actor_type,
            "role_keys": sorted(context.role_keys),
            "model_key": payload.model_key,
            "provider_key": payload.provider_key,
        },
        action=payload.action,
        resource=resource,
        decision=result["decision"],
        reason=result["reason"],
    )
    db.add(evaluation)
    db.flush()
    result["evaluation_id"] = evaluation.id
    _persist_memory(
        db,
        context,
        kind="governance_evaluation",
        title=f"Governance evaluation for {payload.action}",
        payload={**raw, **result, "evidence_ids": payload.evidence_ids},
        lifecycle_status="verified" if result["decision"] == "allow" else "proposed",
    )
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="GOVERNANCE_POLICY_EVALUATED",
        resource_type="policy_evaluation",
        resource_id=evaluation.id,
        result=result["decision"],
        metadata={
            "policy_key": result["policy_key"],
            "risk_level": result["risk_level"],
            "risk_score": result["risk_score"],
            "events": result["events"],
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    return api_response(GovernanceEvaluateResponse(**result).model_dump(mode="json"), request)


@router.post("/approve")
def approve_governance_item(
    payload: GovernanceApprovalRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("governance.approve")),
    db: Session = Depends(get_db),
):
    event_type = "GOVERNANCE_APPROVED" if payload.decision == "approved" else ("GOVERNANCE_REJECTED" if payload.decision == "rejected" else "GOVERNANCE_CHANGES_REQUESTED")
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action=event_type,
        resource_type=payload.object_type,
        resource_id=payload.object_id,
        result=payload.decision,
        metadata={
            "evaluation_id": str(payload.evaluation_id) if payload.evaluation_id else None,
            "approver_role": payload.approver_role,
            "rationale": payload.rationale,
            "evidence_ids": payload.evidence_ids,
            "correlation_id": str(context.correlation_id),
        },
    )
    _persist_memory(
        db,
        context,
        kind="governance_approval",
        title=f"Governance {payload.decision} for {payload.object_type}",
        payload=payload.model_dump(mode="json"),
        lifecycle_status="approved" if payload.decision == "approved" else "proposed",
    )
    db.commit()
    response = GovernanceApprovalResponse(
        object_type=payload.object_type,
        object_id=payload.object_id,
        decision=payload.decision,
        event_type=event_type,
        audit_recorded=True,
        approved_at=datetime.now(timezone.utc),
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/compliance")
def get_compliance_status(
    request: Request,
    frameworks: list[str] = Query(default=[]),
    context: RequestContext = Depends(require_permission("governance.compliance.view")),
    db: Session = Depends(get_db),
):
    evaluations = (
        db.query(ArceusPolicyEvaluation)
        .filter(ArceusPolicyEvaluation.tenant_id == context.tenant_id, ArceusPolicyEvaluation.policy_key.like("governance.%"))
        .order_by(ArceusPolicyEvaluation.created_at.desc())
        .limit(50)
        .all()
    )
    response = GovernanceComplianceResponse(**compliance_report(frameworks, evaluations))
    return api_response(response.model_dump(mode="json"), request)


@router.get("/audit")
def list_governance_audit(
    request: Request,
    action: str | None = Query(default=None, max_length=160),
    result: str | None = Query(default=None, max_length=60),
    limit: int = Query(default=100, ge=1, le=500),
    context: RequestContext = Depends(require_permission("governance.audit.view")),
    db: Session = Depends(get_db),
):
    events = SqlAlchemyUnitOfWork(db).audit.list(
        tenant_id=context.tenant_id,
        action=action,
        result=result,
        limit=limit,
    )
    events = [event for event in events if event.action.startswith("GOVERNANCE_") or event.action in {"PROMPT_ATTACK_DETECTED", "SUPPLY_CHAIN_VALIDATED"}]
    return collection_response([_audit_event_response(event).model_dump(mode="json") for event in events], request)


@router.get("/dashboard")
def get_governance_dashboard(
    request: Request,
    context: RequestContext = Depends(require_permission("governance.view")),
    db: Session = Depends(get_db),
):
    evaluations = (
        db.query(ArceusPolicyEvaluation)
        .filter(ArceusPolicyEvaluation.tenant_id == context.tenant_id, ArceusPolicyEvaluation.policy_key.like("governance.%"))
        .order_by(ArceusPolicyEvaluation.created_at.desc())
        .limit(100)
        .all()
    )
    audit_events = SqlAlchemyUnitOfWork(db).audit.list(tenant_id=context.tenant_id, limit=100)
    response = GovernanceDashboardResponse(**governance_dashboard(_governance_models(db), evaluations, audit_events))
    return api_response(response.model_dump(mode="json"), request)
