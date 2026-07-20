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
