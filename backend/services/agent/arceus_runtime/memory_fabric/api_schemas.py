from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class MemoryStoreRequest(BaseModel):
    memory_type: str | None = Field(default=None, max_length=80)
    memory_scope: str = Field(default="project", max_length=80)
    scope_reference_id: UUID | None = None
    owner_id: UUID | None = None
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=12000)
    source_type: str = Field(default="manual", max_length=80)
    source_ids: list[str] = Field(default_factory=list, max_length=100)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    relationships: list[dict[str, Any]] = Field(default_factory=list, max_length=200)
    tags: list[str] = Field(default_factory=list, max_length=50)
    importance: str | None = Field(default=None, max_length=80)
    confidence: float | None = Field(default=None, ge=0, le=1)
    sensitivity: str = Field(default="mission", max_length=80)
    retention_policy: str = Field(default="standard", max_length=120)
    expires_at: datetime | None = None


class MemoryItemResponse(BaseModel):
    id: UUID
    memory_type: str
    memory_scope: str
    scope_reference_id: UUID | None
    owner_id: UUID | None
    title: str
    summary: str
    content: str
    importance: str
    lifecycle_stage: str
    lifecycle_status: str
    trust_level: str
    confidence: float | None
    sensitivity: str
    provenance: dict[str, Any]
    relationships: list[dict[str, Any]]
    tags: list[str]
    retention_policy: str
    content_hash: str
    created_at: datetime
    valid_until: datetime | None


class MemorySearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=1000)
    memory_types: list[str] = Field(default_factory=list, max_length=20)
    memory_scopes: list[str] = Field(default_factory=list, max_length=20)
    scope_reference_id: UUID | None = None
    mission_context: dict[str, Any] = Field(default_factory=dict)
    include_archived: bool = False
    authorized_sensitivities: list[str] = Field(default_factory=lambda: ["public", "mission", "project", "organization"], max_length=20)
    limit: int = Field(default=10, ge=1, le=100)


class MemoryRecallResult(BaseModel):
    memory: MemoryItemResponse
    relevance_score: float
    ranking_factors: dict[str, Any]
    explanation: str


class MemorySearchResponse(BaseModel):
    query: str
    strategy: list[str]
    results: list[MemoryRecallResult]
    context_budget: dict[str, Any]
    events: list[str]


class MemorySummarizeRequest(BaseModel):
    memory_ids: list[UUID] = Field(default_factory=list, max_length=100)
    query: str | None = Field(default=None, max_length=1000)
    target_scope: str = Field(default="organization", max_length=80)
    summary_title: str | None = Field(default=None, max_length=240)
    preserve_evidence: bool = True


class MemorySummarizeResponse(BaseModel):
    summary_memory: MemoryItemResponse | None
    source_memory_ids: list[UUID]
    summary: str
    themes: list[str]
    patterns: list[str]
    evidence_ids: list[str]
    events: list[str]


class MemoryArchiveRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=1000)
    retain_evidence: bool = True


class MemoryLifecycleResponse(BaseModel):
    memory_id: UUID
    action: str
    lifecycle_status: str
    event_type: str
    audit_recorded: bool


class MemoryFact(BaseModel):
    subject: str
    relation: str
    object: str
    confidence: float = Field(ge=0, le=1)
    source_quote: str


class MemoryExtractRequest(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=20000)
    source_type: str = Field(default="mission", max_length=80)
    source_ids: list[str] = Field(default_factory=list, max_length=100)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    memory_scope: str = Field(default="project", max_length=80)
    scope_reference_id: UUID | None = None
    store: bool = True


class MemoryExtractResponse(BaseModel):
    facts: list[MemoryFact]
    entities: list[dict[str, Any]]
    relationships: list[dict[str, Any]]
    stored_memory: MemoryItemResponse | None
    events: list[str]


class MemoryFeedbackRequest(BaseModel):
    rating: str = Field(pattern="^(correct|incorrect|outdated|incomplete)$")
    comment: str | None = Field(default=None, max_length=1000)
    confidence_delta: float | None = Field(default=None, ge=-1, le=1)


class MemoryFeedbackResponse(BaseModel):
    memory_id: UUID
    rating: str
    previous_confidence: float | None
    new_confidence: float | None
    lifecycle_status: str
    event_type: str


class MemoryConflictResponse(BaseModel):
    conflict_key: str
    title: str
    memory_ids: list[UUID]
    reason: str
    suggested_winner_id: UUID | None
    resolution_strategy: str


class MemoryGraphProjectionResponse(BaseModel):
    memory_id: UUID
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    graph_hash: str


class MemoryRetentionPolicyResponse(BaseModel):
    memory_type: str
    default_scope: str
    default_retention: str
    deletion_policy: str
    sensitivity: str
