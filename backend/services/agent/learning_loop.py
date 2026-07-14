"""
Continuous learning helpers for Arceus AI.

This is retrieval/personalization learning, not live model training. It keeps
small, non-sensitive behavioral signals that can make the next response more
useful without storing private prompts as training data.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy.orm import Session

from services.shared.models import Memory, Task, UsageEvent, UserProfile


def _hour_bucket() -> str:
    hour = datetime.now(timezone.utc).hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def learn_from_interaction(db: Session, user_id: UUID, interaction_data: dict[str, Any]) -> dict[str, Any]:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if not profile:
        return {"learned": False, "reason": "profile_missing"}

    patterns = dict(profile.work_patterns or {})
    products = patterns.setdefault("products", {})
    task_types = patterns.setdefault("task_types", {})
    hours = patterns.setdefault("active_hours", {})

    product = str(interaction_data.get("product") or "core")
    task_type = str(interaction_data.get("task_type") or "chat")
    products[product] = int(products.get(product) or 0) + 1
    task_types[task_type] = int(task_types.get(task_type) or 0) + 1
    bucket = _hour_bucket()
    hours[bucket] = int(hours.get(bucket) or 0) + 1

    patterns["last_interaction_at"] = datetime.now(timezone.utc).isoformat()
    profile.work_patterns = patterns
    db.commit()
    return {"learned": True, "product": product, "task_type": task_type}


def get_personalization_context(db: Session, user_id: UUID) -> dict[str, Any]:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    patterns = dict(profile.work_patterns or {}) if profile else {}
    recent_memories = (
        db.query(Memory)
        .filter(Memory.user_id == user_id, Memory.is_archived == False)  # noqa: E712
        .order_by(Memory.updated_at.desc())
        .limit(5)
        .all()
    )
    open_tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id, Task.status.in_(["todo", "in_progress", "blocked"]))
        .order_by(Task.updated_at.desc())
        .limit(5)
        .all()
    )
    usage = (
        db.query(UsageEvent)
        .filter(UsageEvent.user_id == user_id)
        .order_by(UsageEvent.created_at.desc())
        .limit(5)
        .all()
    )

    return {
        "work_patterns": patterns,
        "recent_memory_titles": [memory.title for memory in recent_memories],
        "open_task_titles": [task.title for task in open_tasks],
        "recent_routes": [event.route for event in usage],
    }


def personalization_prompt(context: dict[str, Any]) -> str:
    if not context:
        return ""
    parts: list[str] = []
    patterns = context.get("work_patterns") or {}
    if patterns.get("active_hours"):
        parts.append(f"User activity pattern: {patterns['active_hours']}.")
    if context.get("open_task_titles"):
        parts.append("Current open tasks: " + "; ".join(context["open_task_titles"][:4]) + ".")
    if context.get("recent_memory_titles"):
        parts.append("Recent useful memories: " + "; ".join(context["recent_memory_titles"][:4]) + ".")
    return "\n".join(parts)
