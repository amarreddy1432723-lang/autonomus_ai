from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ArtifactSummaryResponse(BaseModel):
    id: UUID
    mission_id: UUID
    task_id: UUID | None
    artifact_key: str
    artifact_type: str
    title: str
    current_version_id: UUID | None
    trust_status: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version_number: int


class ArtifactVersionResponse(BaseModel):
    id: UUID
    artifact_id: UUID
    version: int
    content_hash: str
    produced_by_member_id: UUID | None
    provenance: dict[str, Any]
    created_at: datetime
    version_number: int


class ArtifactContentResponse(ArtifactVersionResponse):
    content: dict[str, Any]
