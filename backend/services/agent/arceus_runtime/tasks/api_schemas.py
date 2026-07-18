from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class TaskOperationRequest(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=2_000)


class TaskDependencyResponse(BaseModel):
    id: UUID
    depends_on_task_id: UUID
    dependency_type: str


class TaskAttemptResponse(BaseModel):
    id: UUID
    task_id: UUID
    attempt_number: int
    status: str
    started_at: datetime
    finished_at: datetime | None
    worker_id: str | None
    result: dict[str, Any]
    error: dict[str, Any]
    version_number: int


class WorkerLeaseResponse(BaseModel):
    id: UUID
    task_id: UUID
    worker_id: str
    status: str
    expires_at: datetime
    version_number: int


class TaskSummaryResponse(BaseModel):
    id: UUID
    mission_id: UUID
    workflow_node_id: UUID | None
    task_key: str
    title: str
    task_type: str
    status: str
    owner_member_id: UUID | None
    acceptance_criteria: list[Any]
    started_at: datetime | None
    completed_at: datetime | None
    failure_reason: str | None
    created_at: datetime
    updated_at: datetime
    version_number: int


class TaskDetailResponse(TaskSummaryResponse):
    input_contract: dict[str, Any]
    output_contract: dict[str, Any]
    dependencies: list[TaskDependencyResponse]
    attempts: list[TaskAttemptResponse]
    active_leases: list[WorkerLeaseResponse]


class TaskOperationResponse(BaseModel):
    task_id: UUID
    mission_id: UUID
    previous_status: str
    status: str
    version_number: int
    operation_id: UUID
