from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ScheduleMissionRequest(BaseModel):
    limit: int = Field(default=25, ge=1, le=100)


class ScheduledTaskResponse(BaseModel):
    id: UUID
    task_key: str
    title: str
    status: str
    owner_member_id: UUID | None
    priority_score: float = 0.0


class ScheduleMissionResponse(BaseModel):
    mission_id: UUID
    mission_status: str
    ready_count: int
    completed_count: int
    total_count: int
    expired_leases: int
    ready_tasks: list[ScheduledTaskResponse]


class AcquireLeaseRequest(BaseModel):
    worker_id: str = Field(min_length=2, max_length=160)
    ttl_seconds: int = Field(default=120, ge=30, le=900)


class LeaseResponse(BaseModel):
    id: UUID
    task_id: UUID
    worker_id: str
    lease_token: str
    status: str
    heartbeat_at: datetime
    expires_at: datetime
    version_number: int


class HeartbeatRequest(BaseModel):
    worker_id: str = Field(min_length=2, max_length=160)
    ttl_seconds: int = Field(default=120, ge=30, le=900)
    progress_percent: int = Field(default=0, ge=0, le=100)
    current_operation: str | None = Field(default=None, max_length=240)
    checkpoint: dict[str, Any] = Field(default_factory=dict)


class CompleteTaskRequest(BaseModel):
    worker_id: str = Field(min_length=2, max_length=160)
    outputs: dict[str, Any] = Field(default_factory=dict)
    progress_percent: int = Field(default=100, ge=0, le=100)


class FailTaskRequest(BaseModel):
    worker_id: str = Field(min_length=2, max_length=160)
    error: str = Field(min_length=1, max_length=2_000)
    retryable: bool = False


class RuntimeTaskResultResponse(BaseModel):
    task_id: UUID
    mission_id: UUID
    status: str
    lease_status: str
    checkpoint_id: UUID | None
    version_number: int


class RuntimeCheckpointResponse(BaseModel):
    id: UUID
    mission_id: UUID
    task_id: UUID
    workflow_id: UUID | None
    worker_lease_id: UUID | None
    checkpoint_key: str
    workflow_version: int
    execution_state: dict[str, Any]
    outputs: dict[str, Any]
    progress_percent: int
    created_by_worker_id: str
    created_at: datetime
    version_number: int
