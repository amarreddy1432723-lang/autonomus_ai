from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class EnterpriseAdminSchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


OrganizationType = Literal["personal", "startup", "enterprise", "education", "government", "partner"]
OrganizationStatus = Literal["provisioning", "active", "restricted", "suspended", "deleting", "deleted"]
VerificationMethod = Literal["dns_txt", "html_file", "email"]
SsoProviderType = Literal["saml", "oidc", "clerk", "google_workspace", "azure_ad", "okta"]
SsoStatus = Literal["draft", "testing", "active", "disabled", "error"]
SsoEnforcementMode = Literal["optional", "selected_domains", "administrators", "all_members", "except_break_glass"]
ScimStatus = Literal["draft", "active", "disabled", "error"]
SeatType = Literal["owner", "admin", "developer", "reviewer", "viewer", "contractor", "billing", "support"]
SeatStatus = Literal["invited", "active", "suspended", "removed"]
AccessReviewScope = Literal["tenant", "organization", "workspace", "project", "repository", "environment", "support", "billing"]
AuditExportType = Literal["audit", "security", "billing", "access", "compliance", "support"]
PolicyBundleType = Literal["identity", "security", "data", "billing", "deployment", "plugin", "model", "support", "retention", "quota"]
TenantOperationType = Literal["provision", "suspend", "reactivate", "delete", "migrate"]


class OrganizationProfileRequest(EnterpriseAdminSchema):
    display_name: str = Field(min_length=1, max_length=255)
    legal_name: str | None = None
    primary_domain: str | None = Field(default=None, max_length=255)
    organization_type: OrganizationType = "startup"
    region: str = Field(default="us", max_length=80)
    data_residency_region: str = Field(default="us", max_length=80)
    compliance_profiles: list[str] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)
    onboarding_checklist: dict[str, Any] = Field(default_factory=dict)


class OrganizationProfileResponse(EnterpriseAdminSchema):
    id: UUID
    display_name: str
    legal_name: str | None
    primary_domain: str | None
    organization_type: str
    status: str
    region: str
    data_residency_region: str
    compliance_profiles: list[str]
    onboarding_checklist: dict[str, Any]


class OrgUnitRequest(EnterpriseAdminSchema):
    profile_id: UUID
    name: str = Field(min_length=1)
    unit_key: str = Field(min_length=2, max_length=160)
    parent_unit_id: UUID | None = None
    owner_user_id: UUID | None = None
    budgets: dict[str, Any] = Field(default_factory=dict)
    policies: dict[str, Any] = Field(default_factory=dict)
    quotas: dict[str, Any] = Field(default_factory=dict)


class OrgUnitResponse(EnterpriseAdminSchema):
    id: UUID
    profile_id: UUID
    parent_unit_id: UUID | None
    name: str
    unit_key: str
    status: str


class DomainVerificationRequest(EnterpriseAdminSchema):
    profile_id: UUID
    domain: str = Field(min_length=3, max_length=255)
    verification_method: VerificationMethod = "dns_txt"


class DomainVerificationResponse(EnterpriseAdminSchema):
    id: UUID
    profile_id: UUID
    domain: str
    verification_method: str
    verification_token: str
    status: str
    verified_at: datetime | None
    expires_at: datetime


class DomainVerifyRequest(EnterpriseAdminSchema):
    verification_token: str = Field(min_length=8, max_length=200)


class SsoConfigurationRequest(EnterpriseAdminSchema):
    profile_id: UUID
    provider_key: str = Field(min_length=2, max_length=160)
    provider_type: SsoProviderType
    issuer: str = Field(min_length=3)
    client_id: str | None = None
    metadata_url: str | None = None
    status: SsoStatus = "draft"
    enforced: bool = False
    enforcement_mode: SsoEnforcementMode = "optional"
    jit_provisioning: bool = True
    break_glass_enabled: bool = True
    allowed_domains: list[str] = Field(default_factory=list)
    group_mapping: dict[str, Any] = Field(default_factory=dict)
    attribute_mapping: dict[str, Any] = Field(default_factory=dict)
    certificate_expires_at: datetime | None = None


class SsoConfigurationResponse(EnterpriseAdminSchema):
    id: UUID
    provider_key: str
    provider_type: str
    issuer: str
    status: str
    enforced: bool
    enforcement_mode: str
    allowed_domains: list[str]


class ScimConfigurationRequest(EnterpriseAdminSchema):
    profile_id: UUID
    provider_key: str = Field(min_length=2, max_length=160)
    provider_name: str = Field(min_length=1)
    endpoint_url: str = Field(min_length=8)
    bearer_token: str = Field(min_length=12)
    status: ScimStatus = "draft"
    deletion_safeguard_threshold: int = Field(default=25, ge=1, le=500)
    dry_run: bool = True
    group_mapping: dict[str, Any] = Field(default_factory=dict)


class ScimConfigurationResponse(EnterpriseAdminSchema):
    id: UUID
    provider_key: str
    provider_name: str
    endpoint_url: str
    token_checksum_sha256: str
    status: str
    dry_run: bool
    deletion_safeguard_threshold: int


class SeatAssignmentRequest(EnterpriseAdminSchema):
    profile_id: UUID
    user_id: UUID
    plan_key: str = Field(default="free", max_length=80)
    seat_type: SeatType = "developer"
    status: SeatStatus = "active"
    expires_at: datetime | None = None
    cost_center: str | None = Field(default=None, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SeatAssignmentResponse(EnterpriseAdminSchema):
    id: UUID
    profile_id: UUID
    user_id: UUID
    plan_key: str
    seat_type: str
    status: str
    cost_center: str | None


class AccessReviewRequest(EnterpriseAdminSchema):
    profile_id: UUID
    review_key: str = Field(min_length=3, max_length=160)
    scope_type: AccessReviewScope
    scope_id: str = Field(min_length=1, max_length=160)
    reviewer_user_id: UUID | None = None
    due_at: datetime | None = None
    findings: list[dict[str, Any]] = Field(default_factory=list)


class AccessReviewCompleteRequest(EnterpriseAdminSchema):
    decisions: list[dict[str, Any]] = Field(min_length=1)
    findings: list[dict[str, Any]] = Field(default_factory=list)


class AccessReviewResponse(EnterpriseAdminSchema):
    id: UUID
    review_key: str
    scope_type: str
    scope_id: str
    status: str
    findings: list[dict[str, Any]]
    decisions: list[dict[str, Any]]


class AuditExportRequest(EnterpriseAdminSchema):
    profile_id: UUID
    export_type: AuditExportType = "audit"
    reason: str = Field(min_length=5)
    filters: dict[str, Any] = Field(default_factory=dict)


class AuditExportResponse(EnterpriseAdminSchema):
    id: UUID
    export_type: str
    status: str
    reason: str
    expires_at: datetime


class SupportAccessRequest(EnterpriseAdminSchema):
    profile_id: UUID
    support_user_id: UUID
    reason: str = Field(min_length=8)
    ticket_reference: str = Field(min_length=3, max_length=255)
    scope: dict[str, Any] = Field(default_factory=dict)
    permissions: list[str] = Field(default_factory=lambda: ["support.diagnostics.view"])
    duration_minutes: int = Field(default=60, ge=5, le=1440)


class SupportAccessApproveRequest(EnterpriseAdminSchema):
    approved: bool = True
    reason: str = Field(min_length=5)


class SupportAccessResponse(EnterpriseAdminSchema):
    id: UUID
    profile_id: UUID
    support_user_id: UUID
    requested_by: UUID
    approved_by: UUID | None
    status: str
    ticket_reference: str
    expires_at: datetime


class PolicyBundleRequest(EnterpriseAdminSchema):
    profile_id: UUID
    bundle_key: str = Field(min_length=2, max_length=160)
    name: str = Field(min_length=1)
    policy_type: PolicyBundleType
    version: str = Field(default="1", max_length=40)
    scope_type: Literal["platform", "tenant", "organization", "workspace", "project", "environment"] = "tenant"
    scope_id: str | None = None
    rules: dict[str, Any] = Field(default_factory=dict)
    status: Literal["draft", "active", "deprecated", "rejected"] = "draft"


class PolicyBundleResponse(EnterpriseAdminSchema):
    id: UUID
    bundle_key: str
    name: str
    policy_type: str
    version: str
    scope_type: str
    status: str


class TenantOperationRequest(EnterpriseAdminSchema):
    profile_id: UUID
    operation_type: TenantOperationType
    reason: str = Field(min_length=8)
    safeguards: dict[str, Any] = Field(default_factory=dict)
    scheduled_at: datetime | None = None


class TenantOperationResponse(EnterpriseAdminSchema):
    id: UUID
    operation_type: str
    status: str
    reason: str
    current_step: str
    completed_steps: list[str]
    safeguards: dict[str, Any]


class EnterpriseAdminSummaryResponse(EnterpriseAdminSchema):
    status: str
    blockers: list[str]
    profiles: int
    active_seats: int
    pending_domains: int
    active_sso_configurations: int
    active_scim_configurations: int
    open_access_reviews: int
    active_support_grants: int
    queued_audit_exports: int
    active_policy_bundles: int
    pending_tenant_operations: int
