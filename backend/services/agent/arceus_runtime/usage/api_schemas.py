from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class UsageRecordResponse(BaseModel):
    id: UUID
    user_id: UUID | None
    mission_id: UUID | None
    usage_type: str
    quantity: Decimal
    unit: str
    cost_usd: Decimal
    metadata_json: dict[str, Any]
    occurred_at: datetime


class UsageTypeSummaryResponse(BaseModel):
    usage_type: str
    quantity: Decimal
    unit: str
    cost_usd: Decimal
    record_count: int


class UsageSummaryResponse(BaseModel):
    tenant_id: UUID
    user_id: UUID | None
    mission_id: UUID | None
    record_count: int
    cost_usd: Decimal
    by_type: list[UsageTypeSummaryResponse]


class MissionBudgetSummaryResponse(UsageSummaryResponse):
    mission_budget_amount: Decimal | None
    mission_actual_cost_amount: Decimal
    budget_currency: str
    budget_remaining_amount: Decimal | None
