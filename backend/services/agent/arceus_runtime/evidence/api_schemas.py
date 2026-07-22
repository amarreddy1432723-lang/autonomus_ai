from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


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


class ToolEvidenceRecord(BaseModel):
    tool: str = Field(min_length=1, max_length=160)
    input_summary: str = Field(default="", max_length=2_000)
    output_summary: str = Field(default="", max_length=4_000)
    duration_ms: int | None = Field(default=None, ge=0)
    status: str = Field(default="succeeded", max_length=60)
    error_class: str | None = Field(default=None, max_length=120)
    audit_id: str | None = Field(default=None, max_length=160)
    timestamp: str | None = Field(default=None, max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)


class ToolEvidenceRequest(BaseModel):
    records: list[ToolEvidenceRecord] = Field(min_length=1, max_length=100)
    source: str = Field(default="desktop_tool_runtime", max_length=160)
    summary: str | None = Field(default=None, max_length=4_000)


class ChangeSetOperation(BaseModel):
    operation: Literal["create", "modify", "folder", "delete", "rename"]
    path: str = Field(min_length=1, max_length=1_000)
    old_path: str | None = Field(default=None, max_length=1_000)
    diff: str | None = Field(default=None, max_length=500_000)
    original_sha256: str | None = Field(default=None, max_length=128)
    modified_sha256: str | None = Field(default=None, max_length=128)
    risk: str = Field(default="medium", max_length=60)
    review_required: bool = False
    applied: bool = False
    rollback_snapshot_id: str | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskChangeSetRequest(BaseModel):
    title: str = Field(default="Task Change Set", max_length=300)
    summary: str = Field(default="", max_length=4_000)
    review_state: Literal["proposed", "validated", "review_required", "applied", "rolled_back", "rejected"] = "proposed"
    source: str = Field(default="desktop_tool_runtime", max_length=160)
    changes: list[ChangeSetOperation] = Field(min_length=1, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)


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
