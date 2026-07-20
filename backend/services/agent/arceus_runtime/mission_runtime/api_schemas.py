from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..context_engine.api_schemas import ContextPackage, IntentAnalysis, ModelContextProfile


class RuntimeTaskSpec(BaseModel):
    task_key: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=500)
    task_type: str = Field(default="custom", min_length=1, max_length=80)
    dependencies: list[str] = Field(default_factory=list, max_length=100)
    status: str = Field(default="pending", max_length=60)
    estimated_seconds: int = Field(default=300, ge=1, le=31_536_000)
    priority: int = Field(default=50, ge=0, le=100)
    risk_level: str = Field(default="medium", max_length=40)
    acceptance_criteria: list[str] = Field(default_factory=list, max_length=50)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimePlanValidationRequest(BaseModel):
    tasks: list[RuntimeTaskSpec] = Field(min_length=1, max_length=500)


class RuntimePlanValidationResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    topological_order: list[str] = Field(default_factory=list)
    critical_path: list[str] = Field(default_factory=list)
    critical_path_seconds: int = 0
    ready_task_keys: list[str] = Field(default_factory=list)
    task_count: int = 0
    edge_count: int = 0


class TaskRuntimeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_key: str
    title: str
    task_type: str
    status: str
    owner_member_id: UUID | None = None
    priority_score: float = 0
    dependencies: list[str] = Field(default_factory=list)
    estimated_seconds: int = 300
    progress_weight: float = 1
    failure_reason: str | None = None


class RuntimeEventSummary(BaseModel):
    id: UUID
    event_type: str
    aggregate_type: str
    aggregate_version: int
    actor_type: str
    actor_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class RuntimeBudgetSummary(BaseModel):
    maximum_budget_amount: float | None = None
    actual_cost_amount: float = 0
    budget_currency: str = "USD"
    consumed_percent: float | None = None


class MissionRuntimeSnapshotResponse(BaseModel):
    mission_id: UUID
    mission_status: str
    mission_version: int
    objective: str
    progress_percent: float
    task_counts: dict[str, int]
    ready_tasks: list[TaskRuntimeSummary] = Field(default_factory=list)
    running_tasks: list[TaskRuntimeSummary] = Field(default_factory=list)
    blocked_tasks: list[TaskRuntimeSummary] = Field(default_factory=list)
    failed_tasks: list[TaskRuntimeSummary] = Field(default_factory=list)
    critical_path: list[str] = Field(default_factory=list)
    critical_path_seconds: int = 0
    pending_approvals: int = 0
    evidence_count: int = 0
    artifact_count: int = 0
    budget: RuntimeBudgetSummary
    latest_events: list[RuntimeEventSummary] = Field(default_factory=list)
    generated_at: datetime


class MissionRuntimeReportResponse(BaseModel):
    mission_id: UUID
    mission_status: str
    objective: str
    progress_percent: float
    completed_tasks: list[str] = Field(default_factory=list)
    failed_tasks: list[str] = Field(default_factory=list)
    blocked_tasks: list[str] = Field(default_factory=list)
    outstanding_approvals: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    artifact_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    remaining_risks: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    generated_at: datetime


class RunNextTaskRequest(BaseModel):
    worker_id: str = Field(default="mission-runtime-local-worker", min_length=1, max_length=160)
    ttl_seconds: int = Field(default=120, ge=15, le=3_600)


class RunNextTaskResponse(BaseModel):
    status: str
    task_id: str | None = None
    checkpoint_id: str | None = None
    attempt_id: str | None = None
    expired_leases: int | None = None
    retryable: bool | None = None


class TaskContextBuildRequest(BaseModel):
    model: ModelContextProfile = Field(default_factory=ModelContextProfile)
    root_path: str | None = Field(default=None, max_length=2_000)
    repository_id: str | None = Field(default=None, max_length=160)
    force_rebuild: bool = False


class TaskContextBuildResponse(BaseModel):
    task_id: UUID
    task_key: str
    intent: IntentAnalysis
    package: ContextPackage
    cache_hit: bool
