from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from services.shared.models import Schedule, Task

from .jarvis_planner import daily_brief


_PA_OS_STATE: dict[str, str] = {}
VALID_STATES = {"active", "paused", "sleep", "stopped"}


def _state_for(user_id: UUID) -> str:
    return _PA_OS_STATE.get(str(user_id), "active")


def set_pa_os_state(user_id: UUID, state: str) -> dict:
    normalized = (state or "active").strip().lower()
    if normalized not in VALID_STATES:
        normalized = "active"
    _PA_OS_STATE[str(user_id)] = normalized
    return {"state": normalized, "updated_at": datetime.now(timezone.utc).isoformat()}


def emergency_stop(user_id: UUID) -> dict:
    _PA_OS_STATE[str(user_id)] = "stopped"
    return {
        "state": "stopped",
        "monitoring": False,
        "message": "Emergency stop activated. Monitoring is off and volatile PA context should be treated as cleared.",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }


def pa_os_status(db: Session, user_id: UUID) -> dict:
    state = _state_for(user_id)
    brief = daily_brief(db, user_id)
    next_event = brief["schedule"][0] if brief.get("schedule") else None
    overdue_count = int(
        db.query(func.count(Task.id))
        .filter(
            Task.user_id == user_id,
            Task.due_date < datetime.now(timezone.utc),
            Task.status.notin_(["done", "completed", "cancelled"]),
        )
        .scalar()
        or 0
    )
    pending_tasks = int(
        db.query(func.count(Task.id))
        .filter(Task.user_id == user_id, Task.status.in_(["todo", "in_progress", "blocked"]))
        .scalar()
        or 0
    )
    active_schedules = int(
        db.query(func.count(Schedule.id))
        .filter(Schedule.user_id == user_id, Schedule.is_active == True)  # noqa: E712
        .scalar()
        or 0
    )

    status_label = {
        "active": "Active",
        "paused": "Paused",
        "sleep": "Sleep",
        "stopped": "Stopped",
    }[state]
    monitoring = state == "active"
    daily_brief_text = (
        f"{brief['insight']} Top priority count: {len(brief.get('priorities', []))}. "
        f"Next scheduled item: {next_event['title']}." if next_event else
        f"{brief['insight']} No scheduled item is due today."
    )

    return {
        "state": state,
        "status_label": status_label,
        "monitoring": monitoring,
        "call_ai": "ready" if state != "stopped" else "off",
        "voice": "ready" if state in {"active", "paused"} else "off",
        "next_event": next_event,
        "pending_delegations": pending_tasks,
        "unread_alerts": overdue_count,
        "active_schedules": active_schedules,
        "daily_brief": daily_brief_text,
        "brief": brief,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
