from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class SecurityPolicyResponse(BaseModel):
    policy_key: str
    name: str
    description: str
    severity: str
    protected_actions: list[str]


class SecurityEvaluateRequest(BaseModel):
    mission_id: UUID | None = None
    task_id: UUID | None = None
    policy_key: str | None = None
    subject: dict[str, Any] = Field(default_factory=dict)
    action: str
    resource: dict[str, Any] = Field(default_factory=dict)
    environment: str = "development"
    risk_level: str = "medium"


class SecurityEvaluationResponse(BaseModel):
    id: UUID | None = None
    mission_id: UUID | None
    task_id: UUID | None
    policy_key: str
    subject: dict[str, Any]
    action: str
    resource: dict[str, Any]
    decision: str
    reason: str
    obligations: list[str]
    created_at: datetime | None = None


class SecurityIncidentRequest(BaseModel):
    mission_id: UUID | None = None
    task_id: UUID | None = None
    incident_type: str
    severity: str = "medium"
    summary: str
    evidence: dict[str, Any] = Field(default_factory=dict)
    resource_type: str = "security_incident"
    resource_id: str | None = None


class SecurityIncidentResponse(BaseModel):
    incident_type: str
    severity: str
    result: str
    summary: str
    audit_recorded: bool


class ComplianceProfileResponse(BaseModel):
    profile_key: str
    name: str
    controls: list[str]
    retention_policy: dict[str, str]
    required_security_events: list[str]
