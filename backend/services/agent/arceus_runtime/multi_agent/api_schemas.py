from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AgentCapability(BaseModel):
    capability_key: str = Field(min_length=1, max_length=160)
    category: str = Field(default="engineering", max_length=120)
    confidence: float = Field(default=0.75, ge=0, le=1)
    version: str = Field(default="1.0.0", max_length=40)


class RegisterAgentRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    name: str = Field(min_length=1, max_length=240)
    role: str = Field(min_length=1, max_length=120)
    participant_type: str = Field(default="ai_specialist", max_length=80)
    organization_id: UUID | None = None
    organization_member_id: UUID | None = None
    specialist_profile_id: UUID | None = None
    capabilities: list[AgentCapability] = Field(default_factory=list, max_length=50)
    model_profile: str = Field(default="balanced", max_length=120)
    version: str = Field(default="1.0.0", max_length=40)
    authorities: list[str] = Field(default_factory=list, max_length=50)
    active_mission_ids: list[UUID] = Field(default_factory=list, max_length=20)


class AgentResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: UUID
    organization_id: UUID | None = None
    organization_member_id: UUID | None = None
    specialist_profile_id: UUID | None = None
    name: str
    role: str | None = None
    participant_type: str
    capabilities: list[dict[str, Any]]
    model_profile: str
    version: str
    status: str
    authorities: list[str]
    active_mission_ids: list[str]
    created_at: datetime
    updated_at: datetime
    version_number: int


class AgentHeartbeatRequest(BaseModel):
    status: str = Field(default="available", max_length=60)
    cpu: float | None = Field(default=None, ge=0, le=100)
    memory: float | None = Field(default=None, ge=0, le=100)
    tasks_running: int = Field(default=0, ge=0, le=10_000)
    latency_ms: float | None = Field(default=None, ge=0)
    health_payload: dict[str, Any] = Field(default_factory=dict)


class AgentStatusResponse(BaseModel):
    agent_id: UUID
    status: str
    version_number: int


class AgentMetricsResponse(BaseModel):
    agent_id: UUID
    metrics: dict[str, float]
    observation_count: int
    reputation_score: float


class AssignTaskRequest(BaseModel):
    task_id: UUID
    required_capabilities: list[str] = Field(default_factory=list, max_length=30)
    excluded_agent_ids: list[UUID] = Field(default_factory=list, max_length=30)
    prefer_same_organization: bool = True
    assign: bool = True


class AgentCandidateScore(BaseModel):
    agent_id: UUID
    name: str
    role: str | None
    score: float
    matched_capabilities: list[str]
    missing_capabilities: list[str]
    status: str
    active_task_count: int
    reasons: list[str]


class AssignTaskResponse(BaseModel):
    task_id: UUID
    selected_agent: AgentCandidateScore | None
    candidates: list[AgentCandidateScore]
    assigned: bool


class SendAgentMessageRequest(BaseModel):
    mission_id: UUID
    sender_agent_id: UUID
    receiver_agent_ids: list[UUID] = Field(default_factory=list, max_length=50)
    message_type: str = Field(default="status_update", max_length=80)
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=6_000)
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    task_id: UUID | None = None
    topic_keys: list[str] = Field(default_factory=list, max_length=20)
    priority: str = Field(default="normal", max_length=40)
    confidentiality: str = Field(default="mission", max_length=60)


class AgentMessageResponse(BaseModel):
    id: UUID
    mission_id: UUID
    sender_agent_id: UUID
    receiver_agent_ids: list[UUID]
    message_type: str
    subject: str
    priority: str
    created_at: datetime
