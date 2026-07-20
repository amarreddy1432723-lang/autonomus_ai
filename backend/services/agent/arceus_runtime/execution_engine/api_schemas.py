from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


MissionRuntimeStatus = Literal[
    "draft",
    "planning",
    "awaiting_approval",
    "approved",
    "queued",
    "running",
    "paused",
    "blocked",
    "replanning",
    "recovering",
    "cancelling",
    "verifying",
    "completed",
    "partially_completed",
    "failed",
    "cancelled",
]
NodeRuntimeStatus = Literal[
    "pending",
    "waiting_dependency",
    "ready",
    "leased",
    "dispatched",
    "running",
    "waiting_approval",
    "waiting_external",
    "retry_scheduled",
    "compensating",
    "verifying",
    "succeeded",
    "failed",
    "skipped",
    "cancelled",
    "timed_out",
]
WorkflowNodeType = Literal[
    "agent_task",
    "tool_action",
    "model_inference",
    "approval_gate",
    "verification",
    "checkpoint",
    "condition",
    "fan_out",
    "fan_in",
    "delay",
    "subworkflow",
    "compensation",
    "mission_finalize",
]
EdgeType = Literal["success", "failure", "completion", "condition", "artifact", "approval", "compensation"]
DependencyFailureMode = Literal["fail", "skip", "fallback", "replan", "continue_degraded"]
SideEffectLevel = Literal["none", "reversible", "compensatable", "irreversible"]


class ExecutionEngineSchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class RetryPolicy(ExecutionEngineSchema):
    max_attempts: int = Field(default=3, ge=1, le=20)
    base_delay_seconds: int = Field(default=5, ge=0, le=86_400)
    backoff_multiplier: float = Field(default=2.0, ge=1.0, le=10.0)
    jitter: bool = True
    retryable_failure_classes: list[str] = Field(default_factory=lambda: ["transient", "provider", "timeout"])


class TimeoutPolicy(ExecutionEngineSchema):
    timeout_seconds: int = Field(default=900, ge=1, le=604_800)


class NodeExecutionPolicy(ExecutionEngineSchema):
    dependency_failure_mode: DependencyFailureMode = "fail"
    require_fresh_repository_state: bool = True
    allow_parallel_execution: bool = True
    idempotent: bool = True
    side_effect_level: SideEffectLevel = "none"


class ApprovalPolicy(ExecutionEngineSchema):
    required: bool = False
    approval_type: str = "human_review"
    human_approval_required: bool = True
    quorum: int = Field(default=1, ge=1, le=20)


class VerificationPolicy(ExecutionEngineSchema):
    required: bool = False
    methods: list[str] = Field(default_factory=list)
    block_on_failure: bool = True


class ResourceRequirement(ExecutionEngineSchema):
    resource_type: str = Field(min_length=1, max_length=120)
    resource_key: str = Field(min_length=1, max_length=500)
    lock_mode: Literal["shared", "exclusive"] = "exclusive"


class WorkflowNodeSpec(ExecutionEngineSchema):
    node_id: str = Field(default_factory=lambda: f"node_{uuid4().hex[:12]}", min_length=1, max_length=160)
    node_type: WorkflowNodeType
    name: str = Field(min_length=1, max_length=500)
    dependencies: list[str] = Field(default_factory=list, max_length=100)
    execution_policy: NodeExecutionPolicy = Field(default_factory=NodeExecutionPolicy)
    retry_policy: RetryPolicy = Field(default_factory=RetryPolicy)
    timeout_policy: TimeoutPolicy = Field(default_factory=TimeoutPolicy)
    required_capabilities: list[str] = Field(default_factory=list, max_length=50)
    required_permissions: list[str] = Field(default_factory=list, max_length=50)
    resource_requirements: list[ResourceRequirement] = Field(default_factory=list, max_length=50)
    approval_policy: ApprovalPolicy = Field(default_factory=ApprovalPolicy)
    verification_policy: VerificationPolicy = Field(default_factory=VerificationPolicy)
    compensation_node_id: str | None = Field(default=None, max_length=160)
    priority: int = Field(default=50, ge=0, le=100)
    weight: float = Field(default=1.0, ge=0.01, le=100.0)
    optional: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkflowEdgeSpec(ExecutionEngineSchema):
    edge_id: str = Field(default_factory=lambda: f"edge_{uuid4().hex[:12]}", min_length=1, max_length=160)
    from_node_id: str = Field(min_length=1, max_length=160)
    to_node_id: str = Field(min_length=1, max_length=160)
    edge_type: EdgeType = "success"
    condition_expression: str | None = Field(default=None, max_length=1000)


class WorkflowCompileRequest(ExecutionEngineSchema):
    mission_id: UUID = Field(default_factory=uuid4)
    plan_id: UUID = Field(default_factory=uuid4)
    plan_version: int = Field(default=1, ge=1)
    nodes: list[WorkflowNodeSpec] = Field(min_length=1, max_length=1000)
    edges: list[WorkflowEdgeSpec] = Field(default_factory=list, max_length=5000)
    maximum_concurrency: int = Field(default=4, ge=1, le=100)
    compiler_version: str = Field(default="execution-engine-v1", max_length=80)


class WorkflowValidationResponse(ExecutionEngineSchema):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    topological_order: list[str] = Field(default_factory=list)
    entry_node_ids: list[str] = Field(default_factory=list)
    terminal_node_ids: list[str] = Field(default_factory=list)
    edge_count: int = 0
    critical_path: list[str] = Field(default_factory=list)
    critical_path_weight: float = 0.0


class ExecutableWorkflowResponse(ExecutionEngineSchema):
    workflow_id: UUID
    mission_id: UUID
    plan_id: UUID
    plan_version: int
    workflow_version: int
    nodes: list[WorkflowNodeSpec]
    edges: list[WorkflowEdgeSpec]
    entry_node_ids: list[str]
    terminal_node_ids: list[str]
    maximum_concurrency: int
    compiler_version: str
    graph_hash: str
    validation: WorkflowValidationResponse
    compiled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class NodeState(ExecutionEngineSchema):
    node_id: str
    status: NodeRuntimeStatus = "pending"
    attempt_number: int = 0
    retry_after: datetime | None = None
    active_lease_id: str | None = None
    failure_class: str | None = None
    completed_at: datetime | None = None


class SchedulerRequest(ExecutionEngineSchema):
    mission_status: MissionRuntimeStatus = "running"
    workflow: ExecutableWorkflowResponse
    node_states: list[NodeState] = Field(default_factory=list)
    locked_resources: list[str] = Field(default_factory=list)
    maximum_dispatch: int = Field(default=10, ge=1, le=100)
    budget_remaining_percent: float = Field(default=100, ge=0, le=100)
    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class DependencyEvaluation(ExecutionEngineSchema):
    node_id: str
    satisfied: bool
    missing_dependencies: list[str] = Field(default_factory=list)
    failed_dependencies: list[str] = Field(default_factory=list)
    unresolved_conditions: list[str] = Field(default_factory=list)
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ScheduledNodeResponse(ExecutionEngineSchema):
    node_id: str
    name: str
    queue: str
    priority_score: float
    idempotency_key: str
    required_capabilities: list[str]
    required_permissions: list[str]
    resource_keys: list[str]


class SchedulerResponse(ExecutionEngineSchema):
    ready_nodes: list[ScheduledNodeResponse]
    blocked: list[DependencyEvaluation]
    events: list[str]
    dispatch_count: int


class MissionTransitionRequest(ExecutionEngineSchema):
    current_status: MissionRuntimeStatus
    requested_status: MissionRuntimeStatus


class MissionTransitionResponse(ExecutionEngineSchema):
    allowed: bool
    current_status: MissionRuntimeStatus
    requested_status: MissionRuntimeStatus
    event_type: str | None = None
    reason: str


class LeasePlanRequest(ExecutionEngineSchema):
    mission_id: UUID
    workflow_version: int = Field(default=1, ge=1)
    node_id: str = Field(min_length=1, max_length=160)
    worker_id: str = Field(min_length=1, max_length=160)
    logical_attempt: int = Field(default=1, ge=1)
    ttl_seconds: int = Field(default=60, ge=5, le=3600)
    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LeasePlanResponse(ExecutionEngineSchema):
    lease_id: str
    idempotency_key: str
    fencing_token: int
    acquired_at: datetime
    expires_at: datetime
    status: Literal["planned", "denied"]
    safety_rules: list[str]


class EffectReservationRequest(ExecutionEngineSchema):
    mission_id: UUID
    node_id: str
    execution_id: str
    effect_type: str
    target_resource: str
    idempotency_key: str
    existing_effects: list[dict[str, Any]] = Field(default_factory=list)


class EffectReservationResponse(ExecutionEngineSchema):
    reserved: bool
    status: Literal["reserved", "duplicate", "conflict"]
    idempotency_key: str
    effect_id: str
    reason: str
