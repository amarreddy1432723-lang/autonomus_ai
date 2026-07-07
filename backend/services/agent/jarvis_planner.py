from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from services.shared.models import Goal, Memory, Schedule, Task


def _today_window() -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start, start + timedelta(days=1)


def _task_payload(task: Task) -> dict:
    return {
        "id": str(task.id),
        "title": task.title,
        "status": task.status,
        "priority_score": float(task.priority_score or 0),
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "estimate_hours": float(task.est_hours_pert or task.pert_estimate or 0),
    }


def _goal_payload(goal: Goal) -> dict:
    return {
        "id": str(goal.id),
        "title": goal.title,
        "status": goal.status,
        "progress": round(float(goal.progress_pct or goal.progress or 0) * 100),
        "deadline": goal.deadline.isoformat() if goal.deadline else None,
    }


def _schedule_payload(item: Schedule) -> dict:
    return {
        "id": str(item.id),
        "title": item.title,
        "time": item.next_run_at.isoformat(),
        "type": item.schedule_type,
        "trigger": item.trigger_type,
    }


def daily_brief(db: Session, user_id: UUID) -> dict:
    start, end = _today_window()
    schedules = (
        db.query(Schedule)
        .filter(Schedule.user_id == user_id, Schedule.is_active == True, Schedule.next_run_at >= start, Schedule.next_run_at < end)  # noqa: E712
        .order_by(Schedule.next_run_at.asc())
        .limit(8)
        .all()
    )
    tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id, Task.status.notin_(["done", "completed", "cancelled"]))
        .order_by(Task.priority_score.desc(), Task.due_date.asc().nullslast())
        .limit(6)
        .all()
    )
    goals = (
        db.query(Goal)
        .filter(Goal.user_id == user_id, Goal.status == "active")
        .order_by(Goal.priority.desc(), Goal.deadline.asc().nullslast())
        .limit(4)
        .all()
    )
    meeting_count = len(schedules)
    insight = (
        "You have a meeting-heavy day. Protect one deep-work block before new tasks."
        if meeting_count >= 3
        else "Your calendar has enough open space for one meaningful priority block."
    )
    return {
        "date": datetime.now(timezone.utc).date().isoformat(),
        "schedule": [_schedule_payload(item) for item in schedules],
        "priorities": [_task_payload(task) for task in tasks],
        "goals": [_goal_payload(goal) for goal in goals],
        "insight": insight,
        "suggested_focus_block": "14:00-16:00",
    }


def smart_schedule(db: Session, user_id: UUID, task: str, duration_minutes: int = 60, deadline: str | None = None) -> dict:
    start, _ = _today_window()
    candidates = [
        start + timedelta(days=1, hours=11),
        start + timedelta(days=2, hours=10),
        start + timedelta(days=3, hours=14),
    ]
    existing = (
        db.query(Schedule.next_run_at)
        .filter(Schedule.user_id == user_id, Schedule.is_active == True, Schedule.next_run_at >= start)  # noqa: E712
        .all()
    )
    busy_hours = {item[0].replace(minute=0, second=0, microsecond=0) for item in existing if item[0]}
    selected = next((slot for slot in candidates if slot.replace(minute=0, second=0, microsecond=0) not in busy_hours), candidates[0])
    return {
        "task": task,
        "duration_minutes": duration_minutes,
        "recommended_slot": selected.isoformat(),
        "deadline": deadline,
        "reason": "This slot avoids known meetings and preserves the 2-4 PM deep-work preference when possible.",
        "requires_approval": True,
    }


def meeting_prep(db: Session, user_id: UUID, meeting_context: str) -> dict:
    memories = (
        db.query(Memory)
        .filter(Memory.user_id == user_id, Memory.is_archived == False, Memory.content.ilike(f"%{meeting_context[:40]}%"))  # noqa: E712
        .order_by(Memory.importance.desc(), Memory.created_at.desc())
        .limit(5)
        .all()
    )
    return {
        "context": meeting_context,
        "talking_points": [
            "Confirm the objective and expected decision.",
            "Ask about blockers before proposing new work.",
            "Close with owner, deadline, and follow-up channel.",
        ],
        "related_memories": [{"id": str(memory.id), "content": memory.content} for memory in memories],
        "follow_up_template": "Thanks for the discussion. I captured: decisions, owners, deadlines, and next steps.",
    }


def end_of_day_summary(db: Session, user_id: UUID) -> dict:
    start, end = _today_window()
    completed = db.query(func.count(Task.id)).filter(Task.user_id == user_id, Task.completed_at >= start, Task.completed_at < end).scalar() or 0
    overdue = db.query(func.count(Task.id)).filter(Task.user_id == user_id, Task.due_date < end, Task.status.notin_(["done", "completed"])).scalar() or 0
    open_tasks = (
        db.query(Task)
        .filter(Task.user_id == user_id, Task.status.notin_(["done", "completed", "cancelled"]))
        .order_by(Task.priority_score.desc())
        .limit(5)
        .all()
    )
    return {
        "completed_today": int(completed),
        "rolled_to_tomorrow": [_task_payload(task) for task in open_tasks],
        "overdue_count": int(overdue),
        "insight": "Carry over only the highest priority tasks. Too many rollover items dilute tomorrow morning.",
    }


def delegate_task(db: Session, user_id: UUID, instruction: str) -> dict:
    return {
        "instruction": instruction,
        "subtasks": [
            {"title": "Clarify the outcome", "owner": "user", "status": "needs_input"},
            {"title": "Draft the first version", "owner": "nexus_pa", "status": "ready"},
            {"title": "Review risks and missing data", "owner": "nexus_pa", "status": "ready"},
            {"title": "Prepare final handoff", "owner": "user", "status": "pending_review"},
        ],
        "progress_estimate": 0.35,
        "needs_user_input": ["Final audience", "deadline", "source material"],
    }


def weekly_reflection(db: Session, user_id: UUID) -> dict:
    now = datetime.now(timezone.utc)
    week_start = now - timedelta(days=7)
    completed = db.query(func.count(Task.id)).filter(Task.user_id == user_id, Task.completed_at >= week_start).scalar() or 0
    overdue = db.query(func.count(Task.id)).filter(Task.user_id == user_id, Task.due_date < now, Task.status.notin_(["done", "completed"])).scalar() or 0
    goals = db.query(Goal).filter(Goal.user_id == user_id, Goal.status == "active").limit(5).all()
    return {
        "week_start": week_start.date().isoformat(),
        "week_end": now.date().isoformat(),
        "tasks_completed": int(completed),
        "tasks_overdue": int(overdue),
        "goals_progress": [_goal_payload(goal) for goal in goals],
        "what_worked": "Focused blocks and explicit priorities made the week more predictable.",
        "what_didnt": "Open-ended tasks without deadlines are still likely to roll forward.",
        "ai_recommendations": [
            "Add due dates to ambiguous tasks.",
            "Keep one 90-minute deep-work block on meeting-heavy days.",
            "Review pending approvals before starting new work.",
        ],
    }


def insights(db: Session, user_id: UUID) -> dict:
    brief = daily_brief(db, user_id)
    return {
        "patterns": [
            {"label": "Best focus window", "value": "14:00-16:00", "confidence": 0.72},
            {"label": "Common blocker", "value": "tasks without source material", "confidence": 0.64},
            {"label": "Planning style", "value": "short checklist then execution", "confidence": 0.81},
        ],
        "next_actions": [
            "Confirm today's top priority.",
            "Review pending approvals.",
            "Schedule one deep-work block.",
        ],
        "brief": brief,
    }


def life_graph(db: Session, user_id: UUID) -> dict:
    memories = (
        db.query(Memory)
        .filter(Memory.user_id == user_id, Memory.is_archived == False)  # noqa: E712
        .order_by(Memory.importance.desc(), Memory.created_at.desc())
        .limit(40)
        .all()
    )
    nodes = [{"id": "user", "label": "You", "type": "person", "strength": 1.0}]
    edges = []
    for memory in memories[:20]:
        node_id = str(memory.id)
        memory_type = memory.memory_type or memory.type or "memory"
        nodes.append({
            "id": node_id,
            "label": memory.content[:72],
            "type": memory_type,
            "strength": float(memory.confidence or 0.6),
        })
        edges.append({"source": "user", "target": node_id, "relationship": memory_type, "weight": int(memory.importance or 5)})
    return {"nodes": nodes, "edges": edges}
