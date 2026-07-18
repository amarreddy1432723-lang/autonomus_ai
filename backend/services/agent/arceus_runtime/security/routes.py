from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusPolicyEvaluation
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..audit.routes import _audit_event_response
from .api_schemas import (
    ComplianceProfileResponse,
    SecurityEvaluateRequest,
    SecurityEvaluationResponse,
    SecurityIncidentRequest,
    SecurityIncidentResponse,
    SecurityPolicyResponse,
)
from .service import evaluate_security_policy, list_compliance_profiles, list_security_policies


router = APIRouter(tags=["security-governance"])


def _policy_response(policy) -> SecurityPolicyResponse:
    return SecurityPolicyResponse(
        policy_key=policy.policy_key,
        name=policy.name,
        description=policy.description,
        severity=policy.severity,
        protected_actions=list(policy.protected_actions),
    )


def _evaluation_response(item: ArceusPolicyEvaluation, *, obligations: list[str] | None = None) -> SecurityEvaluationResponse:
    return SecurityEvaluationResponse(
        id=item.id,
        mission_id=item.mission_id,
        task_id=item.task_id,
        policy_key=item.policy_key,
        subject=item.subject or {},
        action=item.action,
        resource=item.resource or {},
        decision=item.decision,
        reason=item.reason,
        obligations=obligations or (item.resource or {}).get("obligations") or [],
        created_at=item.created_at,
    )


@router.get("/api/v1/security/policies")
def get_security_policies(
    request: Request,
    context: RequestContext = Depends(require_permission("security.policy.view")),
):
    return collection_response([_policy_response(policy).model_dump(mode="json") for policy in list_security_policies()], request)


@router.post("/api/v1/security/evaluate")
def evaluate_security_request(
    payload: SecurityEvaluateRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("security.evaluate")),
    db: Session = Depends(get_db),
):
    subject = {
        "identity_id": str(context.user_id),
        "actor_id": str(context.user_id),
        "identity_type": "human",
        "role_keys": sorted(context.role_keys),
        **payload.subject,
    }
    decision = evaluate_security_policy(
        subject=subject,
        action=payload.action,
        resource=payload.resource,
        environment=payload.environment,
        risk_level=payload.risk_level,
        policy_key=payload.policy_key,
    )
    resource = {**payload.resource, "environment": payload.environment, "risk_level": payload.risk_level, "obligations": list(decision.obligations)}
    evaluation = ArceusPolicyEvaluation(
        tenant_id=context.tenant_id,
        mission_id=payload.mission_id,
        task_id=payload.task_id,
        policy_key=decision.policy_key,
        subject=subject,
        action=payload.action,
        resource=resource,
        decision=decision.decision,
        reason=decision.reason,
    )
    db.add(evaluation)
    db.flush()
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="SECURITY_POLICY_EVALUATED",
        resource_type="policy_evaluation",
        resource_id=evaluation.id,
        result=decision.decision,
        metadata={
            "policy_key": decision.policy_key,
            "mission_id": str(payload.mission_id) if payload.mission_id else None,
            "task_id": str(payload.task_id) if payload.task_id else None,
            "reason": decision.reason,
            "obligations": list(decision.obligations),
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    db.refresh(evaluation)
    return api_response(_evaluation_response(evaluation, obligations=list(decision.obligations)).model_dump(mode="json"), request)


@router.get("/api/v1/security/audit")
def list_security_audit(
    request: Request,
    context: RequestContext = Depends(require_permission("security.audit.view")),
    action: str | None = Query(default=None, max_length=160),
    result: str | None = Query(default=None, max_length=60),
    resource_type: str | None = Query(default=None, max_length=120),
    resource_id: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    events = SqlAlchemyUnitOfWork(db).audit.list(
        tenant_id=context.tenant_id,
        action=action,
        result=result,
        resource_type=resource_type,
        resource_id=resource_id,
        limit=limit,
    )
    return collection_response([_audit_event_response(event).model_dump(mode="json") for event in events], request)


@router.post("/api/v1/security/incidents")
def create_security_incident(
    payload: SecurityIncidentRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("security.incident.create")),
    db: Session = Depends(get_db),
):
    result = "blocked" if payload.severity in {"high", "critical"} else "recorded"
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action=f"SECURITY_INCIDENT_{payload.incident_type.upper()}",
        resource_type=payload.resource_type,
        resource_id=payload.resource_id or payload.mission_id or payload.task_id,
        result=result,
        metadata={
            "mission_id": str(payload.mission_id) if payload.mission_id else None,
            "task_id": str(payload.task_id) if payload.task_id else None,
            "severity": payload.severity,
            "summary": payload.summary,
            "evidence": payload.evidence,
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    response = SecurityIncidentResponse(
        incident_type=payload.incident_type,
        severity=payload.severity,
        result=result,
        summary=payload.summary,
        audit_recorded=True,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/api/v1/security/compliance")
def get_security_compliance(
    request: Request,
    context: RequestContext = Depends(require_permission("security.compliance.view")),
):
    profiles = [ComplianceProfileResponse(**profile).model_dump(mode="json") for profile in list_compliance_profiles()]
    return collection_response(profiles, request)
