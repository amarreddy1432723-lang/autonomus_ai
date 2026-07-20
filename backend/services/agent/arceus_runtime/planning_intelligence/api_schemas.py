from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


AutonomyLevel = Literal["assistive", "supervised", "bounded_autonomous", "autonomous"]
PlanningDepth = Literal["fast", "balanced", "deep"]
ConstraintType = Literal["scope", "path", "time", "cost", "tool", "model", "security", "quality", "architecture", "business", "approval"]
CriterionType = Literal["functional", "technical", "quality", "performance", "security", "business", "manual"]


class PlanningConstraint(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    type: ConstraintType
    rule: str = Field(min_length=1, max_length=1000)
    mandatory: bool = True
    priority: int = Field(default=3, ge=1, le=5)
    source_id: str | None = Field(default=None, max_length=160)


class SuccessCriterion(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=1000)
    type: CriterionType = "functional"
    required: bool = True
    verification_method: str = Field(min_length=1, max_length=240)
    target: dict[str, Any] = Field(default_factory=dict)


class PlanningBudget(BaseModel):
    max_cost_usd: float | None = Field(default=None, ge=0)
    max_engineering_hours: float | None = Field(default=None, ge=0)
    max_tokens: int | None = Field(default=None, ge=0)


class PlanningIntelligenceRequest(BaseModel):
    organization_id: UUID | None = None
    workspace_id: UUID | None = None
    repository_id: str | None = Field(default=None, max_length=240)
    objective: str = Field(min_length=3, max_length=4000)
    normalized_objective: str | None = Field(default=None, max_length=4000)
    constraints: list[PlanningConstraint] = Field(default_factory=list, max_length=50)
    success_criteria: list[SuccessCriterion] = Field(default_factory=list, max_length=50)
    budget: PlanningBudget | None = None
    deadline: datetime | None = None
    autonomy_level: AutonomyLevel = "supervised"
    planning_depth: PlanningDepth = "balanced"
    context_package_id: str | None = Field(default=None, max_length=240)
    previous_plan_id: str | None = Field(default=None, max_length=240)
    repository_intelligence: dict[str, Any] = Field(default_factory=dict)
    relevant_memory: list[dict[str, Any]] = Field(default_factory=list, max_length=100)


class GoalNode(BaseModel):
    goal_id: str
    title: str
    description: str
    parent_id: str | None = None
    success_criteria_ids: list[str] = Field(default_factory=list)
    uncertainty: float = Field(ge=0, le=1)


class PlanTask(BaseModel):
    task_key: str
    title: str
    category: str
    owner_role_key: str
    dependencies: list[str]
    risk_level: str
    estimated_hours: float
    estimated_cost_usd: float
    estimated_tokens: int
    acceptance_criteria: list[str]
    verification_methods: list[str]


class StrategyOption(BaseModel):
    strategy_key: str
    name: str
    rationale: str
    tasks: list[PlanTask]
    risk_score: float = Field(ge=0, le=1)
    cost_score: float = Field(ge=0, le=1)
    speed_score: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    decision_score: float = Field(ge=0, le=1)
    required_approvals: list[str]
    constraint_violations: list[dict[str, Any]]
    simulation: dict[str, Any]


class PlanningDecisionResponse(BaseModel):
    plan_id: str
    objective: str
    interpreted_goal: str
    goal_tree: list[GoalNode]
    recommended_strategy_key: str
    alternatives: list[StrategyOption]
    next_best_action: dict[str, Any]
    approval_plan: list[dict[str, Any]]
    uncertainty: dict[str, Any]
    events: list[str]


class ReplanRequest(BaseModel):
    previous_plan: PlanningDecisionResponse
    new_evidence: dict[str, Any] = Field(default_factory=dict)
    failed_task_keys: list[str] = Field(default_factory=list)
    budget_change: PlanningBudget | None = None
    user_feedback: str | None = Field(default=None, max_length=2000)


class ReplanResponse(BaseModel):
    should_replan: bool
    reasons: list[str]
    recommended_adjustments: list[str]
    replacement_plan: PlanningDecisionResponse | None = None


class PlanValidationRequest(BaseModel):
    plan: PlanningDecisionResponse


class PlanValidationResponse(BaseModel):
    valid: bool
    errors: list[str]
    warnings: list[str]

