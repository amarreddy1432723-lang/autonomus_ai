from __future__ import annotations

import hashlib
from uuid import uuid4

import pytest

from services.agent.arceus_runtime.enterprise_admin.api_schemas import (
    AccessReviewCompleteRequest,
    AccessReviewRequest,
    DomainVerificationRequest,
    DomainVerifyRequest,
    OrganizationProfileRequest,
    PolicyBundleRequest,
    ScimConfigurationRequest,
    SeatAssignmentRequest,
    SsoConfigurationRequest,
    SupportAccessApproveRequest,
    SupportAccessRequest,
    TenantOperationRequest,
)
from services.agent.arceus_runtime.enterprise_admin.service import (
    approve_support_access,
    assign_seat,
    complete_access_review,
    configure_scim,
    configure_sso,
    create_tenant_operation,
    enterprise_admin_summary,
    open_access_review,
    request_domain_verification,
    request_support_access,
    upsert_organization_profile,
    upsert_policy_bundle,
    verify_domain,
)
from services.shared.arceus_core_models import (
    ArceusAdminAccessReview,
    ArceusAdminAuditExport,
    ArceusAdminDomainVerification,
    ArceusAdminOrganizationProfile,
    ArceusAdminPolicyBundle,
    ArceusAdminScimConfiguration,
    ArceusAdminSeatAssignment,
    ArceusAdminSsoConfiguration,
    ArceusAdminSupportAccessGrant,
    ArceusAdminTenantOperation,
)


def test_domain_verification_gates_enforced_sso() -> None:
    tenant_id = uuid4()
    actor_id = uuid4()
    db = _FakeDb({})
    profile = upsert_organization_profile(db, tenant_id=tenant_id, actor_id=actor_id, payload=OrganizationProfileRequest(display_name="Acme", primary_domain="acme.test"))

    with pytest.raises(ValueError, match="SSO_ENFORCEMENT_REQUIRES_VERIFIED_DOMAINS"):
        configure_sso(
            db,
            tenant_id=tenant_id,
            payload=SsoConfigurationRequest(
                profile_id=profile.id,
                provider_key="okta",
                provider_type="oidc",
                issuer="https://okta.example",
                enforced=True,
                status="active",
                allowed_domains=["acme.test"],
            ),
        )

    domain = request_domain_verification(db, tenant_id=tenant_id, payload=DomainVerificationRequest(profile_id=profile.id, domain="Acme.test"))
    verified = verify_domain(db, tenant_id=tenant_id, domain_id=domain.id, payload=DomainVerifyRequest(verification_token=domain.verification_token))
    assert verified.status == "verified"

    sso = configure_sso(
        db,
        tenant_id=tenant_id,
        payload=SsoConfigurationRequest(
            profile_id=profile.id,
            provider_key="okta",
            provider_type="oidc",
            issuer="https://okta.example",
            enforced=True,
            status="active",
            allowed_domains=["ACME.TEST"],
        ),
    )
    assert isinstance(sso, ArceusAdminSsoConfiguration)
    assert sso.allowed_domains == ["acme.test"]


def test_scim_configuration_stores_checksum_not_bearer_token() -> None:
    tenant_id = uuid4()
    db, profile = _db_with_profile(tenant_id)
    token = "scim-token-secret-value"

    scim = configure_scim(
        db,
        tenant_id=tenant_id,
        payload=ScimConfigurationRequest(
            profile_id=profile.id,
            provider_key="azure",
            provider_name="Azure AD",
            endpoint_url="https://scim.example/v2",
            bearer_token=token,
            status="active",
            dry_run=False,
        ),
    )

    assert isinstance(scim, ArceusAdminScimConfiguration)
    assert scim.token_checksum_sha256 == hashlib.sha256(token.encode("utf-8")).hexdigest()
    assert token not in repr(scim.__dict__)


def test_support_access_is_time_bound_and_customer_approved() -> None:
    tenant_id = uuid4()
    actor_id = uuid4()
    db, profile = _db_with_profile(tenant_id, actor_id=actor_id)

    grant = request_support_access(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        payload=SupportAccessRequest(
            profile_id=profile.id,
            support_user_id=uuid4(),
            reason="Investigate failed deployment",
            ticket_reference="SUP-123",
            duration_minutes=30,
        ),
    )
    assert grant.status == "requested"

    approved = approve_support_access(db, tenant_id=tenant_id, actor_id=actor_id, grant_id=grant.id, payload=SupportAccessApproveRequest(reason="Customer approved ticket scope"))
    assert approved.status == "active"
    assert approved.approved_by == actor_id


def test_seat_assignment_is_upserted_for_user() -> None:
    tenant_id = uuid4()
    actor_id = uuid4()
    db, profile = _db_with_profile(tenant_id, actor_id=actor_id)
    user_id = uuid4()

    first = assign_seat(db, tenant_id=tenant_id, actor_id=actor_id, payload=SeatAssignmentRequest(profile_id=profile.id, user_id=user_id, seat_type="developer", plan_key="team"))
    second = assign_seat(db, tenant_id=tenant_id, actor_id=actor_id, payload=SeatAssignmentRequest(profile_id=profile.id, user_id=user_id, seat_type="admin", plan_key="enterprise"))

    assert isinstance(first, ArceusAdminSeatAssignment)
    assert first.id == second.id
    assert second.seat_type == "admin"
    assert second.plan_key == "enterprise"


def test_access_review_completion_records_findings_and_decisions() -> None:
    tenant_id = uuid4()
    db, profile = _db_with_profile(tenant_id)

    review = open_access_review(db, tenant_id=tenant_id, payload=AccessReviewRequest(profile_id=profile.id, review_key="q3-admin-review", scope_type="tenant", scope_id=str(tenant_id)))
    completed = complete_access_review(
        db,
        tenant_id=tenant_id,
        review_id=review.id,
        payload=AccessReviewCompleteRequest(findings=[{"type": "dormant_admin"}], decisions=[{"principal": "user-1", "action": "remove_admin"}]),
    )

    assert isinstance(completed, ArceusAdminAccessReview)
    assert completed.status == "completed"
    assert completed.findings[0]["type"] == "dormant_admin"


def test_policy_bundle_activation_records_approver_and_effective_time() -> None:
    tenant_id = uuid4()
    actor_id = uuid4()
    db, profile = _db_with_profile(tenant_id, actor_id=actor_id)

    bundle = upsert_policy_bundle(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        payload=PolicyBundleRequest(profile_id=profile.id, bundle_key="model-usage", name="Model Usage Policy", policy_type="model", status="active", rules={"approved_providers": ["openai"]}),
    )

    assert isinstance(bundle, ArceusAdminPolicyBundle)
    assert bundle.status == "active"
    assert bundle.approved_by == actor_id
    assert bundle.effective_at is not None


def test_tenant_operations_require_safeguards() -> None:
    tenant_id = uuid4()
    actor_id = uuid4()
    db, profile = _db_with_profile(tenant_id, actor_id=actor_id)

    with pytest.raises(ValueError, match="TENANT_DELETION_SAFEGUARDS_MISSING"):
        create_tenant_operation(db, tenant_id=tenant_id, actor_id=actor_id, payload=TenantOperationRequest(profile_id=profile.id, operation_type="delete", reason="Contract ended"))

    op = create_tenant_operation(
        db,
        tenant_id=tenant_id,
        actor_id=actor_id,
        payload=TenantOperationRequest(
            profile_id=profile.id,
            operation_type="delete",
            reason="Contract ended",
            safeguards={
                "owner_confirmation": True,
                "recent_mfa": True,
                "legal_hold_checked": True,
                "export_window_acknowledged": True,
                "billing_closed": True,
            },
        ),
    )
    assert isinstance(op, ArceusAdminTenantOperation)
    assert op.current_step == "approval_required"


def test_enterprise_admin_summary_surfaces_control_plane_blockers() -> None:
    tenant_id = uuid4()
    db, profile = _db_with_profile(tenant_id)
    db.add(ArceusAdminDomainVerification(tenant_id=tenant_id, profile_id=profile.id, domain="acme.test", verification_token="token", verification_method="dns_txt", status="pending"))
    db.add(ArceusAdminAccessReview(tenant_id=tenant_id, profile_id=profile.id, review_key="review", scope_type="tenant", scope_id=str(tenant_id), status="in_progress"))

    summary = enterprise_admin_summary(db, tenant_id=tenant_id)

    assert summary["status"] == "needs_attention"
    assert "domain_verification_pending" in summary["blockers"]
    assert "access_review_open" in summary["blockers"]


def _db_with_profile(tenant_id, actor_id=None):
    db = _FakeDb({})
    profile = upsert_organization_profile(db, tenant_id=tenant_id, actor_id=actor_id or uuid4(), payload=OrganizationProfileRequest(display_name="Acme", primary_domain="acme.test"))
    return db, profile


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *_args):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)

    def count(self):
        return len(self.rows)


class _FakeDb:
    def __init__(self, mapping) -> None:
        self.mapping = mapping
        self.added = []

    def query(self, model):
        return _Query(self.mapping.setdefault(model, []))

    def add(self, item) -> None:
        if getattr(item, "id", None) is None:
            item.id = uuid4()
        self.mapping.setdefault(type(item), []).append(item)
        self.added.append(item)

    def flush(self) -> None:
        return None
