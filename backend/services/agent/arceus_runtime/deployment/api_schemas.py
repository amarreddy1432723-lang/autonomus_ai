from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


ProviderType = Literal["aws", "azure", "gcp", "railway", "render", "vercel", "kubernetes", "docker", "on_premises", "custom"]
ApplicationType = Literal["web", "api", "worker", "desktop", "mobile_backend", "scheduled_job", "service", "monorepo"]
EnvironmentType = Literal["development", "preview", "testing", "staging", "production", "disaster_recovery"]
DeploymentStrategy = Literal["recreate", "rolling", "blue_green", "canary", "shadow", "immutable", "in_place"]


class DeploymentSchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class DeploymentTargetRequest(DeploymentSchema):
    organization_id: UUID | None = None
    name: str = Field(min_length=1, max_length=240)
    provider_type: ProviderType
    credential_binding_id: str = Field(min_length=3, max_length=255)
    regions: list[str] = Field(default_factory=list)
    capabilities: dict[str, bool] = Field(default_factory=dict)
    policy_profile_id: str | None = None


class DeploymentTargetResponse(DeploymentSchema):
    id: UUID
    name: str
    provider_type: str
    credential_binding_id: str
    regions: list[str]
    capabilities: dict[str, Any]
    status: str


class RuntimeProfileRequest(DeploymentSchema):
    name: str = Field(min_length=1, max_length=240)
    runtime_type: Literal["container", "serverless", "static", "virtual_machine", "kubernetes", "edge", "desktop_distribution"]
    startup_command: str | None = None
    port: int | None = Field(default=None, ge=1, le=65535)
    health_check: dict[str, Any] = Field(default_factory=dict)
    resources: dict[str, Any] = Field(default_factory=dict)
    scaling: dict[str, Any] = Field(default_factory=dict)
    shutdown_grace_period_seconds: int = Field(default=30, ge=0, le=600)


class DeploymentApplicationRequest(DeploymentSchema):
    organization_id: UUID | None = None
    project_id: UUID
    name: str = Field(min_length=1, max_length=240)
    source_repository_id: UUID | None = None
    application_type: ApplicationType
    runtime_profile_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeploymentApplicationResponse(DeploymentSchema):
    id: UUID
    project_id: UUID
    name: str
    slug: str
    application_type: str
    runtime_profile_id: UUID | None
    status: str
    created_at: datetime


class DeploymentEnvironmentRequest(DeploymentSchema):
    organization_id: UUID | None = None
    application_id: UUID
    target_id: UUID
    name: str = Field(min_length=1, max_length=160)
    environment_type: EnvironmentType
    region: str = "us-east-1"
    protection_level: Literal["none", "standard", "protected", "critical"] = "standard"
    ttl_expires_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeploymentEnvironmentResponse(DeploymentSchema):
    id: UUID
    application_id: UUID
    target_id: UUID
    name: str
    environment_type: str
    region: str
    status: str
    protection_level: str
    current_release_id: UUID | None


class DeploymentReleaseRequest(DeploymentSchema):
    application_id: UUID
    version: str = Field(min_length=1, max_length=120)
    source_commit_sha: str = Field(min_length=7, max_length=80)
    source_branch: str | None = None
    source_tag: str | None = None
    build_id: str = Field(min_length=1, max_length=255)
    configuration_version_id: UUID | None = None
    verification_report_id: UUID | None = None
    created_by: UUID
    provenance: dict[str, Any] = Field(default_factory=dict)


class DeploymentArtifactRequest(DeploymentSchema):
    release_id: UUID
    artifact_type: Literal["container_image", "server_bundle", "static_assets", "desktop_installer", "mobile_bundle", "function_package", "infrastructure_plan"]
    digest: str = Field(min_length=8, max_length=160)
    uri: str = Field(min_length=1)
    size_bytes: int = Field(default=0, ge=0)
    architecture: str | None = None
    operating_system: str | None = None
    signed: bool = False
    signature_reference: str | None = None
    sbom_reference: str | None = None
    scan_status: Literal["pending", "passed", "warning", "failed", "waived"] = "pending"
    metadata: dict[str, Any] = Field(default_factory=dict)


class DeploymentReleaseResponse(DeploymentSchema):
    id: UUID
    application_id: UUID
    version: str
    source_commit_sha: str
    build_id: str
    artifact_ids: list[Any]
    status: str
    provenance: dict[str, Any]


class DeploymentRequestCreate(DeploymentSchema):
    release_id: UUID
    environment_id: UUID
    strategy: DeploymentStrategy = "rolling"
    requested_by: UUID
    reason: str | None = None
    dry_run: bool = False
    approval_policy_id: str | None = None
    verification_policy_id: str = "default_release_gate"
    scheduled_for: datetime | None = None


class DeploymentRequestResponse(DeploymentSchema):
    id: UUID
    release_id: UUID
    environment_id: UUID
    strategy: str
    status: str
    dry_run: bool
    requested_by: UUID
    reason: str | None
    created_at: datetime


class DeploymentPlanResponse(DeploymentSchema):
    id: UUID | None = None
    request_id: UUID
    release_id: UUID
    environment_id: UUID
    strategy: str
    infrastructure_changes: list[dict[str, Any]]
    configuration_changes: list[dict[str, Any]]
    secret_binding_changes: list[dict[str, Any]]
    migration_plan: dict[str, Any]
    traffic_plan: dict[str, Any]
    health_verification_plan: dict[str, Any]
    rollback_plan: dict[str, Any]
    estimated_duration_seconds: int
    estimated_cost_cents: Decimal
    risk_score: int
    warnings: list[str]
    blockers: list[str]
    deployable: bool
    plan_hash: str


class HealthCheckRequest(DeploymentSchema):
    environment_id: UUID
    deployment_request_id: UUID | None = None
    check_type: Literal["http", "tcp", "synthetic", "metric", "log"] = "http"
    target: str = Field(min_length=1)
    status: Literal["pending", "passed", "warning", "failed"] = "pending"
    latency_ms: int | None = Field(default=None, ge=0)
    output: dict[str, Any] = Field(default_factory=dict)


class RollbackRequest(DeploymentSchema):
    deployment_request_id: UUID
    environment_id: UUID
    from_release_id: UUID
    to_release_id: UUID | None = None
    reason: str = Field(min_length=1, max_length=2000)
    rollback_steps: list[dict[str, Any]] = Field(default_factory=list)


class DriftReportRequest(DeploymentSchema):
    environment_id: UUID
    drift_type: Literal["infrastructure", "configuration", "secret_binding", "network", "runtime", "security"]
    desired_hash: str = Field(min_length=8, max_length=128)
    actual_hash: str = Field(min_length=8, max_length=128)
    severity: Literal["low", "medium", "high", "critical"] = "medium"
    findings: list[dict[str, Any]] = Field(default_factory=list)


class DeploymentHealthSummaryResponse(DeploymentSchema):
    environment_id: UUID
    status: str
    last_release_id: UUID | None
    failed_checks: int
    warning_checks: int
    open_drift_reports: int
    rollback_available: bool
    blockers: list[str]

    @field_validator("status")
    @classmethod
    def valid_status(cls, value: str) -> str:
        return value

