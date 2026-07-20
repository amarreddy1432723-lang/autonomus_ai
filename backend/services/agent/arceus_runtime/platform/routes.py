from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusProviderProfile, ArceusTenant
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..health.routes import classify_runtime_health
from ..operations.service import operation_guard
from .api_schemas import (
    FederationRequest,
    FederationResponse,
    PlatformCapacityResponse,
    PlatformFailoverRequest,
    PlatformFailoverResponse,
    PlatformHealthResponse,
    PlatformRegionResponse,
    PlatformTenantResponse,
)
from .service import (
    calculate_capacity_posture,
    configured_platform_regions,
    evaluate_federation_request,
    region_control_plane_status,
    residency_allows_region,
    tenant_platform_profile,
)


router = APIRouter(prefix="/api/v1/platform", tags=["global-platform"])


def _runtime_summary(db: Session, tenant_id):
    return SqlAlchemyUnitOfWork(db).runtime_health.summary(tenant_id=tenant_id)


def _enabled_providers(db: Session) -> list[ArceusProviderProfile]:
    return db.query(ArceusProviderProfile).filter(ArceusProviderProfile.enabled.is_(True)).all()


def _providers_for_region(providers: list[ArceusProviderProfile], region: str) -> list[ArceusProviderProfile]:
    return [
        provider
        for provider in providers
        if region in (provider.supported_regions or []) or "global" in (provider.supported_regions or []) or region == "local"
    ]


@router.get("/regions")
def list_platform_regions(
    request: Request,
    context: RequestContext = Depends(require_permission("platform.view")),
    db: Session = Depends(get_db),
):
    providers = _enabled_providers(db)
    rows = []
    for region in configured_platform_regions():
        profile = region_control_plane_status(region_key=region, providers=_providers_for_region(providers, region))
        rows.append(PlatformRegionResponse(**profile).model_dump(mode="json"))
    return collection_response(rows, request)


@router.get("/tenants")
def list_platform_tenants(
    request: Request,
    context: RequestContext = Depends(require_permission("platform.view")),
    db: Session = Depends(get_db),
):
    tenants = db.query(ArceusTenant).order_by(ArceusTenant.created_at.desc()).limit(100).all()
    rows = [PlatformTenantResponse(**tenant_platform_profile(tenant)).model_dump(mode="json") for tenant in tenants]
    return collection_response(rows, request)


@router.post("/federation")
def request_federation(
    payload: FederationRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("platform.federation")),
    db: Session = Depends(get_db),
):
    tenant = db.query(ArceusTenant).filter(ArceusTenant.id == context.tenant_id).first()
    profile = tenant_platform_profile(tenant)
    decision = evaluate_federation_request(profile, payload.model_dump())
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action=decision["event_type"],
        resource_type="federation",
        resource_id=payload.peer_deployment_id,
        result=decision["status"],
        metadata={
            "peer_region": payload.peer_region,
            "shared_scopes": payload.shared_scopes,
            "authorized_scopes": decision["authorized_scopes"],
            "denied_scopes": decision["denied_scopes"],
            "dry_run": payload.dry_run,
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    response = FederationResponse(
        peer_deployment_id=payload.peer_deployment_id,
        peer_region=payload.peer_region,
        **decision,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/health")
def get_platform_health(
    request: Request,
    context: RequestContext = Depends(require_permission("platform.view")),
    db: Session = Depends(get_db),
):
    summary = _runtime_summary(db, context.tenant_id)
    status, blockers, warnings = classify_runtime_health(summary)
    providers = _enabled_providers(db)
    regions = [
        region_control_plane_status(region_key=region, providers=_providers_for_region(providers, region))
        for region in configured_platform_regions()
    ]
    tenant = db.query(ArceusTenant).filter(ArceusTenant.id == context.tenant_id).first()
    profile = tenant_platform_profile(tenant)
    if len(regions) < 2:
        warnings = [*warnings, "single_region_deployment"]
    response = PlatformHealthResponse(
        status="blocked" if blockers else ("degraded" if warnings else status),
        ready=not blockers,
        blockers=blockers,
        warnings=warnings,
        control_plane={
            "tenant_id": str(context.tenant_id),
            "control_data_separated": True,
            "mission_statuses": summary.get("mission_statuses") or {},
            "approval_statuses": summary.get("approval_statuses") or {},
        },
        regional_planes=regions,
        data_residency={
            "home_region": profile["home_region"],
            "allowed_regions": profile["residency_regions"],
            "enforced": True,
        },
        federation={
            "enabled": profile["federation_policy"]["enabled"],
            "implicit_trust": False,
            "allowed_scopes": profile["federation_policy"]["allowed_scopes"],
        },
        checked_at=datetime.now(timezone.utc),
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/capacity")
def get_platform_capacity(
    request: Request,
    context: RequestContext = Depends(require_permission("platform.view")),
    db: Session = Depends(get_db),
):
    summary = _runtime_summary(db, context.tenant_id)
    response = PlatformCapacityResponse(**calculate_capacity_posture(summary, region_count=len(configured_platform_regions())))
    return api_response(response.model_dump(mode="json"), request)


@router.post("/failover")
def request_platform_failover(
    payload: PlatformFailoverRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("platform.manage")),
    db: Session = Depends(get_db),
):
    tenant = db.query(ArceusTenant).filter(ArceusTenant.id == context.tenant_id).first()
    profile = tenant_platform_profile(tenant)
    residency_safe = residency_allows_region(profile, payload.target_region)
    accepted, reason, approvals = operation_guard(action="failover", dry_run=payload.dry_run)
    if not residency_safe:
        accepted = False
        reason = "Target region violates tenant data residency policy."
    status = "accepted" if accepted else "needs_approval"
    event_type = "FAILOVER_STARTED" if accepted else "FAILOVER_REQUESTED"
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action=event_type,
        resource_type="platform_region",
        resource_id=payload.target_region,
        result=status,
        metadata={
            "target_region": payload.target_region,
            "dry_run": payload.dry_run,
            "residency_safe": residency_safe,
            "reason": payload.reason,
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    response = PlatformFailoverResponse(
        accepted=accepted,
        dry_run=payload.dry_run,
        status=status,
        target_region=payload.target_region,
        reason=reason,
        required_approvals=approvals,
        residency_safe=residency_safe,
        event_type=event_type,
        audit_recorded=True,
    )
    return api_response(response.model_dump(mode="json"), request)
