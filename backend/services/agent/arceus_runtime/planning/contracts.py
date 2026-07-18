from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID


@dataclass(frozen=True)
class PlanMissionCommand:
    tenant_id: UUID
    mission_id: UUID
    expected_version: int
    actor_id: UUID
    idempotency_key: str
    request_hash: str
    correlation_id: UUID


@dataclass(frozen=True)
class PlannedMember:
    role_key: str
    specialist_key: str
    display_name: str
    specialist_type: str
    assigned_capabilities: tuple[str, ...]
    responsibility: str
    authority: dict[str, Any]
    can_implement: bool = False
    can_review: bool = False
    can_approve: bool = False
    score: float = 0.75
    score_reason: str = "Selected from built-in capability registry."


@dataclass(frozen=True)
class PlannedTask:
    task_key: str
    title: str
    description: str
    category: str
    owner_role_key: str
    required_capabilities: tuple[str, ...]
    dependencies: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    acceptance_criteria: tuple[str, ...] = ()
    verification_methods: tuple[str, ...] = ()
    risk_level: str = "medium"
    estimated_hours: float = 1.0
    estimated_cost_usd: float = 0.0
    estimated_tokens: int = 0


@dataclass(frozen=True)
class OrganizationProposal:
    proposal_key: str
    name: str
    rationale: str
    members: tuple[PlannedMember, ...]
    tasks: tuple[PlannedTask, ...]
    capability_gaps: tuple[str, ...]
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PlanBuildResult:
    mission_id: UUID
    organization_id: UUID
    workflow_id: UUID
    plan_artifact_id: UUID
    approval_id: UUID
    status: str
    organization_size: int
    task_count: int
    graph_hash: str
    critical_path: tuple[str, ...]
    capability_gaps: tuple[str, ...] = ()
    metrics: dict[str, Any] = field(default_factory=dict)
