import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.sql import func

from .database import Base


MISSION_STATUS_VALUES = (
    "draft",
    "compiling",
    "clarification_required",
    "compiled",
    "organizing",
    "plan_pending",
    "awaiting_plan_approval",
    "ready",
    "running",
    "paused",
    "blocked",
    "reviewing",
    "verifying",
    "awaiting_completion_approval",
    "completed",
    "failed",
    "cancelled",
    "archived",
)


def _uuid_pk() -> Column:
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid())


def _tenant_fk(nullable: bool = False) -> Column:
    return Column(UUID(as_uuid=True), ForeignKey("arceus_tenants.id"), nullable=nullable)


class KernelMutableMixin:
    id = _uuid_pk()
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    version_number = Column(BigInteger, default=1, nullable=False)


class KernelTenantMixin(KernelMutableMixin):
    tenant_id = _tenant_fk()


class ArceusTenant(KernelMutableMixin, Base):
    __tablename__ = "arceus_tenants"

    name = Column(Text, nullable=False)
    slug = Column(String(255), nullable=False)
    status = Column(String(40), default="active", nullable=False)
    plan_key = Column(String(80), default="free", nullable=False)
    settings = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended', 'closed')", name="ck_arceus_tenants_status"),
        UniqueConstraint("slug", name="uq_arceus_tenants_slug"),
        Index("ix_arceus_tenants_status", "status"),
    )


class ArceusUser(KernelMutableMixin, Base):
    __tablename__ = "arceus_users"

    external_identity_id = Column(Text, nullable=False)
    email = Column(String(320), nullable=False)
    display_name = Column(Text)
    avatar_url = Column(Text)
    status = Column(String(40), default="active", nullable=False)
    preferences = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled')", name="ck_arceus_users_status"),
        UniqueConstraint("external_identity_id", name="uq_arceus_users_external_identity"),
        UniqueConstraint("email", name="uq_arceus_users_email"),
    )


class ArceusTenantMembership(KernelTenantMixin, Base):
    __tablename__ = "arceus_tenant_memberships"

    user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    role_key = Column(String(120), nullable=False)
    status = Column(String(40), default="active", nullable=False)
    joined_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('invited', 'active', 'suspended', 'removed')", name="ck_arceus_tenant_memberships_status"),
        UniqueConstraint("tenant_id", "user_id", name="uq_arceus_tenant_membership"),
        Index("ix_arceus_tenant_memberships_user", "user_id", "status"),
        Index("ix_arceus_tenant_memberships_tenant_role", "tenant_id", "role_key", "status"),
    )


class ArceusRolePermission(KernelMutableMixin, Base):
    __tablename__ = "arceus_role_permissions"

    role_key = Column(String(120), nullable=False)
    permission_key = Column(String(240), nullable=False)
    source = Column(String(80), default="builtin", nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("role_key", "permission_key", name="uq_arceus_role_permission"),
        Index("ix_arceus_role_permissions_role", "role_key", "active"),
    )


class ArceusUserSession(KernelTenantMixin, Base):
    __tablename__ = "arceus_user_sessions"

    user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    external_session_id = Column(String(255))
    device_id = Column(String(255))
    ip_address = Column(String(80))
    user_agent = Column(Text)
    status = Column(String(40), default="active", nullable=False)
    risk_score = Column(Integer, default=0, nullable=False)
    mfa_verified = Column(Boolean, default=False, nullable=False)
    device_trusted = Column(Boolean, default=False, nullable=False)
    issued_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    revoked_at = Column(DateTime(timezone=True))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'idle', 'high_risk', 'expired', 'revoked')", name="ck_arceus_user_sessions_status"),
        UniqueConstraint("tenant_id", "external_session_id", name="uq_arceus_user_sessions_external"),
        Index("ix_arceus_user_sessions_user_status", "tenant_id", "user_id", "status"),
        Index("ix_arceus_user_sessions_expires", "tenant_id", "expires_at"),
    )


class ArceusApiToken(KernelTenantMixin, Base):
    __tablename__ = "arceus_api_tokens"

    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    service_account_id = Column(UUID(as_uuid=True))
    name = Column(Text, nullable=False)
    prefix = Column(String(32), nullable=False)
    checksum_sha256 = Column(String(64), nullable=False)
    scopes = Column(JSON, default=list, nullable=False)
    environment = Column(String(80), default="development", nullable=False)
    status = Column(String(40), default="active", nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    last_used_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'revoked', 'expired')", name="ck_arceus_api_tokens_status"),
        UniqueConstraint("tenant_id", "checksum_sha256", name="uq_arceus_api_tokens_checksum"),
        Index("ix_arceus_api_tokens_owner", "tenant_id", "owner_user_id", "status"),
        Index("ix_arceus_api_tokens_prefix", "tenant_id", "prefix"),
    )


class ArceusServiceAccount(KernelTenantMixin, Base):
    __tablename__ = "arceus_service_accounts"

    name = Column(Text, nullable=False)
    purpose = Column(Text)
    scopes = Column(JSON, default=list, nullable=False)
    allowed_environments = Column(JSON, default=list, nullable=False)
    status = Column(String(40), default="active", nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled', 'revoked')", name="ck_arceus_service_accounts_status"),
        UniqueConstraint("tenant_id", "name", name="uq_arceus_service_accounts_name"),
        Index("ix_arceus_service_accounts_status", "tenant_id", "status"),
    )


class ArceusAgentIdentity(KernelTenantMixin, Base):
    __tablename__ = "arceus_agent_identities"

    profile_id = Column(String(160), nullable=False)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    capabilities = Column(JSON, default=list, nullable=False)
    allowed_tools = Column(JSON, default=list, nullable=False)
    maximum_risk_level = Column(String(40), default="medium", nullable=False)
    status = Column(String(40), default="active", nullable=False)
    runtime_claims = Column(JSON, default=dict, nullable=False)
    restrictions = Column(JSON, default=list, nullable=False)

    __table_args__ = (
        CheckConstraint("maximum_risk_level IN ('low', 'medium', 'high', 'critical')", name="ck_arceus_agent_identities_risk"),
        CheckConstraint("status IN ('active', 'suspended', 'revoked')", name="ck_arceus_agent_identities_status"),
        Index("ix_arceus_agent_identities_mission", "tenant_id", "mission_id", "status"),
        Index("ix_arceus_agent_identities_profile", "tenant_id", "profile_id", "status"),
    )


class ArceusAuthorizationDecision(KernelTenantMixin, Base):
    __tablename__ = "arceus_authorization_decisions"

    actor_type = Column(String(80), nullable=False)
    actor_id = Column(String(160), nullable=False)
    action = Column(String(160), nullable=False)
    resource_type = Column(String(120), nullable=False)
    resource_id = Column(String(300))
    decision = Column(String(60), nullable=False)
    allowed = Column(Boolean, default=False, nullable=False)
    reason = Column(Text, nullable=False)
    matched_policies = Column(JSON, default=list, nullable=False)
    obligations = Column(JSON, default=list, nullable=False)
    effective_permissions = Column(JSON, default=list, nullable=False)
    request_payload = Column(JSON, default=dict, nullable=False)
    expires_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "decision IN ('allow', 'deny', 'needs_approval', 'requires_mfa', 'requires_reauth')",
            name="ck_arceus_authorization_decisions_decision",
        ),
        Index("ix_arceus_authorization_actor", "tenant_id", "actor_type", "actor_id", "created_at"),
        Index("ix_arceus_authorization_resource", "tenant_id", "resource_type", "resource_id", "created_at"),
        Index("ix_arceus_authorization_decision", "tenant_id", "decision", "created_at"),
    )


class ArceusIdentityProvider(KernelTenantMixin, Base):
    __tablename__ = "arceus_identity_providers"

    provider_key = Column(String(120), nullable=False)
    provider_type = Column(String(80), nullable=False)
    issuer = Column(Text)
    status = Column(String(40), default="configured", nullable=False)
    capabilities = Column(JSON, default=list, nullable=False)
    scim_enabled = Column(Boolean, default=False, nullable=False)
    enterprise_sso_enabled = Column(Boolean, default=False, nullable=False)
    device_trust_enabled = Column(Boolean, default=False, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("provider_type IN ('clerk', 'oidc', 'saml', 'oauth', 'api_token')", name="ck_arceus_identity_providers_type"),
        CheckConstraint("status IN ('configured', 'active', 'disabled', 'error')", name="ck_arceus_identity_providers_status"),
        UniqueConstraint("tenant_id", "provider_key", name="uq_arceus_identity_provider_key"),
    )


class ArceusAdminOrganizationProfile(KernelTenantMixin, Base):
    __tablename__ = "arceus_admin_organization_profiles"

    display_name = Column(Text, nullable=False)
    legal_name = Column(Text)
    primary_domain = Column(String(255))
    organization_type = Column(String(60), default="startup", nullable=False)
    status = Column(String(40), default="active", nullable=False)
    region = Column(String(80), default="us", nullable=False)
    data_residency_region = Column(String(80), default="us", nullable=False)
    compliance_profiles = Column(JSON, default=list, nullable=False)
    settings = Column(JSON, default=dict, nullable=False)
    onboarding_checklist = Column(JSON, default=dict, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))

    __table_args__ = (
        CheckConstraint("organization_type IN ('personal', 'startup', 'enterprise', 'education', 'government', 'partner')", name="ck_arceus_admin_org_profiles_type"),
        CheckConstraint("status IN ('provisioning', 'active', 'restricted', 'suspended', 'deleting', 'deleted')", name="ck_arceus_admin_org_profiles_status"),
        UniqueConstraint("tenant_id", "primary_domain", name="uq_arceus_admin_org_profiles_domain"),
        Index("ix_arceus_admin_org_profiles_status", "tenant_id", "status"),
    )


class ArceusAdminOrgUnit(KernelTenantMixin, Base):
    __tablename__ = "arceus_admin_org_units"

    profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_admin_organization_profiles.id"), nullable=False)
    parent_unit_id = Column(UUID(as_uuid=True), ForeignKey("arceus_admin_org_units.id"))
    name = Column(Text, nullable=False)
    unit_key = Column(String(160), nullable=False)
    owner_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    status = Column(String(40), default="active", nullable=False)
    budgets = Column(JSON, default=dict, nullable=False)
    policies = Column(JSON, default=dict, nullable=False)
    quotas = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_arceus_admin_org_units_status"),
        UniqueConstraint("tenant_id", "profile_id", "unit_key", name="uq_arceus_admin_org_units_key"),
        Index("ix_arceus_admin_org_units_profile", "tenant_id", "profile_id", "status"),
    )


class ArceusAdminDomainVerification(KernelTenantMixin, Base):
    __tablename__ = "arceus_admin_domain_verifications"

    profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_admin_organization_profiles.id"), nullable=False)
    domain = Column(String(255), nullable=False)
    verification_method = Column(String(40), default="dns_txt", nullable=False)
    verification_token = Column(String(160), nullable=False)
    status = Column(String(40), default="pending", nullable=False)
    verified_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("verification_method IN ('dns_txt', 'html_file', 'email')", name="ck_arceus_admin_domains_method"),
        CheckConstraint("status IN ('pending', 'verified', 'failed', 'expired')", name="ck_arceus_admin_domains_status"),
        UniqueConstraint("tenant_id", "profile_id", "domain", name="uq_arceus_admin_domains_domain"),
        Index("ix_arceus_admin_domains_status", "tenant_id", "status", "expires_at"),
    )


class ArceusAdminSsoConfiguration(KernelTenantMixin, Base):
    __tablename__ = "arceus_admin_sso_configurations"

    profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_admin_organization_profiles.id"), nullable=False)
    provider_key = Column(String(160), nullable=False)
    provider_type = Column(String(80), nullable=False)
    issuer = Column(Text, nullable=False)
    client_id = Column(Text)
    metadata_url = Column(Text)
    status = Column(String(40), default="draft", nullable=False)
    enforced = Column(Boolean, default=False, nullable=False)
    enforcement_mode = Column(String(80), default="optional", nullable=False)
    jit_provisioning = Column(Boolean, default=True, nullable=False)
    break_glass_enabled = Column(Boolean, default=True, nullable=False)
    allowed_domains = Column(JSON, default=list, nullable=False)
    group_mapping = Column(JSON, default=dict, nullable=False)
    attribute_mapping = Column(JSON, default=dict, nullable=False)
    certificate_expires_at = Column(DateTime(timezone=True))
    last_tested_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("provider_type IN ('saml', 'oidc', 'clerk', 'google_workspace', 'azure_ad', 'okta')", name="ck_arceus_admin_sso_provider_type"),
        CheckConstraint("status IN ('draft', 'testing', 'active', 'disabled', 'error')", name="ck_arceus_admin_sso_status"),
        CheckConstraint("enforcement_mode IN ('optional', 'selected_domains', 'administrators', 'all_members', 'except_break_glass')", name="ck_arceus_admin_sso_enforcement"),
        UniqueConstraint("tenant_id", "profile_id", "provider_key", name="uq_arceus_admin_sso_provider"),
        Index("ix_arceus_admin_sso_status", "tenant_id", "status", "enforced"),
    )


class ArceusAdminScimConfiguration(KernelTenantMixin, Base):
    __tablename__ = "arceus_admin_scim_configurations"

    profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_admin_organization_profiles.id"), nullable=False)
    provider_key = Column(String(160), nullable=False)
    provider_name = Column(Text, nullable=False)
    endpoint_url = Column(Text, nullable=False)
    token_checksum_sha256 = Column(String(64), nullable=False)
    status = Column(String(40), default="draft", nullable=False)
    deletion_safeguard_threshold = Column(Integer, default=25, nullable=False)
    dry_run = Column(Boolean, default=True, nullable=False)
    last_sync_at = Column(DateTime(timezone=True))
    sync_stats = Column(JSON, default=dict, nullable=False)
    group_mapping = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'active', 'disabled', 'error')", name="ck_arceus_admin_scim_status"),
        UniqueConstraint("tenant_id", "profile_id", "provider_key", name="uq_arceus_admin_scim_provider"),
        Index("ix_arceus_admin_scim_status", "tenant_id", "status", "last_sync_at"),
    )


class ArceusAdminSeatAssignment(KernelTenantMixin, Base):
    __tablename__ = "arceus_admin_seat_assignments"

    profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_admin_organization_profiles.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    plan_key = Column(String(80), default="free", nullable=False)
    seat_type = Column(String(60), default="developer", nullable=False)
    status = Column(String(40), default="active", nullable=False)
    assigned_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True))
    cost_center = Column(String(160))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("seat_type IN ('owner', 'admin', 'developer', 'reviewer', 'viewer', 'contractor', 'billing', 'support')", name="ck_arceus_admin_seats_type"),
        CheckConstraint("status IN ('invited', 'active', 'suspended', 'removed')", name="ck_arceus_admin_seats_status"),
        UniqueConstraint("tenant_id", "profile_id", "user_id", name="uq_arceus_admin_seats_user"),
        Index("ix_arceus_admin_seats_status", "tenant_id", "profile_id", "status"),
    )


class ArceusAdminAccessReview(KernelTenantMixin, Base):
    __tablename__ = "arceus_admin_access_reviews"

    profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_admin_organization_profiles.id"), nullable=False)
    review_key = Column(String(160), nullable=False)
    scope_type = Column(String(80), nullable=False)
    scope_id = Column(String(160), nullable=False)
    reviewer_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    status = Column(String(40), default="draft", nullable=False)
    due_at = Column(DateTime(timezone=True))
    findings = Column(JSON, default=list, nullable=False)
    decisions = Column(JSON, default=list, nullable=False)
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("scope_type IN ('tenant', 'organization', 'workspace', 'project', 'repository', 'environment', 'support', 'billing')", name="ck_arceus_admin_access_reviews_scope"),
        CheckConstraint("status IN ('draft', 'in_progress', 'completed', 'overdue', 'cancelled')", name="ck_arceus_admin_access_reviews_status"),
        UniqueConstraint("tenant_id", "profile_id", "review_key", name="uq_arceus_admin_access_reviews_key"),
        Index("ix_arceus_admin_access_reviews_status", "tenant_id", "profile_id", "status", "due_at"),
    )


class ArceusAdminAuditExport(KernelTenantMixin, Base):
    __tablename__ = "arceus_admin_audit_exports"

    profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_admin_organization_profiles.id"), nullable=False)
    export_type = Column(String(60), nullable=False)
    status = Column(String(40), default="queued", nullable=False)
    requested_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    reason = Column(Text, nullable=False)
    filters = Column(JSON, default=dict, nullable=False)
    storage_reference = Column(Text)
    checksum_sha256 = Column(String(64))
    expires_at = Column(DateTime(timezone=True), nullable=False)
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("export_type IN ('audit', 'security', 'billing', 'access', 'compliance', 'support')", name="ck_arceus_admin_audit_exports_type"),
        CheckConstraint("status IN ('queued', 'running', 'completed', 'failed', 'expired')", name="ck_arceus_admin_audit_exports_status"),
        Index("ix_arceus_admin_audit_exports_status", "tenant_id", "profile_id", "status", "created_at"),
    )


class ArceusAdminSupportAccessGrant(KernelTenantMixin, Base):
    __tablename__ = "arceus_admin_support_access_grants"

    profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_admin_organization_profiles.id"), nullable=False)
    support_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    requested_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    reason = Column(Text, nullable=False)
    ticket_reference = Column(String(255), nullable=False)
    scope = Column(JSON, default=dict, nullable=False)
    permissions = Column(JSON, default=list, nullable=False)
    status = Column(String(40), default="requested", nullable=False)
    starts_at = Column(DateTime(timezone=True), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    revoked_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('requested', 'approved', 'active', 'expired', 'revoked', 'denied')", name="ck_arceus_admin_support_access_status"),
        Index("ix_arceus_admin_support_access_active", "tenant_id", "profile_id", "status", "expires_at"),
        Index("ix_arceus_admin_support_access_agent", "tenant_id", "support_user_id", "status"),
    )


class ArceusAdminPolicyBundle(KernelTenantMixin, Base):
    __tablename__ = "arceus_admin_policy_bundles"

    profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_admin_organization_profiles.id"), nullable=False)
    bundle_key = Column(String(160), nullable=False)
    name = Column(Text, nullable=False)
    policy_type = Column(String(80), nullable=False)
    version = Column(String(40), default="1", nullable=False)
    scope_type = Column(String(80), default="tenant", nullable=False)
    scope_id = Column(String(160))
    rules = Column(JSON, default=dict, nullable=False)
    status = Column(String(40), default="draft", nullable=False)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    effective_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("policy_type IN ('identity', 'security', 'data', 'billing', 'deployment', 'plugin', 'model', 'support', 'retention', 'quota')", name="ck_arceus_admin_policy_bundles_type"),
        CheckConstraint("scope_type IN ('platform', 'tenant', 'organization', 'workspace', 'project', 'environment')", name="ck_arceus_admin_policy_bundles_scope"),
        CheckConstraint("status IN ('draft', 'active', 'deprecated', 'rejected')", name="ck_arceus_admin_policy_bundles_status"),
        UniqueConstraint("tenant_id", "profile_id", "bundle_key", "version", name="uq_arceus_admin_policy_bundles_version"),
        Index("ix_arceus_admin_policy_bundles_active", "tenant_id", "profile_id", "policy_type", "status"),
    )


class ArceusAdminTenantOperation(KernelTenantMixin, Base):
    __tablename__ = "arceus_admin_tenant_operations"

    profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_admin_organization_profiles.id"), nullable=False)
    operation_type = Column(String(60), nullable=False)
    status = Column(String(40), default="requested", nullable=False)
    requested_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    reason = Column(Text, nullable=False)
    current_step = Column(String(160), default="requested", nullable=False)
    completed_steps = Column(JSON, default=list, nullable=False)
    safeguards = Column(JSON, default=dict, nullable=False)
    scheduled_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("operation_type IN ('provision', 'suspend', 'reactivate', 'delete', 'migrate')", name="ck_arceus_admin_tenant_operations_type"),
        CheckConstraint("status IN ('requested', 'approved', 'queued', 'running', 'completed', 'failed', 'cancelled', 'rolling_back')", name="ck_arceus_admin_tenant_operations_status"),
        Index("ix_arceus_admin_tenant_operations_status", "tenant_id", "profile_id", "operation_type", "status"),
    )


class ArceusTelemetryLog(KernelTenantMixin, Base):
    __tablename__ = "arceus_telemetry_logs"

    trace_id = Column(String(160), nullable=False)
    span_id = Column(String(160))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    workflow_id = Column(UUID(as_uuid=True))
    agent_id = Column(String(160))
    user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    service = Column(String(160), nullable=False)
    level = Column(String(20), nullable=False)
    message = Column(Text, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("level IN ('TRACE', 'DEBUG', 'INFO', 'WARN', 'ERROR', 'FATAL')", name="ck_arceus_telemetry_logs_level"),
        Index("ix_arceus_telemetry_logs_trace", "tenant_id", "trace_id", "occurred_at"),
        Index("ix_arceus_telemetry_logs_mission", "tenant_id", "mission_id", "occurred_at"),
        Index("ix_arceus_telemetry_logs_level", "tenant_id", "level", "occurred_at"),
    )


class ArceusMetricSample(KernelTenantMixin, Base):
    __tablename__ = "arceus_metric_samples"

    metric_key = Column(String(160), nullable=False)
    metric_type = Column(String(40), default="gauge", nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String(80), default="count", nullable=False)
    service = Column(String(160))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    workflow_id = Column(UUID(as_uuid=True))
    model_key = Column(String(160))
    provider_key = Column(String(160))
    labels = Column(JSON, default=dict, nullable=False)
    observed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("metric_type IN ('counter', 'gauge', 'histogram', 'summary')", name="ck_arceus_metric_samples_type"),
        Index("ix_arceus_metric_samples_key", "tenant_id", "metric_key", "observed_at"),
        Index("ix_arceus_metric_samples_mission", "tenant_id", "mission_id", "observed_at"),
    )


class ArceusTrace(Base):
    __tablename__ = "arceus_traces"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    trace_id = Column(String(160), nullable=False)
    root_span_id = Column(String(160))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    workflow_id = Column(UUID(as_uuid=True))
    user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    service = Column(String(160), nullable=False)
    name = Column(Text, nullable=False)
    status = Column(String(40), default="running", nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True))
    duration_ms = Column(Float)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('running', 'ok', 'error', 'cancelled')", name="ck_arceus_traces_status"),
        UniqueConstraint("tenant_id", "trace_id", name="uq_arceus_traces_trace_id"),
        Index("ix_arceus_traces_mission", "tenant_id", "mission_id", "started_at"),
    )


class ArceusSpan(Base):
    __tablename__ = "arceus_spans"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    trace_id = Column(String(160), nullable=False)
    span_id = Column(String(160), nullable=False)
    parent_span_id = Column(String(160))
    span_type = Column(String(80), nullable=False)
    name = Column(Text, nullable=False)
    service = Column(String(160), nullable=False)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    workflow_id = Column(UUID(as_uuid=True))
    node_id = Column(String(160))
    agent_id = Column(String(160))
    status = Column(String(40), default="ok", nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    ended_at = Column(DateTime(timezone=True))
    duration_ms = Column(Float)
    attributes = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('ok', 'error', 'cancelled')", name="ck_arceus_spans_status"),
        UniqueConstraint("tenant_id", "trace_id", "span_id", name="uq_arceus_spans_trace_span"),
        Index("ix_arceus_spans_trace", "tenant_id", "trace_id", "started_at"),
        Index("ix_arceus_spans_type", "tenant_id", "span_type", "started_at"),
    )


class ArceusAlert(Base):
    __tablename__ = "arceus_alerts"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    alert_key = Column(String(160), nullable=False)
    severity = Column(String(20), nullable=False)
    status = Column(String(40), default="firing", nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    source = Column(String(160), default="arceus", nullable=False)
    trace_id = Column(String(160))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    labels = Column(JSON, default=dict, nullable=False)
    annotations = Column(JSON, default=dict, nullable=False)
    fired_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("severity IN ('P0', 'P1', 'P2', 'P3')", name="ck_arceus_alerts_severity"),
        CheckConstraint("status IN ('firing', 'acknowledged', 'resolved', 'suppressed')", name="ck_arceus_alerts_status"),
        Index("ix_arceus_alerts_status", "tenant_id", "status", "severity", "fired_at"),
    )


class ArceusIncident(Base):
    __tablename__ = "arceus_incidents"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    incident_key = Column(String(160), nullable=False)
    severity = Column(String(20), nullable=False)
    status = Column(String(40), default="detected", nullable=False)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    assigned_to = Column(String(160))
    related_alert_ids = Column(JSON, default=list, nullable=False)
    trace_id = Column(String(160))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    aiops_recommendations = Column(JSON, default=list, nullable=False)
    postmortem = Column(JSON, default=dict, nullable=False)
    opened_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("severity IN ('P0', 'P1', 'P2', 'P3')", name="ck_arceus_incidents_severity"),
        CheckConstraint("status IN ('detected', 'classified', 'assigned', 'investigating', 'resolved', 'postmortem')", name="ck_arceus_incidents_status"),
        UniqueConstraint("tenant_id", "incident_key", name="uq_arceus_incidents_key"),
        Index("ix_arceus_incidents_status", "tenant_id", "status", "severity", "opened_at"),
    )


class ArceusSecurityAsset(KernelTenantMixin, Base):
    __tablename__ = "arceus_security_assets"

    organization_id = Column(UUID(as_uuid=True))
    workspace_id = Column(UUID(as_uuid=True))
    project_id = Column(UUID(as_uuid=True))
    asset_type = Column(String(80), nullable=False)
    external_reference = Column(Text)
    name = Column(Text, nullable=False)
    description = Column(Text)
    owner_identity_id = Column(String(160))
    owner_team_id = Column(UUID(as_uuid=True))
    criticality = Column(String(40), default="medium", nullable=False)
    internet_exposed = Column(Boolean, default=False, nullable=False)
    environment_type = Column(String(80))
    data_classifications = Column(JSON, default=list, nullable=False)
    tags = Column(JSON, default=list, nullable=False)
    relationships = Column(JSON, default=list, nullable=False)
    first_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "asset_type IN ('repository', 'source_file', 'dependency', 'container_image', 'build_artifact', 'application', 'api', 'service', 'database', 'cloud_resource', 'kubernetes_cluster', 'environment', 'identity', 'service_account', 'agent', 'plugin', 'secret', 'model_provider', 'deployment', 'data_store')",
            name="ck_arceus_security_assets_type",
        ),
        CheckConstraint("criticality IN ('low', 'medium', 'high', 'critical')", name="ck_arceus_security_assets_criticality"),
        UniqueConstraint("tenant_id", "asset_type", "external_reference", name="uq_arceus_security_assets_external_ref"),
        Index("ix_arceus_security_assets_scope", "tenant_id", "project_id", "asset_type"),
        Index("ix_arceus_security_assets_exposure", "tenant_id", "environment_type", "internet_exposed", "criticality"),
    )


class ArceusSecurityFinding(KernelTenantMixin, Base):
    __tablename__ = "arceus_security_findings"

    organization_id = Column(UUID(as_uuid=True))
    workspace_id = Column(UUID(as_uuid=True))
    project_id = Column(UUID(as_uuid=True))
    asset_id = Column(UUID(as_uuid=True), ForeignKey("arceus_security_assets.id"), nullable=False)
    source = Column(String(160), nullable=False)
    source_finding_id = Column(String(255))
    fingerprint = Column(String(128), nullable=False)
    category = Column(String(80), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, default="", nullable=False)
    severity = Column(String(40), nullable=False)
    status = Column(String(40), default="open", nullable=False)
    affected_component = Column(Text)
    vulnerability_ids = Column(JSON, default=list, nullable=False)
    location = Column(JSON, default=dict, nullable=False)
    evidence_references = Column(JSON, default=list, nullable=False)
    enrichment = Column(JSON, default=dict, nullable=False)
    remediation = Column(JSON, default=dict, nullable=False)
    first_detected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_detected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "category IN ('vulnerability', 'misconfiguration', 'secret_exposure', 'malware', 'identity_risk', 'policy_violation', 'runtime_threat', 'supply_chain', 'data_exposure', 'agent_behavior', 'compliance_gap')",
            name="ck_arceus_security_findings_category",
        ),
        CheckConstraint("severity IN ('informational', 'low', 'medium', 'high', 'critical')", name="ck_arceus_security_findings_severity"),
        CheckConstraint("status IN ('open', 'triaged', 'accepted', 'remediating', 'resolved', 'false_positive', 'suppressed')", name="ck_arceus_security_findings_status"),
        UniqueConstraint("tenant_id", "fingerprint", name="uq_arceus_security_findings_fingerprint"),
        Index("ix_arceus_security_findings_asset_status", "tenant_id", "asset_id", "status"),
        Index("ix_arceus_security_findings_risk_queue", "tenant_id", "severity", "status", "last_detected_at"),
    )


class ArceusSecurityRiskScore(KernelTenantMixin, Base):
    __tablename__ = "arceus_security_risk_scores"

    finding_id = Column(UUID(as_uuid=True), ForeignKey("arceus_security_findings.id"), nullable=False)
    base_severity_score = Column(Integer, default=0, nullable=False)
    exploitability_score = Column(Integer, default=0, nullable=False)
    reachability_score = Column(Integer, default=0, nullable=False)
    exposure_score = Column(Integer, default=0, nullable=False)
    asset_criticality_score = Column(Integer, default=0, nullable=False)
    privilege_impact_score = Column(Integer, default=0, nullable=False)
    data_impact_score = Column(Integer, default=0, nullable=False)
    threat_activity_score = Column(Integer, default=0, nullable=False)
    compensating_control_reduction = Column(Integer, default=0, nullable=False)
    total_score = Column(Integer, default=0, nullable=False)
    risk_level = Column(String(40), default="low", nullable=False)
    explanation = Column(JSON, default=dict, nullable=False)
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("risk_level IN ('low', 'moderate', 'high', 'critical', 'emergency')", name="ck_arceus_security_risk_scores_level"),
        Index("ix_arceus_security_risk_scores_finding", "tenant_id", "finding_id", "calculated_at"),
        Index("ix_arceus_security_risk_scores_level", "tenant_id", "risk_level", "total_score"),
    )


class ArceusThreatModel(KernelTenantMixin, Base):
    __tablename__ = "arceus_threat_models"

    organization_id = Column(UUID(as_uuid=True))
    project_id = Column(UUID(as_uuid=True), nullable=False)
    title = Column(Text, nullable=False)
    scope_asset_ids = Column(JSON, default=list, nullable=False)
    architecture_artifact_id = Column(UUID(as_uuid=True))
    trust_boundaries = Column(JSON, default=list, nullable=False)
    data_flows = Column(JSON, default=list, nullable=False)
    threats = Column(JSON, default=list, nullable=False)
    status = Column(String(40), default="draft", nullable=False)
    created_by = Column(UUID(as_uuid=True))

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'review', 'approved', 'outdated')", name="ck_arceus_threat_models_status"),
        Index("ix_arceus_threat_models_project", "tenant_id", "project_id", "status"),
    )


class ArceusSecurityIncident(Base):
    __tablename__ = "arceus_security_incidents"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    organization_id = Column(UUID(as_uuid=True))
    case_id = Column(UUID(as_uuid=True))
    title = Column(Text, nullable=False)
    severity = Column(String(40), nullable=False)
    status = Column(String(40), default="declared", nullable=False)
    incident_commander_id = Column(UUID(as_uuid=True))
    affected_asset_ids = Column(JSON, default=list, nullable=False)
    finding_ids = Column(JSON, default=list, nullable=False)
    evidence_vault_id = Column(UUID(as_uuid=True))
    regulatory_notification_required = Column(Boolean, default=False, nullable=False)
    declared_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    contained_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))
    closed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("severity IN ('low', 'medium', 'high', 'critical', 'emergency')", name="ck_arceus_security_incidents_severity"),
        CheckConstraint("status IN ('declared', 'triaged', 'investigating', 'contained', 'resolved', 'closed')", name="ck_arceus_security_incidents_status"),
        Index("ix_arceus_security_incidents_status", "tenant_id", "status", "severity", "declared_at"),
    )


class ArceusSecurityResponseAction(Base):
    __tablename__ = "arceus_security_response_actions"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    incident_id = Column(UUID(as_uuid=True), ForeignKey("arceus_security_incidents.id"))
    finding_id = Column(UUID(as_uuid=True), ForeignKey("arceus_security_findings.id"))
    action_type = Column(String(120), nullable=False)
    target_id = Column(Text, nullable=False)
    risk_level = Column(String(40), nullable=False)
    automatic_allowed = Column(Boolean, default=False, nullable=False)
    approval_status = Column(String(40), default="not_required", nullable=False)
    execution_status = Column(String(40), default="queued", nullable=False)
    requested_by = Column(UUID(as_uuid=True))
    approved_by = Column(UUID(as_uuid=True))
    trace_id = Column(String(160), nullable=False)
    idempotency_key = Column(String(160), nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    executed_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("risk_level IN ('low', 'moderate', 'high', 'critical', 'emergency')", name="ck_arceus_security_response_actions_risk"),
        CheckConstraint("approval_status IN ('not_required', 'pending', 'approved', 'rejected')", name="ck_arceus_security_response_actions_approval"),
        CheckConstraint("execution_status IN ('queued', 'blocked', 'executing', 'completed', 'failed', 'cancelled')", name="ck_arceus_security_response_actions_execution"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_arceus_security_response_actions_idempotency"),
        Index("ix_arceus_security_response_actions_status", "tenant_id", "execution_status", "risk_level"),
    )


class ArceusSecurityException(Base):
    __tablename__ = "arceus_security_exceptions"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    organization_id = Column(UUID(as_uuid=True))
    finding_id = Column(UUID(as_uuid=True), ForeignKey("arceus_security_findings.id"), nullable=False)
    reason = Column(Text, nullable=False)
    compensating_controls = Column(JSON, default=list, nullable=False)
    approved_by = Column(UUID(as_uuid=True), nullable=False)
    approved_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    review_frequency_days = Column(Integer, default=30, nullable=False)
    status = Column(String(40), default="active", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'expired', 'revoked', 'replaced')", name="ck_arceus_security_exceptions_status"),
        Index("ix_arceus_security_exceptions_finding", "tenant_id", "finding_id", "status", "expires_at"),
    )


class ArceusSecurityEvidence(Base):
    __tablename__ = "arceus_security_evidence"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    organization_id = Column(UUID(as_uuid=True))
    incident_id = Column(UUID(as_uuid=True), ForeignKey("arceus_security_incidents.id"))
    finding_id = Column(UUID(as_uuid=True), ForeignKey("arceus_security_findings.id"))
    evidence_type = Column(String(80), nullable=False)
    storage_reference = Column(Text, nullable=False)
    content_digest = Column(String(160), nullable=False)
    collected_by = Column(UUID(as_uuid=True), nullable=False)
    collected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    retention_until = Column(DateTime(timezone=True))
    legal_hold = Column(Boolean, default=False, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "content_digest", "storage_reference", name="uq_arceus_security_evidence_digest_ref"),
        Index("ix_arceus_security_evidence_scope", "tenant_id", "incident_id", "finding_id"),
    )


class ArceusProviderHealth(Base):
    __tablename__ = "arceus_provider_health"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    provider_key = Column(String(160), nullable=False)
    model_key = Column(String(160))
    availability = Column(Float, default=1.0, nullable=False)
    latency_ms = Column(Float, default=0.0, nullable=False)
    error_rate = Column(Float, default=0.0, nullable=False)
    rate_limited = Column(Boolean, default=False, nullable=False)
    cost_per_1k_tokens = Column(Float, default=0.0, nullable=False)
    status = Column(String(40), default="healthy", nullable=False)
    observed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('healthy', 'degraded', 'down', 'rate_limited')", name="ck_arceus_provider_health_status"),
        Index("ix_arceus_provider_health_provider", "tenant_id", "provider_key", "observed_at"),
    )


class ArceusMissionStatistic(Base):
    __tablename__ = "arceus_mission_statistics"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    status = Column(String(60), nullable=False)
    duration_ms = Column(Float, default=0.0, nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    cost_usd = Column(Numeric(12, 6), default=0, nullable=False)
    prompt_tokens = Column(BigInteger, default=0, nullable=False)
    completion_tokens = Column(BigInteger, default=0, nullable=False)
    success = Column(Boolean, default=False, nullable=False)
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_arceus_mission_statistics_mission", "tenant_id", "mission_id", "recorded_at"),
        Index("ix_arceus_mission_statistics_status", "tenant_id", "status", "recorded_at"),
    )


class ArceusCostStatistic(Base):
    __tablename__ = "arceus_cost_statistics"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    scope_type = Column(String(80), nullable=False)
    scope_id = Column(String(160), nullable=False)
    cost_type = Column(String(80), nullable=False)
    amount_usd = Column(Numeric(12, 6), default=0, nullable=False)
    units = Column(Float, default=0.0, nullable=False)
    provider_key = Column(String(160))
    model_key = Column(String(160))
    observed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_arceus_cost_statistics_scope", "tenant_id", "scope_type", "scope_id", "observed_at"),
        Index("ix_arceus_cost_statistics_type", "tenant_id", "cost_type", "observed_at"),
    )


class ArceusDashboardConfig(Base):
    __tablename__ = "arceus_dashboard_configs"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    dashboard_key = Column(String(160), nullable=False)
    name = Column(Text, nullable=False)
    audience = Column(String(80), nullable=False)
    widgets = Column(JSON, default=list, nullable=False)
    filters = Column(JSON, default=dict, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "dashboard_key", name="uq_arceus_dashboard_configs_key"),
        Index("ix_arceus_dashboard_configs_audience", "tenant_id", "audience", "active"),
    )


class ArceusTelemetryExporterConfig(Base):
    __tablename__ = "arceus_telemetry_exporter_configs"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    exporter_key = Column(String(160), nullable=False)
    exporter_type = Column(String(80), nullable=False)
    target = Column(Text, nullable=False)
    status = Column(String(40), default="configured", nullable=False)
    signal_types = Column(JSON, default=list, nullable=False)
    headers = Column(JSON, default=dict, nullable=False)
    sample_rate = Column(Float, default=1.0, nullable=False)
    last_export_at = Column(DateTime(timezone=True))
    last_error = Column(JSON, default=dict, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("exporter_type IN ('prometheus', 'loki', 'tempo', 'otlp_http', 'otlp_grpc', 'sentry')", name="ck_arceus_telemetry_exporter_configs_type"),
        CheckConstraint("status IN ('configured', 'active', 'disabled', 'error')", name="ck_arceus_telemetry_exporter_configs_status"),
        UniqueConstraint("tenant_id", "exporter_key", name="uq_arceus_telemetry_exporter_configs_key"),
        Index("ix_arceus_telemetry_exporter_configs_type", "tenant_id", "exporter_type", "active"),
    )


class ArceusAlertDeliveryChannel(Base):
    __tablename__ = "arceus_alert_delivery_channels"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    channel_key = Column(String(160), nullable=False)
    channel_type = Column(String(80), nullable=False)
    display_name = Column(Text, nullable=False)
    target = Column(Text, nullable=False)
    severity_filter = Column(JSON, default=list, nullable=False)
    status = Column(String(40), default="active", nullable=False)
    secret_ref = Column(String(255))
    metadata_json = Column(JSON, default=dict, nullable=False)
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("channel_type IN ('slack', 'email', 'teams', 'webhook')", name="ck_arceus_alert_delivery_channels_type"),
        CheckConstraint("status IN ('active', 'disabled', 'error')", name="ck_arceus_alert_delivery_channels_status"),
        UniqueConstraint("tenant_id", "channel_key", name="uq_arceus_alert_delivery_channels_key"),
        Index("ix_arceus_alert_delivery_channels_type", "tenant_id", "channel_type", "active"),
    )


class ArceusAlertDeliveryAttempt(Base):
    __tablename__ = "arceus_alert_delivery_attempts"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    alert_id = Column(UUID(as_uuid=True), ForeignKey("arceus_alerts.id"), nullable=False)
    channel_id = Column(UUID(as_uuid=True), ForeignKey("arceus_alert_delivery_channels.id"), nullable=False)
    status = Column(String(40), default="queued", nullable=False)
    attempt_number = Column(Integer, default=1, nullable=False)
    delivered_at = Column(DateTime(timezone=True))
    response = Column(JSON, default=dict, nullable=False)
    error = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('queued', 'sent', 'failed', 'suppressed')", name="ck_arceus_alert_delivery_attempts_status"),
        Index("ix_arceus_alert_delivery_attempts_alert", "tenant_id", "alert_id", "status"),
        Index("ix_arceus_alert_delivery_attempts_channel", "tenant_id", "channel_id", "created_at"),
    )


class ArceusRecoveryAction(Base):
    __tablename__ = "arceus_recovery_actions"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    action_key = Column(String(160), nullable=False)
    title = Column(Text, nullable=False)
    trigger_alert_key = Column(String(160))
    incident_id = Column(UUID(as_uuid=True), ForeignKey("arceus_incidents.id"))
    risk_level = Column(String(40), default="low", nullable=False)
    policy_status = Column(String(60), default="pending_policy", nullable=False)
    execution_status = Column(String(60), default="proposed", nullable=False)
    action_type = Column(String(120), nullable=False)
    parameters = Column(JSON, default=dict, nullable=False)
    approval_required = Column(Boolean, default=True, nullable=False)
    approved_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    evidence = Column(JSON, default=list, nullable=False)
    result = Column(JSON, default=dict, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    executed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("risk_level IN ('low', 'moderate', 'high', 'critical')", name="ck_arceus_recovery_actions_risk"),
        CheckConstraint("policy_status IN ('pending_policy', 'allowed', 'needs_approval', 'denied')", name="ck_arceus_recovery_actions_policy"),
        CheckConstraint("execution_status IN ('proposed', 'queued', 'executed', 'failed', 'cancelled', 'blocked')", name="ck_arceus_recovery_actions_execution"),
        UniqueConstraint("tenant_id", "action_key", name="uq_arceus_recovery_actions_key"),
        Index("ix_arceus_recovery_actions_status", "tenant_id", "policy_status", "execution_status", "created_at"),
    )


class ArceusPluginPublisher(KernelTenantMixin, Base):
    __tablename__ = "arceus_plugin_publishers"

    publisher_key = Column(String(160), nullable=False)
    display_name = Column(Text, nullable=False)
    verification_level = Column(String(60), default="unverified", nullable=False)
    signing_key_id = Column(String(255))
    status = Column(String(40), default="active", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint(
            "verification_level IN ('unverified', 'identity_verified', 'organization_verified', 'trusted_partner', 'arceus')",
            name="ck_arceus_plugin_publishers_verification",
        ),
        CheckConstraint("status IN ('active', 'suspended', 'revoked')", name="ck_arceus_plugin_publishers_status"),
        UniqueConstraint("tenant_id", "publisher_key", name="uq_arceus_plugin_publishers_key"),
        Index("ix_arceus_plugin_publishers_status", "tenant_id", "verification_level", "status"),
    )


class ArceusPlugin(KernelTenantMixin, Base):
    __tablename__ = "arceus_plugins"

    plugin_key = Column(String(180), nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text)
    publisher_id = Column(UUID(as_uuid=True), ForeignKey("arceus_plugin_publishers.id"), nullable=False)
    category = Column(String(80), default="private", nullable=False)
    latest_version_id = Column(UUID(as_uuid=True))
    status = Column(String(40), default="draft", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("category IN ('official', 'partner', 'private', 'community')", name="ck_arceus_plugins_category"),
        CheckConstraint("status IN ('draft', 'published', 'deprecated', 'revoked')", name="ck_arceus_plugins_status"),
        UniqueConstraint("tenant_id", "plugin_key", name="uq_arceus_plugins_key"),
        Index("ix_arceus_plugins_publisher", "tenant_id", "publisher_id", "status"),
    )


class ArceusPluginVersion(KernelMutableMixin, Base):
    __tablename__ = "arceus_plugin_versions"

    plugin_id = Column(UUID(as_uuid=True), ForeignKey("arceus_plugins.id"), nullable=False)
    version = Column(String(80), nullable=False)
    manifest = Column(JSON, default=dict, nullable=False)
    manifest_digest = Column(String(128), nullable=False)
    package_digest = Column(String(128))
    signing_key_id = Column(String(255))
    signature = Column(Text)
    status = Column(String(60), default="draft", nullable=False)
    security_score = Column(Float, default=0.0, nullable=False)
    compatibility = Column(JSON, default=dict, nullable=False)
    published_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'uploaded', 'scanning', 'pending_review', 'approved', 'published', 'deprecated', 'yanked', 'revoked')",
            name="ck_arceus_plugin_versions_status",
        ),
        UniqueConstraint("plugin_id", "version", name="uq_arceus_plugin_versions_version"),
        Index("ix_arceus_plugin_versions_status", "plugin_id", "status"),
    )


class ArceusPluginInstallation(KernelTenantMixin, Base):
    __tablename__ = "arceus_plugin_installations"

    plugin_id = Column(UUID(as_uuid=True), ForeignKey("arceus_plugins.id"), nullable=False)
    plugin_version_id = Column(UUID(as_uuid=True), ForeignKey("arceus_plugin_versions.id"), nullable=False)
    scope_type = Column(String(60), default="organization", nullable=False)
    scope_id = Column(String(255), nullable=False)
    status = Column(String(60), default="pending_review", nullable=False)
    installed_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    installed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    enabled_at = Column(DateTime(timezone=True))
    disabled_at = Column(DateTime(timezone=True))
    update_policy = Column(String(60), default="manual", nullable=False)
    configuration = Column(JSON, default=dict, nullable=False)
    secret_references = Column(JSON, default=list, nullable=False)
    extension_identity_id = Column(String(255), nullable=False)
    last_health = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("scope_type IN ('organization', 'workspace', 'repository', 'user')", name="ck_arceus_plugin_installations_scope"),
        CheckConstraint(
            "status IN ('pending_review', 'installing', 'installed', 'configuration_required', 'enabled', 'disabled', 'update_available', 'updating', 'suspended', 'revoked', 'removing', 'removed', 'failed')",
            name="ck_arceus_plugin_installations_status",
        ),
        CheckConstraint("update_policy IN ('manual', 'security_only', 'compatible_minor', 'automatic')", name="ck_arceus_plugin_installations_update_policy"),
        UniqueConstraint("tenant_id", "plugin_id", "scope_type", "scope_id", name="uq_arceus_plugin_installations_scope"),
        Index("ix_arceus_plugin_installations_status", "tenant_id", "scope_type", "status"),
    )


class ArceusPluginInstallationPermission(KernelMutableMixin, Base):
    __tablename__ = "arceus_plugin_installation_permissions"

    installation_id = Column(UUID(as_uuid=True), ForeignKey("arceus_plugin_installations.id"), nullable=False)
    permission_key = Column(String(220), nullable=False)
    scope = Column(JSON, default=dict, nullable=False)
    conditions = Column(JSON, default=dict, nullable=False)
    risk_level = Column(String(40), default="low", nullable=False)
    granted_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    expires_at = Column(DateTime(timezone=True))
    revoked_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("risk_level IN ('low', 'moderate', 'high', 'critical')", name="ck_arceus_plugin_installation_permissions_risk"),
        UniqueConstraint("installation_id", "permission_key", name="uq_arceus_plugin_installation_permissions_key"),
        Index("ix_arceus_plugin_installation_permissions_installation", "installation_id", "revoked_at"),
    )


class ArceusPluginInvocation(KernelTenantMixin, Base):
    __tablename__ = "arceus_plugin_invocations"

    installation_id = Column(UUID(as_uuid=True), ForeignKey("arceus_plugin_installations.id"), nullable=False)
    capability_id = Column(String(220), nullable=False)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    workflow_node_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_nodes.id"))
    actor_identity_id = Column(String(255), nullable=False)
    extension_identity_id = Column(String(255), nullable=False)
    trace_id = Column(String(120), nullable=False)
    status = Column(String(40), default="authorized", nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    duration_ms = Column(Integer)
    input_fingerprint = Column(String(128))
    output_fingerprint = Column(String(128))
    error_code = Column(String(120))
    receipt = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('authorized', 'running', 'succeeded', 'failed', 'denied', 'cancelled', 'timeout')", name="ck_arceus_plugin_invocations_status"),
        Index("ix_arceus_plugin_invocations_installation", "tenant_id", "installation_id", "started_at"),
        Index("ix_arceus_plugin_invocations_mission", "tenant_id", "mission_id", "status"),
    )


class ArceusPluginSecurityFinding(KernelMutableMixin, Base):
    __tablename__ = "arceus_plugin_security_findings"

    plugin_version_id = Column(UUID(as_uuid=True), ForeignKey("arceus_plugin_versions.id"), nullable=False)
    category = Column(String(100), nullable=False)
    severity = Column(String(40), default="low", nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text)
    rule_id = Column(String(160))
    blocking = Column(Boolean, default=False, nullable=False)
    status = Column(String(40), default="open", nullable=False)
    resolved_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("severity IN ('info', 'low', 'medium', 'high', 'critical')", name="ck_arceus_plugin_security_findings_severity"),
        CheckConstraint("status IN ('open', 'acknowledged', 'resolved', 'waived')", name="ck_arceus_plugin_security_findings_status"),
        Index("ix_arceus_plugin_security_findings_version", "plugin_version_id", "severity", "status"),
    )


class ArceusPluginUsageEvent(KernelTenantMixin, Base):
    __tablename__ = "arceus_plugin_usage_events"

    plugin_id = Column(UUID(as_uuid=True), ForeignKey("arceus_plugins.id"), nullable=False)
    installation_id = Column(UUID(as_uuid=True), ForeignKey("arceus_plugin_installations.id"), nullable=False)
    invocation_id = Column(UUID(as_uuid=True), ForeignKey("arceus_plugin_invocations.id"))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    metric = Column(String(100), nullable=False)
    quantity = Column(Numeric(18, 6), default=0, nullable=False)
    idempotency_key = Column(String(180), nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_arceus_plugin_usage_events_idempotency"),
        Index("ix_arceus_plugin_usage_events_plugin", "tenant_id", "plugin_id", "metric", "occurred_at"),
    )


class ArceusProject(KernelTenantMixin, Base):
    __tablename__ = "arceus_projects"

    name = Column(Text, nullable=False)
    slug = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(40), default="active", nullable=False)
    settings = Column(JSON, default=dict, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    archived_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('active', 'paused', 'archived')", name="ck_arceus_projects_status"),
        UniqueConstraint("tenant_id", "slug", name="uq_arceus_projects_tenant_slug"),
        Index("ix_arceus_projects_tenant_status", "tenant_id", "status"),
    )


class ArceusProjectRepository(KernelTenantMixin, Base):
    __tablename__ = "arceus_project_repositories"

    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"), nullable=False)
    provider = Column(String(40), nullable=False)
    external_repository_id = Column(Text)
    repository_url = Column(Text, nullable=False)
    default_branch = Column(Text, default="main", nullable=False)
    local_workspace_path = Column(Text)
    status = Column(String(40), default="active", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("provider IN ('github', 'gitlab', 'bitbucket', 'local')", name="ck_arceus_project_repositories_provider"),
        CheckConstraint("status IN ('active', 'disconnected', 'archived')", name="ck_arceus_project_repositories_status"),
        UniqueConstraint("tenant_id", "project_id", "repository_url", name="uq_arceus_project_repository_url"),
        Index("ix_arceus_project_repositories_project", "tenant_id", "project_id", "status"),
    )


class ArceusCollaborationTeam(KernelTenantMixin, Base):
    __tablename__ = "arceus_collaboration_teams"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_organizations.id"))
    name = Column(Text, nullable=False)
    slug = Column(String(255), nullable=False)
    description = Column(Text)
    lead_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    status = Column(String(60), default="active", nullable=False)
    settings = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_arceus_collaboration_teams_slug"),
        CheckConstraint("status IN ('active', 'archived', 'suspended')", name="ck_arceus_collaboration_teams_status"),
        Index("ix_arceus_collaboration_teams_org", "tenant_id", "organization_id", "status"),
    )


class ArceusCollaborationTeamMember(KernelTenantMixin, Base):
    __tablename__ = "arceus_collaboration_team_members"

    team_id = Column(UUID(as_uuid=True), ForeignKey("arceus_collaboration_teams.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"))
    member_type = Column(String(60), default="human", nullable=False)
    role_key = Column(String(120), default="member", nullable=False)
    status = Column(String(60), default="active", nullable=False)
    joined_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "team_id", "user_id", "participant_id", name="uq_arceus_team_member_identity"),
        CheckConstraint("member_type IN ('human', 'ai_agent', 'service')", name="ck_arceus_team_members_type"),
        CheckConstraint("status IN ('invited', 'active', 'suspended', 'removed')", name="ck_arceus_team_members_status"),
        Index("ix_arceus_team_members_team", "tenant_id", "team_id", "status"),
    )


class ArceusProjectMember(KernelTenantMixin, Base):
    __tablename__ = "arceus_project_members"

    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"))
    team_id = Column(UUID(as_uuid=True), ForeignKey("arceus_collaboration_teams.id"))
    role_key = Column(String(120), default="observer", nullable=False)
    permissions = Column(JSON, default=list, nullable=False)
    status = Column(String(60), default="active", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "project_id", "user_id", "participant_id", "team_id", name="uq_arceus_project_member_identity"),
        CheckConstraint("status IN ('active', 'suspended', 'removed')", name="ck_arceus_project_members_status"),
        Index("ix_arceus_project_members_project", "tenant_id", "project_id", "status"),
    )


class ArceusCollaborationMilestone(KernelTenantMixin, Base):
    __tablename__ = "arceus_collaboration_milestones"

    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"), nullable=False)
    title = Column(Text, nullable=False)
    objective = Column(Text)
    status = Column(String(60), default="planned", nullable=False)
    sort_order = Column(Integer, default=0, nullable=False)
    starts_at = Column(DateTime(timezone=True))
    due_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('planned', 'active', 'blocked', 'completed', 'cancelled')", name="ck_arceus_collaboration_milestones_status"),
        Index("ix_arceus_collaboration_milestones_project", "tenant_id", "project_id", "status", "sort_order"),
    )


class ArceusCollaborationTask(KernelTenantMixin, Base):
    __tablename__ = "arceus_collaboration_tasks"

    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"), nullable=False)
    milestone_id = Column(UUID(as_uuid=True), ForeignKey("arceus_collaboration_milestones.id"))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    source_type = Column(String(80), default="user", nullable=False)
    source_id = Column(UUID(as_uuid=True))
    title = Column(Text, nullable=False)
    description = Column(Text)
    assignee_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    assignee_participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"))
    priority = Column(String(40), default="medium", nullable=False)
    status = Column(String(60), default="backlog", nullable=False)
    dependencies = Column(JSON, default=list, nullable=False)
    acceptance_criteria = Column(JSON, default=list, nullable=False)
    due_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("priority IN ('low', 'medium', 'high', 'critical')", name="ck_arceus_collaboration_tasks_priority"),
        CheckConstraint("status IN ('backlog', 'planned', 'in_progress', 'review', 'done', 'blocked', 'cancelled')", name="ck_arceus_collaboration_tasks_status"),
        Index("ix_arceus_collaboration_tasks_project", "tenant_id", "project_id", "status", "priority"),
        Index("ix_arceus_collaboration_tasks_assignee", "tenant_id", "assignee_user_id", "assignee_participant_id", "status"),
    )


class ArceusMission(KernelTenantMixin, Base):
    __tablename__ = "arceus_missions"

    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    title = Column(Text, nullable=False)
    objective = Column(Text, nullable=False)
    status = Column(String(80), default="draft", nullable=False)
    risk_level = Column(String(40), default="medium", nullable=False)
    priority = Column(Integer, default=3, nullable=False)
    maximum_budget_amount = Column(Numeric(14, 4))
    actual_cost_amount = Column(Numeric(14, 4), default=0, nullable=False)
    budget_currency = Column(String(3), default="USD", nullable=False)
    current_version_id = Column(UUID(as_uuid=True))
    active_workflow_id = Column(UUID(as_uuid=True))
    paused_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    failed_at = Column(DateTime(timezone=True))
    failure_reason = Column(Text)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint(f"status IN {MISSION_STATUS_VALUES}", name="ck_arceus_missions_status"),
        CheckConstraint("priority >= 0 AND priority <= 5", name="ck_arceus_missions_priority"),
        Index("ix_arceus_missions_project_status", "tenant_id", "project_id", "status"),
        Index("ix_arceus_missions_created_by", "tenant_id", "created_by", "created_at"),
    )


class ArceusMissionVersion(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_versions"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    version = Column(Integer, nullable=False)
    compiled_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    objective_snapshot = Column(Text, nullable=False)
    mission_contract = Column(JSON, default=dict, nullable=False)
    intent_frame = Column(JSON, default=dict, nullable=False)
    risk_profile = Column(JSON, default=dict, nullable=False)
    execution_graph = Column(JSON, default=dict, nullable=False)
    source_hash = Column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "version", name="uq_arceus_mission_versions_version"),
        UniqueConstraint("mission_id", "source_hash", name="uq_arceus_mission_versions_source_hash"),
        Index("ix_arceus_mission_versions_mission", "tenant_id", "mission_id", "version"),
    )


class ArceusCompilerRun(KernelTenantMixin, Base):
    __tablename__ = "arceus_compiler_runs"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    source_mission_version = Column(BigInteger, nullable=False)
    status = Column(String(60), default="queued", nullable=False)
    current_stage = Column(String(120))
    stage_results = Column(JSON, default=dict, nullable=False)
    source_manifest_id = Column(UUID(as_uuid=True))
    compiled_mission_version_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_versions.id"))
    model_execution_ids = Column(JSON, default=list, nullable=False)
    warning_codes = Column(JSON, default=list, nullable=False)
    error_code = Column(String(160))
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'clarification_required', 'compiled', 'rejected', 'failed', 'stale', 'cancelled')",
            name="ck_arceus_compiler_runs_status",
        ),
        Index("ix_arceus_compiler_runs_mission_status", "tenant_id", "mission_id", "status"),
        Index("ix_arceus_compiler_runs_status_stage", "tenant_id", "status", "current_stage"),
    )


class ArceusMissionRepositoryScope(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_repository_scopes"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    repository_id = Column(UUID(as_uuid=True), ForeignKey("arceus_project_repositories.id"), nullable=False)
    base_ref = Column(Text)
    working_ref = Column(Text)
    allowed_paths = Column(ARRAY(Text), default=list, nullable=False)
    denied_paths = Column(ARRAY(Text), default=list, nullable=False)
    scope_reason = Column(Text)

    __table_args__ = (
        UniqueConstraint("mission_id", "repository_id", name="uq_arceus_mission_repository_scope"),
        Index("ix_arceus_mission_repository_scopes_mission", "tenant_id", "mission_id"),
    )


class ArceusMissionRequirement(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_requirements"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    requirement_key = Column(String(120), nullable=False)
    statement = Column(Text, nullable=False)
    source = Column(String(120), default="user", nullable=False)
    priority = Column(Integer, default=3, nullable=False)
    verified = Column(Boolean, default=False, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "requirement_key", name="uq_arceus_mission_requirement_key"),
        Index("ix_arceus_mission_requirements_mission", "tenant_id", "mission_id"),
    )


class ArceusMissionConstraint(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_constraints"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    constraint_key = Column(String(120), nullable=False)
    statement = Column(Text, nullable=False)
    severity = Column(String(40), default="required", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "constraint_key", name="uq_arceus_mission_constraint_key"),
        Index("ix_arceus_mission_constraints_mission", "tenant_id", "mission_id"),
    )


class ArceusMissionUnknown(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_unknowns"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    question = Column(Text, nullable=False)
    risk_if_unanswered = Column(Text)
    status = Column(String(40), default="open", nullable=False)
    answer = Column(Text)

    __table_args__ = (
        CheckConstraint("status IN ('open', 'answered', 'deferred')", name="ck_arceus_mission_unknowns_status"),
        Index("ix_arceus_mission_unknowns_mission", "tenant_id", "mission_id", "status"),
    )


class ArceusMissionSuccessCriterion(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_success_criteria"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    criterion_key = Column(String(120), nullable=False)
    statement = Column(Text, nullable=False)
    verification_method = Column(String(120), nullable=False)
    required = Column(Boolean, default=True, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "criterion_key", name="uq_arceus_mission_success_criterion_key"),
        Index("ix_arceus_mission_success_criteria_mission", "tenant_id", "mission_id"),
    )


class ArceusCapability(KernelMutableMixin, Base):
    __tablename__ = "arceus_capabilities"

    capability_key = Column(String(160), nullable=False)
    domain = Column(String(120), nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    verification_methods = Column(JSON, default=list, nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("capability_key", name="uq_arceus_capabilities_key"),
        Index("ix_arceus_capabilities_domain", "domain", "active"),
    )


class ArceusMissionRequiredCapability(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_required_capabilities"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    capability_id = Column(UUID(as_uuid=True), ForeignKey("arceus_capabilities.id"), nullable=False)
    reason = Column(Text, nullable=False)
    required_level = Column(String(60), default="standard", nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "capability_id", name="uq_arceus_mission_required_capability"),
        Index("ix_arceus_mission_required_capabilities_mission", "tenant_id", "mission_id"),
    )


class ArceusSpecialistProfile(KernelMutableMixin, Base):
    __tablename__ = "arceus_specialist_profiles"

    specialist_key = Column(String(160), nullable=False)
    display_name = Column(Text, nullable=False)
    specialist_type = Column(String(80), nullable=False)
    authority_profile = Column(JSON, default=dict, nullable=False)
    default_model_policy = Column(JSON, default=dict, nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("specialist_type IN ('human', 'ai', 'system')", name="ck_arceus_specialist_profiles_type"),
        UniqueConstraint("specialist_key", name="uq_arceus_specialist_profiles_key"),
    )


class ArceusSpecialistCapability(KernelMutableMixin, Base):
    __tablename__ = "arceus_specialist_capabilities"

    specialist_profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_specialist_profiles.id"), nullable=False)
    capability_id = Column(UUID(as_uuid=True), ForeignKey("arceus_capabilities.id"), nullable=False)
    proficiency = Column(Float, default=0.75, nullable=False)
    evidence = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("specialist_profile_id", "capability_id", name="uq_arceus_specialist_capability"),
    )


class ArceusMissionOrganization(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_organizations"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    organization_name = Column(Text, nullable=False)
    status = Column(String(60), default="draft", nullable=False)
    rationale = Column(Text, nullable=False)
    budget_policy = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'active', 'paused', 'retired')", name="ck_arceus_mission_organizations_status"),
        UniqueConstraint("mission_id", name="uq_arceus_mission_organizations_mission"),
        Index("ix_arceus_mission_organizations_mission", "tenant_id", "mission_id"),
    )


class ArceusOrganizationMember(KernelTenantMixin, Base):
    __tablename__ = "arceus_organization_members"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_organizations.id"), nullable=False)
    specialist_profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_specialist_profiles.id"), nullable=False)
    participant_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    role_key = Column(String(120), nullable=False)
    responsibility = Column(Text, nullable=False)
    authority = Column(JSON, default=dict, nullable=False)
    can_implement = Column(Boolean, default=False, nullable=False)
    can_review = Column(Boolean, default=False, nullable=False)
    can_approve = Column(Boolean, default=False, nullable=False)
    status = Column(String(60), default="active", nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "role_key", name="uq_arceus_organization_member_role"),
        Index("ix_arceus_organization_members_org", "tenant_id", "organization_id", "status"),
    )


class ArceusWorkflowDefinition(KernelTenantMixin, Base):
    __tablename__ = "arceus_workflow_definitions"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    mission_version_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_versions.id"), nullable=False)
    status = Column(String(60), default="draft", nullable=False)
    graph_hash = Column(String(128), nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "graph_hash", name="uq_arceus_workflow_definitions_graph_hash"),
        Index("ix_arceus_workflow_definitions_mission", "tenant_id", "mission_id", "status"),
    )


class ArceusWorkflowNode(KernelTenantMixin, Base):
    __tablename__ = "arceus_workflow_nodes"

    workflow_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_definitions.id"), nullable=False)
    node_key = Column(String(160), nullable=False)
    node_type = Column(String(80), nullable=False)
    title = Column(Text, nullable=False)
    config = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("workflow_id", "node_key", name="uq_arceus_workflow_nodes_key"),
        Index("ix_arceus_workflow_nodes_workflow", "tenant_id", "workflow_id"),
    )


class ArceusWorkflowEdge(KernelTenantMixin, Base):
    __tablename__ = "arceus_workflow_edges"

    workflow_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_definitions.id"), nullable=False)
    source_node_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_nodes.id"), nullable=False)
    target_node_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_nodes.id"), nullable=False)
    condition = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("workflow_id", "source_node_id", "target_node_id", name="uq_arceus_workflow_edges_pair"),
        Index("ix_arceus_workflow_edges_workflow", "tenant_id", "workflow_id"),
    )


class ArceusTask(KernelTenantMixin, Base):
    __tablename__ = "arceus_tasks"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    workflow_node_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_nodes.id"))
    task_key = Column(String(160), nullable=False)
    title = Column(Text, nullable=False)
    task_type = Column(String(80), nullable=False)
    status = Column(String(60), default="pending", nullable=False)
    owner_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    input_contract = Column(JSON, default=dict, nullable=False)
    output_contract = Column(JSON, default=dict, nullable=False)
    acceptance_criteria = Column(JSON, default=list, nullable=False)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    failure_reason = Column(Text)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'ready', 'running', 'blocked', 'reviewing', 'verifying', 'completed', 'failed', 'cancelled')", name="ck_arceus_tasks_status"),
        UniqueConstraint("mission_id", "task_key", name="uq_arceus_tasks_key"),
        Index("ix_arceus_tasks_mission_status", "tenant_id", "mission_id", "status"),
        Index("ix_arceus_tasks_owner_status", "tenant_id", "owner_member_id", "status"),
    )


class ArceusTaskDependency(KernelTenantMixin, Base):
    __tablename__ = "arceus_task_dependencies"

    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"), nullable=False)
    depends_on_task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"), nullable=False)
    dependency_type = Column(String(60), default="blocks", nullable=False)

    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_arceus_task_dependency"),
        Index("ix_arceus_task_dependencies_task", "tenant_id", "task_id"),
    )


class ArceusTaskAttempt(KernelTenantMixin, Base):
    __tablename__ = "arceus_task_attempts"

    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    status = Column(String(60), default="running", nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True))
    worker_id = Column(String(160))
    idempotency_key = Column(String(255), nullable=False)
    result = Column(JSON, default=dict, nullable=False)
    error = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed', 'cancelled')", name="ck_arceus_task_attempts_status"),
        UniqueConstraint("task_id", "attempt_number", name="uq_arceus_task_attempt_number"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_arceus_task_attempt_idempotency"),
        Index("ix_arceus_task_attempts_task", "tenant_id", "task_id", "started_at"),
    )


class ArceusWorkerLease(KernelTenantMixin, Base):
    __tablename__ = "arceus_worker_leases"

    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"), nullable=False)
    worker_id = Column(String(160), nullable=False)
    lease_token = Column(String(255), nullable=False)
    status = Column(String(60), default="active", nullable=False)
    heartbeat_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'released', 'expired')", name="ck_arceus_worker_leases_status"),
        UniqueConstraint("task_id", "lease_token", name="uq_arceus_worker_lease_token"),
        Index("ix_arceus_worker_leases_active", "tenant_id", "status", "expires_at"),
    )


class ArceusAgentRuntimeWorker(KernelTenantMixin, Base):
    __tablename__ = "arceus_agent_runtime_workers"

    organization_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    role = Column(String(100), nullable=False)
    provider = Column(String(80))
    model = Column(String(120))
    status = Column(String(30), default="idle", nullable=False)
    current_mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    current_task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    capabilities = Column(JSON, default=dict, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    last_heartbeat_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('idle', 'reserved', 'busy', 'offline', 'draining', 'failed')", name="ck_arceus_agent_runtime_workers_status"),
        Index("ix_arceus_agent_runtime_workers_mission", "tenant_id", "current_mission_id", "status"),
        Index("ix_arceus_agent_runtime_workers_member", "tenant_id", "organization_member_id", "status"),
    )


class ArceusMissionTaskAssignment(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_task_assignments"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"), nullable=False)
    worker_id = Column(UUID(as_uuid=True), ForeignKey("arceus_agent_runtime_workers.id"), nullable=False)
    status = Column(String(30), default="assigned", nullable=False)
    assignment_reason = Column(Text)
    score = Column(Numeric(8, 4))
    assigned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True))
    released_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    lease_expires_at = Column(DateTime(timezone=True))
    last_heartbeat_at = Column(DateTime(timezone=True))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('assigned', 'accepted', 'running', 'released', 'completed', 'failed', 'expired')", name="ck_arceus_mission_task_assignments_status"),
        UniqueConstraint("task_id", "status", name="uq_arceus_mission_task_assignment_task_status"),
        Index("ix_arceus_mission_task_assignments_mission", "tenant_id", "mission_id", "status"),
        Index("ix_arceus_mission_task_assignments_task", "tenant_id", "task_id", "status"),
        Index("ix_arceus_mission_task_assignments_worker", "tenant_id", "worker_id", "status"),
    )


class ArceusMissionPathReservation(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_path_reservations"

    repository_id = Column(UUID(as_uuid=True), nullable=False)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"), nullable=False)
    assignment_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_task_assignments.id"))
    path_pattern = Column(Text, nullable=False)
    reservation_mode = Column(String(20), nullable=False)
    status = Column(String(20), default="active", nullable=False)
    acquired_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True))
    released_at = Column(DateTime(timezone=True))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("reservation_mode IN ('read', 'write', 'exclusive')", name="ck_arceus_mission_path_reservations_mode"),
        CheckConstraint("status IN ('active', 'released', 'expired', 'cancelled')", name="ck_arceus_mission_path_reservations_status"),
        Index("ix_arceus_mission_path_reservations_repo", "tenant_id", "repository_id", "status"),
        Index("ix_arceus_mission_path_reservations_mission", "tenant_id", "mission_id", "status"),
        Index("ix_arceus_mission_path_reservations_task", "tenant_id", "task_id", "status"),
    )


class ArceusDesktopSession(KernelTenantMixin, Base):
    __tablename__ = "arceus_desktop_sessions"

    device_id = Column(String(160), nullable=False)
    workspace_id = Column(String(240), nullable=False)
    repository_id = Column(String(240))
    capabilities = Column(JSON, default=dict, nullable=False)
    runtime = Column(JSON, default=dict, nullable=False)
    status = Column(String(40), default="connected", nullable=False)
    heartbeat_interval_seconds = Column(Integer, default=30, nullable=False)
    last_heartbeat_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    active_mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    active_task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    repository_available = Column(Boolean, default=True, nullable=False)
    connected_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('connected', 'disconnected', 'expired', 'revoked')", name="ck_arceus_desktop_sessions_status"),
        Index("ix_arceus_desktop_sessions_device", "tenant_id", "device_id", "status"),
        Index("ix_arceus_desktop_sessions_repo", "tenant_id", "repository_id", "status"),
        Index("ix_arceus_desktop_sessions_expires", "tenant_id", "status", "expires_at"),
    )


class ArceusRuntimeCheckpoint(KernelTenantMixin, Base):
    __tablename__ = "arceus_runtime_checkpoints"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"), nullable=False)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_definitions.id"))
    worker_lease_id = Column(UUID(as_uuid=True), ForeignKey("arceus_worker_leases.id"))
    checkpoint_key = Column(String(160), nullable=False)
    workflow_version = Column(BigInteger, nullable=False)
    execution_state = Column(JSON, default=dict, nullable=False)
    artifacts = Column(JSON, default=list, nullable=False)
    model_calls = Column(JSON, default=list, nullable=False)
    tool_calls = Column(JSON, default=list, nullable=False)
    outputs = Column(JSON, default=dict, nullable=False)
    progress_percent = Column(Integer, default=0, nullable=False)
    created_by_worker_id = Column(String(160), nullable=False)

    __table_args__ = (
        UniqueConstraint("task_id", "checkpoint_key", name="uq_arceus_runtime_checkpoints_task_key"),
        Index("ix_arceus_runtime_checkpoints_mission", "tenant_id", "mission_id", "created_at"),
        Index("ix_arceus_runtime_checkpoints_task", "tenant_id", "task_id", "created_at"),
    )


class ArceusDecision(KernelTenantMixin, Base):
    __tablename__ = "arceus_decisions"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    decision_key = Column(String(160), nullable=False)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    selected_option = Column(JSON, default=dict, nullable=False)
    alternatives = Column(JSON, default=list, nullable=False)
    rationale = Column(Text, nullable=False)
    status = Column(String(60), default="proposed", nullable=False)
    decided_by_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))

    __table_args__ = (
        CheckConstraint("status IN ('proposed', 'approved', 'rejected', 'superseded')", name="ck_arceus_decisions_status"),
        UniqueConstraint("mission_id", "decision_key", name="uq_arceus_decisions_key"),
        Index("ix_arceus_decisions_mission", "tenant_id", "mission_id", "status"),
    )


class ArceusApproval(KernelTenantMixin, Base):
    __tablename__ = "arceus_approvals"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    decision_id = Column(UUID(as_uuid=True), ForeignKey("arceus_decisions.id"))
    approval_type = Column(String(100), nullable=False)
    subject_type = Column(String(100), default="mission_plan", nullable=False)
    subject_hash = Column(String(128), nullable=False)
    proposed_action = Column(Text, default="", nullable=False)
    risk_level = Column(String(40), default="medium", nullable=False)
    status = Column(String(60), default="pending", nullable=False)
    quorum_policy = Column(JSON, default=dict, nullable=False)
    requested_by_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    expires_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="ck_arceus_approvals_status"),
        Index("ix_arceus_approvals_mission_status", "tenant_id", "mission_id", "status"),
    )


class ArceusApprovalVote(KernelTenantMixin, Base):
    __tablename__ = "arceus_approval_votes"

    approval_id = Column(UUID(as_uuid=True), ForeignKey("arceus_approvals.id"), nullable=False)
    voter_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    voter_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    vote = Column(String(40), nullable=False)
    comment = Column(Text)
    is_human_vote = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        CheckConstraint("vote IN ('approve', 'reject', 'abstain')", name="ck_arceus_approval_votes_vote"),
        UniqueConstraint("approval_id", "voter_member_id", "voter_user_id", name="uq_arceus_approval_vote_voter"),
        Index("ix_arceus_approval_votes_approval", "tenant_id", "approval_id"),
    )


class ArceusArtifact(KernelTenantMixin, Base):
    __tablename__ = "arceus_artifacts"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    artifact_key = Column(String(160), nullable=False)
    artifact_type = Column(String(100), nullable=False)
    title = Column(Text, nullable=False)
    current_version_id = Column(UUID(as_uuid=True))
    trust_status = Column(String(60), default="unverified", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("trust_status IN ('unverified', 'verified', 'superseded', 'rejected')", name="ck_arceus_artifacts_trust_status"),
        UniqueConstraint("mission_id", "artifact_key", name="uq_arceus_artifacts_key"),
        Index("ix_arceus_artifacts_mission", "tenant_id", "mission_id", "artifact_type"),
    )


class ArceusArtifactVersion(KernelTenantMixin, Base):
    __tablename__ = "arceus_artifact_versions"

    artifact_id = Column(UUID(as_uuid=True), ForeignKey("arceus_artifacts.id"), nullable=False)
    version = Column(Integer, nullable=False)
    content = Column(JSON, default=dict, nullable=False)
    content_hash = Column(String(128), nullable=False)
    produced_by_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    provenance = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("artifact_id", "version", name="uq_arceus_artifact_versions_version"),
        UniqueConstraint("artifact_id", "content_hash", name="uq_arceus_artifact_versions_content_hash"),
    )


class ArceusEvidence(KernelTenantMixin, Base):
    __tablename__ = "arceus_evidence"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_definitions.id"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    artifact_id = Column(UUID(as_uuid=True), ForeignKey("arceus_artifacts.id"))
    evidence_type = Column(String(100), nullable=False)
    status = Column(String(60), default="collected", nullable=False)
    summary = Column(Text, nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    verification_method = Column(String(120), default="manual", nullable=False)
    content_hash = Column(String(128), nullable=False)
    trust_level = Column(String(60), default="unverified", nullable=False)
    immutable = Column(Boolean, default=True, nullable=False)
    collected_by_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))

    __table_args__ = (
        CheckConstraint("status IN ('generated', 'collected', 'validated', 'trusted', 'referenced', 'archived', 'verified', 'failed')", name="ck_arceus_evidence_status"),
        CheckConstraint("trust_level IN ('unverified', 'ai_reviewed', 'tool_verified', 'independent_review', 'human_approved', 'production_observed')", name="ck_arceus_evidence_trust_level"),
        Index("ix_arceus_evidence_hash", "tenant_id", "mission_id", "content_hash"),
        Index("ix_arceus_evidence_mission", "tenant_id", "mission_id", "evidence_type"),
    )


class ArceusVerificationPlan(KernelTenantMixin, Base):
    __tablename__ = "arceus_verification_plans"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_definitions.id"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    target_type = Column(String(100), default="mission", nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)
    criteria = Column(JSON, default=list, nullable=False)
    methods = Column(JSON, default=list, nullable=False)
    evidence_required = Column(JSON, default=list, nullable=False)
    reviewers = Column(JSON, default=list, nullable=False)
    environment = Column(String(120), default="local", nullable=False)
    blocking = Column(Boolean, default=True, nullable=False)
    timeout_seconds = Column(Integer, default=900, nullable=False)
    status = Column(String(60), default="planned", nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('planned', 'running', 'passed', 'failed', 'cancelled', 'superseded')", name="ck_arceus_verification_plans_status"),
        Index("ix_arceus_verification_plans_mission", "tenant_id", "mission_id", "status"),
    )


class ArceusVerificationRun(KernelTenantMixin, Base):
    __tablename__ = "arceus_verification_runs"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    verification_type = Column(String(100), nullable=False)
    status = Column(String(60), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True))
    command = Column(Text)
    result = Column(JSON, default=dict, nullable=False)
    evidence_id = Column(UUID(as_uuid=True), ForeignKey("arceus_evidence.id"))

    __table_args__ = (
        CheckConstraint("status IN ('running', 'passed', 'failed', 'cancelled')", name="ck_arceus_verification_runs_status"),
        Index("ix_arceus_verification_runs_mission", "tenant_id", "mission_id", "status"),
    )


class ArceusVerificationFinding(KernelTenantMixin, Base):
    __tablename__ = "arceus_verification_findings"

    verification_run_id = Column(UUID(as_uuid=True), ForeignKey("arceus_verification_runs.id"), nullable=False)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    finding_key = Column(String(180), nullable=False)
    severity = Column(String(40), nullable=False)
    title = Column(Text, nullable=False)
    detail = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=False)
    evidence_ids = Column(JSON, default=list, nullable=False)
    blocks_release = Column(Boolean, default=False, nullable=False)
    status = Column(String(60), default="open", nullable=False)

    __table_args__ = (
        CheckConstraint("severity IN ('info', 'low', 'medium', 'moderate', 'high', 'critical')", name="ck_arceus_verification_findings_severity"),
        CheckConstraint("status IN ('open', 'acknowledged', 'resolved', 'waived', 'superseded')", name="ck_arceus_verification_findings_status"),
        Index("ix_arceus_verification_findings_run", "tenant_id", "verification_run_id"),
        Index("ix_arceus_verification_findings_mission", "tenant_id", "mission_id", "severity", "status"),
    )


class ArceusVerificationWorkerJob(KernelTenantMixin, Base):
    __tablename__ = "arceus_verification_worker_jobs"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    plan_id = Column(String(180), nullable=False)
    check_id = Column(String(180), nullable=False)
    check_definition_id = Column(String(180), nullable=False)
    category = Column(String(100), nullable=False)
    evidence_producer = Column(String(120), nullable=False)
    mandatory = Column(Boolean, default=True, nullable=False)
    blocking = Column(Boolean, default=True, nullable=False)
    status = Column(String(60), default="queued", nullable=False)
    inputs = Column(JSON, default=dict, nullable=False)
    depends_on = Column(JSON, default=list, nullable=False)
    timeout_seconds = Column(Integer, default=300, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    last_error = Column(JSON, default=dict, nullable=False)
    durable_task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    evidence_id = Column(UUID(as_uuid=True), ForeignKey("arceus_evidence.id"))
    idempotency_key = Column(String(255), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('queued', 'leased', 'running', 'succeeded', 'failed', 'cancelled', 'blocked')", name="ck_arceus_verification_worker_jobs_status"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_arceus_verification_worker_jobs_idempotency"),
        Index("ix_arceus_verification_worker_jobs_plan", "tenant_id", "mission_id", "plan_id", "status"),
        Index("ix_arceus_verification_worker_jobs_queue", "tenant_id", "status", "category", "created_at"),
    )


class ArceusEvidenceProducerRun(KernelTenantMixin, Base):
    __tablename__ = "arceus_evidence_producer_runs"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    worker_job_id = Column(UUID(as_uuid=True), ForeignKey("arceus_verification_worker_jobs.id"))
    producer_key = Column(String(120), nullable=False)
    check_id = Column(String(180))
    status = Column(String(60), default="running", nullable=False)
    command = Column(Text)
    exit_code = Column(Integer)
    duration_ms = Column(Integer)
    output_summary = Column(Text, default="", nullable=False)
    artifacts = Column(JSON, default=list, nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    evidence_id = Column(UUID(as_uuid=True), ForeignKey("arceus_evidence.id"))
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed', 'cancelled')", name="ck_arceus_evidence_producer_runs_status"),
        Index("ix_arceus_evidence_producer_runs_mission", "tenant_id", "mission_id", "producer_key", "status"),
        Index("ix_arceus_evidence_producer_runs_job", "tenant_id", "worker_job_id"),
    )


class ArceusReleaseReadinessGate(KernelTenantMixin, Base):
    __tablename__ = "arceus_release_readiness_gates"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    subject_type = Column(String(80), default="release", nullable=False)
    subject_id = Column(String(180), nullable=False)
    ready = Column(Boolean, default=False, nullable=False)
    status = Column(String(60), nullable=False)
    score = Column(Float, default=0.0, nullable=False)
    blockers = Column(JSON, default=list, nullable=False)
    warnings = Column(JSON, default=list, nullable=False)
    required_actions = Column(JSON, default=list, nullable=False)
    evidence_summary = Column(JSON, default=dict, nullable=False)
    response_payload = Column(JSON, default=dict, nullable=False)
    checked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("subject_type IN ('pull_request', 'deployment', 'release', 'merge')", name="ck_arceus_release_readiness_gates_subject"),
        CheckConstraint("status IN ('ready', 'blocked', 'review_required')", name="ck_arceus_release_readiness_gates_status"),
        Index("ix_arceus_release_readiness_gates_latest", "tenant_id", "mission_id", "subject_type", "subject_id", "checked_at"),
    )


class ArceusQualityGate(KernelTenantMixin, Base):
    __tablename__ = "arceus_quality_gates"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    verification_plan_id = Column(UUID(as_uuid=True), ForeignKey("arceus_verification_plans.id"))
    gate_key = Column(String(160), nullable=False)
    name = Column(Text, nullable=False)
    category = Column(String(100), nullable=False)
    gate_type = Column(String(60), default="mandatory", nullable=False)
    required = Column(Boolean, default=True, nullable=False)
    verifier = Column(String(120), nullable=False)
    timeout_seconds = Column(Integer, default=300, nullable=False)
    status = Column(String(60), default="pending", nullable=False)
    result = Column(JSON, default=dict, nullable=False)
    evidence_ids = Column(JSON, default=list, nullable=False)
    last_run_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("gate_type IN ('mandatory', 'conditional', 'optional', 'manual')", name="ck_arceus_quality_gates_type"),
        CheckConstraint("status IN ('pending', 'running', 'passed', 'failed', 'waived', 'cancelled')", name="ck_arceus_quality_gates_status"),
        UniqueConstraint("mission_id", "gate_key", name="uq_arceus_quality_gate_key"),
        Index("ix_arceus_quality_gates_mission", "tenant_id", "mission_id", "status"),
    )


class ArceusTrustScore(KernelTenantMixin, Base):
    __tablename__ = "arceus_trust_scores"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    target_type = Column(String(100), default="mission", nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)
    trust_level = Column(Integer, default=0, nullable=False)
    score = Column(Float, default=0.0, nullable=False)
    confidence = Column(Float, default=0.0, nullable=False)
    contributors = Column(JSON, default=dict, nullable=False)
    calculated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("trust_level >= 0 AND trust_level <= 5", name="ck_arceus_trust_scores_level"),
        Index("ix_arceus_trust_scores_target", "tenant_id", "target_type", "target_id", "calculated_at"),
    )


class ArceusCompletionCertificate(KernelTenantMixin, Base):
    __tablename__ = "arceus_completion_certificates"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    certificate_version = Column(Integer, default=1, nullable=False)
    status = Column(String(60), default="draft", nullable=False)
    completed_requirements = Column(JSON, default=list, nullable=False)
    evidence_ids = Column(JSON, default=list, nullable=False)
    gate_ids = Column(JSON, default=list, nullable=False)
    approval_ids = Column(JSON, default=list, nullable=False)
    trust_score_id = Column(UUID(as_uuid=True), ForeignKey("arceus_trust_scores.id"))
    blockers = Column(JSON, default=list, nullable=False)
    certificate_hash = Column(String(128), nullable=False)
    signature = Column(String(256), nullable=False)
    signed_at = Column(DateTime(timezone=True))
    immutable = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'blocked', 'certified', 'approved')", name="ck_arceus_completion_certificates_status"),
        UniqueConstraint("mission_id", "certificate_version", name="uq_arceus_completion_certificate_version"),
        UniqueConstraint("tenant_id", "certificate_hash", name="uq_arceus_completion_certificate_hash"),
        Index("ix_arceus_completion_certificates_mission", "tenant_id", "mission_id", "status"),
    )


class ArceusContextPackage(KernelTenantMixin, Base):
    __tablename__ = "arceus_context_packages"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    recipient_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    purpose = Column(Text, nullable=False)
    selected_items = Column(JSON, default=list, nullable=False)
    excluded_items = Column(JSON, default=list, nullable=False)
    token_budget = Column(Integer, default=0, nullable=False)
    content_hash = Column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "task_id", "recipient_member_id", "content_hash", name="uq_arceus_context_packages_hash"),
    )


class ArceusModelExecution(KernelTenantMixin, Base):
    __tablename__ = "arceus_model_executions"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    provider = Column(String(100), nullable=False)
    model = Column(String(160), nullable=False)
    purpose = Column(String(160), nullable=False)
    prompt_hash = Column(String(128), nullable=False)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    cost_usd = Column(Numeric(12, 6), default=0, nullable=False)
    latency_ms = Column(Integer)
    status = Column(String(60), nullable=False)
    error = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('succeeded', 'failed', 'cancelled')", name="ck_arceus_model_executions_status"),
        Index("ix_arceus_model_executions_mission", "tenant_id", "mission_id", "created_at"),
    )


class ArceusProviderProfile(KernelMutableMixin, Base):
    __tablename__ = "arceus_provider_profiles"

    provider_key = Column(String(120), nullable=False)
    display_name = Column(Text, nullable=False)
    adapter_type = Column(String(120), nullable=False)
    enabled = Column(Boolean, default=True, nullable=False)
    supported_regions = Column(JSON, default=list, nullable=False)
    authentication_reference = Column(Text, nullable=False)
    requests_per_minute = Column(Integer)
    tokens_per_minute = Column(Integer)
    concurrent_request_limit = Column(Integer)
    health_status = Column(String(60), default="healthy", nullable=False)
    circuit_state = Column(String(60), default="closed", nullable=False)
    retention_policy = Column(String(120), default="standard", nullable=False)
    supports_zero_retention = Column(Boolean, default=False, nullable=False)
    enterprise_agreement_required = Column(Boolean, default=False, nullable=False)
    version = Column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("provider_key", name="uq_arceus_provider_profiles_key"),
        CheckConstraint("health_status IN ('healthy', 'degraded', 'rate_limited', 'unavailable', 'misconfigured', 'disabled')", name="ck_arceus_provider_profiles_health"),
        CheckConstraint("circuit_state IN ('closed', 'open', 'half_open')", name="ck_arceus_provider_profiles_circuit"),
    )


class ArceusModelProfile(KernelMutableMixin, Base):
    __tablename__ = "arceus_model_profiles"

    model_key = Column(String(160), nullable=False)
    provider_key = Column(String(120), ForeignKey("arceus_provider_profiles.provider_key"), nullable=False)
    provider_model_name = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    status = Column(String(60), default="available", nullable=False)
    capabilities = Column(JSON, default=list, nullable=False)
    supported_modalities = Column(JSON, default=list, nullable=False)
    supported_output_modes = Column(JSON, default=list, nullable=False)
    context_window_tokens = Column(BigInteger, nullable=False)
    maximum_output_tokens = Column(Integer, nullable=False)
    supports_tool_calling = Column(Boolean, default=False, nullable=False)
    supports_structured_output = Column(Boolean, default=False, nullable=False)
    supports_streaming = Column(Boolean, default=False, nullable=False)
    supports_seed = Column(Boolean, default=False, nullable=False)
    supports_prompt_caching = Column(Boolean, default=False, nullable=False)
    data_residency_regions = Column(JSON, default=list, nullable=False)
    data_retention_policy = Column(String(120), default="standard", nullable=False)
    input_cost_per_million_tokens = Column(Numeric(18, 8), default=0, nullable=False)
    output_cost_per_million_tokens = Column(Numeric(18, 8), default=0, nullable=False)
    cached_input_cost_per_million_tokens = Column(Numeric(18, 8))
    expected_latency_class = Column(String(60), default="medium", nullable=False)
    reliability_score = Column(Float, default=0.9, nullable=False)
    quality_scores = Column(JSON, default=dict, nullable=False)
    version = Column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("model_key", name="uq_arceus_model_profiles_key"),
        CheckConstraint("status IN ('available', 'degraded', 'disabled', 'retired')", name="ck_arceus_model_profiles_status"),
        Index("ix_arceus_model_profiles_provider", "provider_key", "status"),
    )


class ArceusToolProfile(KernelMutableMixin, Base):
    __tablename__ = "arceus_tool_profiles"

    tool_key = Column(String(160), nullable=False)
    display_name = Column(Text, nullable=False)
    adapter_type = Column(String(120), nullable=False)
    version = Column(String(80), nullable=False)
    capabilities = Column(JSON, default=list, nullable=False)
    supported_actions = Column(JSON, default=list, nullable=False)
    risk_level = Column(String(60), default="low", nullable=False)
    side_effect_class = Column(String(80), default="READ_ONLY", nullable=False)
    requires_sandbox = Column(Boolean, default=True, nullable=False)
    supports_dry_run = Column(Boolean, default=False, nullable=False)
    supports_idempotency = Column(Boolean, default=True, nullable=False)
    supports_rollback = Column(Boolean, default=False, nullable=False)
    required_authorities = Column(JSON, default=list, nullable=False)
    allowed_environments = Column(JSON, default=list, nullable=False)
    maximum_runtime_seconds = Column(Integer, default=120, nullable=False)
    output_schema_key = Column(String(160))
    enabled = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("tool_key", name="uq_arceus_tool_profiles_key"),
        CheckConstraint(
            "side_effect_class IN ('READ_ONLY', 'LOCAL_MUTATION', 'REPOSITORY_MUTATION', 'EXTERNAL_REVERSIBLE', 'EXTERNAL_IRREVERSIBLE', 'PRODUCTION_CHANGE', 'FINANCIAL_ACTION', 'SECRET_ACCESS')",
            name="ck_arceus_tool_profiles_side_effect",
        ),
        Index("ix_arceus_tool_profiles_enabled", "enabled", "risk_level"),
    )


class ArceusRoutingDecision(KernelTenantMixin, Base):
    __tablename__ = "arceus_routing_decisions"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    request_id = Column(UUID(as_uuid=True), nullable=False)
    execution_kind = Column(String(40), nullable=False)
    task_type = Column(String(120), nullable=False)
    routing_mode = Column(String(60), default="balanced", nullable=False)
    selected_model_key = Column(String(160))
    selected_provider_key = Column(String(120))
    selected_tool_key = Column(String(160))
    selected_action_key = Column(String(160))
    fallback_model_keys = Column(JSON, default=list, nullable=False)
    candidate_scores = Column(JSON, default=dict, nullable=False)
    hard_exclusions = Column(JSON, default=dict, nullable=False)
    applied_policy_ids = Column(JSON, default=list, nullable=False)
    estimated_input_tokens = Column(Integer, default=0, nullable=False)
    estimated_output_tokens = Column(Integer, default=0, nullable=False)
    estimated_cost_usd = Column(Numeric(18, 8), default=0, nullable=False)
    estimated_latency_ms = Column(Integer, default=0, nullable=False)
    reasoning_summary = Column(Text, nullable=False)
    decision_hash = Column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id", name="uq_arceus_routing_decisions_request"),
        UniqueConstraint("tenant_id", "decision_hash", name="uq_arceus_routing_decisions_hash"),
        Index("ix_arceus_routing_decisions_mission", "tenant_id", "mission_id", "created_at"),
    )


class ArceusBudget(KernelTenantMixin, Base):
    __tablename__ = "arceus_budgets"

    scope_type = Column(String(80), nullable=False)
    scope_id = Column(UUID(as_uuid=True), nullable=False)
    currency = Column(String(12), default="USD", nullable=False)
    limit_amount = Column(Numeric(18, 8), nullable=False)
    reserved_amount = Column(Numeric(18, 8), default=0, nullable=False)
    actual_amount = Column(Numeric(18, 8), default=0, nullable=False)
    warning_threshold_percent = Column(Integer, default=80, nullable=False)
    status = Column(String(60), default="active", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "scope_type", "scope_id", name="uq_arceus_budgets_scope"),
        CheckConstraint("status IN ('active', 'warning', 'exhausted', 'disabled')", name="ck_arceus_budgets_status"),
        Index("ix_arceus_budgets_scope", "tenant_id", "scope_type", "scope_id"),
    )


class ArceusCostReservation(KernelTenantMixin, Base):
    __tablename__ = "arceus_cost_reservations"

    budget_id = Column(UUID(as_uuid=True), ForeignKey("arceus_budgets.id"), nullable=False)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    amount = Column(Numeric(18, 8), nullable=False)
    currency = Column(String(12), default="USD", nullable=False)
    status = Column(String(60), default="reserved", nullable=False)
    idempotency_key = Column(String(180), nullable=False)
    released_at = Column(DateTime(timezone=True))
    settled_at = Column(DateTime(timezone=True))

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_arceus_cost_reservations_idempotency"),
        CheckConstraint("status IN ('reserved', 'released', 'settled', 'failed')", name="ck_arceus_cost_reservations_status"),
        Index("ix_arceus_cost_reservations_budget", "tenant_id", "budget_id", "status"),
    )


class ArceusAIExecutionLedger(KernelTenantMixin, Base):
    __tablename__ = "arceus_ai_execution_ledger"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    execution_kind = Column(String(40), nullable=False)
    task_type = Column(String(120), nullable=False)
    provider_key = Column(String(120))
    model_key = Column(String(160))
    tool_key = Column(String(160))
    action_key = Column(String(160))
    request_hash = Column(String(128), nullable=False)
    context_hash = Column(String(128))
    response_hash = Column(String(128))
    status = Column(String(60), default="pending", nullable=False)
    retry_count = Column(Integer, default=0, nullable=False)
    fallback_used = Column(Boolean, default=False, nullable=False)
    input_tokens = Column(BigInteger, default=0, nullable=False)
    output_tokens = Column(BigInteger, default=0, nullable=False)
    cached_input_tokens = Column(BigInteger, default=0, nullable=False)
    estimated_cost = Column(Numeric(18, 8), default=0, nullable=False)
    actual_cost = Column(Numeric(18, 8), default=0, nullable=False)
    latency_ms = Column(BigInteger)
    routing_decision_id = Column(UUID(as_uuid=True), ForeignKey("arceus_routing_decisions.id"))
    cost_reservation_id = Column(UUID(as_uuid=True), ForeignKey("arceus_cost_reservations.id"))
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True))
    result = Column(JSON, default=dict, nullable=False)
    error = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("execution_kind IN ('model', 'tool', 'retrieval')", name="ck_arceus_ai_execution_ledger_kind"),
        CheckConstraint("status IN ('pending', 'authorized', 'running', 'completed', 'failed', 'denied', 'cancelled')", name="ck_arceus_ai_execution_ledger_status"),
        Index("ix_arceus_ai_execution_ledger_mission", "tenant_id", "mission_id", "created_at"),
        Index("ix_arceus_ai_execution_ledger_routing", "tenant_id", "routing_decision_id"),
    )


class ArceusExecutionEvaluation(KernelTenantMixin, Base):
    __tablename__ = "arceus_execution_evaluations"

    execution_id = Column(UUID(as_uuid=True), ForeignKey("arceus_ai_execution_ledger.id"), nullable=False)
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    task_type = Column(String(120), nullable=False)
    schema_valid = Column(Boolean, default=False, nullable=False)
    verification_passed = Column(Boolean)
    reviewer_score = Column(Float)
    human_score = Column(Float)
    defects_found = Column(Integer, default=0, nullable=False)
    rework_required = Column(Boolean, default=False, nullable=False)
    production_issue = Column(Boolean, default=False, nullable=False)
    quality_score = Column(Float, default=0.0, nullable=False)
    evaluation_version = Column(Integer, default=1, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "execution_id", "evaluation_version", name="uq_arceus_execution_evaluations_version"),
        Index("ix_arceus_execution_evaluations_execution", "tenant_id", "execution_id"),
        Index("ix_arceus_execution_evaluations_task_type", "tenant_id", "task_type", "quality_score"),
    )


class ArceusBillingPlan(KernelMutableMixin, Base):
    __tablename__ = "arceus_billing_plans"

    plan_key = Column(String(120), nullable=False)
    display_name = Column(Text, nullable=False)
    status = Column(String(60), default="active", nullable=False)
    billing_model = Column(String(80), default="hybrid", nullable=False)
    monthly_price_cents = Column(BigInteger, default=0, nullable=False)
    annual_price_cents = Column(BigInteger, default=0, nullable=False)
    currency = Column(String(12), default="USD", nullable=False)
    included_credits_cents = Column(BigInteger, default=0, nullable=False)
    feature_limits = Column(JSON, default=dict, nullable=False)
    stripe_price_ids = Column(JSON, default=dict, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("plan_key", name="uq_arceus_billing_plans_key"),
        CheckConstraint("status IN ('draft', 'active', 'deprecated', 'archived')", name="ck_arceus_billing_plans_status"),
        Index("ix_arceus_billing_plans_status", "status"),
    )


class ArceusBillingSubscription(KernelTenantMixin, Base):
    __tablename__ = "arceus_billing_subscriptions"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_organizations.id"))
    plan_key = Column(String(120), nullable=False)
    status = Column(String(60), default="trial", nullable=False)
    billing_cycle = Column(String(40), default="monthly", nullable=False)
    seat_limit = Column(Integer, default=1, nullable=False)
    assigned_seats = Column(Integer, default=0, nullable=False)
    provider = Column(String(80), default="internal", nullable=False)
    provider_customer_id = Column(String(255))
    provider_subscription_id = Column(String(255))
    renewal_at = Column(DateTime(timezone=True))
    trial_ends_at = Column(DateTime(timezone=True))
    cancel_at = Column(DateTime(timezone=True))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "provider", "provider_subscription_id", name="uq_arceus_billing_subscriptions_provider"),
        CheckConstraint("status IN ('trial', 'active', 'past_due', 'cancelled', 'expired', 'suspended')", name="ck_arceus_billing_subscriptions_status"),
        CheckConstraint("billing_cycle IN ('monthly', 'annual', 'contract', 'usage')", name="ck_arceus_billing_subscriptions_cycle"),
        Index("ix_arceus_billing_subscriptions_tenant", "tenant_id", "status"),
    )


class ArceusBillingEntitlement(KernelTenantMixin, Base):
    __tablename__ = "arceus_billing_entitlements"

    subscription_id = Column(UUID(as_uuid=True), ForeignKey("arceus_billing_subscriptions.id"), nullable=False)
    feature_key = Column(String(160), nullable=False)
    limit_value = Column(String(80), default="0", nullable=False)
    current_usage = Column(Numeric(18, 8), default=0, nullable=False)
    period = Column(String(40), default="monthly", nullable=False)
    reset_at = Column(DateTime(timezone=True))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "subscription_id", "feature_key", name="uq_arceus_billing_entitlements_feature"),
        Index("ix_arceus_billing_entitlements_subscription", "tenant_id", "subscription_id"),
    )


class ArceusBillingUsageEvent(KernelTenantMixin, Base):
    __tablename__ = "arceus_billing_usage_events"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_organizations.id"))
    workspace_id = Column(UUID(as_uuid=True))
    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    execution_id = Column(UUID(as_uuid=True), ForeignKey("arceus_ai_execution_ledger.id"))
    metric = Column(String(160), nullable=False)
    quantity = Column(Numeric(18, 8), nullable=False)
    unit = Column(String(80), default="unit", nullable=False)
    provider_key = Column(String(120))
    model_key = Column(String(160))
    provider_cost_cents = Column(Numeric(18, 6), default=0, nullable=False)
    customer_price_cents = Column(Numeric(18, 6), default=0, nullable=False)
    currency = Column(String(12), default="USD", nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    idempotency_key = Column(String(180), nullable=False)
    source = Column(String(120), default="runtime", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_arceus_billing_usage_events_idempotency"),
        Index("ix_arceus_billing_usage_events_metric", "tenant_id", "metric", "occurred_at"),
        Index("ix_arceus_billing_usage_events_mission", "tenant_id", "mission_id", "occurred_at"),
    )


class ArceusCreditWallet(KernelTenantMixin, Base):
    __tablename__ = "arceus_credit_wallets"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_organizations.id"))
    balance_cents = Column(Numeric(18, 6), default=0, nullable=False)
    currency = Column(String(12), default="USD", nullable=False)
    status = Column(String(60), default="active", nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "organization_id", "currency", name="uq_arceus_credit_wallets_scope"),
        CheckConstraint("status IN ('active', 'locked', 'closed')", name="ck_arceus_credit_wallets_status"),
    )


class ArceusCreditTransaction(KernelTenantMixin, Base):
    __tablename__ = "arceus_credit_transactions"

    wallet_id = Column(UUID(as_uuid=True), ForeignKey("arceus_credit_wallets.id"), nullable=False)
    transaction_type = Column(String(60), nullable=False)
    credit_type = Column(String(80), default="purchased", nullable=False)
    amount_cents = Column(Numeric(18, 6), nullable=False)
    balance_after_cents = Column(Numeric(18, 6), nullable=False)
    currency = Column(String(12), default="USD", nullable=False)
    idempotency_key = Column(String(180), nullable=False)
    reference_type = Column(String(120))
    reference_id = Column(UUID(as_uuid=True))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_arceus_credit_transactions_idempotency"),
        CheckConstraint("transaction_type IN ('grant', 'consume', 'refund', 'expire', 'adjust')", name="ck_arceus_credit_transactions_type"),
        Index("ix_arceus_credit_transactions_wallet", "tenant_id", "wallet_id", "created_at"),
    )


class ArceusInvoice(KernelTenantMixin, Base):
    __tablename__ = "arceus_invoices"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_organizations.id"))
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("arceus_billing_subscriptions.id"))
    invoice_number = Column(String(120), nullable=False)
    status = Column(String(60), default="draft", nullable=False)
    subtotal_cents = Column(Numeric(18, 6), default=0, nullable=False)
    tax_cents = Column(Numeric(18, 6), default=0, nullable=False)
    credits_applied_cents = Column(Numeric(18, 6), default=0, nullable=False)
    total_cents = Column(Numeric(18, 6), default=0, nullable=False)
    currency = Column(String(12), default="USD", nullable=False)
    provider_invoice_id = Column(String(255))
    due_at = Column(DateTime(timezone=True))
    paid_at = Column(DateTime(timezone=True))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "invoice_number", name="uq_arceus_invoices_number"),
        CheckConstraint("status IN ('draft', 'open', 'paid', 'void', 'uncollectible', 'refunded')", name="ck_arceus_invoices_status"),
        Index("ix_arceus_invoices_tenant_status", "tenant_id", "status", "created_at"),
    )


class ArceusInvoiceItem(KernelTenantMixin, Base):
    __tablename__ = "arceus_invoice_items"

    invoice_id = Column(UUID(as_uuid=True), ForeignKey("arceus_invoices.id"), nullable=False)
    usage_event_id = Column(UUID(as_uuid=True), ForeignKey("arceus_billing_usage_events.id"))
    item_type = Column(String(80), nullable=False)
    description = Column(Text, nullable=False)
    quantity = Column(Numeric(18, 8), default=1, nullable=False)
    unit_amount_cents = Column(Numeric(18, 6), default=0, nullable=False)
    total_cents = Column(Numeric(18, 6), default=0, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_arceus_invoice_items_invoice", "tenant_id", "invoice_id"),
    )


class ArceusFinancialLedgerEntry(KernelTenantMixin, Base):
    __tablename__ = "arceus_financial_ledger_entries"

    entry_group_id = Column(UUID(as_uuid=True), nullable=False)
    account = Column(String(160), nullable=False)
    direction = Column(String(20), nullable=False)
    amount_cents = Column(Numeric(18, 6), nullable=False)
    currency = Column(String(12), default="USD", nullable=False)
    source_type = Column(String(120), nullable=False)
    source_id = Column(UUID(as_uuid=True))
    idempotency_key = Column(String(180), nullable=False)
    immutable = Column(Boolean, default=True, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", "account", "direction", name="uq_arceus_financial_ledger_idempotency"),
        CheckConstraint("direction IN ('debit', 'credit')", name="ck_arceus_financial_ledger_direction"),
        Index("ix_arceus_financial_ledger_source", "tenant_id", "source_type", "source_id"),
    )


class ArceusMarketplaceOrder(KernelTenantMixin, Base):
    __tablename__ = "arceus_marketplace_orders"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_organizations.id"))
    plugin_id = Column(UUID(as_uuid=True), ForeignKey("arceus_plugins.id"))
    publisher_id = Column(UUID(as_uuid=True), ForeignKey("arceus_plugin_publishers.id"))
    status = Column(String(60), default="pending", nullable=False)
    gross_cents = Column(Numeric(18, 6), nullable=False)
    tax_cents = Column(Numeric(18, 6), default=0, nullable=False)
    gateway_fee_cents = Column(Numeric(18, 6), default=0, nullable=False)
    marketplace_fee_cents = Column(Numeric(18, 6), default=0, nullable=False)
    publisher_net_cents = Column(Numeric(18, 6), default=0, nullable=False)
    currency = Column(String(12), default="USD", nullable=False)
    provider_payment_id = Column(String(255))
    idempotency_key = Column(String(180), nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_arceus_marketplace_orders_idempotency"),
        CheckConstraint("status IN ('pending', 'paid', 'refunded', 'disputed', 'cancelled')", name="ck_arceus_marketplace_orders_status"),
    )


class ArceusPublisherPayout(KernelTenantMixin, Base):
    __tablename__ = "arceus_publisher_payouts"

    publisher_id = Column(UUID(as_uuid=True), ForeignKey("arceus_plugin_publishers.id"), nullable=False)
    status = Column(String(60), default="scheduled", nullable=False)
    amount_cents = Column(Numeric(18, 6), nullable=False)
    currency = Column(String(12), default="USD", nullable=False)
    period_start = Column(DateTime(timezone=True))
    period_end = Column(DateTime(timezone=True))
    provider_payout_id = Column(String(255))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('scheduled', 'processing', 'paid', 'failed', 'held')", name="ck_arceus_publisher_payouts_status"),
        Index("ix_arceus_publisher_payouts_publisher", "tenant_id", "publisher_id", "status"),
    )


class ArceusDeploymentTarget(KernelTenantMixin, Base):
    __tablename__ = "arceus_deployment_targets"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_organizations.id"))
    name = Column(Text, nullable=False)
    provider_type = Column(String(80), nullable=False)
    credential_binding_id = Column(String(255), nullable=False)
    regions = Column(JSON, default=list, nullable=False)
    capabilities = Column(JSON, default=dict, nullable=False)
    policy_profile_id = Column(String(160))
    status = Column(String(60), default="active", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("provider_type IN ('aws', 'azure', 'gcp', 'railway', 'render', 'vercel', 'kubernetes', 'docker', 'on_premises', 'custom')", name="ck_arceus_deployment_targets_provider"),
        CheckConstraint("status IN ('active', 'degraded', 'disabled', 'unreachable')", name="ck_arceus_deployment_targets_status"),
        Index("ix_arceus_deployment_targets_provider", "tenant_id", "provider_type", "status"),
    )


class ArceusRuntimeProfile(KernelTenantMixin, Base):
    __tablename__ = "arceus_runtime_profiles"

    name = Column(Text, nullable=False)
    runtime_type = Column(String(80), nullable=False)
    startup_command = Column(Text)
    port = Column(Integer)
    health_check = Column(JSON, default=dict, nullable=False)
    resources = Column(JSON, default=dict, nullable=False)
    scaling = Column(JSON, default=dict, nullable=False)
    shutdown_grace_period_seconds = Column(Integer, default=30, nullable=False)
    status = Column(String(60), default="active", nullable=False)

    __table_args__ = (
        CheckConstraint("runtime_type IN ('container', 'serverless', 'static', 'virtual_machine', 'kubernetes', 'edge', 'desktop_distribution')", name="ck_arceus_runtime_profiles_type"),
        CheckConstraint("status IN ('active', 'deprecated', 'archived')", name="ck_arceus_runtime_profiles_status"),
        Index("ix_arceus_runtime_profiles_type", "tenant_id", "runtime_type", "status"),
    )


class ArceusDeploymentApplication(KernelTenantMixin, Base):
    __tablename__ = "arceus_deployment_applications"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_organizations.id"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"), nullable=False)
    name = Column(Text, nullable=False)
    slug = Column(String(255), nullable=False)
    source_repository_id = Column(UUID(as_uuid=True), ForeignKey("arceus_project_repositories.id"))
    application_type = Column(String(80), nullable=False)
    runtime_profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_runtime_profiles.id"))
    status = Column(String(60), default="active", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "project_id", "slug", name="uq_arceus_deployment_applications_slug"),
        CheckConstraint("application_type IN ('web', 'api', 'worker', 'desktop', 'mobile_backend', 'scheduled_job', 'service', 'monorepo')", name="ck_arceus_deployment_applications_type"),
        CheckConstraint("status IN ('active', 'paused', 'archived')", name="ck_arceus_deployment_applications_status"),
        Index("ix_arceus_deployment_applications_project", "tenant_id", "project_id", "status"),
    )


class ArceusDeploymentEnvironment(KernelTenantMixin, Base):
    __tablename__ = "arceus_deployment_environments"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_organizations.id"))
    application_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_applications.id"), nullable=False)
    target_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_targets.id"), nullable=False)
    name = Column(Text, nullable=False)
    environment_type = Column(String(80), nullable=False)
    region = Column(String(120), default="us-east-1", nullable=False)
    status = Column(String(60), default="creating", nullable=False)
    protection_level = Column(String(60), default="standard", nullable=False)
    configuration_version_id = Column(UUID(as_uuid=True))
    infrastructure_stack_id = Column(UUID(as_uuid=True))
    ttl_expires_at = Column(DateTime(timezone=True))
    current_release_id = Column(UUID(as_uuid=True))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "application_id", "name", name="uq_arceus_deployment_environments_name"),
        CheckConstraint("environment_type IN ('development', 'preview', 'testing', 'staging', 'production', 'disaster_recovery')", name="ck_arceus_deployment_environments_type"),
        CheckConstraint("status IN ('creating', 'ready', 'degraded', 'suspended', 'destroying', 'destroyed', 'failed')", name="ck_arceus_deployment_environments_status"),
        CheckConstraint("protection_level IN ('none', 'standard', 'protected', 'critical')", name="ck_arceus_deployment_environments_protection"),
        Index("ix_arceus_deployment_environments_app", "tenant_id", "application_id", "environment_type", "status"),
    )


class ArceusDeploymentRelease(KernelTenantMixin, Base):
    __tablename__ = "arceus_deployment_releases"

    application_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_applications.id"), nullable=False)
    version = Column(String(120), nullable=False)
    source_commit_sha = Column(String(80), nullable=False)
    source_branch = Column(String(255))
    source_tag = Column(String(255))
    build_id = Column(String(255), nullable=False)
    artifact_ids = Column(JSON, default=list, nullable=False)
    configuration_version_id = Column(UUID(as_uuid=True))
    verification_report_id = Column(UUID(as_uuid=True))
    created_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    status = Column(String(60), default="draft", nullable=False)
    provenance = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "application_id", "version", name="uq_arceus_deployment_releases_version"),
        CheckConstraint("status IN ('draft', 'building', 'verified', 'approved', 'deployable', 'deprecated', 'revoked')", name="ck_arceus_deployment_releases_status"),
        Index("ix_arceus_deployment_releases_app", "tenant_id", "application_id", "status", "created_at"),
    )


class ArceusDeploymentArtifact(KernelTenantMixin, Base):
    __tablename__ = "arceus_deployment_artifacts"

    release_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_releases.id"), nullable=False)
    artifact_type = Column(String(80), nullable=False)
    digest = Column(String(160), nullable=False)
    uri = Column(Text, nullable=False)
    size_bytes = Column(BigInteger, default=0, nullable=False)
    architecture = Column(String(80))
    operating_system = Column(String(80))
    signed = Column(Boolean, default=False, nullable=False)
    signature_reference = Column(Text)
    sbom_reference = Column(Text)
    scan_status = Column(String(60), default="pending", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "release_id", "digest", name="uq_arceus_deployment_artifacts_digest"),
        CheckConstraint("artifact_type IN ('container_image', 'server_bundle', 'static_assets', 'desktop_installer', 'mobile_bundle', 'function_package', 'infrastructure_plan')", name="ck_arceus_deployment_artifacts_type"),
        CheckConstraint("scan_status IN ('pending', 'passed', 'warning', 'failed', 'waived')", name="ck_arceus_deployment_artifacts_scan"),
        Index("ix_arceus_deployment_artifacts_release", "tenant_id", "release_id", "artifact_type"),
    )


class ArceusDeploymentRequest(KernelTenantMixin, Base):
    __tablename__ = "arceus_deployment_requests"

    release_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_releases.id"), nullable=False)
    environment_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_environments.id"), nullable=False)
    strategy = Column(String(60), default="rolling", nullable=False)
    requested_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    reason = Column(Text)
    dry_run = Column(Boolean, default=False, nullable=False)
    approval_policy_id = Column(String(160))
    verification_policy_id = Column(String(160), default="default_release_gate", nullable=False)
    status = Column(String(60), default="requested", nullable=False)
    scheduled_for = Column(DateTime(timezone=True))
    approved_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    approved_at = Column(DateTime(timezone=True))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("strategy IN ('recreate', 'rolling', 'blue_green', 'canary', 'shadow', 'immutable', 'in_place')", name="ck_arceus_deployment_requests_strategy"),
        CheckConstraint("status IN ('requested', 'planning', 'awaiting_approval', 'approved', 'queued', 'deploying', 'verifying', 'shifting_traffic', 'completed', 'failed', 'rolling_back', 'rolled_back', 'cancelled')", name="ck_arceus_deployment_requests_status"),
        Index("ix_arceus_deployment_requests_env", "tenant_id", "environment_id", "status", "created_at"),
    )


class ArceusDeploymentPlan(KernelTenantMixin, Base):
    __tablename__ = "arceus_deployment_plans"

    request_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_requests.id"), nullable=False)
    environment_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_environments.id"), nullable=False)
    release_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_releases.id"), nullable=False)
    strategy = Column(String(60), nullable=False)
    infrastructure_changes = Column(JSON, default=list, nullable=False)
    configuration_changes = Column(JSON, default=list, nullable=False)
    secret_binding_changes = Column(JSON, default=list, nullable=False)
    migration_plan = Column(JSON, default=dict, nullable=False)
    traffic_plan = Column(JSON, default=dict, nullable=False)
    health_verification_plan = Column(JSON, default=dict, nullable=False)
    rollback_plan = Column(JSON, default=dict, nullable=False)
    estimated_duration_seconds = Column(Integer, default=0, nullable=False)
    estimated_cost_cents = Column(Numeric(18, 6), default=0, nullable=False)
    risk_score = Column(Integer, default=0, nullable=False)
    warnings = Column(JSON, default=list, nullable=False)
    blockers = Column(JSON, default=list, nullable=False)
    plan_hash = Column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "request_id", "plan_hash", name="uq_arceus_deployment_plans_hash"),
        Index("ix_arceus_deployment_plans_request", "tenant_id", "request_id", "created_at"),
    )


class ArceusDeploymentHealthCheck(KernelTenantMixin, Base):
    __tablename__ = "arceus_deployment_health_checks"

    environment_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_environments.id"), nullable=False)
    deployment_request_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_requests.id"))
    check_type = Column(String(80), nullable=False)
    target = Column(Text, nullable=False)
    status = Column(String(60), default="pending", nullable=False)
    latency_ms = Column(Integer)
    output = Column(JSON, default=dict, nullable=False)
    checked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'passed', 'warning', 'failed')", name="ck_arceus_deployment_health_checks_status"),
        Index("ix_arceus_deployment_health_checks_env", "tenant_id", "environment_id", "status", "checked_at"),
    )


class ArceusDeploymentRollback(KernelTenantMixin, Base):
    __tablename__ = "arceus_deployment_rollbacks"

    deployment_request_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_requests.id"), nullable=False)
    environment_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_environments.id"), nullable=False)
    from_release_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_releases.id"), nullable=False)
    to_release_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_releases.id"))
    reason = Column(Text, nullable=False)
    status = Column(String(60), default="planned", nullable=False)
    rollback_steps = Column(JSON, default=list, nullable=False)
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('planned', 'approved', 'running', 'completed', 'failed', 'cancelled')", name="ck_arceus_deployment_rollbacks_status"),
        Index("ix_arceus_deployment_rollbacks_env", "tenant_id", "environment_id", "status"),
    )


class ArceusDeploymentBackup(KernelTenantMixin, Base):
    __tablename__ = "arceus_deployment_backups"

    environment_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_environments.id"), nullable=False)
    backup_type = Column(String(80), nullable=False)
    status = Column(String(60), default="scheduled", nullable=False)
    storage_uri = Column(Text)
    encrypted = Column(Boolean, default=True, nullable=False)
    integrity_hash = Column(String(160))
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    expires_at = Column(DateTime(timezone=True))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("backup_type IN ('database', 'object_storage', 'configuration', 'full_environment')", name="ck_arceus_deployment_backups_type"),
        CheckConstraint("status IN ('scheduled', 'running', 'completed', 'failed', 'expired', 'restored')", name="ck_arceus_deployment_backups_status"),
        Index("ix_arceus_deployment_backups_env", "tenant_id", "environment_id", "status"),
    )


class ArceusDeploymentDriftReport(KernelTenantMixin, Base):
    __tablename__ = "arceus_deployment_drift_reports"

    environment_id = Column(UUID(as_uuid=True), ForeignKey("arceus_deployment_environments.id"), nullable=False)
    drift_type = Column(String(80), nullable=False)
    desired_hash = Column(String(128), nullable=False)
    actual_hash = Column(String(128), nullable=False)
    severity = Column(String(60), default="medium", nullable=False)
    status = Column(String(60), default="open", nullable=False)
    findings = Column(JSON, default=list, nullable=False)
    checked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("drift_type IN ('infrastructure', 'configuration', 'secret_binding', 'network', 'runtime', 'security')", name="ck_arceus_deployment_drift_reports_type"),
        CheckConstraint("severity IN ('low', 'medium', 'high', 'critical')", name="ck_arceus_deployment_drift_reports_severity"),
        CheckConstraint("status IN ('open', 'accepted', 'resolved', 'ignored')", name="ck_arceus_deployment_drift_reports_status"),
        Index("ix_arceus_deployment_drift_reports_env", "tenant_id", "environment_id", "status", "severity"),
    )


class ArceusParticipant(KernelTenantMixin, Base):
    __tablename__ = "arceus_participants"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_organizations.id"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    organization_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    participant_type = Column(String(80), nullable=False)
    display_name = Column(Text, nullable=False)
    role_key = Column(String(120))
    specialist_profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_specialist_profiles.id"))
    capabilities = Column(JSON, default=list, nullable=False)
    authorities = Column(JSON, default=list, nullable=False)
    active_mission_ids = Column(JSON, default=list, nullable=False)
    status = Column(String(60), default="available", nullable=False)

    __table_args__ = (
        CheckConstraint(
            "participant_type IN ('human', 'ai_specialist', 'service', 'verifier', 'integration', 'policy_authority')",
            name="ck_arceus_participants_type",
        ),
        CheckConstraint(
            "status IN ('available', 'busy', 'waiting', 'paused', 'offline', 'degraded', 'suspended', 'revoked')",
            name="ck_arceus_participants_status",
        ),
        Index("ix_arceus_participants_org_status", "tenant_id", "organization_id", "status"),
    )


class ArceusCollaborationMessage(KernelTenantMixin, Base):
    __tablename__ = "arceus_collaboration_messages"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_definitions.id"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    decision_id = Column(UUID(as_uuid=True), ForeignKey("arceus_decisions.id"))
    review_id = Column(UUID(as_uuid=True))
    message_type = Column(String(80), nullable=False)
    sender_participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"), nullable=False)
    subject = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    structured_payload = Column(JSON, default=dict, nullable=False)
    priority = Column(String(40), default="normal", nullable=False)
    confidentiality = Column(String(60), default="mission", nullable=False)
    requires_acknowledgement = Column(Boolean, default=False, nullable=False)
    response_required_by = Column(DateTime(timezone=True))
    correlation_id = Column(UUID(as_uuid=True), nullable=False)
    causation_id = Column(UUID(as_uuid=True))
    body_hash = Column(String(128), nullable=False)
    deleted_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "message_type IN ('command', 'question', 'answer', 'finding', 'proposal', 'review_request', 'review_result', 'decision_request', 'decision_result', 'handoff', 'status_update', 'risk_alert', 'incident', 'approval_request', 'approval_result', 'knowledge_proposal', 'system_notice')",
            name="ck_arceus_collaboration_messages_type",
        ),
        CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name="ck_arceus_collaboration_messages_priority"),
        CheckConstraint(
            "confidentiality IN ('public', 'tenant', 'project', 'mission', 'task', 'restricted', 'secret_reference_only')",
            name="ck_arceus_collaboration_messages_confidentiality",
        ),
        Index("ix_arceus_collaboration_messages_mission_created", "tenant_id", "mission_id", "created_at"),
        Index("ix_arceus_collaboration_messages_task_created", "tenant_id", "task_id", "created_at"),
    )


class ArceusCollaborationMessageRecipient(KernelTenantMixin, Base):
    __tablename__ = "arceus_collaboration_message_recipients"

    message_id = Column(UUID(as_uuid=True), ForeignKey("arceus_collaboration_messages.id"), nullable=False)
    participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"), nullable=False)
    delivery_status = Column(String(60), default="delivered", nullable=False)
    relevance_score = Column(Float, default=0.0, nullable=False)
    delivered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("participant_id", "message_id", name="uq_arceus_collaboration_recipient_message"),
        Index("ix_arceus_collaboration_recipients_participant", "tenant_id", "participant_id", "delivery_status"),
    )


class ArceusCollaborationMessageTopic(KernelTenantMixin, Base):
    __tablename__ = "arceus_collaboration_message_topics"

    message_id = Column(UUID(as_uuid=True), ForeignKey("arceus_collaboration_messages.id"), nullable=False)
    topic_key = Column(String(240), nullable=False)

    __table_args__ = (
        UniqueConstraint("message_id", "topic_key", name="uq_arceus_collaboration_message_topic"),
        Index("ix_arceus_collaboration_topics_key", "tenant_id", "topic_key"),
    )


class ArceusPresenceSession(KernelTenantMixin, Base):
    __tablename__ = "arceus_presence_sessions"

    user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    resource_type = Column(String(120))
    resource_id = Column(UUID(as_uuid=True))
    status = Column(String(60), default="online", nullable=False)
    activity = Column(String(160), default="viewing", nullable=False)
    device_id = Column(String(180))
    cursor_payload = Column(JSON, default=dict, nullable=False)
    last_seen_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", "participant_id", "device_id", name="uq_arceus_presence_identity"),
        CheckConstraint("status IN ('online', 'away', 'busy', 'offline')", name="ck_arceus_presence_status"),
        Index("ix_arceus_presence_project", "tenant_id", "project_id", "status", "last_seen_at"),
    )


class ArceusDiscussionThread(KernelTenantMixin, Base):
    __tablename__ = "arceus_discussion_threads"

    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    resource_type = Column(String(120), nullable=False)
    resource_id = Column(UUID(as_uuid=True))
    title = Column(Text, nullable=False)
    status = Column(String(60), default="open", nullable=False)
    summary = Column(Text)
    unresolved_questions = Column(JSON, default=list, nullable=False)
    action_items = Column(JSON, default=list, nullable=False)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    created_by_participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"))

    __table_args__ = (
        CheckConstraint("status IN ('open', 'resolved', 'archived')", name="ck_arceus_discussion_threads_status"),
        Index("ix_arceus_discussion_threads_resource", "tenant_id", "resource_type", "resource_id", "status"),
        Index("ix_arceus_discussion_threads_project", "tenant_id", "project_id", "status"),
    )


class ArceusComment(KernelTenantMixin, Base):
    __tablename__ = "arceus_comments"

    thread_id = Column(UUID(as_uuid=True), ForeignKey("arceus_discussion_threads.id"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    resource_type = Column(String(120), nullable=False)
    resource_id = Column(UUID(as_uuid=True))
    parent_comment_id = Column(UUID(as_uuid=True), ForeignKey("arceus_comments.id"))
    author_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    author_participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"))
    body = Column(Text, nullable=False)
    mentions = Column(JSON, default=list, nullable=False)
    reactions = Column(JSON, default=dict, nullable=False)
    body_hash = Column(String(128), nullable=False)
    status = Column(String(60), default="active", nullable=False)
    resolved_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('active', 'resolved', 'deleted')", name="ck_arceus_comments_status"),
        Index("ix_arceus_comments_resource", "tenant_id", "resource_type", "resource_id", "created_at"),
        Index("ix_arceus_comments_thread", "tenant_id", "thread_id", "created_at"),
    )


class ArceusKnowledgePage(KernelTenantMixin, Base):
    __tablename__ = "arceus_knowledge_pages"

    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"), nullable=False)
    parent_page_id = Column(UUID(as_uuid=True), ForeignKey("arceus_knowledge_pages.id"))
    title = Column(Text, nullable=False)
    slug = Column(String(255), nullable=False)
    page_type = Column(String(80), default="doc", nullable=False)
    markdown = Column(Text, nullable=False)
    author_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    author_participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"))
    status = Column(String(60), default="published", nullable=False)
    freshness_status = Column(String(60), default="current", nullable=False)
    source_ids = Column(JSON, default=list, nullable=False)
    content_hash = Column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "project_id", "slug", name="uq_arceus_knowledge_pages_slug"),
        CheckConstraint("page_type IN ('doc', 'adr', 'runbook', 'meeting_note', 'api_doc', 'postmortem', 'requirement')", name="ck_arceus_knowledge_pages_type"),
        CheckConstraint("status IN ('draft', 'published', 'archived')", name="ck_arceus_knowledge_pages_status"),
        Index("ix_arceus_knowledge_pages_project", "tenant_id", "project_id", "page_type", "status"),
    )


class ArceusKnowledgeRevision(KernelTenantMixin, Base):
    __tablename__ = "arceus_knowledge_revisions"

    page_id = Column(UUID(as_uuid=True), ForeignKey("arceus_knowledge_pages.id"), nullable=False)
    revision_number = Column(Integer, nullable=False)
    markdown = Column(Text, nullable=False)
    content_hash = Column(String(128), nullable=False)
    author_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    change_summary = Column(Text)

    __table_args__ = (
        UniqueConstraint("tenant_id", "page_id", "revision_number", name="uq_arceus_knowledge_revisions_number"),
        Index("ix_arceus_knowledge_revisions_page", "tenant_id", "page_id", "revision_number"),
    )


class ArceusActivityEvent(KernelTenantMixin, Base):
    __tablename__ = "arceus_activity_events"

    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    actor_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    actor_participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"))
    event_type = Column(String(160), nullable=False)
    resource_type = Column(String(120), nullable=False)
    resource_id = Column(UUID(as_uuid=True))
    message = Column(Text, nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_arceus_activity_events_project", "tenant_id", "project_id", "occurred_at"),
        Index("ix_arceus_activity_events_resource", "tenant_id", "resource_type", "resource_id"),
    )


class ArceusNotification(KernelTenantMixin, Base):
    __tablename__ = "arceus_notifications"

    recipient_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    recipient_participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"))
    notification_type = Column(String(120), nullable=False)
    title = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    channels = Column(JSON, default=list, nullable=False)
    status = Column(String(60), default="unread", nullable=False)
    resource_type = Column(String(120))
    resource_id = Column(UUID(as_uuid=True))
    delivered_at = Column(DateTime(timezone=True))
    read_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('queued', 'delivered', 'unread', 'read', 'dismissed', 'failed')", name="ck_arceus_notifications_status"),
        Index("ix_arceus_notifications_recipient", "tenant_id", "recipient_user_id", "recipient_participant_id", "status"),
    )


class ArceusCollaborationReviewRequest(KernelTenantMixin, Base):
    __tablename__ = "arceus_collaboration_review_requests"

    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"), nullable=False)
    requester_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    reviewer_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    reviewer_team_id = Column(UUID(as_uuid=True), ForeignKey("arceus_collaboration_teams.id"))
    review_type = Column(String(120), nullable=False)
    target_type = Column(String(120), nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)
    status = Column(String(60), default="requested", nullable=False)
    due_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('requested', 'accepted', 'completed', 'changes_requested', 'cancelled')", name="ck_arceus_collab_review_requests_status"),
        Index("ix_arceus_collab_review_requests_project", "tenant_id", "project_id", "status"),
    )


class ArceusMeetingNote(KernelTenantMixin, Base):
    __tablename__ = "arceus_meeting_notes"

    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"), nullable=False)
    title = Column(Text, nullable=False)
    attendees = Column(JSON, default=list, nullable=False)
    summary = Column(Text, nullable=False)
    action_items = Column(JSON, default=list, nullable=False)
    blockers = Column(JSON, default=list, nullable=False)
    follow_ups = Column(JSON, default=list, nullable=False)
    source_transcript_hash = Column(String(128))

    __table_args__ = (
        Index("ix_arceus_meeting_notes_project", "tenant_id", "project_id", "created_at"),
    )


class ArceusParticipantInboxItem(KernelTenantMixin, Base):
    __tablename__ = "arceus_participant_inbox_items"

    participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"), nullable=False)
    message_id = Column(UUID(as_uuid=True), ForeignKey("arceus_collaboration_messages.id"), nullable=False)
    delivery_status = Column(String(60), default="unread", nullable=False)
    relevance_score = Column(Float, default=0.0, nullable=False)
    delivered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at = Column(DateTime(timezone=True))
    acknowledged_at = Column(DateTime(timezone=True))
    responded_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "delivery_status IN ('unread', 'read', 'acknowledged', 'responded', 'expired', 'dismissed', 'escalated')",
            name="ck_arceus_participant_inbox_status",
        ),
        UniqueConstraint("participant_id", "message_id", name="uq_arceus_participant_inbox_message"),
        Index("ix_arceus_participant_inbox", "tenant_id", "participant_id", "delivery_status", "delivered_at"),
    )


class ArceusStreamSummary(KernelTenantMixin, Base):
    __tablename__ = "arceus_stream_summaries"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    stream_key = Column(String(240), nullable=False)
    source_message_ids = Column(JSON, default=list, nullable=False)
    summary_payload = Column(JSON, default=dict, nullable=False)
    summary_version = Column(Integer, default=1, nullable=False)
    content_hash = Column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "stream_key", "summary_version", name="uq_arceus_stream_summary_version"),
        Index("ix_arceus_stream_summaries_stream", "tenant_id", "mission_id", "stream_key"),
    )


class ArceusReview(KernelTenantMixin, Base):
    __tablename__ = "arceus_reviews"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    review_type = Column(String(100), nullable=False)
    target_type = Column(String(100), nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)
    target_hash = Column(String(128), nullable=False)
    requester_participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"), nullable=False)
    reviewer_participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"), nullable=False)
    required = Column(Boolean, default=True, nullable=False)
    blocking = Column(Boolean, default=True, nullable=False)
    status = Column(String(60), default="requested", nullable=False)
    verdict = Column(String(60))
    due_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('requested', 'assigned', 'completed', 'rejected', 'expired')", name="ck_arceus_reviews_status"),
        Index("ix_arceus_reviews_mission_status", "tenant_id", "mission_id", "status"),
    )


class ArceusReviewFinding(KernelTenantMixin, Base):
    __tablename__ = "arceus_review_findings"

    review_id = Column(UUID(as_uuid=True), ForeignKey("arceus_reviews.id"), nullable=False)
    finding_key = Column(String(160), nullable=False)
    severity = Column(String(60), default="medium", nullable=False)
    statement = Column(Text, nullable=False)
    evidence_ids = Column(JSON, default=list, nullable=False)
    status = Column(String(60), default="open", nullable=False)

    __table_args__ = (
        UniqueConstraint("review_id", "finding_key", name="uq_arceus_review_finding_key"),
        Index("ix_arceus_review_findings_review", "tenant_id", "review_id", "severity"),
    )


class ArceusConflict(KernelTenantMixin, Base):
    __tablename__ = "arceus_conflicts"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    conflict_type = Column(String(100), nullable=False)
    title = Column(Text, nullable=False)
    status = Column(String(60), default="open", nullable=False)
    severity = Column(String(60), default="medium", nullable=False)
    resolution = Column(JSON, default=dict, nullable=False)
    escalated_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('open', 'escalated', 'resolved', 'cancelled')", name="ck_arceus_conflicts_status"),
        Index("ix_arceus_conflicts_mission_status", "tenant_id", "mission_id", "status"),
    )


class ArceusMemoryItem(KernelTenantMixin, Base):
    __tablename__ = "arceus_memory_items"

    memory_scope = Column(String(80), nullable=False)
    scope_reference_id = Column(UUID(as_uuid=True))
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    content_type = Column(String(80), default="fact", nullable=False)
    source_type = Column(String(80), nullable=False)
    source_ids = Column(JSON, default=list, nullable=False)
    evidence_ids = Column(JSON, default=list, nullable=False)
    lifecycle_status = Column(String(60), default="proposed", nullable=False)
    trust_level = Column(String(60), default="unverified", nullable=False)
    confidence = Column(Float)
    sensitivity = Column(String(80), default="mission", nullable=False)
    content_hash = Column(String(128), nullable=False)
    valid_from = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    valid_until = Column(DateTime(timezone=True))
    supersedes_memory_id = Column(UUID(as_uuid=True), ForeignKey("arceus_memory_items.id"))

    __table_args__ = (
        CheckConstraint("memory_scope IN ('working', 'task', 'mission', 'project', 'organization', 'global')", name="ck_arceus_memory_items_scope"),
        CheckConstraint(
            "lifecycle_status IN ('proposed', 'verified', 'approved', 'disputed', 'superseded', 'archived')",
            name="ck_arceus_memory_items_lifecycle",
        ),
        UniqueConstraint("tenant_id", "memory_scope", "scope_reference_id", "content_hash", name="uq_arceus_memory_items_hash"),
        Index("ix_arceus_memory_items_scope", "tenant_id", "memory_scope", "scope_reference_id", "lifecycle_status"),
    )


class ArceusLessonProposal(KernelTenantMixin, Base):
    __tablename__ = "arceus_lesson_proposals"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    title = Column(Text, nullable=False)
    lesson = Column(Text, nullable=False)
    evidence_ids = Column(JSON, default=list, nullable=False)
    status = Column(String(60), default="proposed", nullable=False)
    impact = Column(String(60), default="medium", nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('proposed', 'approved', 'rejected')", name="ck_arceus_lesson_proposals_status"),
        Index("ix_arceus_lesson_proposals_mission", "tenant_id", "mission_id", "status"),
    )


class ArceusPerformanceObservation(KernelTenantMixin, Base):
    __tablename__ = "arceus_performance_observations"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"))
    subject_type = Column(String(80), nullable=False)
    subject_id = Column(UUID(as_uuid=True))
    metric_key = Column(String(120), nullable=False)
    metric_value = Column(Float, nullable=False)
    evidence_ids = Column(JSON, default=list, nullable=False)
    attribution = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_arceus_performance_observations_subject", "tenant_id", "subject_type", "subject_id", "metric_key"),
    )


class ArceusToolDefinition(KernelMutableMixin, Base):
    __tablename__ = "arceus_tool_definitions"

    tool_key = Column(String(160), nullable=False)
    display_name = Column(Text, nullable=False)
    tool_type = Column(String(100), nullable=False)
    permission_requirements = Column(JSON, default=dict, nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("tool_key", name="uq_arceus_tool_definitions_key"),)


class ArceusToolExecution(KernelTenantMixin, Base):
    __tablename__ = "arceus_tool_executions"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    tool_definition_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tool_definitions.id"), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    action = Column(String(160), nullable=False)
    target = Column(Text)
    status = Column(String(60), nullable=False)
    input_payload = Column(JSON, default=dict, nullable=False)
    output_payload = Column(JSON, default=dict, nullable=False)
    error = Column(JSON, default=dict, nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed', 'cancelled', 'blocked')", name="ck_arceus_tool_executions_status"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_arceus_tool_executions_idempotency"),
        Index("ix_arceus_tool_executions_mission", "tenant_id", "mission_id", "created_at"),
    )


class ArceusPolicyEvaluation(KernelTenantMixin, Base):
    __tablename__ = "arceus_policy_evaluations"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    policy_key = Column(String(160), nullable=False)
    subject = Column(JSON, default=dict, nullable=False)
    action = Column(String(160), nullable=False)
    resource = Column(JSON, default=dict, nullable=False)
    decision = Column(String(60), nullable=False)
    reason = Column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("decision IN ('allow', 'deny', 'needs_approval')", name="ck_arceus_policy_evaluations_decision"),
        Index("ix_arceus_policy_evaluations_mission", "tenant_id", "mission_id", "created_at"),
    )


class ArceusEvent(Base):
    __tablename__ = "arceus_events"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    aggregate_type = Column(String(120), nullable=False)
    aggregate_id = Column(UUID(as_uuid=True), nullable=False)
    aggregate_version = Column(BigInteger, nullable=False)
    event_type = Column(String(160), nullable=False)
    actor_type = Column(String(80), nullable=False)
    actor_id = Column(String(160))
    payload = Column(JSON, default=dict, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("aggregate_type", "aggregate_id", "aggregate_version", name="uq_arceus_events_aggregate_version"),
        Index("ix_arceus_events_aggregate", "aggregate_type", "aggregate_id", "aggregate_version"),
        Index("ix_arceus_events_tenant_time", "tenant_id", "occurred_at"),
    )


class ArceusOutboxMessage(Base):
    __tablename__ = "arceus_outbox_messages"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    event_id = Column(UUID(as_uuid=True), ForeignKey("arceus_events.id"), nullable=False)
    topic = Column(String(160), nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    status = Column(String(60), default="pending", nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    next_attempt_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    locked_by = Column(String(160))
    locked_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'processing', 'sent', 'failed', 'dead_letter')", name="ck_arceus_outbox_messages_status"),
        Index("ix_arceus_outbox_messages_pending", "status", "next_attempt_at"),
        Index("ix_arceus_outbox_messages_locked", "locked_by", "locked_at"),
    )


class ArceusInboxMessage(Base):
    __tablename__ = "arceus_inbox_messages"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    source = Column(String(160), nullable=False)
    external_message_id = Column(String(255), nullable=False)
    status = Column(String(60), default="processed", nullable=False)
    payload_hash = Column(String(128), nullable=False)
    processed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_message_id", name="uq_arceus_inbox_messages_external"),
    )


class ArceusDataEventContract(KernelTenantMixin, Base):
    __tablename__ = "arceus_data_event_contracts"

    event_type = Column(String(200), nullable=False)
    version = Column(String(40), nullable=False)
    schema_format = Column(String(40), default="json_schema", nullable=False)
    schema_definition = Column(JSON, default=dict, nullable=False)
    compatibility_mode = Column(String(40), default="backward", nullable=False)
    owner_domain = Column(String(120), nullable=False)
    classification = Column(String(40), default="internal", nullable=False)
    retention_policy_id = Column(String(120), nullable=False)
    status = Column(String(40), default="active", nullable=False)
    example_event = Column(JSON, default=dict, nullable=False)
    documentation = Column(Text)

    __table_args__ = (
        CheckConstraint("schema_format IN ('json_schema', 'avro', 'protobuf')", name="ck_arceus_data_event_contracts_schema_format"),
        CheckConstraint("compatibility_mode IN ('backward', 'forward', 'full', 'none')", name="ck_arceus_data_event_contracts_compat"),
        CheckConstraint("classification IN ('public', 'internal', 'confidential', 'restricted', 'regulated', 'secret')", name="ck_arceus_data_event_contracts_classification"),
        CheckConstraint("status IN ('draft', 'active', 'deprecated', 'retired')", name="ck_arceus_data_event_contracts_status"),
        UniqueConstraint("tenant_id", "event_type", "version", name="uq_arceus_data_event_contracts_type_version"),
        Index("ix_arceus_data_event_contracts_domain", "tenant_id", "owner_domain", "status"),
    )


class ArceusDataOutboxRecord(Base):
    __tablename__ = "arceus_data_outbox_records"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    aggregate_type = Column(String(120), nullable=False)
    aggregate_id = Column(String(160), nullable=False)
    event_type = Column(String(200), nullable=False)
    event_version = Column(String(40), nullable=False)
    organization_id = Column(UUID(as_uuid=True))
    workspace_id = Column(UUID(as_uuid=True))
    actor_id = Column(String(160))
    correlation_id = Column(String(160))
    causation_id = Column(String(160))
    trace_id = Column(String(160))
    subject = Column(JSON, default=dict, nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    classification = Column(String(40), default="internal", nullable=False)
    topic = Column(String(200), nullable=False)
    partition_key = Column(String(200), nullable=False)
    status = Column(String(40), default="pending", nullable=False)
    attempt_count = Column(Integer, default=0, nullable=False)
    next_attempt_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    published_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("classification IN ('public', 'internal', 'confidential', 'restricted', 'regulated', 'secret')", name="ck_arceus_data_outbox_records_classification"),
        CheckConstraint("status IN ('pending', 'publishing', 'published', 'failed', 'dead_letter')", name="ck_arceus_data_outbox_records_status"),
        Index("ix_arceus_data_outbox_records_pending", "status", "next_attempt_at"),
        Index("ix_arceus_data_outbox_records_topic", "tenant_id", "topic", "occurred_at"),
        Index("ix_arceus_data_outbox_records_org", "tenant_id", "organization_id", "occurred_at"),
    )


class ArceusProcessedDataEvent(Base):
    __tablename__ = "arceus_processed_data_events"

    consumer_name = Column(String(200), primary_key=True)
    event_id = Column(UUID(as_uuid=True), primary_key=True)
    tenant_id = _tenant_fk()
    processed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    result_fingerprint = Column(String(160))
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_arceus_processed_data_events_tenant", "tenant_id", "processed_at"),
    )


class ArceusDeadLetterDataEvent(Base):
    __tablename__ = "arceus_dead_letter_data_events"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    original_event_id = Column(UUID(as_uuid=True), nullable=False)
    consumer_id = Column(String(200), nullable=False)
    failure_category = Column(String(60), nullable=False)
    failure_message = Column(Text, nullable=False)
    attempt_count = Column(Integer, default=1, nullable=False)
    replay_status = Column(String(40), default="pending", nullable=False)
    first_failed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_failed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    payload = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("failure_category IN ('schema', 'transient', 'permission', 'business_rule', 'unknown')", name="ck_arceus_dead_letter_data_events_failure"),
        CheckConstraint("replay_status IN ('pending', 'approved', 'replayed', 'discarded')", name="ck_arceus_dead_letter_data_events_replay"),
        Index("ix_arceus_dead_letter_data_events_status", "tenant_id", "replay_status", "last_failed_at"),
    )


class ArceusDataset(KernelTenantMixin, Base):
    __tablename__ = "arceus_datasets"

    dataset_key = Column(String(200), nullable=False)
    name = Column(Text, nullable=False)
    layer = Column(String(40), nullable=False)
    domain = Column(String(120), nullable=False)
    owner_service = Column(String(120), nullable=False)
    classification = Column(String(40), default="internal", nullable=False)
    lifecycle_status = Column(String(40), default="draft", nullable=False)
    freshness_slo_minutes = Column(Integer, default=1440, nullable=False)
    retention_policy_id = Column(String(120), nullable=False)
    access_policy = Column(JSON, default=dict, nullable=False)
    documentation = Column(Text)
    last_refreshed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("layer IN ('bronze', 'silver', 'gold', 'semantic', 'feature')", name="ck_arceus_datasets_layer"),
        CheckConstraint("classification IN ('public', 'internal', 'confidential', 'restricted', 'regulated', 'secret')", name="ck_arceus_datasets_classification"),
        CheckConstraint("lifecycle_status IN ('draft', 'development', 'validated', 'certified', 'active', 'deprecated', 'retired')", name="ck_arceus_datasets_lifecycle"),
        UniqueConstraint("tenant_id", "dataset_key", name="uq_arceus_datasets_key"),
        Index("ix_arceus_datasets_domain", "tenant_id", "domain", "layer"),
    )


class ArceusMetricDefinition(KernelTenantMixin, Base):
    __tablename__ = "arceus_metric_definitions"

    metric_key = Column(String(200), nullable=False)
    version = Column(String(40), nullable=False)
    name = Column(Text, nullable=False)
    domain = Column(String(120), nullable=False)
    expression = Column(Text, nullable=False)
    unit = Column(String(60), default="count", nullable=False)
    dimensions = Column(JSON, default=list, nullable=False)
    source_dataset_keys = Column(JSON, default=list, nullable=False)
    certification_status = Column(String(40), default="draft", nullable=False)
    owner = Column(String(160), nullable=False)
    documentation = Column(Text)

    __table_args__ = (
        CheckConstraint("certification_status IN ('draft', 'review', 'certified', 'deprecated')", name="ck_arceus_metric_definitions_certification"),
        UniqueConstraint("tenant_id", "metric_key", "version", name="uq_arceus_metric_definitions_key_version"),
        Index("ix_arceus_metric_definitions_domain", "tenant_id", "domain", "certification_status"),
    )


class ArceusMetricSnapshot(KernelTenantMixin, Base):
    __tablename__ = "arceus_metric_snapshots"

    metric_key = Column(String(200), nullable=False)
    metric_version = Column(String(40), nullable=False)
    value = Column(Numeric(18, 6), nullable=False)
    dimensions = Column(JSON, default=dict, nullable=False)
    window_start = Column(DateTime(timezone=True), nullable=False)
    window_end = Column(DateTime(timezone=True), nullable=False)
    freshness_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    lineage = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_arceus_metric_snapshots_key_window", "tenant_id", "metric_key", "window_end"),
    )


class ArceusDataQualityRule(KernelTenantMixin, Base):
    __tablename__ = "arceus_data_quality_rules"

    dataset_key = Column(String(200), nullable=False)
    rule_key = Column(String(200), nullable=False)
    rule_type = Column(String(80), nullable=False)
    severity = Column(String(40), default="warning", nullable=False)
    expectation = Column(JSON, default=dict, nullable=False)
    status = Column(String(40), default="active", nullable=False)

    __table_args__ = (
        CheckConstraint("rule_type IN ('completeness', 'accuracy', 'validity', 'uniqueness', 'consistency', 'freshness', 'referential_integrity')", name="ck_arceus_data_quality_rules_type"),
        CheckConstraint("severity IN ('info', 'warning', 'critical')", name="ck_arceus_data_quality_rules_severity"),
        CheckConstraint("status IN ('active', 'disabled')", name="ck_arceus_data_quality_rules_status"),
        UniqueConstraint("tenant_id", "dataset_key", "rule_key", name="uq_arceus_data_quality_rules_key"),
    )


class ArceusDataQualityRun(KernelTenantMixin, Base):
    __tablename__ = "arceus_data_quality_runs"

    dataset_key = Column(String(200), nullable=False)
    rule_key = Column(String(200), nullable=False)
    status = Column(String(40), nullable=False)
    observed_value = Column(JSON, default=dict, nullable=False)
    expected_value = Column(JSON, default=dict, nullable=False)
    row_count = Column(Integer, default=0, nullable=False)
    failed_count = Column(Integer, default=0, nullable=False)
    run_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('passed', 'warning', 'failed')", name="ck_arceus_data_quality_runs_status"),
        Index("ix_arceus_data_quality_runs_dataset", "tenant_id", "dataset_key", "run_at"),
    )


class ArceusDataLineageEdge(KernelTenantMixin, Base):
    __tablename__ = "arceus_data_lineage_edges"

    source_type = Column(String(80), nullable=False)
    source_key = Column(String(240), nullable=False)
    target_type = Column(String(80), nullable=False)
    target_key = Column(String(240), nullable=False)
    transform_key = Column(String(200))
    relationship = Column(String(80), default="derived_from", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "source_type", "source_key", "target_type", "target_key", "relationship", name="uq_arceus_data_lineage_edge"),
        Index("ix_arceus_data_lineage_target", "tenant_id", "target_type", "target_key"),
    )


class ArceusAnalyticsExperiment(KernelTenantMixin, Base):
    __tablename__ = "arceus_analytics_experiments"

    experiment_key = Column(String(200), nullable=False)
    name = Column(Text, nullable=False)
    hypothesis = Column(Text, nullable=False)
    owner = Column(String(160), nullable=False)
    variants = Column(JSON, default=list, nullable=False)
    primary_metric_key = Column(String(200), nullable=False)
    guardrail_metric_keys = Column(JSON, default=list, nullable=False)
    allocation = Column(JSON, default=dict, nullable=False)
    status = Column(String(40), default="draft", nullable=False)
    started_at = Column(DateTime(timezone=True))
    ended_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'running', 'paused', 'completed', 'cancelled')", name="ck_arceus_analytics_experiments_status"),
        UniqueConstraint("tenant_id", "experiment_key", name="uq_arceus_analytics_experiments_key"),
    )


class ArceusIdempotencyRecord(Base):
    __tablename__ = "arceus_idempotency_records"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    scope = Column(String(160), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    request_hash = Column(String(128), nullable=False)
    response_payload = Column(JSON, default=dict, nullable=False)
    status = Column(String(60), default="completed", nullable=False)
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "scope", "idempotency_key", name="uq_arceus_idempotency_records_key"),
        Index("ix_arceus_idempotency_records_expiry", "expires_at"),
    )


class ArceusAuditEvent(Base):
    __tablename__ = "arceus_audit_events"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    actor_type = Column(String(80), nullable=False)
    actor_id = Column(String(160))
    action = Column(String(160), nullable=False)
    resource_type = Column(String(120), nullable=False)
    resource_id = Column(String(160))
    result = Column(String(60), nullable=False)
    ip_address = Column(String(80))
    user_agent = Column(Text)
    metadata_json = Column(JSON, default=dict, nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_arceus_audit_events_resource", "tenant_id", "resource_type", "resource_id", "occurred_at"),
        Index("ix_arceus_audit_events_actor", "tenant_id", "actor_type", "actor_id", "occurred_at"),
    )


class ArceusUsageRecord(Base):
    __tablename__ = "arceus_usage_records"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    usage_type = Column(String(120), nullable=False)
    quantity = Column(Numeric(14, 4), nullable=False)
    unit = Column(String(80), nullable=False)
    cost_usd = Column(Numeric(12, 6), default=0, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_arceus_usage_records_tenant_time", "tenant_id", "occurred_at"),
        Index("ix_arceus_usage_records_mission", "tenant_id", "mission_id", "occurred_at"),
    )
