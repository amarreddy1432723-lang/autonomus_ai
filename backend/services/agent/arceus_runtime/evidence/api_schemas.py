from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class EvidenceResponse(BaseModel):
    id: UUID
    mission_id: UUID
    workflow_id: UUID | None = None
    task_id: UUID | None
    artifact_id: UUID | None
    evidence_type: str
    status: str
    summary: str
    payload: dict[str, Any]
    verification_method: str = "manual"
    content_hash: str = ""
    trust_level: str = "unverified"
    immutable: bool = True
    collected_by_member_id: UUID | None
    created_at: datetime
    updated_at: datetime
    version_number: int


class VerificationRunResponse(BaseModel):
    id: UUID
    mission_id: UUID
    task_id: UUID | None
    verification_type: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    command: str | None
    result: dict[str, Any]
    evidence_id: UUID | None
    created_at: datetime
    updated_at: datetime
    version_number: int
