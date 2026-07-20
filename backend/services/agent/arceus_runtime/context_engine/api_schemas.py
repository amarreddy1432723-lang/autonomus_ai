from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ContextSource = Literal["mission", "conversation", "repository", "documentation", "memory", "tests", "git", "execution_state", "architecture"]


class Citation(BaseModel):
    source: ContextSource
    file: str | None = None
    symbol: str | None = None
    lines: tuple[int, int] | None = None
    reference_id: str
    confidence: float = Field(ge=0, le=1)


class ContextItem(BaseModel):
    item_id: str
    source: ContextSource
    title: str
    content: str
    score: float = Field(ge=0, le=1)
    estimated_tokens: int
    citation: Citation
    metadata: dict[str, Any] = Field(default_factory=dict)


class IntentAnalysis(BaseModel):
    task_type: str
    requested_files: list[str] = Field(default_factory=list)
    requested_symbols: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    risk_level: str
    expected_output: str
    keywords: list[str] = Field(default_factory=list)


class ModelContextProfile(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_profile: str = "balanced"
    max_context_tokens: int = Field(default=128_000, ge=4_000, le=2_000_000)
    reserve_output_tokens: int = Field(default=8_000, ge=1_000, le=200_000)
    preferred_chunk_tokens: int = Field(default=1_200, ge=200, le=20_000)
    supports_long_context: bool = True


class ContextBuildRequest(BaseModel):
    mission_id: str = Field(min_length=1, max_length=160)
    prompt: str = Field(min_length=1, max_length=20_000)
    repository_id: str | None = Field(default=None, max_length=160)
    root_path: str | None = Field(default=None, max_length=2_000)
    model: ModelContextProfile = Field(default_factory=ModelContextProfile)
    conversation: list[str] = Field(default_factory=list, max_length=50)
    memories: list[str] = Field(default_factory=list, max_length=50)
    git_history: list[str] = Field(default_factory=list, max_length=50)
    execution_state: list[str] = Field(default_factory=list, max_length=50)
    include_sources: list[ContextSource] = Field(default_factory=list)
    force_rebuild: bool = False


class ContextPackage(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    package_id: str
    mission_id: str
    prompt: str
    items: list[ContextItem]
    citations: list[Citation]
    estimated_tokens: int
    confidence: float = Field(ge=0, le=1)
    model_profile: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    generated_at: datetime


class ContextBuildResponse(BaseModel):
    intent: IntentAnalysis
    package: ContextPackage
    cache_hit: bool


class ContextExpandRequest(BaseModel):
    package_id: str = Field(min_length=1, max_length=160)
    query: str = Field(min_length=1, max_length=500)
    additional_tokens: int = Field(default=4_000, ge=500, le=100_000)


class ContextRankRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    candidates: list[ContextItem] = Field(min_length=1, max_length=200)
    model: ModelContextProfile = Field(default_factory=ModelContextProfile)


class ContextRankResponse(BaseModel):
    intent: IntentAnalysis
    ranked: list[ContextItem]


class ContextCacheEntry(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    package_id: str
    mission_id: str
    model_profile: str
    repository_id: str | None = None
    graph_hash: str | None = None
    estimated_tokens: int
    confidence: float
    generated_at: datetime
