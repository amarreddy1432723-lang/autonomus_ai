from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class RuntimeHealthResponse(BaseModel):
    tenant_id: UUID
    status: str
    ready: bool
    blockers: list[str]
    warnings: list[str]
    mission_statuses: dict[str, int]
    task_statuses: dict[str, int]
    approval_statuses: dict[str, int]
    outbox_statuses: dict[str, int]
    active_worker_leases: int
    stale_processing_outbox: int
    checked_at: datetime
