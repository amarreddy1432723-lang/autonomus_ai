from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class GraphProvenance(BaseModel):
    source: str = Field(min_length=1, max_length=160)
    connector: str = Field(default="manual", min_length=1, max_length=120)
    observed_at: datetime | None = None
    confidence: float = Field(default=0.7, ge=0, le=1)
    source_version: str | None = Field(default=None, max_length=160)


class GraphEntityInput(BaseModel):
    entity_type: str = Field(min_length=2, max_length=120)
    canonical_name: str = Field(min_length=1, max_length=240)
    aliases: list[str] = Field(default_factory=list)
    attributes: dict[str, Any] = Field(default_factory=dict)
    provenance: list[GraphProvenance] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class GraphRelationshipInput(BaseModel):
    source_key: str = Field(min_length=1, max_length=240)
    destination_key: str = Field(min_length=1, max_length=240)
    relationship_type: str = Field(min_length=2, max_length=120)
    attributes: dict[str, Any] = Field(default_factory=dict)
    provenance: list[GraphProvenance] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0, le=1)


class GraphSyncRequest(BaseModel):
    connector: str = Field(min_length=1, max_length=120)
    source_system: str = Field(min_length=1, max_length=160)
    entities: list[GraphEntityInput] = Field(default_factory=list, max_length=1000)
    relationships: list[GraphRelationshipInput] = Field(default_factory=list, max_length=2000)
    incremental: bool = True


class GraphEntityResponse(BaseModel):
    entity_id: str
    entity_type: str
    canonical_name: str
    aliases: list[str]
    attributes: dict[str, Any]
    version: int
    provenance: list[dict[str, Any]]
    confidence: float
    layer: str


class GraphRelationshipResponse(BaseModel):
    relationship_id: str
    source_id: str
    destination_id: str
    relationship_type: str
    attributes: dict[str, Any]
    version: int
    provenance: list[dict[str, Any]]
    confidence: float


class GraphSyncResponse(BaseModel):
    graph_hash: str
    synced_at: datetime
    connector: str
    source_system: str
    entity_count: int
    relationship_count: int
    resolved_entities: list[GraphEntityResponse]
    relationships: list[GraphRelationshipResponse]
    diff: dict[str, Any]
    consistency: dict[str, Any]
    events: list[str]


class GraphQueryRequest(BaseModel):
    start_entity: str | None = Field(default=None, max_length=240)
    relationship_types: list[str] = Field(default_factory=list)
    max_depth: int = Field(default=2, ge=1, le=5)
    include_low_confidence: bool = False


class GraphQueryResponse(BaseModel):
    query: dict[str, Any]
    entities: list[GraphEntityResponse]
    relationships: list[GraphRelationshipResponse]
    reasoning: dict[str, Any]


class GraphSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    entity_types: list[str] = Field(default_factory=list)
    limit: int = Field(default=10, ge=1, le=100)


class GraphSearchResponse(BaseModel):
    query: str
    strategy: list[str]
    results: list[GraphEntityResponse]
    related_relationships: list[GraphRelationshipResponse]


class GraphHistoryResponse(BaseModel):
    entity_id: str | None
    timeline: list[dict[str, Any]]
    current_version: int | None
    provenance_summary: dict[str, Any]
