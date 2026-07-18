from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ConstitutionalRuleResponse(BaseModel):
    rule_id: str
    name: str
    description: str
    category: str
    priority: int
    applies_to: list[str]
    enforcement_level: str
    version: int


class ConstitutionResponse(BaseModel):
    constitution_key: str
    version: int
    hierarchy: list[str]
    rule_count: int
    absolute_rule_count: int


class ConstitutionEvaluateRequest(BaseModel):
    mission_id: UUID | None = None
    task_id: UUID | None = None
    action_type: str
    objective: str = Field(min_length=1, max_length=5_000)
    evidence_ids: list[UUID] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    selected_alternative: str | None = Field(default=None, max_length=1_000)
    risks: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    requires_human_authority: bool = False
    irreversible: bool = False
    learning_change: bool = False
    repository_change_count: int = Field(default=0, ge=0)


class ConstitutionEvaluationResponse(BaseModel):
    decision: str
    blockers: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    satisfied_rules: list[str]
    reasoning_summary: dict[str, Any]
    checked_at: datetime


class OrganizationStandardResponse(BaseModel):
    standard_key: str
    name: str
    version: int
    category: str
    summary: str
    required_evidence: list[str]


class OrganizationFitnessResponse(BaseModel):
    fitness_score: float
    status: str
    metrics: dict[str, Any]
    bottlenecks: list[str]
    recommendations: list[str]


class LessonProposalRequest(BaseModel):
    mission_id: UUID
    lesson: str = Field(min_length=5, max_length=2_000)
    evidence_ids: list[UUID] = Field(default_factory=list)
    outcome_metric: str | None = Field(default=None, max_length=160)
    proposed_scope: str = Field(default="mission", pattern="^(mission|project|organization)$")


class LessonProposalResponse(BaseModel):
    status: str
    promotion_allowed: bool
    reason: str
    required_approvals: list[str]


class EvolutionRequest(BaseModel):
    proposal_key: str = Field(min_length=3, max_length=160)
    description: str = Field(min_length=5, max_length=2_000)
    changes: dict[str, Any] = Field(default_factory=dict)
    baseline_mission_ids: list[UUID] = Field(default_factory=list)
    dry_run: bool = True


class EvolutionResponse(BaseModel):
    status: str
    accepted: bool
    reason: str
    simulation_required: bool
    blocked_changes: list[str]
    required_approvals: list[str]
