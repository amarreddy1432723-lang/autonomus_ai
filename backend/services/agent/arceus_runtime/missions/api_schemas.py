from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class MissionBudgetRequest(BaseModel):
    currency: str = Field(default="USD", min_length=3, max_length=3)
    maximum_amount: Decimal | None = Field(default=None, ge=0)


class CreateMissionRequest(BaseModel):
    project_id: UUID
    title: str | None = Field(default=None, max_length=300)
    objective: str = Field(min_length=10, max_length=20_000)
    repository_ids: list[UUID] = Field(min_length=1, max_length=10)
    constraints: list[str] = Field(default_factory=list, max_length=100)
    desired_outcomes: list[str] = Field(default_factory=list, max_length=100)
    priority: int = Field(default=50, ge=0, le=100)
    budget: MissionBudgetRequest = Field(default_factory=MissionBudgetRequest)

    @field_validator("constraints", "desired_outcomes")
    @classmethod
    def validate_non_empty_items(cls, values: list[str]) -> list[str]:
        cleaned = [value.strip() for value in values]
        if any(not value for value in cleaned):
            raise ValueError("List entries must not be empty.")
        return cleaned


class MissionTransitionRequest(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=2_000)


class MissionSummaryResponse(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    objective: str
    status: str
    risk_level: str
    priority: int
    current_version: int
    maximum_budget_amount: Decimal | None
    actual_cost_amount: Decimal
    created_at: datetime
    updated_at: datetime
    version_number: int


class MissionEventResponse(BaseModel):
    id: UUID
    event_type: str
    aggregate_version: int
    payload: dict
    occurred_at: datetime


class MissionProgressResponse(BaseModel):
    percent: int
    status: str


class MissionDetailResponse(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    objective: str
    status: str
    risk_level: str
    priority: int
    current_version: int
    progress: MissionProgressResponse
    latest_events: list[MissionEventResponse]
    maximum_budget_amount: Decimal | None
    actual_cost_amount: Decimal
    created_at: datetime
    updated_at: datetime
    version_number: int


class MissionOperationResponse(BaseModel):
    mission_id: UUID
    status: str
    previous_status: str
    version_number: int
    operation_id: UUID


class MissionClarificationResponse(BaseModel):
    id: UUID
    question: str
    impact_level: str
    status: str
    assumption: str | None = None
    answer: str | None = None


class MissionClarificationAnswer(BaseModel):
    unknown_id: UUID
    answer: str = Field(min_length=1, max_length=4_000)


class SubmitClarificationsRequest(BaseModel):
    expected_version: int = Field(ge=1)
    answers: list[MissionClarificationAnswer] = Field(min_length=1, max_length=50)
