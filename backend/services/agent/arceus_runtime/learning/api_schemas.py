from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class LearningRecordRequest(BaseModel):
    mission_id: UUID
    title: str = Field(min_length=3, max_length=240)
    lesson: str = Field(min_length=5, max_length=2_000)
    evidence_ids: list[UUID] = Field(default_factory=list)
    source_type: str = Field(default="mission_outcome", max_length=80)
    impact: str = Field(default="medium", pattern="^(low|medium|high|critical)$")
    outcome_metrics: dict[str, float] = Field(default_factory=dict)


class LearningRecordResponse(BaseModel):
    learning_id: UUID | None
    mission_id: UUID
    title: str
    status: str
    promotion_ready: bool
    evidence_ids: list[UUID]
    trusted_evidence_count: int
    reason: str


class LearningPatternResponse(BaseModel):
    pattern_key: str
    title: str
    category: str
    confidence: float
    support_count: int
    promotion_level: str
    evidence_ids: list[UUID]
    status: str


class LearningScorecardResponse(BaseModel):
    subject_type: str
    subject_id: UUID | None
    score: float
    status: str
    metrics: dict[str, float]
    strengths: list[str]
    improvement_areas: list[str]


class LearningPromotionRequest(BaseModel):
    learning_id: UUID
    target_scope: str = Field(pattern="^(mission|project|organization|global)$")
    dry_run: bool = True


class LearningPromotionResponse(BaseModel):
    accepted: bool
    status: str
    target_scope: str
    reason: str
    required_approvals: list[str]
    reversible: bool
    audit_recorded: bool


class LearningHistoryResponse(BaseModel):
    learning_id: UUID
    mission_id: UUID
    title: str
    status: str
    impact: str
    evidence_ids: list[UUID]
    created_at: datetime


class LearningEvaluateRequest(BaseModel):
    subject_type: str = Field(min_length=2, max_length=80)
    subject_id: UUID | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    evidence_ids: list[UUID] = Field(default_factory=list)


class LearningEvaluateResponse(BaseModel):
    scorecard: LearningScorecardResponse
    learning_recommendations: list[str]
    promotion_allowed: bool
    reason: str
    recorded_observations: int


class CollectiveIntelligenceResponse(BaseModel):
    mission_id: UUID
    reflection_status: str
    what_worked: list[str]
    what_failed: list[str]
    inefficiencies: list[str]
    reusable_lessons: list[dict[str, Any]]
    promotion_candidates: list[dict[str, Any]]
    organization_memory_updates: list[dict[str, Any]]
    training_priorities: list[str]
    future_context: list[str]
    trusted_evidence_count: int


class AgentSkillProfileResponse(BaseModel):
    agent_id: UUID
    name: str
    role: str | None
    status: str
    completed_tasks: int
    failed_tasks: int
    overall_score: float
    skills: dict[str, float]
    strengths: list[str]
    weak_areas: list[str]


class AgentSelectionRequest(BaseModel):
    required_capabilities: list[str] = Field(default_factory=list, max_length=30)
    limit: int = Field(default=10, ge=1, le=50)


class AgentSelectionResponse(BaseModel):
    agent_id: UUID
    name: str
    role: str | None
    score: float
    matched_capabilities: list[str]
    missing_capabilities: list[str]
    reasons: list[str]


class ModelPerformanceResponse(BaseModel):
    task_type: str
    model_key: str
    score: float
    metrics: dict[str, float]
    evidence_count: int
    routing_hint: str


class OrganizationBrainResponse(BaseModel):
    brain_status: str
    project_id: UUID | None
    repository_id: UUID | None
    mission_count: int
    trusted_evidence_count: int
    mission_success_rate: float
    knowledge_candidates: list[dict[str, Any]]
    engineering_standards: list[dict[str, Any]]
    repository_memory: dict[str, Any]
    agent_skill_profiles: list[dict[str, Any]]
    dynamic_scheduling: dict[str, Any]
    cross_agent_review: dict[str, Any]
    knowledge_graph: dict[str, Any]
    ceo_agent: dict[str, Any]
