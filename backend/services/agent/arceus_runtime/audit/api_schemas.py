from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class ReplayEventResponse(BaseModel):
    id: UUID
    aggregate_type: str
    aggregate_id: UUID
    aggregate_version: int
    event_type: str
    actor_type: str
    actor_id: str | None
    payload: dict[str, Any]
    metadata_json: dict[str, Any]
    occurred_at: datetime


class MissionReplayResponse(BaseModel):
    mission_id: UUID
    from_version: int
    to_version: int | None
    event_count: int
    replay_cursor: int
    events: list[ReplayEventResponse]


class AuditEventResponse(BaseModel):
    id: UUID
    actor_type: str
    actor_id: str | None
    action: str
    resource_type: str
    resource_id: str | None
    result: str
    ip_address: str | None
    user_agent: str | None
    metadata_json: dict[str, Any]
    occurred_at: datetime
