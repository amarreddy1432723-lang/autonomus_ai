from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StrategicObjectiveRequest(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    vision: str = Field(min_length=10, max_length=4_000)
    domain: str = Field(default="software", min_length=2, max_length=120)
    horizon: str = Field(default="quarter", min_length=2, max_length=80)
    desired_outcomes: list[str] = Field(default_factory=list)
    kpis: dict[str, float] = Field(default_factory=dict)
    priority: int = Field(default=3, ge=0, le=5)
    evidence_ids: list[UUID] = Field(default_factory=list)


class StrategicObjectiveResponse(BaseModel):
    objective_id: UUID
    title: str
    status: str
    hierarchy: dict[str, Any]
    key_results: list[dict[str, Any]]
    required_governance: list[str]
    traceability: dict[str, Any]


class StrategyDashboardResponse(BaseModel):
    enterprise_health: float
    status: str
    health_dimensions: dict[str, float]
    kpis: dict[str, float]
    risks: list[dict[str, Any]]
    recommendations: list[str]
    portfolio_summary: dict[str, Any]
    generated_at: datetime


class StrategyPortfolioResponse(BaseModel):
    missions_by_status: dict[str, int]
    task_flow: dict[str, int]
    priority_queue: list[dict[str, Any]]
    dependencies: list[dict[str, Any]]
    resource_allocation: dict[str, Any]
    risks: list[dict[str, Any]]


class StrategySimulationRequest(BaseModel):
    scenario_name: str = Field(min_length=3, max_length=200)
    objective: str = Field(min_length=5, max_length=2_000)
    assumptions: dict[str, float] = Field(default_factory=dict)
    horizon_months: int = Field(default=3, ge=1, le=60)
    investment_delta: float = 0.0
    evidence_ids: list[UUID] = Field(default_factory=list)


class StrategySimulationResponse(BaseModel):
    scenario_id: str
    advisory: str
    confidence: float
    expected_impacts: dict[str, float]
    uncertainty: dict[str, Any]
    risks: list[dict[str, Any]]
    recommendation: str
    assumptions: dict[str, float]


class ExecutiveDecisionRequest(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    decision_type: str = Field(min_length=2, max_length=120)
    summary: str = Field(min_length=10, max_length=4_000)
    selected_option: str = Field(min_length=2, max_length=500)
    alternatives: list[str] = Field(default_factory=list)
    expected_impact: Literal["low", "medium", "high", "critical"] = "medium"
    evidence_ids: list[UUID] = Field(default_factory=list)
    reversible: bool = True


class ExecutiveDecisionResponse(BaseModel):
    decision_id: UUID
    status: str
    governance_decision: str
    required_approvals: list[str]
    reusable_knowledge: dict[str, Any]
    traceability: dict[str, Any]


class ExecutiveBriefingResponse(BaseModel):
    generated_at: datetime
    headlines: list[str]
    risks: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    recommendations: list[str]
    next_actions: list[str]
