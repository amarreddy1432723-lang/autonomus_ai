from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


IdentityType = Literal[
    "human",
    "enterprise_user",
    "guest",
    "agent",
    "automation_worker",
    "service_account",
    "api_client",
    "desktop_app",
    "web_app",
    "mobile_app",
]
IdentityStatus = Literal["active", "disabled", "pending", "deleted"]
ResourceType = Literal[
    "organization",
    "workspace",
    "project",
    "repository",
    "mission",
    "artifact",
    "secret",
    "deployment",
    "model",
    "environment",
    "agent",
    "workflow",
    "budget",
    "policy",
]
DecisionStatus = Literal["allow", "deny", "needs_approval", "requires_mfa", "requires_reauth"]
RiskLevel = Literal["low", "medium", "high", "critical"]


class IdentitySchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class IdentityPrincipal(IdentitySchema):
    identity_id: str = Field(min_length=1, max_length=160)
    identity_type: IdentityType
    display_name: str = Field(default="", max_length=300)
    email: str | None = Field(default=None, max_length=320)
    organization_id: str | None = Field(default=None, max_length=160)
    workspace_ids: list[str] = Field(default_factory=list, max_length=100)
    role_keys: list[str] = Field(default_factory=list, max_length=100)
    permissions: list[str] = Field(default_factory=list, max_length=500)
    status: IdentityStatus = "active"
    mfa_verified: bool = False
    reauthenticated: bool = False
    device_trusted: bool = False
    attributes: dict[str, Any] = Field(default_factory=dict)


class RoleDefinition(IdentitySchema):
    role_key: str
    name: str
    permissions: list[str]
    human_only_approvals: bool = False
    description: str


class PolicyDefinition(IdentitySchema):
    policy_key: str
    name: str
    description: str
    severity: Literal["low", "medium", "high", "critical"]
    resource_types: list[ResourceType | str]
    actions: list[str]
    obligations: list[str]


class AuthorizationResource(IdentitySchema):
    resource_type: ResourceType
    resource_id: str = Field(default="", max_length=300)
    organization_id: str | None = Field(default=None, max_length=160)
    workspace_id: str | None = Field(default=None, max_length=160)
    owner_id: str | None = Field(default=None, max_length=160)
    environment: str = Field(default="development", max_length=80)
    risk_level: RiskLevel = "medium"
    data_classification: str = Field(default="internal", max_length=80)
    attributes: dict[str, Any] = Field(default_factory=dict)


class AuthorizationDecisionRequest(IdentitySchema):
    principal: IdentityPrincipal
    action: str = Field(min_length=1, max_length=160)
    resource: AuthorizationResource
    required_human_approval: bool = False
    existing_approver_ids: list[str] = Field(default_factory=list, max_length=100)
    required_permissions: list[str] = Field(default_factory=list, max_length=100)
    reason: str = Field(default="", max_length=2000)


class AuthorizationDecisionResponse(IdentitySchema):
    decision_id: str
    allowed: bool
    decision: DecisionStatus
    reason: str
    matched_policies: list[str]
    obligations: list[str]
    effective_permissions: list[str]
    expires_at: datetime | None = None
    audit_event: dict[str, Any]


class UserSessionRiskRequest(IdentitySchema):
    session_id: str = Field(default_factory=lambda: f"sess_{uuid4().hex[:12]}", max_length=160)
    user_id: str = Field(min_length=1, max_length=160)
    ip_address: str | None = Field(default=None, max_length=80)
    user_agent: str | None = Field(default=None, max_length=1000)
    device_trusted: bool = False
    mfa_verified: bool = False
    last_seen_minutes_ago: int = Field(default=0, ge=0, le=100_000)
    failed_login_attempts: int = Field(default=0, ge=0, le=1000)
    impossible_travel: bool = False


class UserSessionRiskResponse(IdentitySchema):
    session_id: str
    risk_score: int = Field(ge=0, le=100)
    status: Literal["active", "idle", "high_risk", "expired", "revoked"]
    required_actions: list[str]
    expires_at: datetime


class ApiTokenIssueRequest(IdentitySchema):
    name: str = Field(min_length=1, max_length=160)
    owner_id: str = Field(min_length=1, max_length=160)
    scopes: list[str] = Field(default_factory=list, min_length=1, max_length=100)
    environment: str = Field(default="development", max_length=80)
    expires_in_days: int = Field(default=30, ge=1, le=365)


class ApiTokenIssueResponse(IdentitySchema):
    token_id: str
    name: str
    prefix: str
    checksum: str
    scopes: list[str]
    environment: str
    expires_at: datetime
    one_time_token_preview: str
    audit_event: dict[str, Any]


class ServiceAccountRequest(IdentitySchema):
    name: str = Field(min_length=1, max_length=160)
    organization_id: str = Field(min_length=1, max_length=160)
    purpose: str = Field(default="", max_length=1000)
    scopes: list[str] = Field(default_factory=list, max_length=100)
    allowed_environments: list[str] = Field(default_factory=lambda: ["development"], max_length=20)


class ServiceAccountResponse(IdentitySchema):
    service_account_id: str
    principal: IdentityPrincipal
    token_policy: dict[str, Any]
    audit_event: dict[str, Any]


class AgentIdentityRequest(IdentitySchema):
    profile_id: str = Field(min_length=1, max_length=160)
    organization_id: str = Field(min_length=1, max_length=160)
    mission_id: str | None = Field(default=None, max_length=160)
    capabilities: list[str] = Field(default_factory=list, max_length=100)
    allowed_tools: list[str] = Field(default_factory=list, max_length=100)
    maximum_risk_level: RiskLevel = "medium"


class AgentIdentityResponse(IdentitySchema):
    agent_identity_id: str
    principal: IdentityPrincipal
    runtime_claims: dict[str, Any]
    restrictions: list[str]
    audit_event: dict[str, Any]


class GovernanceSummaryResponse(IdentitySchema):
    default_deny: bool
    supported_identity_types: list[str]
    built_in_roles: list[RoleDefinition]
    policies: list[PolicyDefinition]
    sensitive_actions: list[str]
    audit_required_for: list[str]
    mvp_readiness: dict[str, bool]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class IdentityProviderSyncRequest(IdentitySchema):
    provider_key: str = Field(default="clerk", max_length=120)
    provider_type: Literal["clerk", "oidc", "saml", "oauth", "api_token"] = "clerk"
    issuer: str | None = Field(default=None, max_length=2000)
    capabilities: list[str] = Field(default_factory=list, max_length=100)
    scim_enabled: bool = False
    enterprise_sso_enabled: bool = False
    device_trust_enabled: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class IdentityProviderSyncResponse(IdentitySchema):
    provider_id: UUID
    provider_key: str
    provider_type: str
    status: str
    capabilities: list[str]
    scim_enabled: bool
    enterprise_sso_enabled: bool
    device_trust_enabled: bool
    audit_recorded: bool
