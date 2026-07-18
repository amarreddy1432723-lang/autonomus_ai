from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CreateVerificationRequest(BaseModel):
    mission_id: UUID
    workflow_id: UUID | None = None
    task_id: UUID | None = None
    target_type: str = "mission"
    target_id: UUID | None = None
    criteria: list[dict[str, Any]] = Field(default_factory=list)
    methods: list[str] = Field(default_factory=list)
    evidence_required: list[str] = Field(default_factory=list)
    reviewers: list[UUID] = Field(default_factory=list)
    environment: str = "local"
    blocking: bool = True
    timeout_seconds: int = Field(default=900, ge=1, le=86400)


class VerificationPlanResponse(BaseModel):
    id: UUID
    mission_id: UUID
    workflow_id: UUID | None
    task_id: UUID | None
    target_type: str
    target_id: UUID
    criteria: list[dict[str, Any]]
    methods: list[str]
    evidence_required: list[str]
    reviewers: list[str]
    environment: str
    blocking: bool
    timeout_seconds: int
    status: str
    created_at: datetime
    updated_at: datetime
    version_number: int


class CreateEvidenceRequest(BaseModel):
    mission_id: UUID
    workflow_id: UUID | None = None
    task_id: UUID | None = None
    artifact_id: UUID | None = None
    evidence_type: str
    summary: str
    payload: dict[str, Any] = Field(default_factory=dict)
    verification_method: str = "manual"
    trust_level: str = "unverified"
    collected_by_member_id: UUID | None = None


class RunQualityGatesRequest(BaseModel):
    mission_id: UUID
    gate_keys: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)


class QualityGateResponse(BaseModel):
    id: UUID
    mission_id: UUID
    verification_plan_id: UUID | None
    gate_key: str
    name: str
    category: str
    gate_type: str
    required: bool
    verifier: str
    timeout_seconds: int
    status: str
    result: dict[str, Any]
    evidence_ids: list[str]
    last_run_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version_number: int


class TrustScoreResponse(BaseModel):
    id: UUID
    mission_id: UUID
    target_type: str
    target_id: UUID
    trust_level: int
    score: float
    confidence: float
    contributors: dict[str, Any]
    calculated_at: datetime


class CompletionCertificateResponse(BaseModel):
    id: UUID
    mission_id: UUID
    certificate_version: int
    status: str
    completed_requirements: list[dict[str, Any]]
    evidence_ids: list[str]
    gate_ids: list[str]
    approval_ids: list[str]
    trust_score_id: UUID | None
    blockers: list[dict[str, Any]]
    certificate_hash: str
    signature: str
    signed_at: datetime | None
    immutable: bool
    created_at: datetime
    updated_at: datetime
    version_number: int


class CompletionApprovalRequest(BaseModel):
    mission_id: UUID
    certificate_id: UUID | None = None
    human_approved: bool = True
    approval_notes: str = ""
