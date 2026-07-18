from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class PlanMissionRequest(BaseModel):
    expected_version: int = Field(ge=1)


class PlanMissionResponse(BaseModel):
    mission_id: UUID
    organization_id: UUID
    workflow_id: UUID
    plan_artifact_id: UUID
    approval_id: UUID
    status: str
    organization_size: int
    task_count: int
    graph_hash: str
    critical_path: list[str]
    capability_gaps: list[str]
    metrics: dict


class WorkflowGraphNodeResponse(BaseModel):
    id: UUID
    node_key: str
    node_type: str
    title: str
    owner_role_key: str | None = None
    status: str | None = None
    estimates: dict = Field(default_factory=dict)
    config: dict = Field(default_factory=dict)


class WorkflowGraphEdgeResponse(BaseModel):
    id: UUID
    source_node_id: UUID
    target_node_id: UUID
    condition: dict = Field(default_factory=dict)


class WorkflowGraphResponse(BaseModel):
    workflow_id: UUID
    mission_id: UUID
    status: str
    graph_hash: str
    workflow_version: int
    selected_proposal: str | None = None
    metrics: dict = Field(default_factory=dict)
    nodes: list[WorkflowGraphNodeResponse]
    edges: list[WorkflowGraphEdgeResponse]
