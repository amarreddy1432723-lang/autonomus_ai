from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


InteractionMode = Literal["chat", "voice", "command", "visual", "code", "diagram", "document", "image", "video", "terminal", "workflow"]
IntentCategory = Literal[
    "information",
    "planning",
    "execution",
    "review",
    "analysis",
    "automation",
    "investigation",
    "learning",
    "configuration",
    "conversation",
]
ContextScope = Literal["personal", "mission", "project", "organization", "global"]


class UnifiedContextResponse(BaseModel):
    active_workspace: dict[str, Any]
    current_mission: dict[str, Any] | None
    repository: dict[str, Any] | None
    organization: dict[str, Any] | None
    open_decisions: list[dict[str, Any]]
    reviews: list[dict[str, Any]]
    memory: dict[str, Any]
    policies: list[str]


class PersonalWorkspaceResponse(BaseModel):
    workspace_id: str
    owner_id: str
    organizations: list[dict[str, Any]]
    repositories: list[dict[str, Any]]
    dashboards: list[dict[str, Any]]
    preferences: dict[str, Any]
    memory: dict[str, Any]
    settings: dict[str, Any]
    context: UnifiedContextResponse
    synced_at: datetime


class IntentRequest(BaseModel):
    objective: str = Field(min_length=1, max_length=2_000)
    mode: InteractionMode = "chat"
    context_scope: ContextScope = "mission"
    entities: dict[str, Any] = Field(default_factory=dict)
    constraints: list[str] = Field(default_factory=list, max_length=40)


class IntentResponse(BaseModel):
    intent_id: str
    objective: str
    category: IntentCategory
    entities: dict[str, Any]
    confidence: float = Field(ge=0, le=1)
    constraints: list[str]
    context: dict[str, Any]
    permissions: list[str]
    suggested_action: str
    explainability: dict[str, Any]


class IntentExecutionResponse(BaseModel):
    intent: IntentResponse
    accepted: bool
    status: str
    mission_thread: dict[str, Any]
    verification: dict[str, Any]
    response: dict[str, Any]
    events: list[str]


class TimelineItemResponse(BaseModel):
    item_id: str
    occurred_at: datetime
    event_type: str
    title: str
    summary: str
    related_mission_id: str | None = None
    priority: str = "normal"
    required_action: str | None = None


class DashboardWidgetResponse(BaseModel):
    widget_key: str
    title: str
    value: str
    status: str
    action: str | None = None


class DashboardResponse(BaseModel):
    dashboard_id: str
    role: str
    generated_at: datetime
    widgets: list[DashboardWidgetResponse]
    notifications: list[dict[str, Any]]
    accessibility: dict[str, Any]
    localization: dict[str, Any]


class VoiceRequest(BaseModel):
    transcript: str = Field(min_length=1, max_length=2_000)
    locale: str = Field(default="en-US", max_length=20)
    device: str = Field(default="desktop", max_length=80)
    context_scope: ContextScope = "mission"


class VoiceResponse(BaseModel):
    transcript: str
    intent: IntentResponse
    spoken_response: str
    command_safe_to_execute: bool
    requires_confirmation: bool


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    scopes: list[str] = Field(default_factory=lambda: ["missions", "knowledge", "decisions", "incidents", "code"], max_length=20)
    limit: int = Field(default=10, ge=1, le=50)


class SearchResultResponse(BaseModel):
    result_id: str
    title: str
    scope: str
    summary: str
    relevance: float
    related_intent: IntentCategory
    action: str


class SearchResponse(BaseModel):
    query: str
    scopes: list[str]
    strategy: list[str]
    results: list[SearchResultResponse]
    completed_at: datetime
