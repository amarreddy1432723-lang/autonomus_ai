from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class ComputePlanRequest(BaseModel):
    mission_id: UUID | None = None
    task_id: UUID | None = None
    workload_type: str = Field(default="software_engineering", min_length=2, max_length=120)
    objective: str = Field(min_length=5, max_length=4_000)
    required_capabilities: list[str] = Field(default_factory=list)
    modalities: list[str] = Field(default_factory=lambda: ["text"])
    sensitivity: Literal["public", "internal", "confidential", "restricted", "secret"] = "internal"
    routing_mode: Literal["balanced", "quality_first", "latency_first", "cost_first", "privacy_first"] = "balanced"
    maximum_cost_usd: Decimal | None = None
    maximum_latency_ms: int | None = Field(default=None, ge=1)
    maximum_context_tokens: int | None = Field(default=None, ge=1)
    required_region: str | None = None
    allow_speculation: bool = False
    allow_ensemble: bool = False
    cache_policy: Literal["prefer_cache", "bypass_cache", "write_through"] = "prefer_cache"


class ComputeResourceResponse(BaseModel):
    resource_id: str
    provider_key: str
    model_key: str
    environment: str
    capabilities: list[str]
    modalities: list[str]
    latency_ms: int
    throughput_score: float
    context_limit: int
    estimated_cost_per_1k_tokens: Decimal
    availability: float
    privacy_tier: str
    status: str


class ComputePlanResponse(BaseModel):
    plan_id: str
    workload_type: str
    selected_resource: dict[str, Any] | None
    fallback_resources: list[dict[str, Any]]
    stages: list[dict[str, Any]]
    context_distribution: list[dict[str, Any]]
    cache: dict[str, Any]
    speculation: dict[str, Any]
    ensemble: dict[str, Any]
    estimated_cost_usd: Decimal
    estimated_latency_ms: int
    candidate_scores: dict[str, float]
    hard_exclusions: dict[str, list[str]]
    reasoning_summary: str
    events: list[str]


class ComputeInferRequest(ComputePlanRequest):
    prompt_hash: str | None = Field(default=None, max_length=160)
    dry_run: bool = True


class ComputeInferResponse(BaseModel):
    accepted: bool
    dry_run: bool
    execution_plan: ComputePlanResponse
    provider_execution: dict[str, Any]
    governance: dict[str, Any]


class ComputeCostResponse(BaseModel):
    estimated_monthly_cost_usd: Decimal
    estimated_cache_savings_usd: Decimal
    cost_by_provider: dict[str, Decimal]
    optimization_recommendations: list[str]


class ComputeCacheResponse(BaseModel):
    enabled: bool
    cache_policy: str
    cacheable_items: list[str]
    invalidation_rules: list[str]
    estimated_lookup_ms: int


class ComputeScheduleResponse(BaseModel):
    accepted: bool
    plan: ComputePlanResponse
    required_events: list[str]
    audit_recorded: bool
