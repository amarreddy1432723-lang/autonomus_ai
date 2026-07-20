from __future__ import annotations

from decimal import Decimal
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


RoutingMode = Literal["balanced", "quality_first", "latency_first", "cost_first", "privacy_first"]
Sensitivity = Literal["public", "internal", "restricted", "secret"]


class ModelGatewaySchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class ModelGatewayRequest(ModelGatewaySchema):
    request_id: UUID = Field(default_factory=uuid4)
    mission_id: UUID | None = None
    task_id: UUID | None = None
    task_type: str = Field(default="software_engineering", max_length=160)
    objective: str = Field(min_length=1, max_length=8000)
    prompt: str | None = Field(default=None, max_length=200000)
    required_capabilities: list[str] = Field(default_factory=list, max_length=40)
    required_modalities: list[str] = Field(default_factory=lambda: ["text"], max_length=10)
    required_output_schema: dict[str, Any] | None = None
    sensitivity: Sensitivity = "internal"
    risk_level: str = Field(default="medium", max_length=60)
    routing_mode: RoutingMode = "balanced"
    maximum_input_tokens: int | None = Field(default=None, ge=1)
    maximum_output_tokens: int | None = Field(default=None, ge=1)
    maximum_cost_usd: Decimal | None = Field(default=None, ge=0)
    maximum_latency_ms: int | None = Field(default=None, ge=1)
    required_region: str | None = Field(default=None, max_length=80)
    allowed_provider_keys: list[str] = Field(default_factory=list, max_length=50)
    prohibited_provider_keys: list[str] = Field(default_factory=list, max_length=50)
    deterministic_required: bool = False
    allow_streaming: bool = False
    allow_tool_calling: bool = False
    allow_prompt_caching: bool = True
    dry_run: bool = True
    idempotency_key: str | None = Field(default=None, max_length=255)


class ModelCandidateResponse(ModelGatewaySchema):
    provider_key: str
    model_key: str
    display_name: str
    capabilities: list[str]
    context_window_tokens: int
    maximum_output_tokens: int
    supports_streaming: bool
    supports_tool_calling: bool
    supports_structured_output: bool
    supports_prompt_caching: bool
    data_retention_policy: str
    expected_latency_ms: int
    estimated_cost_usd: Decimal
    score: float
    score_breakdown: dict[str, float]


class ModelRoutingResponse(ModelGatewaySchema):
    request_id: UUID
    selected_provider_key: str | None
    selected_model_key: str | None
    fallback_model_keys: list[str]
    candidates: list[ModelCandidateResponse]
    hard_exclusions: dict[str, list[str]]
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: Decimal
    estimated_latency_ms: int
    reasoning_summary: str
    decision_hash: str
    events: list[str]


class ModelInferenceResponse(ModelGatewaySchema):
    request_id: UUID
    execution_id: UUID | None = None
    provider_key: str | None
    model_key: str | None
    status: Literal["planned", "completed", "failed", "blocked"]
    normalized_output: dict[str, Any] | str
    finish_reason: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    latency_ms: int
    cost_usd: Decimal
    fallback_used: bool
    response_hash: str
    routing: ModelRoutingResponse


class ModelCostEstimateResponse(ModelGatewaySchema):
    request_id: UUID
    estimated_input_tokens: int
    estimated_output_tokens: int
    by_model: list[ModelCandidateResponse]
    cheapest_model_key: str | None
    fastest_model_key: str | None
    highest_quality_model_key: str | None


class ProviderHealthResponse(ModelGatewaySchema):
    provider_key: str
    enabled: bool
    health_status: str
    circuit_state: str
    model_count: int
    available_model_count: int
    readiness: Literal["ready", "degraded", "blocked"]
    reasons: list[str]


class ModelFeedbackRequest(ModelGatewaySchema):
    model_key: str = Field(min_length=1, max_length=160)
    task_type: str = Field(default="general", max_length=160)
    quality_score: float = Field(ge=0, le=1)
    latency_ms: int | None = Field(default=None, ge=0)
    cost_usd: Decimal | None = Field(default=None, ge=0)
    outcome: Literal["success", "failure", "partial"] = "success"
    notes: str | None = Field(default=None, max_length=1000)


class ModelFeedbackResponse(ModelGatewaySchema):
    model_key: str
    task_type: str
    previous_quality_score: float | None
    new_quality_score: float
    event_type: str

