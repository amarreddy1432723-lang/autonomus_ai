from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


PriorityFramework = Literal["rice", "ice", "moscow", "wsjf", "value_effort"]
SignalType = Literal["customer", "product", "engineering", "business", "market"]
RoadmapHorizon = Literal["now", "next", "later", "future"]


class ProductSignal(BaseModel):
    signal_type: SignalType
    source: str = Field(min_length=1, max_length=160)
    theme: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=3, max_length=2_000)
    count: int = Field(default=1, ge=1)
    severity: int = Field(default=3, ge=1, le=5)
    revenue_usd: float = Field(default=0.0, ge=0)
    customer_segment: str | None = Field(default=None, max_length=160)


class ProductOpportunityResponse(BaseModel):
    opportunity_id: str
    title: str
    theme: str
    priority_score: float
    framework: PriorityFramework
    horizon: RoadmapHorizon
    business_impact: float
    customer_demand: float
    strategic_alignment: float
    engineering_effort: float
    risk: float
    revenue_potential: float
    urgency: float
    evidence: list[str]
    recommended_action: str


class ProductRequirementRequest(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    business_problem: str = Field(min_length=3, max_length=2_000)
    user_problem: str = Field(min_length=3, max_length=2_000)
    signals: list[ProductSignal] = Field(default_factory=list, max_length=200)
    objectives: list[str] = Field(default_factory=list, max_length=20)
    stakeholders: list[str] = Field(default_factory=list, max_length=20)
    dependencies: list[str] = Field(default_factory=list, max_length=40)
    risks: list[str] = Field(default_factory=list, max_length=40)
    framework: PriorityFramework = "rice"


class ProductRequirementResponse(BaseModel):
    requirement_id: str
    title: str
    business_problem: str
    user_problem: str
    objectives: list[str]
    user_stories: list[str]
    success_metrics: list[str]
    stakeholders: list[str]
    dependencies: list[str]
    risks: list[str]
    acceptance_criteria: list[str]
    priority: ProductOpportunityResponse
    mission_seed: dict[str, Any]
    generated_at: datetime


class PersonaResponse(BaseModel):
    persona_key: str
    name: str
    goals: list[str]
    frustrations: list[str]
    workflows: list[str]
    feature_usage: list[str]
    satisfaction_signals: list[str]


class RoadmapItemResponse(BaseModel):
    roadmap_item_id: str
    title: str
    horizon: RoadmapHorizon
    priority_score: float
    linked_opportunity_id: str
    dependencies: list[str]
    release_candidate: str
    engineering_mission: dict[str, Any]


class ExperimentRequest(BaseModel):
    hypothesis: str = Field(min_length=5, max_length=1_000)
    variants: list[str] = Field(min_length=2, max_length=10)
    metrics: list[str] = Field(min_length=1, max_length=20)
    success_threshold: float = Field(ge=0.01, le=1.0)
    rollout: float = Field(default=0.1, ge=0.01, le=1.0)
    duration_days: int = Field(default=14, ge=1, le=180)
    owner: str = Field(min_length=1, max_length=160)

    @model_validator(mode="after")
    def ensure_distinct_variants(self) -> "ExperimentRequest":
        normalized = {variant.strip().lower() for variant in self.variants}
        if len(normalized) != len(self.variants):
            raise ValueError("Experiment variants must be distinct.")
        return self


class ExperimentResponse(BaseModel):
    experiment_id: str
    hypothesis: str
    variants: list[str]
    metrics: list[str]
    success_threshold: float
    rollout: float
    duration_days: int
    owner: str
    status: str
    governance: dict[str, Any]
    created_at: datetime


class ReleaseResponse(BaseModel):
    release_id: str
    name: str
    status: str
    features: list[str]
    verification_status: str
    business_readiness: str
    documentation_readiness: str
    support_readiness: str
    rollback_strategy: str
    communication_plan: str


class ProductMetricsResponse(BaseModel):
    mrr: float
    arr: float
    churn: float
    retention: float
    activation: float
    conversion: float
    engagement: float
    feature_adoption: float
    customer_satisfaction: float
    engineering_velocity: float
    deployment_frequency: float


class ProductDashboardResponse(BaseModel):
    generated_at: datetime
    opportunities: list[ProductOpportunityResponse]
    roadmap: list[RoadmapItemResponse]
    personas: list[PersonaResponse]
    releases: list[ReleaseResponse]
    metrics: ProductMetricsResponse
    product_health: str
    recommendations: list[str]
