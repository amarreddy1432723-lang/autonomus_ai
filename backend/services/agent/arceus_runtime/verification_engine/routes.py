from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusEvidence,
    ArceusEvidenceProducerRun,
    ArceusMission,
    ArceusReleaseReadinessGate,
    ArceusTask,
    ArceusVerificationFinding,
    ArceusVerificationRun,
    ArceusVerificationWorkerJob,
)
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..compiler.utils import stable_hash
from .api_schemas import (
    EvidenceProducerRequest,
    MissionControlReleaseGateRequest,
    MissionControlReleaseGateResponse,
    OutputContractValidationRequest,
    ReleaseReadinessRequest,
    ReviewRequest,
    VerificationPlanRequest,
    VerificationRunRequest,
    VerificationTestDiscoveryRequest,
)
from .service import (
    check_registry,
    discover_tests,
    evaluate_release_readiness,
    execute_worker_job_payload,
    normalize_evidence_producer_output,
    perform_autonomous_review,
    plan_verification,
    run_verification,
    validate_output_contract,
    worker_jobs_for_plan,
)


router = APIRouter(prefix="/api/v1/verification-engine", tags=["verification-engine"])


def _mission_exists(db: Session, context: RequestContext, mission_id: UUID) -> bool:
    return (
        db.query(ArceusMission.id)
        .filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.id == mission_id)
        .first()
        is not None
    )


def _run_status(status: str) -> str:
    return "passed" if status in {"passed", "warning"} else "failed" if status in {"failed", "blocked"} else "cancelled"


def _content_hash(payload: dict) -> str:
    return stable_hash(payload)


def _persist_evidence(db: Session, context: RequestContext, payload: EvidenceProducerRequest):
    normalized = normalize_evidence_producer_output(payload)
    evidence_payload = normalized.evidence.model_dump(mode="json")
    evidence = ArceusEvidence(
        tenant_id=context.tenant_id,
        mission_id=payload.mission_id,
        task_id=payload.task_id,
        evidence_type=normalized.evidence.evidence_type,
        status="collected" if normalized.normalized_status == "cancelled" else "validated",
        summary=normalized.summary,
        payload=evidence_payload["payload"],
        verification_method=normalized.evidence.verification_method,
        content_hash=_content_hash({"mission_id": str(payload.mission_id), "evidence": evidence_payload}),
        trust_level=normalized.evidence.trust_level,
        immutable=True,
    )
    db.add(evidence)
    db.flush()
    producer = ArceusEvidenceProducerRun(
        tenant_id=context.tenant_id,
        mission_id=payload.mission_id,
        task_id=payload.task_id,
        worker_job_id=payload.worker_job_id,
        producer_key=payload.producer_key,
        check_id=payload.check_id,
        status=payload.status,
        command=payload.command,
        exit_code=payload.exit_code,
        duration_ms=payload.duration_ms,
        output_summary=normalized.summary,
        artifacts=payload.artifacts,
        payload={**payload.payload, "output_excerpt": payload.output[:4000]},
        evidence_id=evidence.id,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(producer)
    if payload.worker_job_id:
        job = (
            db.query(ArceusVerificationWorkerJob)
            .filter(ArceusVerificationWorkerJob.tenant_id == context.tenant_id, ArceusVerificationWorkerJob.id == payload.worker_job_id)
            .first()
        )
        if job:
            job.status = "succeeded" if payload.status == "succeeded" else "failed" if payload.status == "failed" else "cancelled"
            job.evidence_id = evidence.id
            job.attempts = int(job.attempts or 0) + 1
            job.last_error = {} if payload.status == "succeeded" else {"summary": normalized.summary, "exit_code": payload.exit_code}
    db.commit()
    db.refresh(evidence)
    db.refresh(producer)
    return normalized, evidence, producer


def _worker_job_response(job: ArceusVerificationWorkerJob) -> dict:
    return {
        "job_id": str(job.id),
        "mission_id": str(job.mission_id),
        "task_id": str(job.task_id) if job.task_id else None,
        "plan_id": job.plan_id,
        "check_id": job.check_id,
        "check_definition_id": job.check_definition_id,
        "category": job.category,
        "evidence_producer": job.evidence_producer,
        "mandatory": job.mandatory,
        "blocking": job.blocking,
        "status": job.status,
        "inputs": job.inputs or {},
        "depends_on": job.depends_on or [],
        "timeout_seconds": job.timeout_seconds,
        "attempts": job.attempts,
        "evidence_id": str(job.evidence_id) if job.evidence_id else None,
        "durable_task_id": str(job.durable_task_id) if job.durable_task_id else None,
    }


def _hydrate_evidence(db: Session, context: RequestContext, mission_id: UUID, task_id: UUID | None = None):
    query = db.query(ArceusEvidence).filter(
        ArceusEvidence.tenant_id == context.tenant_id,
        ArceusEvidence.mission_id == mission_id,
        ArceusEvidence.status.in_(["collected", "validated", "trusted", "verified"]),
    )
    if task_id:
        query = query.filter((ArceusEvidence.task_id == task_id) | (ArceusEvidence.task_id.is_(None)))
    rows = query.order_by(ArceusEvidence.created_at.asc()).limit(1000).all()
    return [
        {
            "evidence_id": str(row.id),
            "evidence_type": row.evidence_type,
            "status": row.status,
            "trust_level": row.trust_level,
            "summary": row.summary,
            "payload": row.payload or {},
            "verification_method": row.verification_method,
        }
        for row in rows
    ]


def _claim_jobs(db: Session, context: RequestContext, *, mission_id: UUID | None = None, limit: int = 1) -> list[ArceusVerificationWorkerJob]:
    query = db.query(ArceusVerificationWorkerJob).filter(
        ArceusVerificationWorkerJob.tenant_id == context.tenant_id,
        ArceusVerificationWorkerJob.status == "queued",
    )
    if mission_id:
        query = query.filter(ArceusVerificationWorkerJob.mission_id == mission_id)
    jobs = query.order_by(ArceusVerificationWorkerJob.blocking.desc(), ArceusVerificationWorkerJob.created_at.asc()).limit(limit).all()
    for job in jobs:
        job.status = "leased"
    db.commit()
    for job in jobs:
        db.refresh(job)
    return jobs


@router.get("/checks")
def list_verification_checks(
    request: Request,
    _context: RequestContext = Depends(require_permission("verification.view")),
):
    return api_response({"checks": [item.model_dump(mode="json") for item in check_registry()]}, request)


@router.post("/plan")
def plan_quality_verification(
    payload: VerificationPlanRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("verification.manage")),
    db: Session = Depends(get_db),
):
    response = plan_verification(payload)
    persisted_jobs: list[dict] = []
    if _mission_exists(db, context, payload.mission_id):
        for job in worker_jobs_for_plan(response):
            idempotency_key = stable_hash({"mission_id": str(payload.mission_id), "plan_id": job.plan_id, "check_id": job.check_id})
            existing = (
                db.query(ArceusVerificationWorkerJob)
                .filter(ArceusVerificationWorkerJob.tenant_id == context.tenant_id, ArceusVerificationWorkerJob.idempotency_key == idempotency_key)
                .first()
            )
            if existing is not None:
                persisted_jobs.append(_worker_job_response(existing))
                continue
            task_key = f"verification:{job.plan_id}:{job.check_id}"
            durable_task = (
                db.query(ArceusTask)
                .filter(ArceusTask.tenant_id == context.tenant_id, ArceusTask.mission_id == payload.mission_id, ArceusTask.task_key == task_key)
                .first()
            )
            if durable_task is None:
                durable_task = ArceusTask(
                    tenant_id=context.tenant_id,
                    mission_id=payload.mission_id,
                    task_key=task_key,
                    title=f"Run verification: {job.check_definition_id}",
                    task_type="verification",
                    status="ready",
                    input_contract={
                        "plan_id": job.plan_id,
                        "check_id": job.check_id,
                        "check_definition_id": job.check_definition_id,
                        "evidence_producer": job.evidence_producer,
                        "inputs": job.inputs,
                    },
                    output_contract={"required": ["evidence_id", "status", "summary"]},
                    acceptance_criteria=[
                        "worker reports evidence through verification evidence producer endpoint",
                        "blocking failures remain visible in release readiness",
                    ],
                )
                db.add(durable_task)
                db.flush()
            row = ArceusVerificationWorkerJob(
                tenant_id=context.tenant_id,
                mission_id=payload.mission_id,
                durable_task_id=durable_task.id,
                plan_id=job.plan_id,
                check_id=job.check_id,
                check_definition_id=job.check_definition_id,
                category=job.category,
                evidence_producer=job.evidence_producer,
                mandatory=job.mandatory,
                blocking=job.blocking,
                status="queued",
                inputs=job.inputs,
                depends_on=job.depends_on,
                timeout_seconds=job.timeout_seconds,
                idempotency_key=idempotency_key,
            )
            db.add(row)
            db.flush()
            persisted_jobs.append(_worker_job_response(row))
        db.commit()
    return api_response(response.model_dump(mode="json"), request, persisted={"worker_jobs": persisted_jobs, "skipped": not bool(persisted_jobs)})


@router.post("/contracts/validate")
def validate_contract_output(
    payload: OutputContractValidationRequest,
    request: Request,
    _context: RequestContext = Depends(require_permission("verification.manage")),
):
    response = validate_output_contract(payload)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/tests/discover")
def discover_verification_tests(
    payload: VerificationTestDiscoveryRequest,
    request: Request,
    _context: RequestContext = Depends(require_permission("verification.manage")),
):
    response = discover_tests(payload)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/run")
def run_quality_verification(
    payload: VerificationRunRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("verification.manage")),
    db: Session = Depends(get_db),
):
    hydrated_payload = payload
    hydrated_count = 0
    if not payload.evidence and _mission_exists(db, context, payload.mission_id):
        persisted_evidence = _hydrate_evidence(db, context, payload.mission_id, payload.task_id)
        if persisted_evidence:
            hydrated_count = len(persisted_evidence)
            hydrated_payload = payload.model_copy(update={"evidence": persisted_evidence})
    response = run_verification(hydrated_payload)
    persisted_run_id: str | None = None
    if _mission_exists(db, context, payload.mission_id):
        run = ArceusVerificationRun(
            tenant_id=context.tenant_id,
            mission_id=payload.mission_id,
            task_id=payload.task_id,
            verification_type="release_candidate" if payload.release_candidate else payload.target_type,
            status=_run_status(response.status),
            finished_at=response.generated_at,
            command="verification_engine.run",
            result=response.model_dump(mode="json"),
        )
        db.add(run)
        db.flush()
        for finding in response.findings:
            db.add(
                ArceusVerificationFinding(
                    tenant_id=context.tenant_id,
                    verification_run_id=run.id,
                    mission_id=payload.mission_id,
                    task_id=payload.task_id,
                    finding_key=finding.finding_key,
                    severity=finding.severity,
                    title=finding.title,
                    detail=finding.detail,
                    recommendation=finding.recommendation,
                    evidence_ids=finding.evidence_ids,
                    blocks_release=finding.blocks_release,
                    status="open",
                )
            )
        db.commit()
        db.refresh(run)
        persisted_run_id = str(run.id)
    return api_response(response.model_dump(mode="json"), request, persisted={"verification_run_id": persisted_run_id, "hydrated_evidence_count": hydrated_count})


@router.post("/review")
def run_autonomous_review(
    payload: ReviewRequest,
    request: Request,
    _context: RequestContext = Depends(require_permission("review.create")),
):
    response = perform_autonomous_review(payload)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/release-readiness")
def run_release_readiness(
    payload: ReleaseReadinessRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("verification.manage")),
    db: Session = Depends(get_db),
):
    response = evaluate_release_readiness(payload)
    persisted_gate_id: str | None = None
    if _mission_exists(db, context, payload.mission_id):
        gate = ArceusReleaseReadinessGate(
            tenant_id=context.tenant_id,
            mission_id=payload.mission_id,
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            ready=response.ready,
            status=response.status,
            score=response.score,
            blockers=response.blockers,
            warnings=response.warnings,
            required_actions=response.required_actions,
            evidence_summary=response.evidence_summary,
            response_payload=response.model_dump(mode="json"),
        )
        db.add(gate)
        db.commit()
        db.refresh(gate)
        persisted_gate_id = str(gate.id)
    return api_response(response.model_dump(mode="json"), request, persisted={"release_gate_id": persisted_gate_id})


@router.get("/worker-jobs")
def list_worker_jobs(
    request: Request,
    mission_id: UUID | None = Query(default=None),
    status: str | None = Query(default=None, max_length=60),
    context: RequestContext = Depends(require_permission("verification.view")),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusVerificationWorkerJob).filter(ArceusVerificationWorkerJob.tenant_id == context.tenant_id)
    if mission_id:
        query = query.filter(ArceusVerificationWorkerJob.mission_id == mission_id)
    if status:
        query = query.filter(ArceusVerificationWorkerJob.status == status)
    jobs = query.order_by(ArceusVerificationWorkerJob.created_at.asc()).limit(200).all()
    return collection_response([_worker_job_response(job) for job in jobs], request)


@router.post("/worker-jobs/claim")
def claim_worker_jobs(
    request: Request,
    mission_id: UUID | None = Query(default=None),
    limit: int = Query(default=1, ge=1, le=25),
    context: RequestContext = Depends(require_permission("verification.manage")),
    db: Session = Depends(get_db),
):
    jobs = _claim_jobs(db, context, mission_id=mission_id, limit=limit)
    return collection_response([_worker_job_response(job) for job in jobs], request)


@router.post("/worker-jobs/{job_id}/execute")
def execute_worker_job(
    job_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("evidence.collect")),
    db: Session = Depends(get_db),
):
    job = db.query(ArceusVerificationWorkerJob).filter(ArceusVerificationWorkerJob.tenant_id == context.tenant_id, ArceusVerificationWorkerJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Verification worker job not found.")
    if job.status not in {"queued", "leased", "running", "failed"}:
        return api_response({"worker_job": _worker_job_response(job), "skipped": True, "reason": f"job_status_{job.status}"}, request)
    job.status = "running"
    db.commit()
    db.refresh(job)
    produced_payload = execute_worker_job_payload(job)
    normalized, evidence, producer = _persist_evidence(db, context, produced_payload)
    db.refresh(job)
    return api_response(
        normalized.model_dump(mode="json"),
        request,
        persisted={"evidence_id": str(evidence.id), "producer_run_id": str(producer.id), "worker_job": _worker_job_response(job)},
    )


@router.post("/worker-jobs/drain")
def drain_worker_jobs(
    request: Request,
    mission_id: UUID | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    context: RequestContext = Depends(require_permission("evidence.collect")),
    db: Session = Depends(get_db),
):
    jobs = _claim_jobs(db, context, mission_id=mission_id, limit=limit)
    results = []
    for job in jobs:
        job.status = "running"
        db.commit()
        db.refresh(job)
        produced_payload = execute_worker_job_payload(job)
        normalized, evidence, producer = _persist_evidence(db, context, produced_payload)
        db.refresh(job)
        results.append(
            {
                "job": _worker_job_response(job),
                "evidence_id": str(evidence.id),
                "producer_run_id": str(producer.id),
                "status": normalized.normalized_status,
                "summary": normalized.summary,
            }
        )
    return api_response({"processed": len(results), "results": results}, request)


@router.post("/evidence-producers/run")
def record_evidence_producer(
    payload: EvidenceProducerRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("evidence.collect")),
    db: Session = Depends(get_db),
):
    if not _mission_exists(db, context, payload.mission_id):
        normalized = normalize_evidence_producer_output(payload)
        return api_response(
            normalized.model_dump(mode="json"),
            request,
            persisted={"skipped": True, "reason": "mission_not_found"},
        )
    normalized, evidence, producer = _persist_evidence(db, context, payload)
    return api_response(
        normalized.model_dump(mode="json"),
        request,
        persisted={"evidence_id": str(evidence.id), "producer_run_id": str(producer.id)},
    )


@router.post("/worker-jobs/{job_id}/complete")
def complete_worker_job(
    job_id: UUID,
    payload: EvidenceProducerRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("evidence.collect")),
    db: Session = Depends(get_db),
):
    job = db.query(ArceusVerificationWorkerJob).filter(ArceusVerificationWorkerJob.tenant_id == context.tenant_id, ArceusVerificationWorkerJob.id == job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Verification worker job not found.")
    normalized_payload = payload.model_copy(update={"mission_id": job.mission_id, "task_id": job.task_id, "worker_job_id": job.id, "check_id": job.check_id})
    normalized, evidence, producer = _persist_evidence(db, context, normalized_payload)
    return api_response(
        normalized.model_dump(mode="json"),
        request,
        persisted={"evidence_id": str(evidence.id), "producer_run_id": str(producer.id), "worker_job": _worker_job_response(job)},
    )


@router.post("/mission-control/release-gate")
def mission_control_release_gate(
    payload: MissionControlReleaseGateRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("verification.view")),
    db: Session = Depends(get_db),
):
    gate = (
        db.query(ArceusReleaseReadinessGate)
        .filter(
            ArceusReleaseReadinessGate.tenant_id == context.tenant_id,
            ArceusReleaseReadinessGate.mission_id == payload.mission_id,
            ArceusReleaseReadinessGate.subject_type == payload.subject_type,
            ArceusReleaseReadinessGate.subject_id == payload.subject_id,
        )
        .order_by(ArceusReleaseReadinessGate.checked_at.desc())
        .first()
    )
    if gate is None:
        response = MissionControlReleaseGateResponse(
            allowed=False,
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            readiness_status="missing",
            score=0.0,
            blockers=["Release readiness has not been evaluated for this subject."],
            warnings=[],
            required_actions=["run_release_readiness"],
            checked_at=None,
        )
    else:
        response = MissionControlReleaseGateResponse(
            allowed=bool(gate.ready and gate.status == "ready"),
            subject_type=payload.subject_type,
            subject_id=payload.subject_id,
            readiness_status=gate.status,
            score=gate.score,
            blockers=gate.blockers or [],
            warnings=gate.warnings or [],
            required_actions=gate.required_actions or [],
            checked_at=gate.checked_at,
        )
    return api_response(response.model_dump(mode="json"), request)
