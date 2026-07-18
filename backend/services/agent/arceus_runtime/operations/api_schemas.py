from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class OperationHealthResponse(BaseModel):
    status: str
    ready: bool
    blockers: list[str]
    warnings: list[str]
    control_plane: dict[str, Any]
    execution_plane: dict[str, Any]
    checked_at: datetime


class RegionResponse(BaseModel):
    region_key: str
    status: str
    role: str
    data_residency_allowed: bool
    provider_count: int
    healthy_provider_count: int
    warnings: list[str]


class WorkerPoolResponse(BaseModel):
    active_worker_leases: int
    stale_processing_outbox: int
    ready_tasks: int
    running_tasks: int
    blocked_tasks: int
    failed_tasks: int
    utilization_status: str
    recommendations: list[str]


class QueueResponse(BaseModel):
    queue_key: str
    pending: int
    processing: int
    failed: int
    dead_letter: int
    health: str
    recommendations: list[str]


class SloResponse(BaseModel):
    slo_key: str
    target: float
    observed: float
    status: str
    error_budget_remaining: float
    burn_reasons: list[str]


class OperationsActionRequest(BaseModel):
    target_region: str | None = Field(default=None, max_length=120)
    reason: str = Field(min_length=3, max_length=2_000)
    dry_run: bool = True


class OperationsActionResponse(BaseModel):
    action: str
    accepted: bool
    dry_run: bool
    status: str
    reason: str
    required_approvals: list[str]
    audit_recorded: bool
