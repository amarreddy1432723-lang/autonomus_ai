from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


ExtensionType = Literal[
    "tool",
    "model_provider",
    "agent_profile",
    "workflow_template",
    "repository_connector",
    "deployment_provider",
    "data_connector",
    "verification_check",
    "policy_provider",
    "ui_extension",
    "notification_provider",
    "authentication_provider",
    "billing_integration",
    "telemetry_exporter",
]

InstallationStatus = Literal[
    "pending_review",
    "installing",
    "installed",
    "configuration_required",
    "enabled",
    "disabled",
    "update_available",
    "updating",
    "suspended",
    "revoked",
    "removing",
    "removed",
    "failed",
]


class ExtensionPermission(BaseModel):
    permission: str
    risk_level: Literal["low", "moderate", "high", "critical"] = "low"
    scope: dict[str, Any] = Field(default_factory=dict)
    conditions: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None


class ManifestValidationRequest(BaseModel):
    manifest: dict[str, Any]
    package_digest: str | None = None


class ManifestValidationResponse(BaseModel):
    valid: bool
    plugin_key: str | None = None
    name: str | None = None
    version: str | None = None
    publisher_key: str | None = None
    extension_types: list[str] = Field(default_factory=list)
    permissions: list[ExtensionPermission] = Field(default_factory=list)
    signed: bool = False
    verified: bool = False
    security_score: float = 0.0
    review_required: bool = False
    manifest_digest: str | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    normalized_manifest: dict[str, Any] = Field(default_factory=dict)


class MarketplaceListingResponse(BaseModel):
    plugin_key: str
    name: str
    publisher: str
    category: str
    version: str
    description: str
    extension_types: list[str]
    permissions: list[str]
    verification_level: str
    install_state: str = "available"


class PluginInstallRequest(BaseModel):
    manifest: dict[str, Any]
    scope_type: Literal["organization", "workspace", "repository", "user"] = "organization"
    scope_id: str | None = None
    granted_permissions: list[ExtensionPermission] | None = None
    update_policy: Literal["manual", "security_only", "compatible_minor", "automatic"] = "manual"
    configuration: dict[str, Any] = Field(default_factory=dict)
    secret_references: list[str] = Field(default_factory=list)


class PluginInstallationResponse(BaseModel):
    installation_id: UUID
    plugin_id: UUID
    plugin_version_id: UUID
    plugin_key: str
    name: str
    version: str
    scope_type: str
    scope_id: str
    status: InstallationStatus
    extension_identity_id: str
    granted_permissions: list[ExtensionPermission]
    review_required: bool
    signed: bool
    security_score: float


class PluginUpdateRequest(BaseModel):
    manifest: dict[str, Any]
    granted_permissions: list[ExtensionPermission] | None = None
    allow_new_permissions: bool = False


class PluginLifecycleResponse(BaseModel):
    installation_id: UUID
    status: InstallationStatus
    message: str
    permission_diff: dict[str, list[str]] = Field(default_factory=dict)
    health: dict[str, Any] = Field(default_factory=dict)


class PermissionEvaluationRequest(BaseModel):
    installation_id: UUID
    permission: str
    resource_type: str = "extension"
    resource_id: str = "*"
    risk_level: Literal["low", "moderate", "high", "critical"] = "low"
    scope: dict[str, Any] = Field(default_factory=dict)
    mission_id: UUID | None = None


class PermissionEvaluationResponse(BaseModel):
    allowed: bool
    decision: Literal["allow", "deny", "needs_review"]
    reason: str
    matched_permissions: list[str] = Field(default_factory=list)
    obligations: list[str] = Field(default_factory=list)


class PluginInvocationRequest(BaseModel):
    installation_id: UUID
    capability_id: str
    permission: str
    mission_id: UUID | None = None
    workflow_node_id: UUID | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    risk_level: Literal["low", "moderate", "high", "critical"] = "low"
    dry_run: bool = True


class PluginInvocationResponse(BaseModel):
    invocation_id: UUID
    status: Literal["authorized", "succeeded", "denied"]
    allowed: bool
    receipt: dict[str, Any]
    audit_recorded: bool


class PluginSecretUseRequest(BaseModel):
    installation_id: UUID
    secret_ref: str = Field(min_length=1, max_length=255)
    purpose: str = Field(min_length=1, max_length=500)
    target_domain: str | None = Field(default=None, max_length=255)
    mission_id: UUID | None = None


class PluginSecretUseResponse(BaseModel):
    allowed: bool
    broker_receipt_id: str
    secret_ref: str
    secret_fingerprint: str | None = None
    expires_in_seconds: int
    direct_value_returned: bool = False
    reason: str
    obligations: list[str] = Field(default_factory=list)


class PluginRuntimePolicyResponse(BaseModel):
    installation_id: UUID
    runtime_type: str
    minimum_isolation: str
    allow_network: bool
    allowed_domains: list[str]
    filesystem_mode: str
    maximum_cpu_millis: int
    maximum_memory_mb: int
    maximum_execution_seconds: int
    allow_subprocesses: bool


class SdkManifestResponse(BaseModel):
    api_version: str
    manifest_schema_version: str
    supported_extension_types: list[str]
    supported_permissions: list[str]
    runtimes: list[str]
    lifecycle_hooks: list[str]
    security: dict[str, Any]
