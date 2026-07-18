from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class IntelligenceTaskCreate(BaseModel):
    title: str = Field(default="Untitled engineering task", min_length=1, max_length=255)
    raw_request: str = Field(..., min_length=1)
    project_id: UUID | None = None
    workspace_id: UUID | None = None
    priority: str = "normal"
    budget_limit: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceCreate(BaseModel):
    evidence_type: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=255)
    summary: str = ""
    uri: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    confidence: float = 1.0


class ApprovalRequest(BaseModel):
    notes: str = ""
    approval_type: str = "plan"


class LifecycleRequest(BaseModel):
    reason: str = ""


class WorkerAssignmentRequest(BaseModel):
    preference: str = "balanced"
