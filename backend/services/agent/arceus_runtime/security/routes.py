from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusPolicyEvaluation
from services.shared.arceus_core_models import (
    ArceusSecurityAsset,
    ArceusSecurityFinding,
    ArceusSecurityIncident,
    ArceusSecurityResponseAction,
)
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..audit.routes import _audit_event_response
from .api_schemas import (
    ComplianceProfileResponse,
    SecurityAssetRequest,
    SecurityAssetResponse,
    SecurityDashboardResponse,
    SecurityEvidenceRequest,
    SecurityExceptionRequest,
    SecurityFindingRequest,
    SecurityFindingResponse,
    SecurityGateRequest,
    SecurityIncidentRequest,
    SecurityIncidentResponse,
    SecurityOpsIncidentRequest,
    SecurityOpsIncidentResponse,
    SecurityEvaluateRequest,
    SecurityEvaluationResponse,
    SecurityPolicyResponse,
    SecurityResponseActionRequest,
    SecurityResponseActionResponse,
    SecurityRiskScoreResponse,
)
from .service import (
    approve_exception,
    calculate_risk_score,
    create_response_action,
    declare_security_incident,
    evaluate_security_gate,
    evaluate_security_policy,
    latest_risk_score,
    list_compliance_profiles,
    list_security_policies,
    normalize_finding,
    security_dashboard,
    store_security_evidence,
    upsert_security_asset,
)


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


@router.post("/api/v1/security/assets")
def upsert_asset(
    payload: SecurityAssetRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("security.ops.manage")),
    db: Session = Depends(get_db),
):
    item = upsert_security_asset(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response(_asset_response(item).model_dump(mode="json"), request)


@router.get("/api/v1/security/assets")
def list_assets(
    request: Request,
    context: RequestContext = Depends(require_permission("security.ops.view")),
    asset_type: str | None = Query(default=None, max_length=80),
    project_id: UUID | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(ArceusSecurityAsset).filter(ArceusSecurityAsset.tenant_id == context.tenant_id)
    if asset_type:
        query = query.filter(ArceusSecurityAsset.asset_type == asset_type)
    if project_id:
        query = query.filter(ArceusSecurityAsset.project_id == project_id)
    rows = query.order_by(ArceusSecurityAsset.last_seen_at.desc()).limit(200).all()
    return collection_response([_asset_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/api/v1/security/findings")
def ingest_finding(
    payload: SecurityFindingRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("security.finding.write")),
    db: Session = Depends(get_db),
):
    finding, created = normalize_finding(db, tenant_id=context.tenant_id, payload=payload)
    risk = calculate_risk_score(db, tenant_id=context.tenant_id, finding=finding)
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="SECURITY_FINDING_CREATED" if created else "SECURITY_FINDING_DEDUPED",
        resource_type="security_finding",
        resource_id=finding.id,
        result="recorded",
        metadata={"fingerprint": finding.fingerprint, "severity": finding.severity, "risk_level": risk.risk_level},
    )
    db.commit()
    db.refresh(finding)
    return api_response(
        {
            "finding": _finding_response(finding).model_dump(mode="json"),
            "created": created,
            "risk": _risk_response(risk).model_dump(mode="json"),
        },
        request,
    )


@router.get("/api/v1/security/findings")
def list_findings(
    request: Request,
    context: RequestContext = Depends(require_permission("security.ops.view")),
    status: str | None = Query(default=None, max_length=60),
    severity: str | None = Query(default=None, max_length=60),
    asset_id: UUID | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(ArceusSecurityFinding).filter(ArceusSecurityFinding.tenant_id == context.tenant_id)
    if status:
        query = query.filter(ArceusSecurityFinding.status == status)
    if severity:
        query = query.filter(ArceusSecurityFinding.severity == severity)
    if asset_id:
        query = query.filter(ArceusSecurityFinding.asset_id == asset_id)
    rows = query.order_by(ArceusSecurityFinding.last_detected_at.desc()).limit(200).all()
    return collection_response([_finding_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/api/v1/security/findings/{finding_id}/risk")
def recalculate_finding_risk(
    finding_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("security.evaluate")),
    db: Session = Depends(get_db),
):
    finding = db.query(ArceusSecurityFinding).filter(ArceusSecurityFinding.tenant_id == context.tenant_id, ArceusSecurityFinding.id == finding_id).first()
    if finding is None:
        raise HTTPException(status_code=404, detail={"code": "SECURITY_FINDING_NOT_FOUND", "message": "Security finding was not found."})
    risk = calculate_risk_score(db, tenant_id=context.tenant_id, finding=finding)
    db.commit()
    return api_response(_risk_response(risk).model_dump(mode="json"), request)


@router.post("/api/v1/security/gates/evaluate")
def evaluate_gate(
    payload: SecurityGateRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("security.evaluate")),
    db: Session = Depends(get_db),
):
    decision = evaluate_security_gate(db, tenant_id=context.tenant_id, payload=payload)
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action=f"SECURITY_GATE_{payload.gate_type.upper()}",
        resource_type="security_gate",
        resource_id=None,
        result=decision.decision,
        metadata=decision.model_dump(mode="json"),
    )
    db.commit()
    return api_response(decision.model_dump(mode="json"), request)


@router.post("/api/v1/security/ops/incidents")
def declare_incident(
    payload: SecurityOpsIncidentRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("security.incident.create")),
    db: Session = Depends(get_db),
):
    item = declare_security_incident(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response(_ops_incident_response(item).model_dump(mode="json"), request)


@router.post("/api/v1/security/response-actions")
def request_response_action(
    payload: SecurityResponseActionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("security.response.manage")),
    db: Session = Depends(get_db),
):
    item = create_response_action(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response(_response_action_response(item).model_dump(mode="json"), request)


@router.post("/api/v1/security/exceptions")
def create_exception(
    payload: SecurityExceptionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("security.exception.approve")),
    db: Session = Depends(get_db),
):
    item = approve_exception(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response({"id": str(item.id), "status": item.status, "finding_id": str(item.finding_id), "expires_at": item.expires_at.isoformat()}, request)


@router.post("/api/v1/security/evidence")
def add_evidence(
    payload: SecurityEvidenceRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("security.evidence.write")),
    db: Session = Depends(get_db),
):
    item = store_security_evidence(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response({"id": str(item.id), "evidence_type": item.evidence_type, "content_digest": item.content_digest, "legal_hold": item.legal_hold}, request)


@router.get("/api/v1/security/dashboard")
def get_security_dashboard(
    request: Request,
    context: RequestContext = Depends(require_permission("security.ops.view")),
    db: Session = Depends(get_db),
):
    return api_response(SecurityDashboardResponse(**security_dashboard(db, tenant_id=context.tenant_id)).model_dump(mode="json"), request)


def _asset_response(item: ArceusSecurityAsset) -> SecurityAssetResponse:
    return SecurityAssetResponse(
        id=item.id,
        asset_type=item.asset_type,
        name=item.name,
        external_reference=item.external_reference,
        criticality=item.criticality,
        internet_exposed=item.internet_exposed,
        environment_type=item.environment_type,
        data_classifications=item.data_classifications or [],
        tags=item.tags or [],
        last_seen_at=item.last_seen_at,
    )


def _finding_response(item: ArceusSecurityFinding) -> SecurityFindingResponse:
    return SecurityFindingResponse(
        id=item.id,
        asset_id=item.asset_id,
        fingerprint=item.fingerprint,
        source=item.source,
        category=item.category,
        title=item.title,
        severity=item.severity,
        status=item.status,
        affected_component=item.affected_component,
        vulnerability_ids=item.vulnerability_ids or [],
        evidence_references=item.evidence_references or [],
        last_detected_at=item.last_detected_at,
    )


def _risk_response(item) -> SecurityRiskScoreResponse:
    return SecurityRiskScoreResponse(
        finding_id=item.finding_id,
        base_severity_score=item.base_severity_score,
        exploitability_score=item.exploitability_score,
        reachability_score=item.reachability_score,
        exposure_score=item.exposure_score,
        asset_criticality_score=item.asset_criticality_score,
        privilege_impact_score=item.privilege_impact_score,
        data_impact_score=item.data_impact_score,
        threat_activity_score=item.threat_activity_score,
        compensating_control_reduction=item.compensating_control_reduction,
        total_score=item.total_score,
        risk_level=item.risk_level,
        explanation=item.explanation or {},
    )


def _ops_incident_response(item: ArceusSecurityIncident) -> SecurityOpsIncidentResponse:
    return SecurityOpsIncidentResponse(
        id=item.id,
        title=item.title,
        severity=item.severity,
        status=item.status,
        affected_asset_ids=item.affected_asset_ids or [],
        finding_ids=item.finding_ids or [],
    )


def _response_action_response(item: ArceusSecurityResponseAction) -> SecurityResponseActionResponse:
    return SecurityResponseActionResponse(
        id=item.id,
        action_type=item.action_type,
        target_id=item.target_id,
        risk_level=item.risk_level,
        automatic_allowed=item.automatic_allowed,
        approval_status=item.approval_status,
        execution_status=item.execution_status,
        trace_id=item.trace_id,
    )
