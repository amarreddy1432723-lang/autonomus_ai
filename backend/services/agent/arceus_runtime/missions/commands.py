from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID


@dataclass(frozen=True)
class CreateMissionCommand:
    tenant_id: UUID
    project_id: UUID
    mission_owner_id: UUID
    objective: str
    title: str | None
    repository_ids: tuple[UUID, ...]
    constraints: tuple[str, ...]
    desired_outcomes: tuple[str, ...]
    maximum_budget_amount: Decimal | None
    budget_currency: str
    priority: int
    idempotency_key: str
    request_hash: str
    actor_id: UUID
    correlation_id: UUID


@dataclass(frozen=True)
class MissionTransitionCommand:
    tenant_id: UUID
    mission_id: UUID
    expected_version: int
    action: str
    reason: str | None
    actor_id: UUID
    idempotency_key: str
    request_hash: str
    correlation_id: UUID


@dataclass(frozen=True)
class SubmitClarificationsCommand:
    tenant_id: UUID
    mission_id: UUID
    expected_version: int
    answers: tuple[tuple[UUID, str], ...]
    actor_id: UUID
    idempotency_key: str
    request_hash: str
    correlation_id: UUID
