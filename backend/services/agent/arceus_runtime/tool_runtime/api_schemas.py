from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


RiskLevel = Literal["low", "medium", "high", "critical"]
SideEffectClass = Literal[
    "READ_ONLY",
    "LOCAL_MUTATION",
    "REPOSITORY_MUTATION",
    "EXTERNAL_REVERSIBLE",
    "EXTERNAL_IRREVERSIBLE",
    "PRODUCTION_CHANGE",
    "FINANCIAL_ACTION",
    "SECRET_ACCESS",
]
ToolDecision = Literal["allow", "require_review", "deny"]


class ToolRuntimeProfile(BaseModel):
    tool_key: str = Field(..., min_length=2, max_length=160)
    display_name: str
    category: str = "custom"
    adapter_type: str = "internal"
    version: str = "1.0"
    capabilities: list[str] = Field(default_factory=list)
    supported_actions: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = "low"
    side_effect_class: SideEffectClass = "READ_ONLY"
    requires_sandbox: bool = True
    supports_dry_run: bool = True
    supports_idempotency: bool = True
    supports_rollback: bool = False
    required_authorities: list[str] = Field(default_factory=list)
    allowed_environments: list[str] = Field(default_factory=lambda: ["local"])
    maximum_runtime_seconds: int = Field(120, ge=1, le=3600)
    enabled: bool = True


class ToolAuthorizationRequest(BaseModel):
    mission_id: UUID | None = None
    task_id: UUID | None = None
    member_id: UUID | None = None
    tool_key: str = Field(..., min_length=2, max_length=160)
    action_key: str = Field(..., min_length=1, max_length=160)
    arguments: dict[str, Any] = Field(default_factory=dict)
    environment: str = "local"
    dry_run: bool = True
    requester_authorities: list[str] = Field(default_factory=list)
    idempotency_key: str | None = Field(default=None, max_length=255)
    profile: ToolRuntimeProfile | None = None


class ToolAuthorizationResponse(BaseModel):
    decision: ToolDecision
    tool_key: str
    action_key: str
    risk_level: RiskLevel
    side_effect_class: SideEffectClass
    reasons: list[str]
    required_approvals: list[str]
    required_authorities: list[str]
    execution_boundary: dict[str, Any]
    idempotency_fingerprint: str
    sanitized_arguments: dict[str, Any]


class ToolExecutionRequest(ToolAuthorizationRequest):
    dry_run: bool = False
    timeout_seconds: int | None = Field(default=None, ge=1, le=3600)
    expected_outputs: dict[str, Any] = Field(default_factory=dict)


class ToolExecutionReceipt(BaseModel):
    execution_id: UUID | None = None
    status: Literal["authorized", "running", "succeeded", "failed", "cancelled", "blocked"]
    decision: ToolDecision
    tool_key: str
    action_key: str
    dry_run: bool
    replayed: bool = False
    input_hash: str
    output_hash: str | None = None
    redacted_input: dict[str, Any]
    redacted_output: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    rollback_available: bool = False
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ToolRuntimeCatalogResponse(BaseModel):
    tools: list[ToolRuntimeProfile]


class ToolReceiptVerificationRequest(BaseModel):
    receipt: ToolExecutionReceipt


class ToolReceiptVerificationResponse(BaseModel):
    valid: bool
    reasons: list[str]
