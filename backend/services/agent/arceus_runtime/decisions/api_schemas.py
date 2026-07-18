from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class DecisionResponse(BaseModel):
    id: UUID
    mission_id: UUID
    task_id: UUID | None
    decision_key: str
    title: str
    summary: str
    selected_option: dict[str, Any]
    alternatives: list[Any]
    rationale: str
    status: str
    decided_by_member_id: UUID | None
    created_at: datetime
    updated_at: datetime
    version_number: int
