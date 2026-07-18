from __future__ import annotations

TASK_STATUSES = {
    "created",
    "analyzed",
    "planned",
    "plan_approved",
    "ready_for_execution",
    "paused",
    "cancelled",
    "completed",
    "failed",
}

RISK_LEVELS = ("low", "medium", "high", "critical")

SAFE_TRANSITIONS = {
    "created": {"analyzed", "cancelled"},
    "analyzed": {"planned", "cancelled"},
    "planned": {"plan_approved", "cancelled"},
    "plan_approved": {"ready_for_execution", "paused", "cancelled"},
    "ready_for_execution": {"paused", "cancelled", "completed", "failed"},
    "paused": {"ready_for_execution", "cancelled"},
}


def can_transition(current: str, target: str) -> bool:
    if current == target:
        return True
    return target in SAFE_TRANSITIONS.get(current, set())

