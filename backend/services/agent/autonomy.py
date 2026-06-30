from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy.orm import Session

from services.shared.models import Approval, AuditLog, Task, TaskExecution, UserProfile

from .executor import run_task_execution
from .reflection import run_aar_reflection


AUTONOMY_THRESHOLDS = {
    "observer": {"auto": 95, "notify": 85, "confirm": 60},
    "assistant": {"auto": 88, "notify": 72, "confirm": 50},
    "partner": {"auto": 78, "notify": 60, "confirm": 40},
    "chief_of_staff": {"auto": 68, "notify": 50, "confirm": 30},
}

HARD_APPROVAL_KEYWORDS = (
    "delete",
    "drop table",
    "destroy",
    "send email",
    "email external",
    "send message",
    "slack message",
    "share data",
    "share user data",
    "payment",
    "pay ",
    "purchase",
    "checkout",
    "billing",
    "subscription",
    "push to main",
    "push to master",
    "production",
)


@dataclass
class AutonomyDecision:
    task_id: str
    task_title: str
    impact_score: float
    risk_level: str
    decision: str
    requires_approval: bool
    reasoning: str
    action_type: str = "task_execution"


def _combined_text(task: Task) -> str:
    return f"{task.title or ''} {task.description or ''}".lower()


def _score_factor(text: str, severe: tuple[str, ...], moderate: tuple[str, ...] = ()) -> int:
    if any(keyword in text for keyword in severe):
        return 0
    if any(keyword in text for keyword in moderate):
        return 3
    return 5


def _action_family(text: str) -> str:
    if "search" in text or "research" in text:
        return "research"
    if "calendar" in text or "schedule" in text:
        return "calendar"
    if "email" in text or "message" in text or "slack" in text:
        return "communication"
    if "github" in text or "branch" in text or "pull request" in text or "push" in text:
        return "code_hosting"
    if "file" in text or "code" in text or "implement" in text:
        return "coding"
    if "memory" in text or "remember" in text:
        return "memory"
    return "task"


def _trust_history_score(db: Session, user_id: UUID, action_family: str) -> tuple[int, str]:
    approvals = db.query(Approval).filter(Approval.user_id == user_id).all()
    approved = 0
    rejected = 0
    for approval in approvals:
        payload = approval.payload or {}
        text = " ".join(
            str(payload.get(key, ""))
            for key in ("task_title", "task_description", "action_family")
        ).lower()
        if action_family not in text:
            continue
        if approval.status == "approved":
            approved += 1
        elif approval.status == "rejected":
            rejected += 1

    if rejected:
        return 0, f"previous rejection found for {action_family}"
    if approved >= 10:
        return 5, f"{approved} prior approvals for {action_family}"
    if approved >= 3:
        return 3, f"{approved} prior approvals for {action_family}"
    return 0, "no established trust history"


def get_or_create_user_profile(db: Session, user_id: UUID) -> UserProfile:
    profile = db.query(UserProfile).filter(UserProfile.user_id == user_id).first()
    if profile:
        return profile
    profile = UserProfile(user_id=user_id, autonomy_level="observer")
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def assess_autonomy_decision(db: Session, user_id: UUID, task: Task) -> AutonomyDecision:
    profile = get_or_create_user_profile(db, user_id)
    autonomy_level = profile.autonomy_level or "observer"
    thresholds = AUTONOMY_THRESHOLDS.get(autonomy_level, AUTONOMY_THRESHOLDS["observer"])
    text = _combined_text(task)
    action_family = _action_family(text)

    hard_trigger = any(keyword in text for keyword in HARD_APPROVAL_KEYWORDS)
    reversibility = _score_factor(
        text,
        ("delete", "drop table", "destroy", "send email", "payment", "purchase", "push to main", "push to master"),
        ("create file", "write file", "write code", "schedule event", "create calendar", "create branch", "push to feature"),
    )
    external_impact = _score_factor(
        text,
        ("send email", "email external", "send message", "slack message", "share data", "share user data"),
        ("calendar", "email draft", "integration", "github"),
    )
    financial = _score_factor(
        text,
        ("payment", "pay ", "purchase", "checkout", "billing"),
        ("subscription", "pricing", "signup", "sign up"),
    )
    scope = _score_factor(
        text,
        ("delete database", "drop table", "production", "push to main", "push to master"),
        ("github", "integration", "calendar", "settings"),
    )
    trust_history, trust_reason = _trust_history_score(db, user_id, action_family)

    impact_score = (
        0.35 * reversibility
        + 0.25 * external_impact
        + 0.20 * financial
        + 0.12 * scope
        + 0.08 * trust_history
    ) * 20

    risk_level = "low"
    decision = "autonomous"
    requires_approval = False
    if hard_trigger or impact_score < thresholds["confirm"]:
        risk_level = "high"
        decision = "approval_required"
        requires_approval = True
    elif impact_score < thresholds["notify"]:
        risk_level = "medium"
        decision = "confirm"
        requires_approval = True
    elif impact_score < thresholds["auto"]:
        risk_level = "low"
        decision = "notify"

    reasoning = (
        f"Score {impact_score:.1f} for {action_family}; autonomy={autonomy_level}; "
        f"reversibility={reversibility}, external={external_impact}, financial={financial}, "
        f"scope={scope}, trust={trust_history} ({trust_reason})."
    )
    if hard_trigger:
        reasoning += " Hard approval trigger matched."

    return AutonomyDecision(
        task_id=str(task.id),
        task_title=task.title,
        impact_score=round(impact_score, 2),
        risk_level=risk_level,
        decision=decision,
        requires_approval=requires_approval,
        reasoning=reasoning,
        action_type=f"task_execution:{action_family}",
    )


def _pending_approval(db: Session, user_id: UUID, task_id: UUID) -> Approval | None:
    return db.query(Approval).filter(
        Approval.user_id == user_id,
        Approval.task_id == task_id,
        Approval.status == "pending",
    ).first()


def create_approval_for_task(db: Session, user_id: UUID, task: Task, decision: AutonomyDecision) -> Approval:
    existing = _pending_approval(db, user_id, task.id)
    if existing:
        return existing

    payload = {
        "task_id": str(task.id),
        "task_title": task.title,
        "task_description": task.description,
        "impact_score": decision.impact_score,
        "decision": decision.decision,
        "action_family": decision.action_type,
    }
    approval = Approval(
        user_id=user_id,
        task_id=task.id,
        requested_by_agent="autonomy_engine",
        action_type="task_execution",
        payload=payload,
        action_payload=payload,
        action_description=f"Execute task: {task.title}",
        risk_level=decision.risk_level,
        risk_reasoning=decision.reasoning,
        if_approved="The task will be queued for autonomous execution.",
        if_rejected="The task will be marked failed for now and can be edited or retried manually.",
        alternatives=[
            "Edit the task to reduce external impact.",
            "Run the task manually.",
            "Leave it queued until you raise the autonomy level.",
        ],
        timeout_at=datetime.utcnow() + timedelta(minutes=30),
        status="pending",
    )
    db.add(approval)
    db.flush()
    return approval


def _eligible_tasks(db: Session, user_id: UUID, max_tasks: int) -> list[Task]:
    return db.query(Task).filter(
        Task.user_id == user_id,
        Task.status == "queued",
    ).order_by(Task.priority_score.desc(), Task.created_at.asc()).limit(max_tasks).all()


def _dependency_state(task: Task) -> str:
    for dependency in task.dependencies:
        if dependency.status == "failed":
            return "failed_dependency"
        if dependency.status != "done":
            return "blocked"
    return "ready"


def _log_autonomy_event(db: Session, user_id: UUID, event_type: str, action: str, data: dict) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            event_type=event_type,
            actor_type="autonomy_engine",
            action=action,
            metadata_json=data,
        )
    )


def run_autonomous_cycle(db: Session, user_id: UUID, max_tasks: int = 3, dry_run: bool = False) -> dict:
    get_or_create_user_profile(db, user_id)
    max_tasks = max(1, min(max_tasks, 20))
    tasks = _eligible_tasks(db, user_id, max_tasks)
    results = []

    for task in tasks:
        dependency_state = _dependency_state(task)
        if dependency_state != "ready":
            results.append({
                "task_id": str(task.id),
                "task_title": task.title,
                "decision": "skip",
                "status": task.status,
                "reasoning": dependency_state,
            })
            continue

        decision = assess_autonomy_decision(db, user_id, task)
        result = {
            "task_id": str(task.id),
            "task_title": task.title,
            "decision": decision.decision,
            "risk_level": decision.risk_level,
            "impact_score": decision.impact_score,
            "requires_approval": decision.requires_approval,
            "reasoning": decision.reasoning,
            "status": task.status,
        }

        if dry_run:
            result["action"] = "dry_run_only"
            results.append(result)
            continue

        if decision.requires_approval:
            approval = create_approval_for_task(db, user_id, task, decision)
            task.status = "waiting_approval"
            result["approval_id"] = str(approval.id)
            result["status"] = "waiting_approval"
            result["action"] = "approval_requested"
            _log_autonomy_event(db, user_id, "autonomy_approval_requested", task.title, result)
        else:
            task.status = "in_progress"
            db.flush()
            success = run_task_execution(db, task)
            task.status = "done" if success else "failed"
            task.completed_at = datetime.utcnow() if success else None
            result["status"] = task.status
            result["action"] = "executed"
            try:
                run_aar_reflection(db, task, success)
            except Exception as exc:
                result["reflection_error"] = str(exc)
            _log_autonomy_event(db, user_id, "autonomy_task_executed", task.title, result)

        results.append(result)

    if not dry_run:
        db.commit()

    return {
        "dry_run": dry_run,
        "max_tasks": max_tasks,
        "evaluated": len(results),
        "executed": sum(1 for item in results if item.get("action") == "executed"),
        "approval_required": sum(1 for item in results if item.get("action") == "approval_requested"),
        "results": results,
    }


def get_autonomy_status(db: Session, user_id: UUID) -> dict:
    profile = get_or_create_user_profile(db, user_id)
    queued = db.query(Task).filter(Task.user_id == user_id, Task.status == "queued").count()
    waiting = db.query(Task).filter(Task.user_id == user_id, Task.status == "waiting_approval").count()
    pending_approvals = db.query(Approval).filter(Approval.user_id == user_id, Approval.status == "pending").count()
    recent_executions = db.query(TaskExecution).filter(TaskExecution.user_id == user_id).count()

    return {
        "autonomy_level": profile.autonomy_level or "observer",
        "model_confidence": profile.model_confidence or 0.0,
        "queued_tasks": queued,
        "waiting_approval_tasks": waiting,
        "pending_approvals": pending_approvals,
        "task_executions": recent_executions,
        "thresholds": AUTONOMY_THRESHOLDS.get(profile.autonomy_level or "observer", AUTONOMY_THRESHOLDS["observer"]),
        "guardrails": {
            "hard_approval_keywords": list(HARD_APPROVAL_KEYWORDS),
            "approval_timeout_minutes": 30,
            "safe_default": "reject_on_timeout",
        },
    }
