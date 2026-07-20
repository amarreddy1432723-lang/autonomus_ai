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
