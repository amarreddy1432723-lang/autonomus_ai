from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class GatewaySchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class ExecutionKind(StrEnum):
    MODEL = "model"
    TOOL = "tool"
    RETRIEVAL = "retrieval"


class ModelProfileRequest(GatewaySchema):
    model_key: str
    provider_key: str
    provider_model_name: str
    display_name: str
    status: str = "available"
    capabilities: list[str] = Field(default_factory=list)
    supported_modalities: list[str] = Field(default_factory=lambda: ["text"])
    supported_output_modes: list[str] = Field(default_factory=lambda: ["text"])
    context_window_tokens: int = Field(default=128000, ge=1)
    maximum_output_tokens: int = Field(default=8192, ge=1)
    supports_tool_calling: bool = False
    supports_structured_output: bool = False
    supports_streaming: bool = False
    supports_seed: bool = False
    supports_prompt_caching: bool = False
    data_residency_regions: list[str] = Field(default_factory=lambda: ["global"])
    data_retention_policy: str = "standard"
    input_cost_per_million_tokens: Decimal = Decimal("1.00")
    output_cost_per_million_tokens: Decimal = Decimal("5.00")
    cached_input_cost_per_million_tokens: Decimal | None = None
    expected_latency_class: str = "medium"
    reliability_score: float = Field(default=0.9, ge=0, le=1)
    quality_scores: dict[str, float] = Field(default_factory=dict)


class ModelProfileResponse(ModelProfileRequest):
    id: UUID
    version: int
    created_at: datetime
    updated_at: datetime


class ProviderProfileRequest(GatewaySchema):
    provider_key: str
    display_name: str
    adapter_type: str
    enabled: bool = True
    supported_regions: list[str] = Field(default_factory=lambda: ["global"])
    authentication_reference: str = "env"
    requests_per_minute: int | None = None
    tokens_per_minute: int | None = None
    concurrent_request_limit: int | None = None
    health_status: str = "healthy"
    circuit_state: str = "closed"
    retention_policy: str = "standard"
    supports_zero_retention: bool = False
    enterprise_agreement_required: bool = False


class ProviderProfileResponse(ProviderProfileRequest):
    id: UUID
    version: int
    created_at: datetime
    updated_at: datetime


class ToolProfileRequest(GatewaySchema):
    tool_key: str
    display_name: str
    adapter_type: str
    version: str = "1"
    capabilities: list[str] = Field(default_factory=list)
    supported_actions: list[str] = Field(default_factory=list)
    risk_level: str = "low"
    side_effect_class: str = "READ_ONLY"
    requires_sandbox: bool = True
    supports_dry_run: bool = False
    supports_idempotency: bool = True
    supports_rollback: bool = False
    required_authorities: list[str] = Field(default_factory=list)
    allowed_environments: list[str] = Field(default_factory=lambda: ["local"])
    maximum_runtime_seconds: int = Field(default=120, ge=1, le=86400)
    output_schema_key: str | None = None
    enabled: bool = True


class ToolProfileResponse(ToolProfileRequest):
    id: UUID
    created_at: datetime
    updated_at: datetime


class AIExecutionRequest(GatewaySchema):
    request_id: UUID = Field(default_factory=uuid4)
    tenant_id: UUID | None = None
    mission_id: UUID
    task_id: UUID | None = None
    execution_kind: ExecutionKind = ExecutionKind.MODEL
    task_type: str
    objective: str
    required_capabilities: list[str] = Field(default_factory=list)
    required_output_schema: dict[str, Any] | None = None
    context_package_id: UUID | None = None
    sensitivity: str = "internal"
    risk_level: str = "medium"
    maximum_input_tokens: int | None = None
    maximum_output_tokens: int | None = None
    maximum_cost_usd: Decimal | None = None
    maximum_latency_ms: int | None = None
    required_region: str | None = None
    allowed_provider_keys: list[str] = Field(default_factory=list)
    prohibited_provider_keys: list[str] = Field(default_factory=list)
    deterministic_required: bool = False
    human_visible: bool = False
    idempotency_key: str
    routing_mode: str = "balanced"


class RoutingDecisionResponse(GatewaySchema):
    id: UUID
    request_id: UUID
    selected_model_key: str | None
    selected_provider_key: str | None
    selected_tool_key: str | None = None
    selected_action_key: str | None = None
    fallback_model_keys: list[str]
    candidate_scores: dict[str, float]
    hard_exclusions: dict[str, list[str]]
    applied_policy_ids: list[str]
    estimated_input_tokens: int
    estimated_output_tokens: int
    estimated_cost_usd: Decimal
    estimated_latency_ms: int
    reasoning_summary: str
    decision_hash: str


class ModelExecutionResultResponse(GatewaySchema):
    execution_id: UUID
    request_id: UUID
    provider_key: str | None
    model_key: str | None
    normalized_output: dict[str, Any] | str | list[Any]
    finish_reason: str
    validation_status: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    latency_ms: int
    cost_usd: Decimal
    retry_count: int
    fallback_used: bool
    response_hash: str


class ToolExecutionRequest(GatewaySchema):
    execution_id: UUID = Field(default_factory=uuid4)
    mission_id: UUID
    task_id: UUID | None = None
    tool_key: str
    action_key: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    environment: str = "local"
    execution_boundary_id: UUID | None = None
    expected_outputs: list[str] = Field(default_factory=list)
    timeout_seconds: int = Field(default=120, ge=1, le=86400)
    dry_run: bool = False
    idempotency_key: str
    approval_id: UUID | None = None
    secret_reference_ids: list[UUID] = Field(default_factory=list)


class ToolAuthorizationResponse(GatewaySchema):
    authorized: bool
    denial_reasons: list[str]
    tool_key: str
    action_key: str
    side_effect_class: str | None
    requires_approval: bool
    requires_sandbox: bool


class ExecutionLedgerResponse(GatewaySchema):
    id: UUID
    mission_id: UUID
    task_id: UUID | None
    execution_kind: str
    task_type: str
    provider_key: str | None
    model_key: str | None
    tool_key: str | None
    action_key: str | None
    status: str
    estimated_cost: Decimal
    actual_cost: Decimal
    latency_ms: int | None
    result: dict[str, Any]
    error: dict[str, Any]
    created_at: datetime


class BudgetRequest(GatewaySchema):
    scope_type: str
    scope_id: UUID
    currency: str = "USD"
    limit_amount: Decimal
    warning_threshold_percent: int = Field(default=80, ge=1, le=100)


class BudgetResponse(BudgetRequest):
    id: UUID
    reserved_amount: Decimal
    actual_amount: Decimal
    status: str
    created_at: datetime
    updated_at: datetime
