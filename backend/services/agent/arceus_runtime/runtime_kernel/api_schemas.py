from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


SchedulingStrategy = Literal["fifo", "priority", "deadline", "weighted_fair", "cost_optimized", "latency_optimized", "resource_optimized"]
RuntimeMissionState = Literal["created", "planned", "waiting", "ready", "running", "blocked", "review", "verification", "completed", "archived", "paused", "cancelled"]
RuntimeTaskState = Literal["pending", "queued", "leased", "running", "checkpoint", "succeeded", "failed", "retry", "cancelled"]


class RuntimeTaskDefinition(BaseModel):
    task_key: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=240)
    task_type: str = Field(default="execution", max_length=120)
    dependencies: list[str] = Field(default_factory=list, max_length=50)
    required_capabilities: list[str] = Field(default_factory=list, max_length=20)
    priority: int = Field(default=50, ge=0, le=100)
    estimated_cost: float = Field(default=0.0, ge=0)


class RuntimeMissionRequest(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    objective: str = Field(min_length=3, max_length=2_000)
    priority: int = Field(default=50, ge=0, le=100)
    scheduling_strategy: SchedulingStrategy = "priority"
    tasks: list[RuntimeTaskDefinition] = Field(min_length=1, max_length=200)
    resource_budget: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def task_keys_are_unique(self) -> "RuntimeMissionRequest":
        keys = [task.task_key for task in self.tasks]
        if len(keys) != len(set(keys)):
            raise ValueError("Runtime task keys must be unique.")
        unknown_dependencies = sorted({dep for task in self.tasks for dep in task.dependencies if dep not in set(keys)})
        if unknown_dependencies:
            raise ValueError(f"Unknown runtime task dependencies: {', '.join(unknown_dependencies)}")
        return self


class RuntimeTaskResponse(BaseModel):
    task_id: str
    task_key: str
    title: str
    task_type: str
    dependencies: list[str]
    required_capabilities: list[str]
    priority: int
    status: RuntimeTaskState
    assigned_worker: str | None = None
    lease_id: str | None = None
    retry_policy: dict[str, Any]
    execution_policy: dict[str, Any]


class RuntimeMissionResponse(BaseModel):
    mission_id: str
    title: str
    objective: str
    priority: int
    workflow: dict[str, Any]
    graph: dict[str, Any]
    scheduler: dict[str, Any]
    checkpoints: list[dict[str, Any]]
    runtime_state: RuntimeMissionState
    tasks: list[RuntimeTaskResponse]
    events: list[dict[str, Any]]
    created_at: datetime


class LeaseRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=160)
    worker_capabilities: list[str] = Field(default_factory=list, max_length=50)
    ttl_seconds: int = Field(default=300, ge=30, le=3600)


class LeaseResponse(BaseModel):
    lease_id: str
    task_id: str
    worker_id: str
    expires_at: datetime
    renewals: int
    status: str
    cognitive_state: dict[str, Any]


class CheckpointRequest(BaseModel):
    worker_id: str = Field(min_length=1, max_length=160)
    progress: float = Field(ge=0, le=1)
    outputs: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list, max_length=50)
    cognitive_state: dict[str, Any] = Field(default_factory=dict)
    resource_usage: dict[str, Any] = Field(default_factory=dict)


class CheckpointResponse(BaseModel):
    checkpoint_id: str
    task_id: str
    timestamp: datetime
    state_hash: str
    artifacts: list[str]
    evidence: list[str]
    metadata: dict[str, Any]


class RuntimeActionResponse(BaseModel):
    accepted: bool
    status: str
    reason: str
    events: list[dict[str, Any]]


class RuntimeEventResponse(BaseModel):
    event_id: str
    sequence: int
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime


class RuntimeReplayResponse(BaseModel):
    mission_id: str
    deterministic: bool
    replay_hash: str
    event_count: int
    checkpoint_count: int
    simulated_side_effects: bool
    reconstructed_state: dict[str, Any]


class RuntimeMetricsResponse(BaseModel):
    mission_duration_ms: int
    queue_wait_ms: int
    worker_utilization: float
    checkpoint_frequency: float
    retry_rate: float
    lease_expirations: int
    recovery_success: float
    scheduler_latency_ms: int
    parallelism_efficiency: float
