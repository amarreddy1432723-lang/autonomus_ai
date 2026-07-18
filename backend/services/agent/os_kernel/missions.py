"""Mission intake and state machine for Arceus OS."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .core import new_id, utc_now
from .events import Actor, AppendOnlyEventStore, EventMetadata, KernelEvent


MissionState = Literal[
    "DRAFT",
    "DISCOVERY",
    "REQUIREMENTS_REVIEW",
    "PLANNING",
    "PLAN_REVIEW",
    "AWAITING_APPROVAL",
    "READY",
    "EXECUTING",
    "RUNNING",
    "REVIEWING",
    "PAUSED",
    "BLOCKED",
    "VERIFYING",
    "AWAITING_FINAL_APPROVAL",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
    "ARCHIVED",
]
RiskLevel = Literal["low", "medium", "high", "critical"]


ALLOWED_TRANSITIONS: dict[MissionState, set[MissionState]] = {
    "DRAFT": {"DISCOVERY", "CANCELLED"},
    "DISCOVERY": {"REQUIREMENTS_REVIEW", "PLANNING", "BLOCKED", "CANCELLED"},
    "REQUIREMENTS_REVIEW": {"DISCOVERY", "PLANNING", "BLOCKED", "CANCELLED"},
    "PLANNING": {"PLAN_REVIEW", "AWAITING_APPROVAL", "READY", "BLOCKED", "CANCELLED"},
    "PLAN_REVIEW": {"PLANNING", "AWAITING_APPROVAL", "BLOCKED", "CANCELLED"},
    "AWAITING_APPROVAL": {"READY", "PLANNING", "CANCELLED"},
    "READY": {"EXECUTING", "RUNNING", "PAUSED", "CANCELLED"},
    "EXECUTING": {"PAUSED", "BLOCKED", "REVIEWING", "VERIFYING", "FAILED", "CANCELLED"},
    "RUNNING": {"PAUSED", "BLOCKED", "REVIEWING", "VERIFYING", "FAILED", "CANCELLED"},
    "REVIEWING": {"EXECUTING", "VERIFYING", "BLOCKED", "FAILED", "CANCELLED"},
    "PAUSED": {"EXECUTING", "RUNNING", "CANCELLED"},
    "BLOCKED": {"PLANNING", "EXECUTING", "RUNNING", "FAILED", "CANCELLED"},
    "VERIFYING": {"AWAITING_FINAL_APPROVAL", "REVIEWING", "EXECUTING", "RUNNING", "FAILED"},
    "AWAITING_FINAL_APPROVAL": {"COMPLETED", "REVIEWING", "FAILED", "CANCELLED"},
    "COMPLETED": {"ARCHIVED"},
    "FAILED": {"ARCHIVED"},
    "CANCELLED": {"ARCHIVED"},
    "ARCHIVED": set(),
}


@dataclass(slots=True)
class MissionBudget:
    maximum_cost: float = 0.0
    token_budget: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {"maximum_cost": self.maximum_cost, "token_budget": self.token_budget}


@dataclass(slots=True)
class OSMission:
    tenant_id: str
    owner_id: str
    title: str
    objective: str
    business_priority: float = 0.5
    urgency: float = 0.5
    dependency_impact: float = 0.0
    user_importance: float = 0.5
    risk_reduction_value: float = 0.0
    estimated_cost: float = 0.0
    resource_contention: float = 0.0
    risk_level: RiskLevel = "medium"
    dependencies: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    budget: MissionBudget = field(default_factory=MissionBudget)
    state: MissionState = "DRAFT"
    paused_by_user: bool = False
    mission_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    @property
    def priority_score(self) -> float:
        return round(
            self.business_priority
            + self.urgency
            + self.dependency_impact
            + self.user_importance
            + self.risk_reduction_value
            - self.estimated_cost
            - self.resource_contention,
            4,
        )

    def transition(self, new_state: MissionState) -> None:
        if new_state not in ALLOWED_TRANSITIONS[self.state]:
            raise ValueError(f"Invalid mission transition {self.state} -> {new_state}")
        self.state = new_state
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "tenant_id": self.tenant_id,
            "owner_id": self.owner_id,
            "title": self.title,
            "objective": self.objective,
            "business_priority": self.business_priority,
            "urgency": self.urgency,
            "dependency_impact": self.dependency_impact,
            "user_importance": self.user_importance,
            "risk_reduction_value": self.risk_reduction_value,
            "estimated_cost": self.estimated_cost,
            "resource_contention": self.resource_contention,
            "priority_score": self.priority_score,
            "risk_level": self.risk_level,
            "dependencies": self.dependencies,
            "success_criteria": self.success_criteria,
            "budget": self.budget.to_dict(),
            "state": self.state,
            "paused_by_user": self.paused_by_user,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class MissionService:
    def __init__(self, events: AppendOnlyEventStore) -> None:
        self.events = events
        self.missions: dict[str, OSMission] = {}

    def intake(self, mission: OSMission, actor: Actor, *, idempotency_key: str | None = None) -> OSMission:
        self.missions[mission.mission_id] = mission
        self.events.append(
            KernelEvent(
                event_type="MISSION_CREATED",
                aggregate_type="mission",
                aggregate_id=mission.mission_id,
                mission_id=mission.mission_id,
                actor=actor,
                payload=mission.to_dict(),
                metadata=EventMetadata(correlation_id=mission.mission_id, idempotency_key=idempotency_key),
            )
        )
        return mission

    def transition(self, mission_id: str, new_state: MissionState, actor: Actor) -> OSMission:
        mission = self.missions[mission_id]
        old_state = mission.state
        mission.transition(new_state)
        event_type = {
            "AWAITING_APPROVAL": "MISSION_UPDATED",
            "READY": "MISSION_APPROVED",
            "PAUSED": "MISSION_PAUSED",
            "RUNNING": "MISSION_RESUMED" if old_state == "PAUSED" else "MISSION_UPDATED",
            "CANCELLED": "MISSION_CANCELLED",
            "COMPLETED": "MISSION_COMPLETED",
        }.get(new_state, "MISSION_UPDATED")
        self.events.append(
            KernelEvent(
                event_type=event_type,
                aggregate_type="mission",
                aggregate_id=mission_id,
                mission_id=mission_id,
                actor=actor,
                payload={"from": old_state, "to": new_state},
                metadata=EventMetadata(correlation_id=mission_id),
            )
        )
        return mission

    def pause_immediately(self, mission_id: str, actor: Actor) -> OSMission:
        mission = self.missions[mission_id]
        mission.paused_by_user = True
        if mission.state != "PAUSED":
            mission.transition("PAUSED")
        self.events.append(
            KernelEvent(
                event_type="MISSION_PAUSED",
                aggregate_type="mission",
                aggregate_id=mission_id,
                mission_id=mission_id,
                actor=actor,
                payload={"reason": "user_requested_global_pause"},
                metadata=EventMetadata(correlation_id=mission_id),
            )
        )
        return mission
