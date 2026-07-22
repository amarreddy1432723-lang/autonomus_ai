from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusAdminAccessReview,
    ArceusAdminAuditExport,
    ArceusAdminDomainVerification,
    ArceusAdminOrganizationProfile,
    ArceusAdminOrgUnit,
    ArceusAdminPolicyBundle,
    ArceusAdminScimConfiguration,
    ArceusAdminSeatAssignment,
    ArceusAdminSsoConfiguration,
    ArceusAdminSupportAccessGrant,
    ArceusAdminTenantOperation,
)
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from .api_schemas import (
    AccessReviewCompleteRequest,
    AccessReviewRequest,
    AccessReviewResponse,
    AuditExportRequest,
    AuditExportResponse,
    DomainVerificationRequest,
    DomainVerificationResponse,
    DomainVerifyRequest,
    EnterpriseAdminSummaryResponse,
    OrgUnitRequest,
    OrgUnitResponse,
    OrganizationProfileRequest,
    OrganizationProfileResponse,
    PolicyBundleRequest,
    PolicyBundleResponse,
    ScimConfigurationRequest,
    ScimConfigurationResponse,
    SeatAssignmentRequest,
    SeatAssignmentResponse,
    SsoConfigurationRequest,
    SsoConfigurationResponse,
    SupportAccessApproveRequest,
    SupportAccessRequest,
    SupportAccessResponse,
    TenantOperationRequest,
    TenantOperationResponse,
)
from .service import (
    approve_support_access,
    assign_seat,
    complete_access_review,
    configure_scim,
    configure_sso,
    create_org_unit,
    create_tenant_operation,
    enterprise_admin_summary,
    open_access_review,
    request_audit_export,
    request_domain_verification,
    request_support_access,
    upsert_organization_profile,
    upsert_policy_bundle,
    verify_domain,
)


router = APIRouter(prefix="/api/v1/enterprise-admin", tags=["arceus-enterprise-admin"])


@router.post("/profile")
def save_profile(payload: OrganizationProfileRequest, request: Request, context: RequestContext = Depends(require_permission("admin.enterprise.manage")), db: Session = Depends(get_db)):
    row = upsert_organization_profile(db, tenant_id=context.tenant_id, actor_id=context.user_id, payload=payload)
    db.commit()
    db.refresh(row)
    return api_response(_profile(row).model_dump(mode="json"), request)


@router.get("/profile")
def get_profile(request: Request, context: RequestContext = Depends(require_permission("admin.enterprise.view")), db: Session = Depends(get_db)):
    rows = db.query(ArceusAdminOrganizationProfile).filter(ArceusAdminOrganizationProfile.tenant_id == context.tenant_id).order_by(ArceusAdminOrganizationProfile.created_at.desc()).limit(10).all()
    return collection_response([_profile(row).model_dump(mode="json") for row in rows], request)


@router.post("/org-units")
def create_unit(payload: OrgUnitRequest, request: Request, context: RequestContext = Depends(require_permission("admin.enterprise.manage")), db: Session = Depends(get_db)):
    try:
        row = create_org_unit(db, tenant_id=context.tenant_id, payload=payload)
    except ValueError as exc:
        raise _unprocessable(exc)
    db.commit()
    db.refresh(row)
    return api_response(_org_unit(row).model_dump(mode="json"), request)


@router.get("/org-units")
def list_units(request: Request, context: RequestContext = Depends(require_permission("admin.enterprise.view")), db: Session = Depends(get_db)):
    rows = db.query(ArceusAdminOrgUnit).filter(ArceusAdminOrgUnit.tenant_id == context.tenant_id).order_by(ArceusAdminOrgUnit.unit_key.asc()).limit(200).all()
    return collection_response([_org_unit(row).model_dump(mode="json") for row in rows], request)


@router.post("/domains")
def create_domain_verification(payload: DomainVerificationRequest, request: Request, context: RequestContext = Depends(require_permission("admin.identity.manage")), db: Session = Depends(get_db)):
    try:
        row = request_domain_verification(db, tenant_id=context.tenant_id, payload=payload)
    except ValueError as exc:
        raise _unprocessable(exc)
    db.commit()
    db.refresh(row)
    return api_response(_domain(row).model_dump(mode="json"), request)


@router.post("/domains/{domain_id}/verify")
def complete_domain_verification(domain_id: UUID, payload: DomainVerifyRequest, request: Request, context: RequestContext = Depends(require_permission("admin.identity.manage")), db: Session = Depends(get_db)):
    try:
        row = verify_domain(db, tenant_id=context.tenant_id, domain_id=domain_id, payload=payload)
    except ValueError as exc:
        raise _unprocessable(exc)
    db.commit()
    db.refresh(row)
    return api_response(_domain(row).model_dump(mode="json"), request)


@router.post("/sso")
def save_sso(payload: SsoConfigurationRequest, request: Request, context: RequestContext = Depends(require_permission("admin.identity.manage")), db: Session = Depends(get_db)):
    try:
        row = configure_sso(db, tenant_id=context.tenant_id, payload=payload)
    except ValueError as exc:
        raise _unprocessable(exc)
    db.commit()
    db.refresh(row)
    return api_response(_sso(row).model_dump(mode="json"), request)


@router.post("/scim")
def save_scim(payload: ScimConfigurationRequest, request: Request, context: RequestContext = Depends(require_permission("admin.identity.manage")), db: Session = Depends(get_db)):
    try:
        row = configure_scim(db, tenant_id=context.tenant_id, payload=payload)
    except ValueError as exc:
        raise _unprocessable(exc)
    db.commit()
    db.refresh(row)
    return api_response(_scim(row).model_dump(mode="json"), request)


@router.post("/seats")
def save_seat(payload: SeatAssignmentRequest, request: Request, context: RequestContext = Depends(require_permission("admin.enterprise.manage")), db: Session = Depends(get_db)):
    try:
        row = assign_seat(db, tenant_id=context.tenant_id, actor_id=context.user_id, payload=payload)
    except ValueError as exc:
        raise _unprocessable(exc)
    db.commit()
    db.refresh(row)
    return api_response(_seat(row).model_dump(mode="json"), request)


@router.get("/seats")
def list_seats(request: Request, context: RequestContext = Depends(require_permission("admin.enterprise.view")), db: Session = Depends(get_db)):
    rows = db.query(ArceusAdminSeatAssignment).filter(ArceusAdminSeatAssignment.tenant_id == context.tenant_id).order_by(ArceusAdminSeatAssignment.assigned_at.desc()).limit(300).all()
    return collection_response([_seat(row).model_dump(mode="json") for row in rows], request)


@router.post("/access-reviews")
def create_access_review(payload: AccessReviewRequest, request: Request, context: RequestContext = Depends(require_permission("admin.access_review.manage")), db: Session = Depends(get_db)):
    try:
        row = open_access_review(db, tenant_id=context.tenant_id, payload=payload)
    except ValueError as exc:
        raise _unprocessable(exc)
    db.commit()
    db.refresh(row)
    return api_response(_access_review(row).model_dump(mode="json"), request)


@router.post("/access-reviews/{review_id}/complete")
def finish_access_review(review_id: UUID, payload: AccessReviewCompleteRequest, request: Request, context: RequestContext = Depends(require_permission("admin.access_review.manage")), db: Session = Depends(get_db)):
    try:
        row = complete_access_review(db, tenant_id=context.tenant_id, review_id=review_id, payload=payload)
    except ValueError as exc:
        raise _unprocessable(exc)
    db.commit()
    db.refresh(row)
    return api_response(_access_review(row).model_dump(mode="json"), request)


@router.post("/audit-exports")
def create_audit_export(payload: AuditExportRequest, request: Request, context: RequestContext = Depends(require_permission("admin.audit.export")), db: Session = Depends(get_db)):
    try:
        row = request_audit_export(db, tenant_id=context.tenant_id, actor_id=context.user_id, payload=payload)
    except ValueError as exc:
        raise _unprocessable(exc)
    db.commit()
    db.refresh(row)
    return api_response(_audit_export(row).model_dump(mode="json"), request)


@router.post("/support-access")
def create_support_access(payload: SupportAccessRequest, request: Request, context: RequestContext = Depends(require_permission("admin.support.manage")), db: Session = Depends(get_db)):
    try:
        row = request_support_access(db, tenant_id=context.tenant_id, actor_id=context.user_id, payload=payload)
    except ValueError as exc:
        raise _unprocessable(exc)
    db.commit()
    db.refresh(row)
    return api_response(_support_access(row).model_dump(mode="json"), request)


@router.post("/support-access/{grant_id}/approve")
def approve_support_grant(grant_id: UUID, payload: SupportAccessApproveRequest, request: Request, context: RequestContext = Depends(require_permission("admin.support.manage")), db: Session = Depends(get_db)):
    try:
        row = approve_support_access(db, tenant_id=context.tenant_id, actor_id=context.user_id, grant_id=grant_id, payload=payload)
    except ValueError as exc:
        raise _unprocessable(exc)
    db.commit()
    db.refresh(row)
    return api_response(_support_access(row).model_dump(mode="json"), request)


@router.post("/policy-bundles")
def save_policy_bundle(payload: PolicyBundleRequest, request: Request, context: RequestContext = Depends(require_permission("admin.policy.manage")), db: Session = Depends(get_db)):
    try:
        row = upsert_policy_bundle(db, tenant_id=context.tenant_id, actor_id=context.user_id, payload=payload)
    except ValueError as exc:
        raise _unprocessable(exc)
    db.commit()
    db.refresh(row)
    return api_response(_policy(row).model_dump(mode="json"), request)


@router.post("/tenant-operations")
def request_tenant_operation(payload: TenantOperationRequest, request: Request, context: RequestContext = Depends(require_permission("admin.tenant.operate")), db: Session = Depends(get_db)):
    try:
        row = create_tenant_operation(db, tenant_id=context.tenant_id, actor_id=context.user_id, payload=payload)
    except ValueError as exc:
        raise _unprocessable(exc)
    db.commit()
    db.refresh(row)
    return api_response(_tenant_operation(row).model_dump(mode="json"), request)


@router.get("/summary")
def get_summary(request: Request, context: RequestContext = Depends(require_permission("admin.enterprise.view")), db: Session = Depends(get_db)):
    return api_response(EnterpriseAdminSummaryResponse(**enterprise_admin_summary(db, tenant_id=context.tenant_id)).model_dump(mode="json"), request)


def _profile(row: ArceusAdminOrganizationProfile) -> OrganizationProfileResponse:
    return OrganizationProfileResponse(id=row.id, display_name=row.display_name, legal_name=row.legal_name, primary_domain=row.primary_domain, organization_type=row.organization_type, status=row.status, region=row.region, data_residency_region=row.data_residency_region, compliance_profiles=row.compliance_profiles or [], onboarding_checklist=row.onboarding_checklist or {})


def _org_unit(row: ArceusAdminOrgUnit) -> OrgUnitResponse:
    return OrgUnitResponse(id=row.id, profile_id=row.profile_id, parent_unit_id=row.parent_unit_id, name=row.name, unit_key=row.unit_key, status=row.status)


def _domain(row: ArceusAdminDomainVerification) -> DomainVerificationResponse:
    return DomainVerificationResponse(id=row.id, profile_id=row.profile_id, domain=row.domain, verification_method=row.verification_method, verification_token=row.verification_token, status=row.status, verified_at=row.verified_at, expires_at=row.expires_at)


def _sso(row: ArceusAdminSsoConfiguration) -> SsoConfigurationResponse:
    return SsoConfigurationResponse(id=row.id, provider_key=row.provider_key, provider_type=row.provider_type, issuer=row.issuer, status=row.status, enforced=row.enforced, enforcement_mode=row.enforcement_mode, allowed_domains=row.allowed_domains or [])


def _scim(row: ArceusAdminScimConfiguration) -> ScimConfigurationResponse:
    return ScimConfigurationResponse(id=row.id, provider_key=row.provider_key, provider_name=row.provider_name, endpoint_url=row.endpoint_url, token_checksum_sha256=row.token_checksum_sha256, status=row.status, dry_run=row.dry_run, deletion_safeguard_threshold=row.deletion_safeguard_threshold)


def _seat(row: ArceusAdminSeatAssignment) -> SeatAssignmentResponse:
    return SeatAssignmentResponse(id=row.id, profile_id=row.profile_id, user_id=row.user_id, plan_key=row.plan_key, seat_type=row.seat_type, status=row.status, cost_center=row.cost_center)


def _access_review(row: ArceusAdminAccessReview) -> AccessReviewResponse:
    return AccessReviewResponse(id=row.id, review_key=row.review_key, scope_type=row.scope_type, scope_id=row.scope_id, status=row.status, findings=row.findings or [], decisions=row.decisions or [])


def _audit_export(row: ArceusAdminAuditExport) -> AuditExportResponse:
    return AuditExportResponse(id=row.id, export_type=row.export_type, status=row.status, reason=row.reason, expires_at=row.expires_at)


def _support_access(row: ArceusAdminSupportAccessGrant) -> SupportAccessResponse:
    return SupportAccessResponse(id=row.id, profile_id=row.profile_id, support_user_id=row.support_user_id, requested_by=row.requested_by, approved_by=row.approved_by, status=row.status, ticket_reference=row.ticket_reference, expires_at=row.expires_at)


def _policy(row: ArceusAdminPolicyBundle) -> PolicyBundleResponse:
    return PolicyBundleResponse(id=row.id, bundle_key=row.bundle_key, name=row.name, policy_type=row.policy_type, version=row.version, scope_type=row.scope_type, status=row.status)


def _tenant_operation(row: ArceusAdminTenantOperation) -> TenantOperationResponse:
    return TenantOperationResponse(id=row.id, operation_type=row.operation_type, status=row.status, reason=row.reason, current_step=row.current_step, completed_steps=row.completed_steps or [], safeguards=row.safeguards or {})


def _unprocessable(exc: ValueError) -> HTTPException:
    code = str(exc).split(":", 1)[0]
    return HTTPException(status_code=422, detail={"code": code, "message": str(exc)})
