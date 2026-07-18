from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class ApprovalVoteRequest(BaseModel):
    expected_mission_version: int = Field(ge=1)
    subject_hash: str = Field(min_length=1, max_length=128)
    rationale: str = Field(default="", max_length=2_000)


class ApprovalVoteResponse(BaseModel):
    approval_id: UUID
    mission_id: UUID
    status: str
    mission_status: str
    mission_version: int
    vote: str


class ApprovalSummaryResponse(BaseModel):
    id: UUID
    mission_id: UUID
    approval_type: str
    subject_type: str
    subject_hash: str
    proposed_action: str
    risk_level: str
    status: str
    required_human_votes: int
    human_approvals: int
    expires_at: datetime | None
    created_at: datetime


class ApprovalDetailResponse(ApprovalSummaryResponse):
    quorum_policy: dict
    votes: list[dict]
