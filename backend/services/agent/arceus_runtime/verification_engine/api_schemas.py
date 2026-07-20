from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


GateCategory = Literal["build", "test", "security", "performance", "accessibility", "architecture", "review", "release"]
GateStatus = Literal["passed", "failed", "warning", "blocked", "not_applicable"]
FindingSeverity = Literal["info", "low", "medium", "moderate", "high", "critical"]
ReviewVerdict = Literal["approved", "approved_with_warnings", "changes_requested", "blocked"]
VerificationSubjectType = Literal[
    "source_change",
    "configuration",
    "migration",
    "api_contract",
    "ui_change",
    "deployment",
    "artifact",
    "plan",
    "release",
]
RiskLevel = Literal["low", "moderate", "high", "critical"]
VerificationCategory = Literal[
    "schema",
    "syntax",
    "compile",
    "type_check",
    "lint",
    "unit_test",
    "integration_test",
    "end_to_end_test",
    "security",
    "dependency",
    "secret_scan",
    "architecture",
    "compatibility",
    "performance",
    "accessibility",
    "visual",
    "deployment",
    "ai_review",
    "policy",
]
VerificationStatus = Literal[
    "requested",
    "planning",
    "queued",
    "running",
    "waiting_resource",
    "waiting_approval",
    "repairing",
    "rechecking",
    "evaluating",
    "passed",
    "passed_with_warnings",
    "failed",
    "waived",
    "manual_review_required",
    "cancelled",
]
EvidenceProducerKey = Literal[
    "lint",
    "build",
    "test",
    "security",
    "playwright",
    "github_checks",
    "contract",
    "review",
]
WorkerJobStatus = Literal["queued", "leased", "running", "succeeded", "failed", "cancelled", "blocked"]
ReleaseSubjectType = Literal["pull_request", "deployment", "release", "merge"]


class VerificationEngineSchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class EvidenceInput(VerificationEngineSchema):
    evidence_id: str = Field(default_factory=lambda: f"evidence_{uuid4().hex[:12]}", min_length=1, max_length=160)
    evidence_type: str = Field(min_length=1, max_length=160)
    status: str = Field(default="validated", max_length=80)
    trust_level: str = Field(default="tool_verified", max_length=80)
    summary: str = Field(default="", max_length=5000)
    payload: dict[str, Any] = Field(default_factory=dict)
    verification_method: str = Field(default="tool", max_length=160)


class EvidenceProducerRequest(VerificationEngineSchema):
    mission_id: UUID = Field(default_factory=uuid4)
    task_id: UUID | None = None
    worker_job_id: UUID | None = None
    producer_key: EvidenceProducerKey
    check_id: str | None = Field(default=None, max_length=180)
    status: Literal["succeeded", "failed", "cancelled"] = "succeeded"
    command: str | None = Field(default=None, max_length=2000)
    exit_code: int | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    output: str = Field(default="", max_length=20000)
    artifacts: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    payload: dict[str, Any] = Field(default_factory=dict)


class EvidenceProducerResponse(VerificationEngineSchema):
    producer_run_id: str
    mission_id: UUID
    producer_key: EvidenceProducerKey
    normalized_status: Literal["validated", "failed", "cancelled"]
    evidence: EvidenceInput
    retryable: bool
    blocks_release: bool
    summary: str


class VerificationCheckDefinition(VerificationEngineSchema):
    check_id: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=500)
    version: str = Field(default="1.0", max_length=40)
    category: VerificationCategory
    supported_subject_types: list[VerificationSubjectType] = Field(default_factory=list)
    supported_languages: list[str] = Field(default_factory=list)
    supported_frameworks: list[str] = Field(default_factory=list)
    deterministic: bool = True
    required_capabilities: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    default_timeout_seconds: int = Field(default=300, ge=1, le=86_400)
    produces_evidence_types: list[str] = Field(default_factory=list)
    enabled: bool = True


class PlannedVerificationCheck(VerificationEngineSchema):
    check_id: str
    check_definition_id: str
    name: str
    category: VerificationCategory
    mandatory: bool
    blocking: bool
    inputs: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int
    depends_on: list[str] = Field(default_factory=list)
    success_threshold: float | None = Field(default=None, ge=0, le=100)
    failure_severity: FindingSeverity = "medium"


class VerificationWorkerJobResponse(VerificationEngineSchema):
    job_id: str
    mission_id: UUID
    task_id: UUID | None = None
    plan_id: str
    check_id: str
    check_definition_id: str
    category: VerificationCategory
    evidence_producer: str
    mandatory: bool
    blocking: bool
    status: WorkerJobStatus
    inputs: dict[str, Any]
    depends_on: list[str]
    timeout_seconds: int
    attempts: int
    evidence_id: str | None = None
    durable_task_id: str | None = None


class VerificationPlanRequest(VerificationEngineSchema):
    mission_id: UUID = Field(default_factory=uuid4)
    node_id: str | None = Field(default=None, max_length=160)
    subject_type: VerificationSubjectType = "source_change"
    subject_reference: str = Field(default="", max_length=2000)
    repository_id: str | None = Field(default=None, max_length=160)
    base_revision: str | None = Field(default=None, max_length=160)
    target_revision: str | None = Field(default=None, max_length=160)
    risk_level: RiskLevel = "moderate"
    required_gate_profile: str | None = Field(default=None, max_length=160)
    requested_checks: list[str] = Field(default_factory=list, max_length=100)
    changed_files: list[str] = Field(default_factory=list, max_length=1000)
    repository_files: list[str] = Field(default_factory=list, max_length=5000)
    package_scripts: dict[str, str] = Field(default_factory=dict)
    allow_repair: bool = True
    maximum_repair_attempts: int = Field(default=1, ge=0, le=10)


class VerificationExecutionGroup(VerificationEngineSchema):
    group_key: str
    check_ids: list[str]
    run_after: list[str] = Field(default_factory=list)
    parallel: bool = True


class VerificationPlanResponse(VerificationEngineSchema):
    plan_id: str
    mission_id: UUID
    status: VerificationStatus
    profile_id: str
    risk_level: RiskLevel
    checks: list[PlannedVerificationCheck]
    execution_groups: list[VerificationExecutionGroup]
    mandatory_check_ids: list[str]
    advisory_check_ids: list[str]
    estimated_duration_seconds: int
    estimated_cost_usd: float
    repair_policy: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


class OutputContractValidationRequest(VerificationEngineSchema):
    output: dict[str, Any]
    required_fields: list[str] = Field(default_factory=list)
    allowed_fields: list[str] = Field(default_factory=list)
    field_types: dict[str, str] = Field(default_factory=dict)


class ContractValidationError(VerificationEngineSchema):
    field: str
    message: str


class OutputContractValidationResponse(VerificationEngineSchema):
    schema_valid: bool
    required_fields_present: bool
    unsupported_fields: list[str]
    validation_errors: list[ContractValidationError]


class DiscoveredTestCommand(VerificationEngineSchema):
    command_id: str
    command: str
    working_directory: str = "."
    test_type: Literal["unit", "integration", "e2e", "contract", "smoke"]
    source: Literal["package_manifest", "ci_config", "repository_memory", "convention", "user"]
    confidence: float = Field(ge=0, le=1)


class VerificationTestDiscoveryRequest(VerificationEngineSchema):
    repository_files: list[str] = Field(default_factory=list, max_length=10000)
    package_scripts: dict[str, str] = Field(default_factory=dict)
    changed_files: list[str] = Field(default_factory=list, max_length=1000)
    language: str | None = Field(default=None, max_length=80)
    framework: str | None = Field(default=None, max_length=120)


class TestDiscoveryResponse(VerificationEngineSchema):
    framework: str | None = None
    commands: list[DiscoveredTestCommand]
    unit_test_locations: list[str]
    integration_test_locations: list[str]
    end_to_end_test_locations: list[str]
    coverage_available: bool
    confidence: float
    warnings: list[str]


class QualityGateDefinition(VerificationEngineSchema):
    gate_key: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=1, max_length=500)
    category: GateCategory
    required: bool = True
    evidence_type: str | None = Field(default=None, max_length=160)
    command_key: str | None = Field(default=None, max_length=160)
    minimum_score: float | None = Field(default=None, ge=0, le=100)
    maximum_findings: dict[FindingSeverity, int] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)


class ReviewFinding(VerificationEngineSchema):
    finding_key: str
    severity: FindingSeverity
    title: str
    detail: str
    evidence_ids: list[str] = Field(default_factory=list)
    recommendation: str
    blocks_release: bool = False


class QualityGateResult(VerificationEngineSchema):
    gate_key: str
    name: str
    category: GateCategory
    required: bool
    status: GateStatus
    score: float
    evidence_ids: list[str] = Field(default_factory=list)
    findings: list[ReviewFinding] = Field(default_factory=list)
    reason: str


class VerificationRunRequest(VerificationEngineSchema):
    mission_id: UUID = Field(default_factory=uuid4)
    task_id: UUID | None = None
    target_type: str = Field(default="mission", max_length=120)
    target_id: UUID | None = None
    changed_files: list[str] = Field(default_factory=list, max_length=1000)
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=1000)
    gates: list[QualityGateDefinition] = Field(default_factory=list, max_length=100)
    require_independent_review: bool = True
    release_candidate: bool = False


class VerificationRunResponse(VerificationEngineSchema):
    run_id: str
    mission_id: UUID
    target_type: str
    target_id: UUID
    status: GateStatus
    overall_score: float
    verdict: ReviewVerdict
    gate_results: list[QualityGateResult]
    findings: list[ReviewFinding]
    evidence_score: float
    release_blockers: list[ReviewFinding]
    recommended_actions: list[str]
    repair_loop_required: bool
    events: list[str]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReviewRequest(VerificationEngineSchema):
    mission_id: UUID = Field(default_factory=uuid4)
    target_type: str = Field(default="patch", max_length=120)
    target_id: UUID = Field(default_factory=uuid4)
    changed_files: list[str] = Field(default_factory=list, max_length=1000)
    diff_summary: str = Field(default="", max_length=20000)
    evidence: list[EvidenceInput] = Field(default_factory=list, max_length=1000)
    reviewer_role: str = Field(default="qa_reviewer", max_length=160)


class ReviewResponse(VerificationEngineSchema):
    review_id: str
    mission_id: UUID
    target_type: str
    target_id: UUID
    reviewer_role: str
    verdict: ReviewVerdict
    score: float
    findings: list[ReviewFinding]
    evidence_ids: list[str]
    independent_review_required: bool
    completed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ReleaseReadinessRequest(VerificationEngineSchema):
    mission_id: UUID = Field(default_factory=uuid4)
    gate_results: list[QualityGateResult] = Field(default_factory=list, max_length=200)
    reviews: list[ReviewResponse] = Field(default_factory=list, max_length=100)
    approvals: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    require_human_approval: bool = True
    subject_type: ReleaseSubjectType = "release"
    subject_id: str = Field(default="latest", min_length=1, max_length=180)


class ReleaseReadinessResponse(VerificationEngineSchema):
    ready: bool
    status: Literal["ready", "blocked", "review_required"]
    score: float
    blockers: list[str]
    warnings: list[str]
    required_actions: list[str]
    evidence_summary: dict[str, Any]


class MissionControlReleaseGateRequest(VerificationEngineSchema):
    mission_id: UUID = Field(default_factory=uuid4)
    subject_type: ReleaseSubjectType = "pull_request"
    subject_id: str = Field(default="latest", min_length=1, max_length=180)
    require_fresh_readiness: bool = True


class MissionControlReleaseGateResponse(VerificationEngineSchema):
    allowed: bool
    subject_type: ReleaseSubjectType
    subject_id: str
    readiness_status: Literal["ready", "blocked", "review_required", "missing"]
    score: float
    blockers: list[str]
    warnings: list[str]
    required_actions: list[str]
    checked_at: datetime | None = None
