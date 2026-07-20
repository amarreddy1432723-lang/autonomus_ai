from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class KernelEntityResponse(BaseModel):
    entity_type: str
    table: str
    owner_field: str | None
    tenant_scoped: bool
    versioned: bool
    lifecycle: list[str]
    required_links: list[str]
    invariants: list[str]


class KernelContractResponse(BaseModel):
    contract_key: str
    purpose: str
    operations: list[str]
    required_events: list[str]
    invariants: list[str]


class KernelEventResponse(BaseModel):
    event_id: UUID
    aggregate_type: str
    aggregate_id: UUID
    aggregate_version: int
    event_type: str
    actor_type: str
    actor_id: str | None
    payload: dict[str, Any]
    metadata_json: dict[str, Any]
    occurred_at: datetime


class KernelValidationRequest(BaseModel):
    entity_type: str = Field(min_length=2, max_length=120)
    payload: dict[str, Any] = Field(default_factory=dict)
    intended_action: str = Field(default="execute", min_length=2, max_length=120)


class KernelValidationResponse(BaseModel):
    valid: bool
    status: str
    violations: list[dict[str, Any]]
    required_events: list[str]
    required_audit: bool
    constitutional_path: list[str]


class KernelReplayRequest(BaseModel):
    aggregate_type: str = Field(min_length=2, max_length=120)
    aggregate_id: UUID
    from_version: int = Field(default=1, ge=1)
    to_version: int | None = Field(default=None, ge=1)


class KernelReplayResponse(BaseModel):
    aggregate_type: str
    aggregate_id: UUID
    replayable: bool
    version_range: dict[str, int | None]
    event_count: int
    state: dict[str, Any]
    violations: list[dict[str, Any]]


class KernelInvariantResponse(BaseModel):
    invariant_key: str
    statement: str
    severity: str
    enforced_by: list[str]
