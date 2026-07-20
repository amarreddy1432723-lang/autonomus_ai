from __future__ import annotations

from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CivilizationEvolveRequest(BaseModel):
    civilization_id: UUID | str | None = None
    objective: str = Field(min_length=5, max_length=4000)
    evolution_type: str = Field(default="capability", max_length=120)
    target_state: str = Field(default="improved_operational_state", max_length=240)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    human_approval_id: UUID | str | None = None
    constraints: list[str] = Field(default_factory=list, max_length=50)
    affected_organizations: list[str] = Field(default_factory=list, max_length=50)


class CivilizationEvolveResponse(BaseModel):
    evolution_id: UUID | str
    status: str
    objective: str
    evolution_type: str
    target_state: str
    stage: str
    required_approvals: list[str]
    verification_plan: list[str]
    promotion_ready: bool
    blocked_reasons: list[str]
    events: list[str]


class CivilizationProposalRequest(BaseModel):
    goal: str = Field(min_length=5, max_length=4000)
    domain: str = Field(default="software_engineering", max_length=120)
    current_organizations: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    required_capabilities: list[str] = Field(default_factory=list, max_length=50)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    budget_limit: float | None = Field(default=None, ge=0)


class CivilizationProposalResponse(BaseModel):
    proposal_id: UUID | str
    status: str
    goal: str
    capability_gaps: list[dict[str, Any]]
    proposed_organization: dict[str, Any]
    specialists: list[dict[str, Any]]
    governance_review: dict[str, Any]
    estimated_resources: dict[str, Any]
    events: list[str]


class CivilizationSimulateRequest(BaseModel):
    scenario: str = Field(min_length=5, max_length=4000)
    evolution_type: str = Field(default="strategic_expansion", max_length=120)
    affected_domains: list[str] = Field(default_factory=list, max_length=50)
    affected_organizations: list[str] = Field(default_factory=list, max_length=50)
    constraints: list[str] = Field(default_factory=list, max_length=50)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)


class CivilizationSimulateResponse(BaseModel):
    simulation_id: UUID | str
    status: str
    scenario: str
    predicted_impact: dict[str, Any]
    risk_analysis: dict[str, Any]
    resource_plan: dict[str, Any]
    governance_review: dict[str, Any]
    recommendation: str
    events: list[str]


class CivilizationStateResponse(BaseModel):
    civilization_id: UUID | str
    vision: str
    status: str
    organizations: list[dict[str, Any]]
    ecosystem: list[str]
    knowledge_layers: list[str]
    evolution_state: dict[str, Any]
    resilience: dict[str, Any]
    latest_events: list[str]


class CivilizationMetricsResponse(BaseModel):
    innovation_rate: float
    learning_velocity: float
    mission_success: float
    knowledge_growth: int
    automation_coverage: float
    customer_value: float
    sustainability: float
    governance_health: float
    research_output: int
    operational_resilience: float
    status: str


class CivilizationConstitutionResponse(BaseModel):
    version: str
    immutable_principles: list[str]
    governance_boundaries: list[str]
    human_authority: list[str]
    approval_rules: list[str]
    evolution_constraints: list[str]
    ethical_obligations: list[str]
    change_policy: str

