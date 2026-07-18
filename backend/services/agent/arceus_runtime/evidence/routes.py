from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import EvidenceResponse, VerificationRunResponse


router = APIRouter(tags=["evidence"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _evidence_response(evidence) -> EvidenceResponse:
    return EvidenceResponse(
        id=evidence.id,
        mission_id=evidence.mission_id,
        task_id=evidence.task_id,
        artifact_id=evidence.artifact_id,
        evidence_type=evidence.evidence_type,
        status=evidence.status,
        summary=evidence.summary,
        payload=evidence.payload or {},
        collected_by_member_id=evidence.collected_by_member_id,
        created_at=evidence.created_at,
        updated_at=evidence.updated_at,
        version_number=evidence.version_number,
    )


def _verification_run_response(run) -> VerificationRunResponse:
    return VerificationRunResponse(
        id=run.id,
        mission_id=run.mission_id,
        task_id=run.task_id,
        verification_type=run.verification_type,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        command=run.command,
        result=run.result or {},
        evidence_id=run.evidence_id,
        created_at=run.created_at,
        updated_at=run.updated_at,
        version_number=run.version_number,
    )


@router.get("/api/v1/missions/{mission_id}/evidence")
def list_mission_evidence(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("evidence.view")),
    evidence_type: str | None = Query(default=None, max_length=100),
    evidence_status: str | None = Query(default=None, alias="status", max_length=60),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    evidence = uow.evidence.list_for_mission(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        evidence_type=evidence_type,
        status=evidence_status,
        limit=limit,
    )
    return collection_response([_evidence_response(item).model_dump(mode="json") for item in evidence], request)


@router.get("/api/v1/evidence/{evidence_id}")
def get_evidence(
    evidence_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("evidence.view")),
    db: Session = Depends(get_db),
):
    evidence = _uow(db).evidence.get(tenant_id=context.tenant_id, evidence_id=evidence_id)
    return api_response(_evidence_response(evidence).model_dump(mode="json"), request)


@router.get("/api/v1/missions/{mission_id}/verification-runs")
def list_mission_verification_runs(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("verification.view")),
    verification_type: str | None = Query(default=None, max_length=100),
    verification_status: str | None = Query(default=None, alias="status", max_length=60),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    runs = uow.verification_runs.list_for_mission(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        verification_type=verification_type,
        status=verification_status,
        limit=limit,
    )
    return collection_response([_verification_run_response(item).model_dump(mode="json") for item in runs], request)


@router.get("/api/v1/verification-runs/{verification_run_id}")
def get_verification_run(
    verification_run_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("verification.view")),
    db: Session = Depends(get_db),
):
    run = _uow(db).verification_runs.get(tenant_id=context.tenant_id, verification_run_id=verification_run_id)
    return api_response(_verification_run_response(run).model_dump(mode="json"), request)
