from __future__ import annotations

from datetime import datetime, timezone

from services.shared.arceus_core_models import ArceusMission

from ..application.errors import MissionStateConflict


TRANSITIONS = {
    "compile": {"draft": "compiling", "clarification_required": "compiling", "failed": "compiling"},
    "start": {"ready": "running"},
    "pause": {"running": "paused", "blocked": "paused"},
    "resume": {"paused": "running", "blocked": "running", "failed": "running"},
    "cancel": {
        "draft": "cancelled",
        "compiling": "cancelled",
        "clarification_required": "cancelled",
        "compiled": "cancelled",
        "organizing": "cancelled",
        "awaiting_plan_approval": "cancelled",
        "ready": "cancelled",
        "running": "cancelled",
        "paused": "cancelled",
        "blocked": "cancelled",
        "reviewing": "cancelled",
        "verifying": "cancelled",
        "failed": "cancelled",
    },
}


EVENT_BY_ACTION = {
    "compile": "MISSION_COMPILATION_REQUESTED",
    "start": "MISSION_STARTED",
    "pause": "MISSION_PAUSED",
    "resume": "MISSION_RESUMED",
    "cancel": "MISSION_CANCELLATION_REQUESTED",
}


TOPIC_BY_ACTION = {
    "compile": "arceus.mission.compilation.requested",
    "start": "arceus.workflow.ready",
    "pause": "arceus.mission.recovery.requested",
    "resume": "arceus.workflow.ready",
    "cancel": "arceus.mission.recovery.requested",
}


def transition_mission(mission: ArceusMission, action: str) -> tuple[str, str]:
    allowed = TRANSITIONS.get(action, {})
    previous = mission.status
    target = allowed.get(previous)
    if target is None:
        raise MissionStateConflict(
            f"Mission cannot perform '{action}' from state '{previous}'.",
            details={"current_state": previous, "action": action, "allowed_from": sorted(allowed.keys())},
        )

    mission.status = target
    mission.version_number = int(mission.version_number) + 1
    mission.updated_at = datetime.now(timezone.utc)
    if target == "cancelled":
        mission.completed_at = mission.completed_at
    return previous, target
