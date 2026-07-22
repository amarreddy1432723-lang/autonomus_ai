from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusDeploymentApplication,
    ArceusDeploymentEnvironment,
    ArceusDeploymentRelease,
    ArceusDeploymentRequest,
    ArceusDeploymentTarget,
)
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from .api_schemas import (
    DeploymentApplicationRequest,
    DeploymentApplicationResponse,
    DeploymentArtifactRequest,
    DeploymentEnvironmentRequest,
    DeploymentEnvironmentResponse,
    DeploymentHealthSummaryResponse,
    DeploymentReleaseRequest,
    DeploymentReleaseResponse,
    DeploymentRequestCreate,
    DeploymentRequestResponse,
    DeploymentTargetRequest,
    DeploymentTargetResponse,
    DriftReportRequest,
    HealthCheckRequest,
    RollbackRequest,
    RuntimeProfileRequest,
)
from .service import (
    attach_artifact,
    create_application,
    create_deployment_request,
    create_environment,
    create_release,
    create_rollback,
    create_runtime_profile,
    create_target,
    health_summary,
    plan_deployment,
    record_drift,
    record_health_check,
)


router = APIRouter(prefix="/api/v1/deployment", tags=["arceus-deployment"])


@router.post("/targets")
def register_target(
    payload: DeploymentTargetRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("deployment.manage")),
    db: Session = Depends(get_db),
):
    item = create_target(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response(_target_response(item).model_dump(mode="json"), request)


@router.get("/targets")
def list_targets(
    request: Request,
    context: RequestContext = Depends(require_permission("deployment.view")),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(ArceusDeploymentTarget)
        .filter(ArceusDeploymentTarget.tenant_id == context.tenant_id)
        .order_by(ArceusDeploymentTarget.created_at.desc())
        .limit(100)
        .all()
    )
    return collection_response([_target_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/runtime-profiles")
def register_runtime_profile(
    payload: RuntimeProfileRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("deployment.manage")),
    db: Session = Depends(get_db),
):
    item = create_runtime_profile(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response(
        {
            "id": str(item.id),
            "name": item.name,
            "runtime_type": item.runtime_type,
            "startup_command": item.startup_command,
            "port": item.port,
            "health_check": item.health_check,
            "resources": item.resources,
            "scaling": item.scaling,
        },
        request,
    )


@router.post("/applications")
def register_application(
    payload: DeploymentApplicationRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("deployment.manage")),
    db: Session = Depends(get_db),
):
    item = create_application(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response(_application_response(item).model_dump(mode="json"), request)


@router.get("/applications")
def list_applications(
    request: Request,
    project_id: UUID | None = None,
    context: RequestContext = Depends(require_permission("deployment.view")),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusDeploymentApplication).filter(ArceusDeploymentApplication.tenant_id == context.tenant_id)
    if project_id is not None:
        query = query.filter(ArceusDeploymentApplication.project_id == project_id)
    rows = query.order_by(ArceusDeploymentApplication.created_at.desc()).limit(100).all()
    return collection_response([_application_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/environments")
def register_environment(
    payload: DeploymentEnvironmentRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("environment.manage")),
    db: Session = Depends(get_db),
):
    try:
        item = create_environment(db, tenant_id=context.tenant_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc), "message": "Deployment target was not found."}) from exc
    db.commit()
    db.refresh(item)
    return api_response(_environment_response(item).model_dump(mode="json"), request)


@router.get("/environments")
def list_environments(
    request: Request,
    application_id: UUID | None = None,
    context: RequestContext = Depends(require_permission("environment.view")),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusDeploymentEnvironment).filter(ArceusDeploymentEnvironment.tenant_id == context.tenant_id)
    if application_id is not None:
        query = query.filter(ArceusDeploymentEnvironment.application_id == application_id)
    rows = query.order_by(ArceusDeploymentEnvironment.created_at.desc()).limit(100).all()
    return collection_response([_environment_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/releases")
def register_release(
    payload: DeploymentReleaseRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("release.manage")),
    db: Session = Depends(get_db),
):
    item = create_release(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response(_release_response(item).model_dump(mode="json"), request)


@router.get("/releases")
def list_releases(
    request: Request,
    application_id: UUID | None = None,
    context: RequestContext = Depends(require_permission("release.view")),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusDeploymentRelease).filter(ArceusDeploymentRelease.tenant_id == context.tenant_id)
    if application_id is not None:
        query = query.filter(ArceusDeploymentRelease.application_id == application_id)
    rows = query.order_by(ArceusDeploymentRelease.created_at.desc()).limit(100).all()
    return collection_response([_release_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/artifacts")
def register_artifact(
    payload: DeploymentArtifactRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("release.manage")),
    db: Session = Depends(get_db),
):
    item = attach_artifact(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response(
        {
            "id": str(item.id),
            "release_id": str(item.release_id),
            "artifact_type": item.artifact_type,
            "digest": item.digest,
            "uri": item.uri,
            "signed": item.signed,
            "scan_status": item.scan_status,
        },
        request,
    )


@router.post("/requests")
def request_deployment(
    payload: DeploymentRequestCreate,
    request: Request,
    context: RequestContext = Depends(require_permission("deployment.plan")),
    db: Session = Depends(get_db),
):
    item = create_deployment_request(db, tenant_id=context.tenant_id, payload=payload)
    plan = plan_deployment(db, tenant_id=context.tenant_id, deployment_request_id=item.id)
    db.commit()
    db.refresh(item)
    return api_response(
        {
            "request": _request_response(item).model_dump(mode="json"),
            "plan": plan.model_dump(mode="json"),
        },
        request,
    )


@router.get("/requests")
def list_deployment_requests(
    request: Request,
    environment_id: UUID | None = None,
    context: RequestContext = Depends(require_permission("deployment.view")),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusDeploymentRequest).filter(ArceusDeploymentRequest.tenant_id == context.tenant_id)
    if environment_id is not None:
        query = query.filter(ArceusDeploymentRequest.environment_id == environment_id)
    rows = query.order_by(ArceusDeploymentRequest.created_at.desc()).limit(100).all()
    return collection_response([_request_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/requests/{deployment_request_id}/plan")
def create_plan(
    deployment_request_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("deployment.plan")),
    db: Session = Depends(get_db),
):
    try:
        plan = plan_deployment(db, tenant_id=context.tenant_id, deployment_request_id=deployment_request_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc), "message": "Deployment request could not be planned."}) from exc
    db.commit()
    return api_response(plan.model_dump(mode="json"), request)


@router.post("/health-checks")
def add_health_check(
    payload: HealthCheckRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("deployment.health")),
    db: Session = Depends(get_db),
):
    item = record_health_check(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response({"id": str(item.id), "status": item.status, "target": item.target, "check_type": item.check_type}, request)


@router.get("/environments/{environment_id}/health")
def get_environment_health(
    environment_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("deployment.health")),
    db: Session = Depends(get_db),
):
    try:
        summary = health_summary(db, tenant_id=context.tenant_id, environment_id=environment_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc), "message": "Deployment environment was not found."}) from exc
    return api_response(DeploymentHealthSummaryResponse(**summary).model_dump(mode="json"), request)


@router.post("/rollbacks")
def register_rollback(
    payload: RollbackRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("deployment.rollback")),
    db: Session = Depends(get_db),
):
    item = create_rollback(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response({"id": str(item.id), "status": item.status, "rollback_steps": item.rollback_steps}, request)


@router.post("/drift")
def report_drift(
    payload: DriftReportRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("deployment.drift")),
    db: Session = Depends(get_db),
):
    item = record_drift(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response({"id": str(item.id), "status": item.status, "severity": item.severity, "findings": item.findings}, request)


def _target_response(item: ArceusDeploymentTarget) -> DeploymentTargetResponse:
    return DeploymentTargetResponse(
        id=item.id,
        name=item.name,
        provider_type=item.provider_type,
        credential_binding_id=item.credential_binding_id,
        regions=item.regions or [],
        capabilities=item.capabilities or {},
        status=item.status,
    )


def _application_response(item: ArceusDeploymentApplication) -> DeploymentApplicationResponse:
    return DeploymentApplicationResponse(
        id=item.id,
        project_id=item.project_id,
        name=item.name,
        slug=item.slug,
        application_type=item.application_type,
        runtime_profile_id=item.runtime_profile_id,
        status=item.status,
        created_at=item.created_at,
    )


def _environment_response(item: ArceusDeploymentEnvironment) -> DeploymentEnvironmentResponse:
    return DeploymentEnvironmentResponse(
        id=item.id,
        application_id=item.application_id,
        target_id=item.target_id,
        name=item.name,
        environment_type=item.environment_type,
        region=item.region,
        status=item.status,
        protection_level=item.protection_level,
        current_release_id=item.current_release_id,
    )


def _release_response(item: ArceusDeploymentRelease) -> DeploymentReleaseResponse:
    return DeploymentReleaseResponse(
        id=item.id,
        application_id=item.application_id,
        version=item.version,
        source_commit_sha=item.source_commit_sha,
        build_id=item.build_id,
        artifact_ids=item.artifact_ids or [],
        status=item.status,
        provenance=item.provenance or {},
    )


def _request_response(item: ArceusDeploymentRequest) -> DeploymentRequestResponse:
    return DeploymentRequestResponse(
        id=item.id,
        release_id=item.release_id,
        environment_id=item.environment_id,
        strategy=item.strategy,
        status=item.status,
        dry_run=item.dry_run,
        requested_by=item.requested_by,
        reason=item.reason,
        created_at=item.created_at,
    )
