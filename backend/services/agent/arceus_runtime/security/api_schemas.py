from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SecuritySchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class SecurityPolicyResponse(SecuritySchema):
    policy_key: str
    name: str
    description: str
    severity: str
    protected_actions: list[str]


class SecurityEvaluateRequest(SecuritySchema):
    mission_id: UUID | None = None
    task_id: UUID | None = None
    policy_key: str | None = None
    subject: dict[str, Any] = Field(default_factory=dict)
    action: str
    resource: dict[str, Any] = Field(default_factory=dict)
    environment: str = "development"
    risk_level: str = "medium"


class SecurityEvaluationResponse(SecuritySchema):
    id: UUID | None = None
    mission_id: UUID | None
    task_id: UUID | None
    policy_key: str
    subject: dict[str, Any]
    action: str
    resource: dict[str, Any]
    decision: str
    reason: str
    obligations: list[str]
    created_at: datetime | None = None


class SecurityIncidentRequest(SecuritySchema):
    mission_id: UUID | None = None
    task_id: UUID | None = None
    incident_type: str
    severity: str = "medium"
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    resource_type: str = "security_incident"
    resource_id: str | None = None


class SecurityIncidentResponse(SecuritySchema):
    incident_type: str
    severity: str
    result: str
    summary: str
    audit_recorded: bool


class ComplianceProfileResponse(SecuritySchema):
    profile_key: str
    name: str
    controls: list[str]
    retention_policy: dict[str, str]
    required_security_events: list[str]


SecurityAssetType = Literal[
    "repository",
    "source_file",
    "dependency",
    "container_image",
    "build_artifact",
    "application",
    "api",
    "service",
    "database",
    "cloud_resource",
    "kubernetes_cluster",
    "environment",
    "identity",
    "service_account",
    "agent",
    "plugin",
    "secret",
    "model_provider",
    "deployment",
    "data_store",
]
SecurityFindingCategory = Literal[
    "vulnerability",
    "misconfiguration",
    "secret_exposure",
    "malware",
    "identity_risk",
    "policy_violation",
    "runtime_threat",
    "supply_chain",
    "data_exposure",
    "agent_behavior",
    "compliance_gap",
]
SecuritySeverity = Literal["informational", "low", "medium", "high", "critical"]
SecurityRiskLevel = Literal["low", "moderate", "high", "critical", "emergency"]


class SecurityAssetRequest(SecuritySchema):
    organization_id: UUID | None = None
    workspace_id: UUID | None = None
    project_id: UUID | None = None
    asset_type: SecurityAssetType
    external_reference: str | None = None
    name: str = Field(min_length=1, max_length=500)
    description: str | None = None
    owner_identity_id: str | None = None
    owner_team_id: UUID | None = None
    criticality: Literal["low", "medium", "high", "critical"] = "medium"
    internet_exposed: bool = False
    environment_type: str | None = None
    data_classifications: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)


class SecurityAssetResponse(SecuritySchema):
    id: UUID
    asset_type: str
    name: str
    external_reference: str | None
    criticality: str
    internet_exposed: bool
    environment_type: str | None
    data_classifications: list[str]
    tags: list[str]
    last_seen_at: datetime | None = None


class SecurityFindingRequest(SecuritySchema):
    organization_id: UUID | None = None
    workspace_id: UUID | None = None
    project_id: UUID | None = None
    asset_id: UUID
    source: str = Field(min_length=1, max_length=160)
    source_finding_id: str | None = None
    category: SecurityFindingCategory
    title: str = Field(min_length=1, max_length=1000)
    description: str = ""
    severity: SecuritySeverity
    affected_component: str | None = None
    vulnerability_ids: list[str] = Field(default_factory=list)
    location: dict[str, Any] = Field(default_factory=dict)
    evidence_references: list[str] = Field(default_factory=list)
    enrichment: dict[str, Any] = Field(default_factory=dict)
    remediation: dict[str, Any] = Field(default_factory=dict)


class SecurityFindingResponse(SecuritySchema):
    id: UUID
    asset_id: UUID
    fingerprint: str
    source: str
    category: str
    title: str
    severity: str
    status: str
    affected_component: str | None
    vulnerability_ids: list[str]
    evidence_references: list[str]
    last_detected_at: datetime | None = None


class SecurityRiskScoreResponse(SecuritySchema):
    finding_id: UUID
    base_severity_score: int
    exploitability_score: int
    reachability_score: int
    exposure_score: int
    asset_criticality_score: int
    privilege_impact_score: int
    data_impact_score: int
    threat_activity_score: int
    compensating_control_reduction: int
    total_score: int
    risk_level: str
    explanation: dict[str, Any]


class SecurityGateRequest(SecuritySchema):
    gate_type: Literal["pull_request", "build", "release", "deployment", "runtime"]
    asset_ids: list[UUID] = Field(default_factory=list)
    environment_type: str = "development"
    require_signed_artifacts: bool = True
    allow_active_exceptions: bool = True


class SecurityGateResponse(SecuritySchema):
    gate_type: str
    decision: Literal["allow", "needs_approval", "block"]
    blockers: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    obligations: list[str]


class SecurityOpsIncidentRequest(SecuritySchema):
    organization_id: UUID | None = None
    case_id: UUID | None = None
    title: str = Field(min_length=1, max_length=1000)
    severity: SecurityRiskLevel
    incident_commander_id: UUID | None = None
    affected_asset_ids: list[UUID] = Field(default_factory=list)
    finding_ids: list[UUID] = Field(default_factory=list)
    regulatory_notification_required: bool = False


class SecurityOpsIncidentResponse(SecuritySchema):
    id: UUID
    title: str
    severity: str
    status: str
    affected_asset_ids: list[Any]
    finding_ids: list[Any]


class SecurityResponseActionRequest(SecuritySchema):
    incident_id: UUID | None = None
    finding_id: UUID | None = None
    action_type: Literal[
        "revoke_token",
        "rotate_secret",
        "isolate_agent",
        "pause_mission",
        "disable_plugin",
        "block_deployment",
        "rollback_release",
        "open_remediation_mission",
    ]
    target_id: str = Field(min_length=1, max_length=500)
    risk_level: SecurityRiskLevel
    requested_by: UUID | None = None
    trace_id: str = Field(min_length=1, max_length=160)
    idempotency_key: str = Field(min_length=8, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SecurityResponseActionResponse(SecuritySchema):
    id: UUID
    action_type: str
    target_id: str
    risk_level: str
    automatic_allowed: bool
    approval_status: str
    execution_status: str
    trace_id: str


class SecurityExceptionRequest(SecuritySchema):
    organization_id: UUID | None = None
    finding_id: UUID
    reason: str = Field(min_length=10, max_length=4000)
    compensating_controls: list[dict[str, Any]] = Field(default_factory=list)
    approved_by: UUID
    expires_at: datetime
    review_frequency_days: int = Field(default=30, ge=1, le=365)


class SecurityEvidenceRequest(SecuritySchema):
    organization_id: UUID | None = None
    incident_id: UUID | None = None
    finding_id: UUID | None = None
    evidence_type: Literal["scanner_report", "log_excerpt", "screenshot", "sbom", "attestation", "policy_decision", "manual_note"]
    storage_reference: str = Field(min_length=1, max_length=1000)
    content_digest: str = Field(min_length=8, max_length=160)
    collected_by: UUID
    retention_until: datetime | None = None
    legal_hold: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class SecurityDashboardResponse(SecuritySchema):
    open_findings: int
    critical_findings: int
    high_findings: int
    exposed_critical_assets: int
    active_incidents: int
    pending_response_actions: int
    active_exceptions: int
    release_gate_status: str
