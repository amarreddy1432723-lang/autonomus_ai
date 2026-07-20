from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class ResearchProjectRequest(BaseModel):
    title: str = Field(min_length=3, max_length=240)
    objective: str = Field(min_length=5, max_length=4000)
    domain: str = Field(default="software_engineering", max_length=120)
    observations: list[str] = Field(default_factory=list, max_length=50)
    research_questions: list[str] = Field(default_factory=list, max_length=50)
    constraints: list[str] = Field(default_factory=list, max_length=50)
    success_metrics: list[str] = Field(default_factory=list, max_length=50)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)


class ResearchProjectResponse(BaseModel):
    research_id: UUID | str
    title: str
    objective: str
    domain: str
    status: str
    research_organization: list[dict[str, Any]]
    research_questions: list[str]
    initial_hypotheses: list[dict[str, Any]]
    confidence: float
    uncertainty: dict[str, Any]
    events: list[str]
    created_at: datetime


class HypothesisRequest(BaseModel):
    research_id: UUID | None = None
    observation: str = Field(min_length=5, max_length=4000)
    research_goal: str = Field(min_length=5, max_length=4000)
    domain: str = Field(default="software_engineering", max_length=120)
    competing_count: int = Field(default=3, ge=1, le=5)
    constraints: list[str] = Field(default_factory=list, max_length=50)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)


class HypothesisResponse(BaseModel):
    hypothesis_id: UUID | str
    research_id: UUID | None
    hypotheses: list[dict[str, Any]]
    selected_for_experiment: list[str]
    uncertainty: dict[str, Any]
    events: list[str]


class ExperimentRequest(BaseModel):
    research_id: UUID | None = None
    hypothesis_id: UUID | str | None = None
    hypothesis: str = Field(min_length=5, max_length=4000)
    objective: str = Field(min_length=5, max_length=4000)
    variables: list[str] = Field(default_factory=list, max_length=50)
    controls: list[str] = Field(default_factory=list, max_length=50)
    datasets: list[str] = Field(default_factory=list, max_length=50)
    metrics: list[str] = Field(default_factory=list, max_length=50)
    ethical_constraints: list[str] = Field(default_factory=list, max_length=50)
    simulation_type: str | None = Field(default=None, max_length=120)


class ExperimentResponse(BaseModel):
    experiment_id: UUID | str
    research_id: UUID | None
    hypothesis_id: UUID | str | None
    design: dict[str, Any]
    reproducibility: dict[str, Any]
    statistical_plan: dict[str, Any]
    status: str
    events: list[str]


class FindingResponse(BaseModel):
    finding_id: str
    title: str
    confidence: float
    conclusion_strength: str
    evidence_score: dict[str, Any]
    known_facts: list[str]
    probable_findings: list[str]
    uncertain_areas: list[str]
    unknown_questions: list[str]
    linked_items: list[str]


class PublicationRequest(BaseModel):
    research_id: UUID | None = None
    title: str = Field(min_length=3, max_length=240)
    audience: str = Field(default="internal", max_length=120)
    findings: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    publication_type: str = Field(default="internal_report", max_length=120)
    require_human_review: bool = True


class PublicationResponse(BaseModel):
    publication_id: UUID | str
    title: str
    publication_type: str
    status: str
    report: dict[str, Any]
    review_workflow: list[dict[str, Any]]
    events: list[str]


class InnovationResponse(BaseModel):
    innovation_id: str
    title: str
    version: int
    innovation_type: str
    scores: dict[str, float]
    priority_score: float
    confidence: float
    supporting_evidence: list[str]
    linked_research: list[str]
    status: str
