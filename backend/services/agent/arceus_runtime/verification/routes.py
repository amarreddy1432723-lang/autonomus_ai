from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusApproval,
    ArceusCompletionCertificate,
    ArceusEvidence,
    ArceusMissionSuccessCriterion,
    ArceusQualityGate,
    ArceusReview,
    ArceusTrustScore,
    ArceusVerificationPlan,
)
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    CompletionApprovalRequest,
    CompletionCertificateResponse,
    CreateEvidenceRequest,
    CreateVerificationRequest,
    QualityGateResponse,
    RunQualityGatesRequest,
    TrustScoreResponse,
    VerificationPlanResponse,
)
from .service import (
    build_completion_certificate,
    build_default_quality_gate,
    calculate_trust_score,
    evaluate_completion,
    evidence_content_hash,
    gate_passes_with_evidence,
)


router = APIRouter(tags=["verification-governance"])


def _plan_response(plan: ArceusVerificationPlan) -> VerificationPlanResponse:
    return VerificationPlanResponse(
        id=plan.id,
        mission_id=plan.mission_id,
        workflow_id=plan.workflow_id,
        task_id=plan.task_id,
        target_type=plan.target_type,
        target_id=plan.target_id,
        criteria=plan.criteria or [],
        methods=plan.methods or [],
        evidence_required=plan.evidence_required or [],
        reviewers=[str(item) for item in (plan.reviewers or [])],
        environment=plan.environment,
        blocking=plan.blocking,
        timeout_seconds=plan.timeout_seconds,
        status=plan.status,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        version_number=plan.version_number,
    )


def _gate_response(gate: ArceusQualityGate) -> QualityGateResponse:
    return QualityGateResponse(
        id=gate.id,
        mission_id=gate.mission_id,
        verification_plan_id=gate.verification_plan_id,
        gate_key=gate.gate_key,
        name=gate.name,
        category=gate.category,
        gate_type=gate.gate_type,
        required=gate.required,
        verifier=gate.verifier,
        timeout_seconds=gate.timeout_seconds,
        status=gate.status,
        result=gate.result or {},
        evidence_ids=[str(item) for item in (gate.evidence_ids or [])],
        last_run_at=gate.last_run_at,
        created_at=gate.created_at,
        updated_at=gate.updated_at,
        version_number=gate.version_number,
    )


def _trust_response(score: ArceusTrustScore) -> TrustScoreResponse:
    return TrustScoreResponse(
        id=score.id,
        mission_id=score.mission_id,
        target_type=score.target_type,
        target_id=score.target_id,
        trust_level=score.trust_level,
        score=score.score,
        confidence=score.confidence,
        contributors=score.contributors or {},
        calculated_at=score.calculated_at,
    )


def _certificate_response(certificate: ArceusCompletionCertificate) -> CompletionCertificateResponse:
    return CompletionCertificateResponse(
        id=certificate.id,
        mission_id=certificate.mission_id,
        certificate_version=certificate.certificate_version,
        status=certificate.status,
        completed_requirements=certificate.completed_requirements or [],
        evidence_ids=[str(item) for item in (certificate.evidence_ids or [])],
        gate_ids=[str(item) for item in (certificate.gate_ids or [])],
        approval_ids=[str(item) for item in (certificate.approval_ids or [])],
        trust_score_id=certificate.trust_score_id,
        blockers=certificate.blockers or [],
        certificate_hash=certificate.certificate_hash,
        signature=certificate.signature,
        signed_at=certificate.signed_at,
        immutable=certificate.immutable,
        created_at=certificate.created_at,
        updated_at=certificate.updated_at,
        version_number=certificate.version_number,
    )


def _mission_evidence(db: Session, tenant_id: UUID, mission_id: UUID) -> list[ArceusEvidence]:
    return db.query(ArceusEvidence).filter(ArceusEvidence.tenant_id == tenant_id, ArceusEvidence.mission_id == mission_id).all()


def _mission_gates(db: Session, tenant_id: UUID, mission_id: UUID) -> list[ArceusQualityGate]:
    return db.query(ArceusQualityGate).filter(ArceusQualityGate.tenant_id == tenant_id, ArceusQualityGate.mission_id == mission_id).all()


def _mission_reviews(db: Session, tenant_id: UUID, mission_id: UUID) -> list[ArceusReview]:
    return db.query(ArceusReview).filter(ArceusReview.tenant_id == tenant_id, ArceusReview.mission_id == mission_id).all()


def _mission_approvals(db: Session, tenant_id: UUID, mission_id: UUID) -> list[ArceusApproval]:
    return db.query(ArceusApproval).filter(ArceusApproval.tenant_id == tenant_id, ArceusApproval.mission_id == mission_id).all()


@router.post("/api/v1/verifications")
def create_verification(
    payload: CreateVerificationRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("verification.manage")),
    db: Session = Depends(get_db),
):
    uow = SqlAlchemyUnitOfWork(db)
    mission = uow.missions.get(tenant_id=context.tenant_id, mission_id=payload.mission_id)
    target_id = payload.target_id or payload.task_id or mission.id
    methods = payload.methods or [str(item.get("verification_method") or "manual_review") for item in payload.criteria] or ["manual_review"]
    evidence_required = payload.evidence_required or list(methods)
    plan = ArceusVerificationPlan(
        tenant_id=context.tenant_id,
        mission_id=mission.id,
        workflow_id=payload.workflow_id,
        task_id=payload.task_id,
        target_type=payload.target_type,
        target_id=target_id,
        criteria=payload.criteria,
        methods=methods,
        evidence_required=evidence_required,
        reviewers=[str(item) for item in payload.reviewers],
        environment=payload.environment,
        blocking=payload.blocking,
        timeout_seconds=payload.timeout_seconds,
        status="planned",
    )
    db.add(plan)
    db.flush()
    for method, evidence_type in zip(methods, evidence_required, strict=False):
        db.add(build_default_quality_gate(plan=plan, method=method, evidence_type=evidence_type))
    db.commit()
    db.refresh(plan)
    return api_response(_plan_response(plan).model_dump(mode="json"), request)


@router.get("/api/v1/verifications/{verification_id}")
def get_verification(
    verification_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("verification.view")),
    db: Session = Depends(get_db),
):
    plan = db.query(ArceusVerificationPlan).filter(ArceusVerificationPlan.tenant_id == context.tenant_id, ArceusVerificationPlan.id == verification_id).first()
    if plan is None:
        raise HTTPException(status_code=404, detail="Verification plan not found.")
    return api_response(_plan_response(plan).model_dump(mode="json"), request)


@router.post("/api/v1/evidence")
def create_evidence(
    payload: CreateEvidenceRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("evidence.collect")),
    db: Session = Depends(get_db),
):
    SqlAlchemyUnitOfWork(db).missions.get(tenant_id=context.tenant_id, mission_id=payload.mission_id)
    content_hash = evidence_content_hash(
        mission_id=payload.mission_id,
        evidence_type=payload.evidence_type,
        summary=payload.summary,
        payload=payload.payload,
    )
    evidence = ArceusEvidence(
        tenant_id=context.tenant_id,
        mission_id=payload.mission_id,
        workflow_id=payload.workflow_id,
        task_id=payload.task_id,
        artifact_id=payload.artifact_id,
        evidence_type=payload.evidence_type,
        status="validated" if payload.trust_level in {"tool_verified", "independent_review", "human_approved", "production_observed"} else "collected",
        summary=payload.summary,
        payload=payload.payload,
        verification_method=payload.verification_method,
        content_hash=content_hash,
        trust_level=payload.trust_level,
        immutable=True,
        collected_by_member_id=payload.collected_by_member_id,
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)
    from ..evidence.routes import _evidence_response

    return api_response(_evidence_response(evidence).model_dump(mode="json"), request)


@router.post("/api/v1/quality-gates/run")
def run_quality_gates(
    payload: RunQualityGatesRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("verification.manage")),
    db: Session = Depends(get_db),
):
    SqlAlchemyUnitOfWork(db).missions.get(tenant_id=context.tenant_id, mission_id=payload.mission_id)
    query = db.query(ArceusQualityGate).filter(ArceusQualityGate.tenant_id == context.tenant_id, ArceusQualityGate.mission_id == payload.mission_id)
    if payload.gate_keys:
        query = query.filter(ArceusQualityGate.gate_key.in_(payload.gate_keys))
    gates = query.order_by(ArceusQualityGate.created_at.asc()).all()
    evidence = _mission_evidence(db, context.tenant_id, payload.mission_id)
    if payload.evidence_ids:
        evidence = [item for item in evidence if item.id in payload.evidence_ids]
    for gate in gates:
        passed, result = gate_passes_with_evidence(gate, evidence)
        gate.status = "passed" if passed else "failed"
        gate.result = {**(gate.result or {}), **result}
        gate.evidence_ids = result.get("matched_evidence_ids") or []
        gate.last_run_at = datetime.now(timezone.utc)
        gate.version_number = int(gate.version_number or 1) + 1
    db.commit()
    return collection_response([_gate_response(gate).model_dump(mode="json") for gate in gates], request)


@router.get("/api/v1/completion/{mission_id}")
def get_completion(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("completion.view")),
    db: Session = Depends(get_db),
):
    mission = SqlAlchemyUnitOfWork(db).missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    criteria = db.query(ArceusMissionSuccessCriterion).filter(
        ArceusMissionSuccessCriterion.tenant_id == context.tenant_id,
        ArceusMissionSuccessCriterion.mission_id == mission_id,
    ).all()
    evidence = _mission_evidence(db, context.tenant_id, mission_id)
    gates = _mission_gates(db, context.tenant_id, mission_id)
    reviews = _mission_reviews(db, context.tenant_id, mission_id)
    approvals = _mission_approvals(db, context.tenant_id, mission_id)
    trust_score = calculate_trust_score(mission_id=mission_id, target_id=mission_id, evidence=evidence, gates=gates, reviews=reviews, approvals=approvals)
    trust_score.tenant_id = context.tenant_id
    db.add(trust_score)
    db.flush()
    evaluation = evaluate_completion(mission=mission, criteria=criteria, evidence=evidence, gates=gates, reviews=reviews, approvals=approvals)
    latest_version = (
        db.query(ArceusCompletionCertificate)
        .filter(ArceusCompletionCertificate.tenant_id == context.tenant_id, ArceusCompletionCertificate.mission_id == mission_id)
        .count()
        + 1
    )
    certificate = build_completion_certificate(
        tenant_id=context.tenant_id,
        mission=mission,
        evaluation=evaluation,
        trust_score=trust_score,
        version=latest_version,
    )
    db.add(certificate)
    db.commit()
    db.refresh(certificate)
    return api_response(
        _certificate_response(certificate).model_dump(mode="json"),
        request,
        trust_score=_trust_response(trust_score).model_dump(mode="json"),
    )


@router.post("/api/v1/completion/approve")
def approve_completion(
    payload: CompletionApprovalRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("completion.approve")),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusCompletionCertificate).filter(
        ArceusCompletionCertificate.tenant_id == context.tenant_id,
        ArceusCompletionCertificate.mission_id == payload.mission_id,
    )
    if payload.certificate_id:
        query = query.filter(ArceusCompletionCertificate.id == payload.certificate_id)
    certificate = query.order_by(ArceusCompletionCertificate.certificate_version.desc()).first()
    if certificate is None:
        raise HTTPException(status_code=404, detail="Completion certificate not found.")
    if certificate.status != "certified":
        raise HTTPException(status_code=409, detail={"code": "COMPLETION_BLOCKED", "blockers": certificate.blockers or []})
    if payload.human_approved:
        certificate.status = "approved"
        certificate.version_number = int(certificate.version_number or 1) + 1
    db.commit()
    db.refresh(certificate)
    return api_response(_certificate_response(certificate).model_dump(mode="json"), request)
