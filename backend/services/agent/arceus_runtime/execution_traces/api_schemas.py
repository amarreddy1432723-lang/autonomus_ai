from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ContextPackageResponse(BaseModel):
    id: UUID
    mission_id: UUID
    task_id: UUID | None
    recipient_member_id: UUID | None
    purpose: str
    selected_items: list[Any]
    excluded_items: list[Any]
    token_budget: int
    content_hash: str
    created_at: datetime
    updated_at: datetime
    version_number: int


class ModelExecutionResponse(BaseModel):
    id: UUID
    mission_id: UUID | None
    task_id: UUID | None
    member_id: UUID | None
    provider: str
    model: str
    purpose: str
    prompt_hash: str
    input_tokens: int
    output_tokens: int
    cost_usd: Decimal
    latency_ms: int | None
    status: str
    error: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    version_number: int


class ToolDefinitionResponse(BaseModel):
    id: UUID
    tool_key: str
    display_name: str
    tool_type: str
    permission_requirements: dict[str, Any]
    active: bool
    created_at: datetime
    updated_at: datetime
    version_number: int


class ToolExecutionResponse(BaseModel):
    id: UUID
    mission_id: UUID | None
    task_id: UUID | None
    member_id: UUID | None
    tool_definition_id: UUID
    tool_definition: ToolDefinitionResponse | None
    action: str
    target: str | None
    status: str
    input_payload: dict[str, Any]
    output_payload: dict[str, Any]
    error: dict[str, Any]
    started_at: datetime
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    version_number: int


class PolicyEvaluationResponse(BaseModel):
    id: UUID
    mission_id: UUID | None
    task_id: UUID | None
    policy_key: str
    subject: dict[str, Any]
    action: str
    resource: dict[str, Any]
    decision: str
    reason: str
    created_at: datetime
    updated_at: datetime
    version_number: int
