from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class CapabilityResponse(BaseModel):
    id: UUID
    capability_key: str
    domain: str
    name: str
    description: str
    verification_methods: list[Any]
    active: bool
    created_at: datetime
    updated_at: datetime
    version_number: int


class MissionRequiredCapabilityResponse(BaseModel):
    id: UUID
    mission_id: UUID
    capability_id: UUID
    reason: str
    required_level: str
    capability: CapabilityResponse | None
    created_at: datetime
    updated_at: datetime
    version_number: int


class SpecialistCapabilityResponse(BaseModel):
    id: UUID
    specialist_profile_id: UUID
    capability_id: UUID
    proficiency: float
    evidence: dict[str, Any]
    capability: CapabilityResponse | None
    created_at: datetime
    updated_at: datetime
    version_number: int
