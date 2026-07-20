from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


RepositoryType = Literal["application", "library", "monorepo", "service"]
SymbolKind = Literal[
    "class",
    "interface",
    "function",
    "method",
    "variable",
    "enum",
    "namespace",
    "module",
    "type_alias",
    "decorator",
]
RelationshipKind = Literal["imports", "exports", "calls", "references", "implements", "extends", "uses", "owns", "tests", "depends_on"]


class RepositoryIndexRequest(BaseModel):
    root_path: str = Field(min_length=1, max_length=2_000)
    repository_id: str | None = Field(default=None, max_length=160)
    max_files: int = Field(default=2_000, ge=1, le=20_000)
    max_file_bytes: int = Field(default=250_000, ge=1_000, le=1_000_000)


class RepositoryQueryRequest(BaseModel):
    repository_id: str | None = Field(default=None, max_length=160)
    root_path: str | None = Field(default=None, max_length=2_000)


class LanguageSummary(BaseModel):
    language: str
    file_count: int
    bytes: int
    percentage: float


class FrameworkSummary(BaseModel):
    name: str
    confidence: float = Field(ge=0, le=1)
    evidence: list[str] = Field(default_factory=list)


class PackageManagerSummary(BaseModel):
    name: str
    files: list[str] = Field(default_factory=list)


class BuildSystemSummary(BaseModel):
    name: str
    files: list[str] = Field(default_factory=list)


class RepositoryProfile(BaseModel):
    id: str
    root: str
    name: str
    git_repository: bool
    default_branch: str | None = None
    languages: list[LanguageSummary]
    frameworks: list[FrameworkSummary]
    package_managers: list[PackageManagerSummary]
    build_systems: list[BuildSystemSummary]
    repository_type: RepositoryType
    estimated_size: int
    indexed_file_count: int
    skipped_file_count: int
    generated_at: datetime
    graph_hash: str


class RepositoryFile(BaseModel):
    path: str
    language: str
    kind: str
    bytes: int
    content_hash: str
    imports: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)


class RepositorySymbol(BaseModel):
    id: str
    name: str
    kind: SymbolKind
    file: str
    range: dict[str, int]
    signature: str
    visibility: str = "unknown"
    documentation: str | None = None


class RepositoryRelationship(BaseModel):
    id: str
    source: str
    target: str
    kind: RelationshipKind
    file: str | None = None
    evidence: list[str] = Field(default_factory=list)


class RepositoryTestMapping(BaseModel):
    test_path: str
    target_paths: list[str] = Field(default_factory=list)
    test_kind: str
    confidence: float = Field(ge=0, le=1)


class RepositoryArchitectureReport(BaseModel):
    style: str
    confidence: float = Field(ge=0, le=1)
    signals: list[str] = Field(default_factory=list)
    modules: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class RepositoryIndexResponse(BaseModel):
    profile: RepositoryProfile
    files: list[RepositoryFile]
    symbols: list[RepositorySymbol]
    relationships: list[RepositoryRelationship]
    tests: list[RepositoryTestMapping]
    documentation_paths: list[str]
    configuration_paths: list[str]
    architecture: RepositoryArchitectureReport


class RepositorySearchResponse(BaseModel):
    repository_id: str
    query: str
    results: list[dict[str, Any]]


class RepositoryDependencyResponse(BaseModel):
    repository_id: str
    relationships: list[RepositoryRelationship]
    cycles: list[list[str]] = Field(default_factory=list)
