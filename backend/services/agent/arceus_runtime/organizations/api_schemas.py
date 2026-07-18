from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class SpecialistProfileResponse(BaseModel):
    id: UUID
    specialist_key: str
    display_name: str
    specialist_type: str
    authority_profile: dict[str, Any]
    default_model_policy: dict[str, Any]
    active: bool


class OrganizationMemberResponse(BaseModel):
    id: UUID
    organization_id: UUID
    specialist_profile_id: UUID
    participant_user_id: UUID | None
    role_key: str
    responsibility: str
    authority: dict[str, Any]
    can_implement: bool
    can_review: bool
    can_approve: bool
    status: str
    specialist_profile: SpecialistProfileResponse | None
    created_at: datetime
    updated_at: datetime
    version_number: int


class OrganizationResponse(BaseModel):
    id: UUID
    mission_id: UUID
    organization_name: str
    status: str
    rationale: str
    budget_policy: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version_number: int


class OrganizationDetailResponse(OrganizationResponse):
    members: list[OrganizationMemberResponse]
