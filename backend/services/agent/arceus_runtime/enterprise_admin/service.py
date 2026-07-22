from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

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

from .api_schemas import (
    AccessReviewCompleteRequest,
    AccessReviewRequest,
    AuditExportRequest,
    DomainVerificationRequest,
    DomainVerifyRequest,
    OrgUnitRequest,
    OrganizationProfileRequest,
    PolicyBundleRequest,
    ScimConfigurationRequest,
    SeatAssignmentRequest,
    SsoConfigurationRequest,
    SupportAccessApproveRequest,
    SupportAccessRequest,
    TenantOperationRequest,
)


def upsert_organization_profile(db: Session, *, tenant_id: UUID, actor_id: UUID, payload: OrganizationProfileRequest) -> ArceusAdminOrganizationProfile:
    profile = db.query(ArceusAdminOrganizationProfile).filter(ArceusAdminOrganizationProfile.tenant_id == tenant_id).first()
    if profile is None:
        profile = ArceusAdminOrganizationProfile(tenant_id=tenant_id, created_by=actor_id)
        db.add(profile)
    for key, value in payload.model_dump().items():
        setattr(profile, key, value)
    profile.status = profile.status or "active"
    db.flush()
    return profile


def create_org_unit(db: Session, *, tenant_id: UUID, payload: OrgUnitRequest) -> ArceusAdminOrgUnit:
    _require_profile(db, tenant_id=tenant_id, profile_id=payload.profile_id)
    unit = db.query(ArceusAdminOrgUnit).filter(ArceusAdminOrgUnit.tenant_id == tenant_id, ArceusAdminOrgUnit.profile_id == payload.profile_id, ArceusAdminOrgUnit.unit_key == payload.unit_key).first()
    if unit is None:
        unit = ArceusAdminOrgUnit(tenant_id=tenant_id, profile_id=payload.profile_id)
        db.add(unit)
    for key, value in payload.model_dump(exclude={"profile_id"}).items():
        setattr(unit, key, value)
    unit.status = "active"
    db.flush()
    return unit


def request_domain_verification(db: Session, *, tenant_id: UUID, payload: DomainVerificationRequest) -> ArceusAdminDomainVerification:
    _require_profile(db, tenant_id=tenant_id, profile_id=payload.profile_id)
    domain = _normalize_domain(payload.domain)
    row = db.query(ArceusAdminDomainVerification).filter(ArceusAdminDomainVerification.tenant_id == tenant_id, ArceusAdminDomainVerification.profile_id == payload.profile_id, ArceusAdminDomainVerification.domain == domain).first()
    if row is None:
        row = ArceusAdminDomainVerification(tenant_id=tenant_id, profile_id=payload.profile_id, domain=domain)
        db.add(row)
    row.verification_method = payload.verification_method
    row.verification_token = f"arceus-verify-{secrets.token_urlsafe(24)}"
    row.status = "pending"
    row.expires_at = _now() + timedelta(days=14)
    row.verified_at = None
    row.metadata_json = {"dns_record": f"_arceus-domain-verification.{domain}", "dns_value": row.verification_token}
    db.flush()
    return row


def verify_domain(db: Session, *, tenant_id: UUID, domain_id: UUID, payload: DomainVerifyRequest) -> ArceusAdminDomainVerification:
    row = db.query(ArceusAdminDomainVerification).filter(ArceusAdminDomainVerification.tenant_id == tenant_id, ArceusAdminDomainVerification.id == domain_id).first()
    if row is None:
        raise ValueError("DOMAIN_VERIFICATION_NOT_FOUND")
    if row.status == "verified":
        return row
    if row.expires_at and _coerce_aware(row.expires_at) < _now():
        row.status = "expired"
        raise ValueError("DOMAIN_VERIFICATION_EXPIRED")
    if not secrets.compare_digest(row.verification_token, payload.verification_token):
        row.status = "failed"
        raise ValueError("DOMAIN_VERIFICATION_TOKEN_MISMATCH")
    row.status = "verified"
    row.verified_at = _now()
    db.flush()
    return row


def configure_sso(db: Session, *, tenant_id: UUID, payload: SsoConfigurationRequest) -> ArceusAdminSsoConfiguration:
    _require_profile(db, tenant_id=tenant_id, profile_id=payload.profile_id)
    domains = [_normalize_domain(domain) for domain in payload.allowed_domains]
    if payload.enforced and domains:
        _require_verified_domains(db, tenant_id=tenant_id, profile_id=payload.profile_id, domains=domains)
    row = db.query(ArceusAdminSsoConfiguration).filter(ArceusAdminSsoConfiguration.tenant_id == tenant_id, ArceusAdminSsoConfiguration.profile_id == payload.profile_id, ArceusAdminSsoConfiguration.provider_key == payload.provider_key).first()
    if row is None:
        row = ArceusAdminSsoConfiguration(tenant_id=tenant_id, profile_id=payload.profile_id)
        db.add(row)
    for key, value in payload.model_dump(exclude={"profile_id"}).items():
        setattr(row, key, value)
    row.allowed_domains = domains
    db.flush()
    return row


def configure_scim(db: Session, *, tenant_id: UUID, payload: ScimConfigurationRequest) -> ArceusAdminScimConfiguration:
    _require_profile(db, tenant_id=tenant_id, profile_id=payload.profile_id)
    row = db.query(ArceusAdminScimConfiguration).filter(ArceusAdminScimConfiguration.tenant_id == tenant_id, ArceusAdminScimConfiguration.profile_id == payload.profile_id, ArceusAdminScimConfiguration.provider_key == payload.provider_key).first()
    if row is None:
        row = ArceusAdminScimConfiguration(tenant_id=tenant_id, profile_id=payload.profile_id)
        db.add(row)
    data = payload.model_dump(exclude={"bearer_token", "profile_id"})
    for key, value in data.items():
        setattr(row, key, value)
    row.token_checksum_sha256 = hashlib.sha256(payload.bearer_token.encode("utf-8")).hexdigest()
    db.flush()
    return row


def assign_seat(db: Session, *, tenant_id: UUID, actor_id: UUID, payload: SeatAssignmentRequest) -> ArceusAdminSeatAssignment:
    _require_profile(db, tenant_id=tenant_id, profile_id=payload.profile_id)
    row = db.query(ArceusAdminSeatAssignment).filter(ArceusAdminSeatAssignment.tenant_id == tenant_id, ArceusAdminSeatAssignment.profile_id == payload.profile_id, ArceusAdminSeatAssignment.user_id == payload.user_id).first()
    if row is None:
        row = ArceusAdminSeatAssignment(tenant_id=tenant_id, profile_id=payload.profile_id, user_id=payload.user_id)
        db.add(row)
    for key, value in payload.model_dump(exclude={"profile_id", "user_id", "metadata"}).items():
        setattr(row, key, value)
    row.metadata_json = payload.metadata
    row.assigned_by = actor_id
    row.status = payload.status
    db.flush()
    return row


def open_access_review(db: Session, *, tenant_id: UUID, payload: AccessReviewRequest) -> ArceusAdminAccessReview:
    _require_profile(db, tenant_id=tenant_id, profile_id=payload.profile_id)
    row = db.query(ArceusAdminAccessReview).filter(ArceusAdminAccessReview.tenant_id == tenant_id, ArceusAdminAccessReview.profile_id == payload.profile_id, ArceusAdminAccessReview.review_key == payload.review_key).first()
    if row is None:
        row = ArceusAdminAccessReview(tenant_id=tenant_id, profile_id=payload.profile_id)
        db.add(row)
    for key, value in payload.model_dump(exclude={"profile_id"}).items():
        setattr(row, key, value)
    row.status = "in_progress"
    db.flush()
    return row


def complete_access_review(db: Session, *, tenant_id: UUID, review_id: UUID, payload: AccessReviewCompleteRequest) -> ArceusAdminAccessReview:
    row = db.query(ArceusAdminAccessReview).filter(ArceusAdminAccessReview.tenant_id == tenant_id, ArceusAdminAccessReview.id == review_id).first()
    if row is None:
        raise ValueError("ACCESS_REVIEW_NOT_FOUND")
    row.decisions = payload.decisions
    row.findings = payload.findings or row.findings or []
    row.status = "completed"
    row.completed_at = _now()
    db.flush()
    return row


def request_audit_export(db: Session, *, tenant_id: UUID, actor_id: UUID, payload: AuditExportRequest) -> ArceusAdminAuditExport:
    _require_profile(db, tenant_id=tenant_id, profile_id=payload.profile_id)
    row = ArceusAdminAuditExport(
        tenant_id=tenant_id,
        profile_id=payload.profile_id,
        export_type=payload.export_type,
        requested_by=actor_id,
        reason=payload.reason,
        filters=payload.filters,
        status="queued",
        expires_at=_now() + timedelta(days=7),
    )
    db.add(row)
    db.flush()
    return row


def request_support_access(db: Session, *, tenant_id: UUID, actor_id: UUID, payload: SupportAccessRequest) -> ArceusAdminSupportAccessGrant:
    _require_profile(db, tenant_id=tenant_id, profile_id=payload.profile_id)
    if payload.duration_minutes > 24 * 60:
        raise ValueError("SUPPORT_ACCESS_DURATION_TOO_LONG")
    row = ArceusAdminSupportAccessGrant(
        tenant_id=tenant_id,
        profile_id=payload.profile_id,
        support_user_id=payload.support_user_id,
        requested_by=actor_id,
        reason=payload.reason,
        ticket_reference=payload.ticket_reference,
        scope=payload.scope,
        permissions=payload.permissions,
        status="requested",
        starts_at=_now(),
        expires_at=_now() + timedelta(minutes=payload.duration_minutes),
    )
    db.add(row)
    db.flush()
    return row


def approve_support_access(db: Session, *, tenant_id: UUID, actor_id: UUID, grant_id: UUID, payload: SupportAccessApproveRequest) -> ArceusAdminSupportAccessGrant:
    row = db.query(ArceusAdminSupportAccessGrant).filter(ArceusAdminSupportAccessGrant.tenant_id == tenant_id, ArceusAdminSupportAccessGrant.id == grant_id).first()
    if row is None:
        raise ValueError("SUPPORT_ACCESS_NOT_FOUND")
    if _coerce_aware(row.expires_at) <= _now():
        row.status = "expired"
        raise ValueError("SUPPORT_ACCESS_EXPIRED")
    row.approved_by = actor_id
    row.status = "active" if payload.approved else "denied"
    db.flush()
    return row


def upsert_policy_bundle(db: Session, *, tenant_id: UUID, actor_id: UUID, payload: PolicyBundleRequest) -> ArceusAdminPolicyBundle:
    _require_profile(db, tenant_id=tenant_id, profile_id=payload.profile_id)
    row = db.query(ArceusAdminPolicyBundle).filter(ArceusAdminPolicyBundle.tenant_id == tenant_id, ArceusAdminPolicyBundle.profile_id == payload.profile_id, ArceusAdminPolicyBundle.bundle_key == payload.bundle_key, ArceusAdminPolicyBundle.version == payload.version).first()
    if row is None:
        row = ArceusAdminPolicyBundle(tenant_id=tenant_id, profile_id=payload.profile_id)
        db.add(row)
    for key, value in payload.model_dump(exclude={"profile_id"}).items():
        setattr(row, key, value)
    if payload.status == "active":
        row.approved_by = actor_id
        row.effective_at = _now()
    db.flush()
    return row


def create_tenant_operation(db: Session, *, tenant_id: UUID, actor_id: UUID, payload: TenantOperationRequest) -> ArceusAdminTenantOperation:
    _require_profile(db, tenant_id=tenant_id, profile_id=payload.profile_id)
    _validate_tenant_operation(payload)
    row = ArceusAdminTenantOperation(
        tenant_id=tenant_id,
        profile_id=payload.profile_id,
        operation_type=payload.operation_type,
        requested_by=actor_id,
        reason=payload.reason,
        status="requested",
        current_step="approval_required" if payload.operation_type in {"suspend", "delete", "migrate"} else "queued",
        completed_steps=["request_recorded"],
        safeguards=payload.safeguards,
        scheduled_at=payload.scheduled_at,
    )
    db.add(row)
    db.flush()
    return row


def enterprise_admin_summary(db: Session, *, tenant_id: UUID) -> dict[str, object]:
    profiles = db.query(ArceusAdminOrganizationProfile).filter(ArceusAdminOrganizationProfile.tenant_id == tenant_id).count()
    active_seats = db.query(ArceusAdminSeatAssignment).filter(ArceusAdminSeatAssignment.tenant_id == tenant_id, ArceusAdminSeatAssignment.status == "active").count()
    pending_domains = db.query(ArceusAdminDomainVerification).filter(ArceusAdminDomainVerification.tenant_id == tenant_id, ArceusAdminDomainVerification.status == "pending").count()
    active_sso = db.query(ArceusAdminSsoConfiguration).filter(ArceusAdminSsoConfiguration.tenant_id == tenant_id, ArceusAdminSsoConfiguration.status == "active").count()
    active_scim = db.query(ArceusAdminScimConfiguration).filter(ArceusAdminScimConfiguration.tenant_id == tenant_id, ArceusAdminScimConfiguration.status == "active").count()
    open_reviews = db.query(ArceusAdminAccessReview).filter(ArceusAdminAccessReview.tenant_id == tenant_id, ArceusAdminAccessReview.status.in_(["draft", "in_progress", "overdue"])).count()
    active_support = db.query(ArceusAdminSupportAccessGrant).filter(ArceusAdminSupportAccessGrant.tenant_id == tenant_id, ArceusAdminSupportAccessGrant.status == "active").count()
    queued_exports = db.query(ArceusAdminAuditExport).filter(ArceusAdminAuditExport.tenant_id == tenant_id, ArceusAdminAuditExport.status == "queued").count()
    active_policies = db.query(ArceusAdminPolicyBundle).filter(ArceusAdminPolicyBundle.tenant_id == tenant_id, ArceusAdminPolicyBundle.status == "active").count()
    pending_ops = db.query(ArceusAdminTenantOperation).filter(ArceusAdminTenantOperation.tenant_id == tenant_id, ArceusAdminTenantOperation.status.in_(["requested", "approved", "queued", "running"])).count()

    blockers: list[str] = []
    if profiles == 0:
        blockers.append("organization_profile_missing")
    if pending_domains:
        blockers.append("domain_verification_pending")
    if open_reviews:
        blockers.append("access_review_open")
    if pending_ops:
        blockers.append("tenant_operation_pending")
    status = "blocked" if "organization_profile_missing" in blockers else "needs_attention" if blockers else "ready"
    return {
        "status": status,
        "blockers": blockers,
        "profiles": profiles,
        "active_seats": active_seats,
        "pending_domains": pending_domains,
        "active_sso_configurations": active_sso,
        "active_scim_configurations": active_scim,
        "open_access_reviews": open_reviews,
        "active_support_grants": active_support,
        "queued_audit_exports": queued_exports,
        "active_policy_bundles": active_policies,
        "pending_tenant_operations": pending_ops,
    }


def _require_profile(db: Session, *, tenant_id: UUID, profile_id: UUID) -> ArceusAdminOrganizationProfile:
    profile = db.query(ArceusAdminOrganizationProfile).filter(ArceusAdminOrganizationProfile.tenant_id == tenant_id, ArceusAdminOrganizationProfile.id == profile_id).first()
    if profile is None:
        raise ValueError("ORGANIZATION_PROFILE_NOT_FOUND")
    return profile


def _require_verified_domains(db: Session, *, tenant_id: UUID, profile_id: UUID, domains: list[str]) -> None:
    rows = db.query(ArceusAdminDomainVerification).filter(ArceusAdminDomainVerification.tenant_id == tenant_id, ArceusAdminDomainVerification.profile_id == profile_id, ArceusAdminDomainVerification.status == "verified").all()
    verified = {_normalize_domain(row.domain) for row in rows}
    missing = sorted(set(domains) - verified)
    if missing:
        raise ValueError("SSO_ENFORCEMENT_REQUIRES_VERIFIED_DOMAINS:" + ",".join(missing))


def _validate_tenant_operation(payload: TenantOperationRequest) -> None:
    if payload.operation_type == "delete":
        required = {"owner_confirmation", "recent_mfa", "legal_hold_checked", "export_window_acknowledged", "billing_closed"}
        missing = sorted(required - set(payload.safeguards))
        if missing:
            raise ValueError("TENANT_DELETION_SAFEGUARDS_MISSING:" + ",".join(missing))
    if payload.operation_type == "suspend" and not payload.safeguards.get("customer_notification_planned"):
        raise ValueError("TENANT_SUSPENSION_NOTIFICATION_REQUIRED")


def _normalize_domain(domain: str) -> str:
    return domain.strip().lower().removeprefix("https://").removeprefix("http://").strip("/")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value
