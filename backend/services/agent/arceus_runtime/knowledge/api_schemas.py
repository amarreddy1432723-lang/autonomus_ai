from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


KnowledgeNodeType = Literal[
    "repository",
    "file",
    "module",
    "class",
    "function",
    "api",
    "database",
    "workflow",
    "decision",
    "incident",
    "policy",
    "standard",
    "infrastructure",
    "documentation",
    "package",
]
KnowledgeConfidence = Literal["verified", "observed", "inferred", "hypothesized"]
KnowledgeRelationship = Literal[
    "CONTAINS",
    "CALLS",
    "IMPLEMENTS",
    "DEPENDS_ON",
    "IMPORTS",
    "USES",
    "DEPLOYS_TO",
    "REVIEWS",
    "GENERATES",
    "VERIFIES",
    "OWNS",
    "AFFECTS",
    "REQUIRES",
    "BLOCKS",
    "REPLACES",
    "SUPERSEDES",
    "LEARNS_FROM",
    "DOCUMENTS",
    "TESTS",
]


class KnowledgeSourceFile(BaseModel):
    path: str = Field(min_length=1, max_length=1_000)
    language: str | None = Field(default=None, max_length=80)
    content: str = Field(default="", max_length=250_000)
    content_hash: str | None = Field(default=None, max_length=160)
    last_modified: datetime | None = None


class KnowledgeNodeResponse(BaseModel):
    node_id: str
    type: KnowledgeNodeType
    name: str
    version: int = 1
    ontology: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    owner: str | None = None
    confidence: KnowledgeConfidence
    evidence: list[str] = Field(default_factory=list)
    created_at: datetime


class KnowledgeEdgeResponse(BaseModel):
    edge_id: str
    source: str
    destination: str
    relationship: KnowledgeRelationship
    confidence: KnowledgeConfidence
    evidence: list[str] = Field(default_factory=list)
    version: int = 1


class KnowledgeIndexRequest(BaseModel):
    repository_id: str = Field(min_length=1, max_length=160)
    repository_name: str = Field(min_length=1, max_length=240)
    repository_url: str | None = Field(default=None, max_length=1_000)
    default_branch: str = Field(default="main", max_length=120)
    files: list[KnowledgeSourceFile] = Field(default_factory=list, max_length=500)
    incremental: bool = True
    previous_graph_hash: str | None = Field(default=None, max_length=160)


class KnowledgeIndexResponse(BaseModel):
    repository_id: str
    repository_name: str
    indexed_at: datetime
    incremental: bool
    graph_hash: str
    node_count: int
    edge_count: int
    ontology_counts: dict[str, int]
    confidence_counts: dict[str, int]
    changed_paths: list[str]
    nodes: list[KnowledgeNodeResponse]
    edges: list[KnowledgeEdgeResponse]
    events: list[str]


class KnowledgeSearchResponse(BaseModel):
    query: str
    strategy: list[str]
    results: list[KnowledgeNodeResponse]
    related_edges: list[KnowledgeEdgeResponse]


class KnowledgeGraphResponse(BaseModel):
    graph_id: str
    graph_hash: str
    nodes: list[KnowledgeNodeResponse]
    edges: list[KnowledgeEdgeResponse]
    generated_at: datetime
    memory_layers: list[str]


class KnowledgeImpactResponse(BaseModel):
    changed_entity: str
    risk_level: str
    affected_nodes: list[KnowledgeNodeResponse]
    affected_edges: list[KnowledgeEdgeResponse]
    verification_plan: list[str]
    migration_notes: list[str]
    confidence: KnowledgeConfidence
