from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


RiskLevel = str
GovernanceDecision = str


class GovernanceModelResponse(BaseModel):
    model_key: str
    provider_key: str
    display_name: str
    status: str
    lifecycle_stage: str
    risk_level: RiskLevel
    approval_status: str
    known_risks: list[str]
    controls: list[str]
    monitoring_intensity: str


class GovernancePolicyResponse(BaseModel):
    policy_key: str
    name: str
    domain: str
    description: str
    severity: RiskLevel
    applies_to: list[str]
    requirements: list[str]
    version: str


class GovernanceEvaluateRequest(BaseModel):
    action: str = Field(min_length=2, max_length=160)
    object_type: str = Field(min_length=2, max_length=120)
    object_id: str | None = Field(default=None, max_length=240)
    actor_type: str = Field(default="human", max_length=80)
    mission_id: UUID | None = None
    task_id: UUID | None = None
    data_classification: str = Field(default="internal", max_length=80)
    lifecycle_stage: str = Field(default="development", max_length=80)
    model_key: str | None = Field(default=None, max_length=160)
    provider_key: str | None = Field(default=None, max_length=120)
    capabilities: list[str] = Field(default_factory=list, max_length=100)
    frameworks: list[str] = Field(default_factory=list, max_length=30)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    approvals: list[str] = Field(default_factory=list, max_length=50)
    artifact: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)


class GovernanceEvaluateResponse(BaseModel):
    evaluation_id: UUID | None = None
    policy_key: str
    action: str
    object_type: str
    decision: GovernanceDecision
    risk_level: RiskLevel
    risk_score: int
    reason: str
    required_approvals: list[str]
    controls: list[str]
    compliance: dict[str, Any]
    privacy: dict[str, Any]
    content_safety: dict[str, Any]
    supply_chain: dict[str, Any]
    monitoring: dict[str, Any]
    events: list[str]


class GovernanceApprovalRequest(BaseModel):
    evaluation_id: UUID | None = None
    object_type: str = Field(min_length=2, max_length=120)
    object_id: str = Field(min_length=1, max_length=240)
    decision: str = Field(pattern="^(approved|rejected|needs_changes)$")
    rationale: str = Field(min_length=3, max_length=2000)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    approver_role: str = Field(default="human_reviewer", max_length=120)


class GovernanceApprovalResponse(BaseModel):
    object_type: str
    object_id: str
    decision: str
    event_type: str
    audit_recorded: bool
    approved_at: datetime


class GovernanceComplianceResponse(BaseModel):
    frameworks: list[str]
    controls: list[dict[str, Any]]
    blockers: list[str]
    warnings: list[str]
    ready: bool
    checked_at: datetime


class GovernanceDashboardResponse(BaseModel):
    status: str
    risk: dict[str, Any]
    compliance: dict[str, Any]
    privacy: dict[str, Any]
    model_registry: dict[str, Any]
    incidents: dict[str, Any]
    policy_activity: dict[str, Any]
    open_reviews: int
    refreshed_at: datetime
