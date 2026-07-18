from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class CreateWorkspaceRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2_000)
    settings: dict[str, Any] = Field(default_factory=dict)

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Workspace name is required.")
        return cleaned


class WorkspaceResponse(BaseModel):
    id: UUID
    name: str
    slug: str
    description: str | None
    status: str
    settings: dict[str, Any]
    repository_count: int
    mission_count: int
    active_mission_count: int
    created_at: datetime
    updated_at: datetime
    version_number: int


class AddWorkspaceRepositoryRequest(BaseModel):
    provider: str = Field(default="local", pattern="^(github|gitlab|bitbucket|local)$")
    repository_url: str = Field(min_length=1, max_length=2_000)
    default_branch: str = Field(default="main", min_length=1, max_length=200)
    local_workspace_path: str | None = Field(default=None, max_length=2_000)
    external_repository_id: str | None = Field(default=None, max_length=500)
    metadata_json: dict[str, Any] = Field(default_factory=dict)


class WorkspaceRepositoryResponse(BaseModel):
    id: UUID
    project_id: UUID
    provider: str
    repository_url: str
    default_branch: str
    local_workspace_path: str | None
    status: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version_number: int


class WorkspaceActivityResponse(BaseModel):
    id: UUID
    mission_id: UUID
    sequence: int
    event_type: str
    payload: dict[str, Any]
    occurred_at: datetime


class WorkspaceOrganizationResponse(BaseModel):
    workspace_id: UUID
    mission_count: int
    organization_count: int
    active_specialists: int
    roles: list[dict[str, Any]]


class WorkspaceKnowledgeResponse(BaseModel):
    workspace_id: UUID
    mission_count: int
    decision_count: int
    evidence_count: int
    artifact_count: int
    current_decision_count: int
    trusted_evidence_count: int
