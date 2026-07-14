from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from services.shared.models import AuditLog, Memory, Notification, Schedule, Task, UserProfile

from .pa_os import pa_os_status, set_pa_os_state


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_datetime(value: str | None, default_minutes: int = 60) -> datetime:
    if not value:
        return _now() + timedelta(minutes=default_minutes)


PA_SETTINGS_DEFAULTS: dict[str, Any] = {
    "voice_enabled": True,
    "daily_brief_enabled": True,
    "notification_enabled": True,
    "automation_mode": "confirm",
    "emergency_paused": False,
    "preferred_brief_time": "08:00",
}


def _profile(db: Session, user_id: UUID) -> UserProfile:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile:
        return profile
    profile = UserProfile(user_id=user_id, tool_preferences={})
    db.add(profile)
    db.flush()
    return profile


def get_pa_settings(db: Session, user_id: UUID) -> dict[str, Any]:
    profile = _profile(db, user_id)
    prefs = dict(profile.tool_preferences or {})
    pa = dict(prefs.get("pa") or {})
    settings = {**PA_SETTINGS_DEFAULTS, **pa.get("settings", {})}
    settings["emergency_paused"] = bool(settings.get("emergency_paused"))
    return settings


def update_pa_settings(db: Session, user_id: UUID, updates: dict[str, Any]) -> dict[str, Any]:
    allowed = set(PA_SETTINGS_DEFAULTS)
    cleaned: dict[str, Any] = {}
    for key, value in updates.items():
        if key not in allowed:
            continue
        if key in {"voice_enabled", "daily_brief_enabled", "notification_enabled", "emergency_paused"}:
            cleaned[key] = bool(value)
        elif key == "automation_mode":
            cleaned[key] = str(value or "confirm").lower() if str(value or "").lower() in {"confirm", "notify", "auto"} else "confirm"
        elif key == "preferred_brief_time":
            cleaned[key] = str(value or "08:00")[:16]
    profile = _profile(db, user_id)
    prefs = dict(profile.tool_preferences or {})
    pa = dict(prefs.get("pa") or {})
    pa["settings"] = {**PA_SETTINGS_DEFAULTS, **pa.get("settings", {}), **cleaned}
    prefs["pa"] = pa
    profile.tool_preferences = prefs
    flag_modified(profile, "tool_preferences")
    audit_event(db, user_id, "settings.update", metadata={"updated": sorted(cleaned.keys())})
    db.commit()
    return pa["settings"]


def _brief_cache_key() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def get_cached_daily_brief(db: Session, user_id: UUID, force_refresh: bool = False) -> dict[str, Any]:
    from .jarvis_planner import daily_brief

    settings = get_pa_settings(db, user_id)
    profile = _profile(db, user_id)
    prefs = dict(profile.tool_preferences or {})
    pa = dict(prefs.get("pa") or {})
    cache = dict(pa.get("daily_brief_cache") or {})
    today_key = _brief_cache_key()
    if not force_refresh and cache.get("date") == today_key and cache.get("brief"):
        return {"cached": True, "settings": settings, **cache["brief"]}
    brief = daily_brief(db, user_id)
    pa["daily_brief_cache"] = {
        "date": today_key,
        "created_at": _now().isoformat(),
        "brief": brief,
    }
    prefs["pa"] = pa
    profile.tool_preferences = prefs
    flag_modified(profile, "tool_preferences")
    audit_event(db, user_id, "daily_brief.refresh", metadata={"force": force_refresh})
    db.commit()
    return {"cached": False, "settings": settings, **brief}
    cleaned = value.strip()
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(cleaned)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return _now() + timedelta(minutes=default_minutes)


def audit_event(
    db: Session,
    user_id: UUID,
    action: str,
    *,
    product: str = "pa",
    entity_type: str | None = None,
    entity_id: UUID | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            event_type=f"{product}.{action}",
            entity_type=entity_type,
            entity_id=entity_id,
            actor_type="user",
            actor_id=str(user_id),
            action=action,
            metadata_json={k: v for k, v in (metadata or {}).items() if "token" not in k.lower() and "secret" not in k.lower()},
        )
    )


def serialize_task(task: Task) -> dict[str, Any]:
    return {
        "id": str(task.id),
        "title": task.title,
        "description": task.description or "",
        "status": task.status,
        "priority_score": float(task.priority_score or 0),
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }


def serialize_schedule(schedule: Schedule) -> dict[str, Any]:
    payload = schedule.trigger_payload or {}
    return {
        "id": str(schedule.id),
        "title": schedule.title,
        "type": payload.get("pa_type") or schedule.schedule_type,
        "status": "active" if schedule.is_active else "paused",
        "next_run_at": schedule.next_run_at.isoformat() if schedule.next_run_at else None,
        "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        "trigger": schedule.trigger_type,
        "permission": payload.get("permission", "confirm"),
        "logs": payload.get("logs", []),
        "source": payload.get("source", "nexus_pa"),
    }


def serialize_notification(notification: Notification) -> dict[str, Any]:
    return {
        "id": str(notification.id),
        "title": notification.title,
        "body": notification.body,
        "priority": int(notification.priority or 2),
        "status": notification.status,
        "read_at": notification.read_at.isoformat() if notification.read_at else None,
        "created_at": notification.created_at.isoformat() if notification.created_at else None,
        "source": "nexus_pa",
    }


def _recent_memories(db: Session, user_id: UUID, limit: int = 5) -> list[dict[str, Any]]:
    rows = (
        db.query(Memory)
        .filter(Memory.user_id == user_id, Memory.is_archived == False, Memory.is_superseded == False)  # noqa: E712
        .order_by(Memory.importance.desc(), Memory.updated_at.desc())
        .limit(limit)
        .all()
    )
    return [
        {
            "id": str(item.id),
            "content": item.content[:220],
            "type": item.memory_type,
            "importance": item.importance,
            "sensitive": bool((item.meta_data or {}).get("sensitive")),
        }
        for item in rows
    ]


def pa_today(db: Session, user_id: UUID) -> dict[str, Any]:
    status = pa_os_status(db, user_id)
    settings = get_pa_settings(db, user_id)
    brief = get_cached_daily_brief(db, user_id, force_refresh=False)
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id, Task.status.notin_(["done", "completed", "cancelled"]))
        .order_by(Task.priority_score.desc(), Task.due_date.asc().nullslast(), Task.created_at.asc())
        .limit(8)
        .all()
    )
    reminders = (
        db.query(Schedule)
        .filter(
            Schedule.user_id == user_id,
            Schedule.is_active == True,  # noqa: E712
            Schedule.trigger_payload["pa_type"].as_string() == "reminder",
        )
        .order_by(Schedule.next_run_at.asc())
        .limit(6)
        .all()
    )
    automations = (
        db.query(Schedule)
        .filter(
            Schedule.user_id == user_id,
            Schedule.trigger_payload["pa_type"].as_string() == "automation",
        )
        .order_by(Schedule.updated_at.desc())
        .limit(6)
        .all()
    )
    notifications = (
        db.query(Notification)
        .filter(Notification.user_id == user_id)
        .order_by(Notification.read_at.asc().nullsfirst(), Notification.created_at.desc())
        .limit(8)
        .all()
    )
    return {
        **status,
        "settings": settings,
        "brief": brief,
        "daily_brief_cached": bool(brief.get("cached")),
        "tasks": [serialize_task(item) for item in tasks],
        "reminders": [serialize_schedule(item) for item in reminders],
        "automations": [serialize_schedule(item) for item in automations],
        "notifications": [serialize_notification(item) for item in notifications],
        "memories": _recent_memories(db, user_id),
        "context_used": {
            "tasks": len(tasks),
            "reminders": len(reminders),
            "automations": len(automations),
            "notifications": len(notifications),
            "memories": min(len(_recent_memories(db, user_id)), 5),
        },
    }


def list_tasks(db: Session, user_id: UUID) -> list[dict[str, Any]]:
    return [
        serialize_task(item)
        for item in (
            db.query(Task)
            .filter(Task.user_id == user_id)
            .order_by(Task.status.asc(), Task.priority_score.desc(), Task.created_at.desc())
            .limit(100)
            .all()
        )
    ]


def create_task(db: Session, user_id: UUID, title: str, description: str = "", due_at: str | None = None, priority: float = 0.5) -> dict[str, Any]:
    task = Task(
        user_id=user_id,
        title=title.strip()[:255],
        description=description.strip() or None,
        status="queued",
        priority_score=max(0.0, min(float(priority or 0.5), 1.0)),
        due_date=_parse_datetime(due_at, 24 * 60) if due_at else None,
        assigned_agent="nexus_pa",
    )
    db.add(task)
    db.flush()
    audit_event(db, user_id, "task.create", entity_type="task", entity_id=task.id, metadata={"title": task.title})
    db.commit()
    db.refresh(task)
    return serialize_task(task)


def update_task(db: Session, user_id: UUID, task_id: UUID, payload: dict[str, Any]) -> dict[str, Any]:
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if not task:
        raise ValueError("Task not found")
    if "title" in payload and payload["title"]:
        task.title = str(payload["title"])[:255]
    if "description" in payload:
        task.description = str(payload["description"] or "")
    if "status" in payload and payload["status"]:
        task.status = str(payload["status"])
        if task.status in {"done", "completed"}:
            task.completed_at = _now()
    if "priority_score" in payload:
        task.priority_score = max(0.0, min(float(payload["priority_score"] or 0), 1.0))
    if "due_at" in payload:
        task.due_date = _parse_datetime(payload.get("due_at"), 24 * 60) if payload.get("due_at") else None
    audit_event(db, user_id, "task.update", entity_type="task", entity_id=task.id, metadata={"status": task.status})
    db.commit()
    db.refresh(task)
    return serialize_task(task)


def delete_task(db: Session, user_id: UUID, task_id: UUID) -> dict[str, str]:
    task = db.query(Task).filter(Task.id == task_id, Task.user_id == user_id).first()
    if not task:
        raise ValueError("Task not found")
    audit_event(db, user_id, "task.delete", entity_type="task", entity_id=task.id, metadata={"title": task.title})
    db.delete(task)
    db.commit()
    return {"status": "deleted"}


def list_schedules(db: Session, user_id: UUID, pa_type: str) -> list[dict[str, Any]]:
    return [
        serialize_schedule(item)
        for item in (
            db.query(Schedule)
            .filter(Schedule.user_id == user_id, Schedule.trigger_payload["pa_type"].as_string() == pa_type)
            .order_by(Schedule.is_active.desc(), Schedule.next_run_at.asc())
            .limit(100)
            .all()
        )
    ]


def create_schedule(
    db: Session,
    user_id: UUID,
    *,
    title: str,
    pa_type: str,
    next_run_at: str | None = None,
    trigger: str = "time",
    permission: str = "confirm",
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_pa_settings(db, user_id)
    if pa_type == "automation" and settings.get("emergency_paused"):
        raise ValueError("Arceus PA emergency pause is active. Resume PA before creating automations.")
    schedule = Schedule(
        user_id=user_id,
        title=title.strip()[:255],
        schedule_type="pa",
        next_run_at=_parse_datetime(next_run_at),
        trigger_type=trigger or "time",
        trigger_payload={
            **(payload or {}),
            "pa_type": pa_type,
            "permission": permission or "confirm",
            "source": "nexus_pa",
            "logs": [{"at": _now().isoformat(), "message": f"{pa_type.title()} created"}],
        },
        is_active=True,
    )
    db.add(schedule)
    db.flush()
    audit_event(db, user_id, f"{pa_type}.create", entity_type="schedule", entity_id=schedule.id, metadata={"title": title})
    db.commit()
    db.refresh(schedule)
    return serialize_schedule(schedule)


def update_schedule(db: Session, user_id: UUID, schedule_id: UUID, payload: dict[str, Any], pa_type: str) -> dict[str, Any]:
    schedule = (
        db.query(Schedule)
        .filter(Schedule.id == schedule_id, Schedule.user_id == user_id, Schedule.trigger_payload["pa_type"].as_string() == pa_type)
        .first()
    )
    if not schedule:
        raise ValueError(f"{pa_type.title()} not found")
    if payload.get("title"):
        schedule.title = str(payload["title"])[:255]
    if "next_run_at" in payload:
        schedule.next_run_at = _parse_datetime(payload.get("next_run_at"))
    if "status" in payload:
        schedule.is_active = str(payload.get("status")).lower() not in {"paused", "inactive", "disabled"}
    if payload.get("permission"):
        merged = dict(schedule.trigger_payload or {})
        merged["permission"] = payload.get("permission")
        schedule.trigger_payload = merged
    audit_event(db, user_id, f"{pa_type}.update", entity_type="schedule", entity_id=schedule.id, metadata={"active": schedule.is_active})
    db.commit()
    db.refresh(schedule)
    return serialize_schedule(schedule)


def delete_schedule(db: Session, user_id: UUID, schedule_id: UUID, pa_type: str) -> dict[str, str]:
    schedule = (
        db.query(Schedule)
        .filter(Schedule.id == schedule_id, Schedule.user_id == user_id, Schedule.trigger_payload["pa_type"].as_string() == pa_type)
        .first()
    )
    if not schedule:
        raise ValueError(f"{pa_type.title()} not found")
    audit_event(db, user_id, f"{pa_type}.delete", entity_type="schedule", entity_id=schedule.id, metadata={"title": schedule.title})
    db.delete(schedule)
    db.commit()
    return {"status": "deleted"}


def list_notifications(db: Session, user_id: UUID) -> list[dict[str, Any]]:
    return [
        serialize_notification(item)
        for item in db.query(Notification).filter(Notification.user_id == user_id).order_by(Notification.created_at.desc()).limit(100).all()
    ]


def mark_notification_read(db: Session, user_id: UUID, notification_id: UUID) -> dict[str, Any]:
    item = db.query(Notification).filter(Notification.id == notification_id, Notification.user_id == user_id).first()
    if not item:
        raise ValueError("Notification not found")
    item.read_at = _now()
    item.status = "read"
    audit_event(db, user_id, "notification.read", entity_type="notification", entity_id=item.id)
    db.commit()
    db.refresh(item)
    return serialize_notification(item)


def pause_pa(db: Session, user_id: UUID) -> dict[str, Any]:
    set_pa_os_state(user_id, "paused")
    update_pa_settings(db, user_id, {"emergency_paused": True})
    db.query(Schedule).filter(
        Schedule.user_id == user_id,
        Schedule.trigger_payload["pa_type"].as_string() == "automation",
    ).update({"is_active": False}, synchronize_session=False)
    audit_event(db, user_id, "pause")
    db.commit()
    return pa_today(db, user_id)


def resume_pa(db: Session, user_id: UUID) -> dict[str, Any]:
    set_pa_os_state(user_id, "active")
    update_pa_settings(db, user_id, {"emergency_paused": False})
    audit_event(db, user_id, "resume")
    db.commit()
    return pa_today(db, user_id)


def handle_command(db: Session, user_id: UUID, command: str) -> dict[str, Any]:
    text = (command or "").strip()
    lower = text.lower()
    if not text:
        return {"type": "empty", "message": "Tell Arceus PA what to handle."}
    if "pause" in lower and "automation" in lower:
        return {"type": "pause", "result": pause_pa(db, user_id)}
    if lower.startswith(("remind me", "reminder", "schedule reminder")):
        result = create_schedule(db, user_id, title=text.replace("remind me to", "", 1).strip() or text, pa_type="reminder")
        return {"type": "reminder_created", "result": result}
    if lower.startswith(("task", "todo", "create task", "add task")):
        cleaned = text
        for prefix in ("create task", "add task", "task", "todo"):
            if cleaned.lower().startswith(prefix):
                cleaned = cleaned[len(prefix):].strip(" :-")
                break
        result = create_task(db, user_id, cleaned or text)
        return {"type": "task_created", "result": result}
    if "today" in lower or "brief" in lower:
        return {"type": "today", "result": pa_today(db, user_id)}
    memories = _recent_memories(db, user_id, 3)
    audit_event(db, user_id, "command", metadata={"command": text[:200]})
    db.commit()
    return {
        "type": "answer",
        "message": "I can help turn that into a task, reminder, memory search, meeting prep, or automation.",
        "suggested_actions": ["Create task", "Schedule reminder", "Search memory", "Prepare meeting"],
        "context_used": {"memories": memories},
    }


def admin_usage_summary(db: Session) -> dict[str, Any]:
    return {
        "users": int(db.query(func.count(Task.user_id.distinct())).scalar() or 0),
        "tasks": int(db.query(func.count(Task.id)).scalar() or 0),
        "notifications": int(db.query(func.count(Notification.id)).scalar() or 0),
        "automations": int(db.query(func.count(Schedule.id)).filter(Schedule.trigger_payload["pa_type"].as_string() == "automation").scalar() or 0),
    }
