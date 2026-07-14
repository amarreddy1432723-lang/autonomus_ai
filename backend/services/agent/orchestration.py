from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from services.shared.database import get_db
from services.shared.models import (
    AuditLog,
    CodeProjectDecision,
    CodeProjectOrchestration,
    CodeSolutionProposal,
)

from .code_workspace import (
    active_session_for_project,
    create_code_session,
    get_code_project,
    require_project_role,
    upsert_workspace_task,
)
from .deps import get_current_user_id

router = APIRouter(prefix="/api/v1/code/projects/{project_id}/orchestration", tags=["code-orchestration"])


class OrchestrationAnalyzeRequest(BaseModel):
    problem: str = Field(..., min_length=3)
    business_goal: str = ""
    target_users: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    budget: str = ""
    deadline: str = ""


class ProposalSelectionRequest(BaseModel):
    rationale: str = ""


class ArchitectureApprovalRequest(BaseModel):
    approved: bool = True
    notes: str = ""


class ExecutionTaskRequest(BaseModel):
    task_id: str
    status: str = "typed"


class ReviewBoardRequest(BaseModel):
    notes: str = ""
    approve_ready: bool = False


class DeliveryPackageRequest(BaseModel):
    include_release_notes: bool = True
    target: str = "pull_request"


PERSPECTIVES = [
    {
        "key": "pragmatic",
        "title": "Pragmatic Launch Path",
        "lens": "simplest reliable solution that can launch quickly",
    },
    {
        "key": "platform",
        "title": "Scalable Platform Path",
        "lens": "service boundaries, reliability, observability, and future teams",
    },
    {
        "key": "innovation",
        "title": "Product Differentiation Path",
        "lens": "user value, intelligent automation, and standout product experience",
    },
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _tokens(text: str) -> list[str]:
    return [part.strip(".,:;!?()[]{}").lower() for part in text.split() if len(part.strip(".,:;!?()[]{}")) > 2]


def _infer_domain(problem: str) -> dict[str, Any]:
    text = problem.lower()
    tags = []
    if any(word in text for word in ("payment", "stripe", "checkout", "subscription", "billing")):
        tags.extend(["payments", "security"])
    if any(word in text for word in ("health", "medical", "doctor", "patient", "clinic")):
        tags.extend(["healthcare", "privacy", "security"])
    if any(word in text for word in ("chat", "live", "realtime", "socket", "tracking")):
        tags.append("realtime")
    if any(word in text for word in ("mobile", "android", "ios", "phone")):
        tags.append("mobile")
    if any(word in text for word in ("marketplace", "vendor", "seller", "buyer")):
        tags.append("marketplace")
    if any(word in text for word in ("ai", "agent", "automation", "recommend")):
        tags.append("ai")
    return {"tags": sorted(set(tags)), "keywords": _tokens(problem)[:18]}


def _criteria(request: OrchestrationAnalyzeRequest) -> list[str]:
    criteria = [item.strip() for item in request.acceptance_criteria if item.strip()]
    if criteria:
        return criteria[:12]
    return [
        "Core user journey is implemented end to end.",
        "Important data is persisted safely.",
        "Build and focused checks pass.",
        "User can review changes before approval.",
    ]


def _proposal_for(request: OrchestrationAnalyzeRequest, perspective: dict[str, str], domain: dict[str, Any]) -> dict[str, Any]:
    tags = domain["tags"]
    problem = request.problem.strip()
    base_architecture = [
        "Next.js interface for the primary workflow",
        "FastAPI backend with explicit domain services",
        "PostgreSQL for durable state",
        "Redis for queues, locks, and streaming events",
        "Docker sandbox for checks and risky execution",
    ]
    if "realtime" in tags:
        base_architecture.append("WebSocket/SSE channel for realtime updates")
    if "payments" in tags:
        base_architecture.append("Stripe billing boundary with webhook verification")
    if "ai" in tags:
        base_architecture.append("Task-scoped agent tools with work receipts and approval gates")

    key = perspective["key"]
    if key == "pragmatic":
        return {
            "title": perspective["title"],
            "summary": f"Launch the smallest reliable version of: {problem}",
            "architecture": "\n".join(base_architecture[:5]),
            "advantages": ["Fastest to ship", "Lower operating cost", "Easy to review and maintain"],
            "disadvantages": ["May need later modularization", "Some enterprise controls are deferred"],
            "estimated_cost": "low",
            "estimated_complexity": "medium",
            "risks": ["Scope creep", "Insufficient test coverage if milestones are rushed"],
            "recommended_for": "First production version or founder-led validation.",
        }
    if key == "platform":
        return {
            "title": perspective["title"],
            "summary": f"Build a scalable foundation for: {problem}",
            "architecture": "\n".join(base_architecture + ["Module boundaries for auth, billing, jobs, audit, and integrations"]),
            "advantages": ["Stronger reliability", "Better observability", "Easier team scaling"],
            "disadvantages": ["Slower first release", "More infrastructure decisions up front"],
            "estimated_cost": "medium-high",
            "estimated_complexity": "high",
            "risks": ["Premature abstraction", "Longer feedback loop before users can try it"],
            "recommended_for": "Products with enterprise, compliance, or multi-team expectations.",
        }
    return {
        "title": perspective["title"],
        "summary": f"Differentiate the product experience around: {problem}",
        "architecture": "\n".join(base_architecture + ["Guidance engine for next-best actions", "Product analytics loop for user outcomes"]),
        "advantages": ["Clearer market differentiation", "Stronger user guidance", "More memorable UX"],
        "disadvantages": ["Higher design risk", "Needs careful guardrails to avoid over-automation"],
        "estimated_cost": "medium",
        "estimated_complexity": "medium-high",
        "risks": ["Novel UX may require iteration", "Harder to evaluate than standard CRUD"],
        "recommended_for": "Products where decision support is the core advantage.",
    }


def _score_proposal(proposal: dict[str, Any], request: OrchestrationAnalyzeRequest, perspective: str) -> tuple[int, str]:
    score = 70
    problem = request.problem.lower()
    if perspective == "pragmatic":
        score += 8
    if perspective == "platform" and any(word in problem for word in ("enterprise", "scale", "team", "compliance", "production")):
        score += 10
    if perspective == "innovation" and any(word in problem for word in ("ai", "agent", "automate", "recommend", "unique")):
        score += 10
    if request.deadline:
        score += 4 if perspective == "pragmatic" else -2
    if len(request.constraints) > 3 and perspective == "platform":
        score += 5
    score = max(0, min(100, score))
    if score >= 85:
        reason = "Best fit for the stated constraints and project stage."
    elif score >= 78:
        reason = "Strong option with manageable trade-offs."
    else:
        reason = "Useful alternative, but not the default recommendation."
    return score, reason


def _get_or_create_state(db: Session, user_id: UUID, project_id: UUID) -> CodeProjectOrchestration:
    state = (
        db.query(CodeProjectOrchestration)
        .filter(CodeProjectOrchestration.user_id == user_id, CodeProjectOrchestration.project_id == project_id)
        .order_by(CodeProjectOrchestration.updated_at.desc(), CodeProjectOrchestration.created_at.desc())
        .first()
    )
    if state:
        return state
    state = CodeProjectOrchestration(user_id=user_id, project_id=project_id, stage="intake")
    db.add(state)
    db.commit()
    db.refresh(state)
    return state


def _serialize_state(db: Session, state: CodeProjectOrchestration) -> dict[str, Any]:
    proposals = (
        db.query(CodeSolutionProposal)
        .filter(CodeSolutionProposal.orchestration_id == state.id)
        .order_by(CodeSolutionProposal.score.desc(), CodeSolutionProposal.created_at.asc())
        .all()
    )
    decisions = (
        db.query(CodeProjectDecision)
        .filter(CodeProjectDecision.orchestration_id == state.id)
        .order_by(CodeProjectDecision.created_at.desc())
        .limit(20)
        .all()
    )
    return {
        "id": str(state.id),
        "project_id": str(state.project_id),
        "stage": state.stage,
        "original_problem": state.original_problem or "",
        "clarified_problem": state.clarified_problem or "",
        "business_goal": state.business_goal or "",
        "target_users": state.target_users or [],
        "constraints": state.constraints or [],
        "acceptance_criteria": state.acceptance_criteria or [],
        "selected_proposal_id": str(state.selected_proposal_id) if state.selected_proposal_id else None,
        "architecture_document": state.architecture_document or {},
        "implementation_plan": state.implementation_plan or {},
        "tasks": state.tasks or [],
        "review_findings": state.review_findings or [],
        "test_results": state.test_results or [],
        "budget_used_usd": state.budget_used_usd or 0,
        "token_usage": state.token_usage or 0,
        "proposals": [_serialize_proposal(item) for item in proposals],
        "decisions": [
            {
                "id": str(item.id),
                "decision_type": item.decision_type,
                "title": item.title,
                "selected_option_id": str(item.selected_option_id) if item.selected_option_id else None,
                "rationale": item.rationale or "",
                "payload": item.payload or {},
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in decisions
        ],
        "updated_at": state.updated_at.isoformat() if state.updated_at else None,
    }


def _serialize_proposal(proposal: CodeSolutionProposal) -> dict[str, Any]:
    return {
        "id": str(proposal.id),
        "perspective": proposal.perspective,
        "title": proposal.title,
        "summary": proposal.summary or "",
        "architecture": proposal.architecture or "",
        "advantages": proposal.advantages or [],
        "disadvantages": proposal.disadvantages or [],
        "estimated_cost": proposal.estimated_cost or "",
        "estimated_complexity": proposal.estimated_complexity or "",
        "risks": proposal.risks or [],
        "recommended_for": proposal.recommended_for or "",
        "score": proposal.score or 0,
        "judge_summary": proposal.judge_summary or "",
        "metadata": proposal.metadata_json or {},
    }


def _architecture_from(proposal: CodeSolutionProposal, state: CodeProjectOrchestration) -> dict[str, Any]:
    return {
        "title": proposal.title,
        "summary": proposal.summary,
        "selected_perspective": proposal.perspective,
        "components": [line for line in (proposal.architecture or "").splitlines() if line.strip()],
        "quality_gates": [
            "Work receipt generated for each implementation task",
            "Diff review before file changes are applied",
            "Focused checks run after implementation",
            "Human approval required before PR/deploy",
        ],
        "risks": proposal.risks or [],
        "acceptance_criteria": state.acceptance_criteria or [],
        "created_at": _now(),
    }


def _tasks_from(proposal: CodeSolutionProposal, state: CodeProjectOrchestration) -> list[dict[str, Any]]:
    criteria = state.acceptance_criteria or []
    selected_components = [line for line in (proposal.architecture or "").splitlines() if line.strip()]
    return [
        {
            "id": "T1",
            "title": "Confirm requirements and acceptance criteria",
            "assigned_role": "product_lead",
            "depends_on": [],
            "status": "ready",
            "mode": "plan",
            "risk": "low",
            "expected_files": [],
            "expected_commands": [],
            "acceptance_criteria": criteria[:4] or ["Problem statement is clarified"],
        },
        {
            "id": "T2",
            "title": "Create architecture skeleton",
            "assigned_role": "solution_architect",
            "depends_on": ["T1"],
            "status": "ready",
            "mode": "plan",
            "risk": "medium",
            "expected_files": ["architecture notes", "folder structure"],
            "expected_commands": [],
            "acceptance_criteria": [
                "Architecture matches selected proposal",
                "Risks and trade-offs are documented",
                *selected_components[:3],
            ],
        },
        {
            "id": "T3",
            "title": "Implement first bounded task",
            "assigned_role": "coding_agent",
            "depends_on": ["T2"],
            "status": "ready",
            "mode": "code",
            "risk": "medium",
            "expected_files": ["smallest impacted files after inspection"],
            "expected_commands": ["Run discovered build/test/lint checks"],
            "acceptance_criteria": [
                "Files changed are reviewable",
                "Focused checks pass",
                "Rollback remains available",
            ],
        },
        {
            "id": "T4",
            "title": "Run review board",
            "assigned_role": "review_board",
            "depends_on": ["T3"],
            "status": "blocked",
            "mode": "plan",
            "risk": "low",
            "expected_files": [],
            "expected_commands": ["Run focused checks if not already run"],
            "acceptance_criteria": ["Requirements, security, tests, and maintainability reviewed"],
        },
    ]


def _task_prompt(state: CodeProjectOrchestration, task: dict[str, Any]) -> str:
    architecture = state.architecture_document or {}
    components = architecture.get("components") or []
    criteria = task.get("acceptance_criteria") or state.acceptance_criteria or []
    steps = [
        f"Execute Arceus engineering task {task.get('id')}: {task.get('title')}",
        "",
        f"Project goal: {state.clarified_problem or state.original_problem}",
        f"Role lens: {task.get('assigned_role') or 'coding_agent'}",
        "",
        "Selected architecture:",
        *[f"- {item}" for item in components[:8]],
        "",
        "Acceptance criteria:",
        *[f"- {item}" for item in criteria[:8]],
        "",
        "Execution rules:",
        "- Inspect the relevant files before changing anything.",
        "- Keep the change bounded to this task.",
        "- Produce a work receipt with inspected files, changed files, line impact, commands, checks, and next actions.",
        "- Prepare reviewable patches only; do not apply without approval.",
    ]
    commands = task.get("expected_commands") or []
    if commands:
        steps.extend(["", "Expected checks or commands:", *[f"- {item}" for item in commands]])
    return "\n".join(steps).strip()


def _workspace_task_payload(state: CodeProjectOrchestration, task: dict[str, Any]) -> dict[str, Any]:
    prompt = task.get("suggested_prompt") or _task_prompt(state, task)
    criteria = task.get("acceptance_criteria") or []
    return {
        "id": task.get("workspace_task_id") or task.get("id"),
        "title": task.get("title") or "Engineering task",
        "description": f"{task.get('assigned_role') or 'agent'} task from the approved Arceus engineering plan.",
        "summary": "; ".join(criteria[:2]) or task.get("title") or "",
        "mode": task.get("mode") or ("code" if task.get("assigned_role") == "coding_agent" else "plan"),
        "risk": task.get("risk") or "medium",
        "requires_approval": True,
        "files": task.get("expected_files") or [],
        "folders": task.get("expected_folders") or [],
        "steps": [
            f"Confirm task scope: {task.get('title')}",
            "Inspect relevant files and current project state",
            "Prepare the smallest reviewable output",
            "Report work receipt and recommended checks",
        ],
        "commands": task.get("expected_commands") or [],
        "expected_commands": task.get("expected_commands") or [],
        "suggested_prompt": prompt,
        "prompt": prompt,
        "impact": "Links approved architecture to one bounded agent execution.",
        "file_hint": ", ".join(task.get("expected_files") or []) or "Infer from project files",
        "check_hint": ", ".join(task.get("expected_commands") or []) or "Recommend focused checks",
        "confidence": 0.82,
        "decision_reason": "Generated from the selected architecture and task graph.",
        "tradeoffs": ["Keeps execution bounded", "Requires user approval before applying changes"],
        "thinking_prompt": "What file evidence proves this task is complete?",
        "coach_lens": ["architecture", "maintainability", "verification"],
        "alternatives": ["Split this task smaller", "Run review board first"],
        "next_after_done": "Review the work receipt, apply approved changes, then run focused checks.",
        "metadata": {
            "source": "engineering_org",
            "orchestration_id": str(state.id),
            "orchestration_task_id": task.get("id"),
            "selected_proposal_id": str(state.selected_proposal_id) if state.selected_proposal_id else None,
            "assigned_role": task.get("assigned_role"),
            "acceptance_criteria": criteria,
            "depends_on": task.get("depends_on") or [],
        },
    }


def _ensure_active_session(db: Session, user_id: UUID, project_id: UUID):
    project = get_code_project(db, user_id, project_id)
    require_project_role(db, user_id, project_id, "editor")
    session = active_session_for_project(db, user_id, project)
    if session:
        return session
    return create_code_session(db, user_id, f"{project.name} Agent", project.file_ids or [], project_id=project.id)


def _update_task_in_state(state: CodeProjectOrchestration, task_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    tasks = list(state.tasks or [])
    for index, task in enumerate(tasks):
        if str(task.get("id")) != task_id:
            continue
        next_task = {**task, **updates, "updated_at": _now()}
        tasks[index] = next_task
        state.tasks = tasks
        return next_task
    raise HTTPException(status_code=404, detail="Engineering task not found")


def _session_metadata(session) -> dict[str, Any]:
    return dict(session.metadata_json or {})


def _workspace_tasks_from_session(session) -> list[dict[str, Any]]:
    tasks = _session_metadata(session).get("workspace_tasks") or []
    return [task for task in tasks if isinstance(task, dict)]


def _workspace_status_to_engineering(status: str) -> str:
    value = (status or "").lower()
    if value in {"done", "failed", "dismissed", "waiting_approval", "typed", "accepted", "running"}:
        return value
    if value == "suggested":
        return "ready"
    return "ready"


def _latest_task_receipt(metadata: dict[str, Any], workspace_task_id: str | None) -> dict[str, Any]:
    if not workspace_task_id:
        return {}
    for event in reversed(metadata.get("activity_log") or []):
        if str(event.get("task_id") or "") != str(workspace_task_id):
            continue
        receipt = event.get("work_receipt") or {}
        if receipt:
            return receipt
    return {}


def _task_execution_evidence(session, workspace_task: dict[str, Any] | None) -> dict[str, Any]:
    if not workspace_task:
        return {"status": "not_materialized", "files_changed": [], "commands": [], "checks": [], "line_impact": {"additions": 0, "deletions": 0}}
    metadata = _session_metadata(session)
    workspace_task_id = str(workspace_task.get("id") or "")
    receipt = _latest_task_receipt(metadata, workspace_task_id)
    task_meta = workspace_task.get("metadata") or {}
    last_apply = task_meta.get("last_apply") or {}
    files_changed = receipt.get("files_changed") or last_apply.get("changed_files") or []
    commands = receipt.get("commands_run") or workspace_task.get("expected_commands") or workspace_task.get("commands") or []
    checks = receipt.get("checks") or []
    line_impact = receipt.get("line_impact") or {
        "additions": int(last_apply.get("total_additions") or 0),
        "deletions": int(last_apply.get("total_deletions") or 0),
    }
    return {
        "status": workspace_task.get("status") or "suggested",
        "workspace_task_id": workspace_task_id,
        "files_changed": files_changed,
        "commands": commands,
        "checks": checks,
        "line_impact": line_impact,
        "approval_state": receipt.get("approval_state") or ("done" if workspace_task.get("status") == "done" else workspace_task.get("status")),
        "last_apply": last_apply,
        "last_receipt": receipt,
        "updated_at": workspace_task.get("updated_at"),
    }


def _sync_tasks_from_workspace(state: CodeProjectOrchestration, session) -> dict[str, Any]:
    metadata = _session_metadata(session)
    workspace_tasks = _workspace_tasks_from_session(session)
    by_id = {str(task.get("id")): task for task in workspace_tasks if task.get("id")}
    by_orchestration_id = {
        str((task.get("metadata") or {}).get("orchestration_task_id")): task
        for task in workspace_tasks
        if (task.get("metadata") or {}).get("orchestration_task_id")
    }
    tasks = list(state.tasks or [])
    synced: list[dict[str, Any]] = []
    done_ids: set[str] = set()
    for index, task in enumerate(tasks):
        task_id = str(task.get("id") or "")
        workspace_task = by_id.get(str(task.get("workspace_task_id") or "")) or by_orchestration_id.get(task_id)
        evidence = _task_execution_evidence(session, workspace_task)
        status = _workspace_status_to_engineering(evidence.get("status") or task.get("status") or "ready")
        if task.get("status") == "blocked" and not workspace_task:
            status = "blocked"
        next_task = {
            **task,
            "workspace_status": evidence.get("status"),
            "status": status,
            "execution_evidence": evidence,
            "progress": {
                "files_changed": len(evidence.get("files_changed") or []),
                "commands": len(evidence.get("commands") or []),
                "checks": len(evidence.get("checks") or []),
                "additions": (evidence.get("line_impact") or {}).get("additions") or 0,
                "deletions": (evidence.get("line_impact") or {}).get("deletions") or 0,
            },
            "updated_at": _now(),
        }
        if workspace_task and workspace_task.get("id"):
            next_task["workspace_task_id"] = str(workspace_task["id"])
            next_task["workspace_session_id"] = str(session.id)
        if status == "done":
            done_ids.add(task_id)
            next_task.setdefault("completed_at", _now())
        tasks[index] = next_task
        synced.append(next_task)

    for index, task in enumerate(tasks):
        if task.get("status") != "blocked":
            continue
        dependencies = [str(dep) for dep in (task.get("depends_on") or [])]
        if dependencies and all(dep in done_ids for dep in dependencies):
            tasks[index] = {**task, "status": "ready", "unblocked_at": _now(), "updated_at": _now()}

    state.tasks = tasks
    total = len(tasks)
    completed = len([task for task in tasks if task.get("status") == "done"])
    failed = len([task for task in tasks if task.get("status") == "failed"])
    waiting_approval = len([task for task in tasks if task.get("status") == "waiting_approval"])
    state.implementation_plan = {
        **(state.implementation_plan or {}),
        "workspace_session_id": str(session.id),
        "last_synced_at": _now(),
        "progress": {
            "total": total,
            "completed": completed,
            "failed": failed,
            "waiting_approval": waiting_approval,
            "percent": round((completed / total) * 100, 2) if total else 0,
        },
    }
    latest_receipts = [
        event.get("work_receipt")
        for event in (metadata.get("activity_log") or [])[-20:]
        if isinstance(event, dict) and event.get("work_receipt")
    ]
    state.test_results = latest_receipts[-8:]
    if failed:
        state.stage = "review"
    elif completed == total and total:
        state.stage = "review"
    elif waiting_approval:
        state.stage = "waiting_approval"
    else:
        state.stage = "execution"
    return state.implementation_plan["progress"]


def _review_board_findings(state: CodeProjectOrchestration, notes: str = "") -> list[dict[str, Any]]:
    tasks = state.tasks or []
    findings: list[dict[str, Any]] = []
    for task in tasks:
        evidence = task.get("execution_evidence") or {}
        progress = task.get("progress") or {}
        status = task.get("status") or "unknown"
        severity = "info"
        message = "Task has not produced execution evidence yet."
        if status == "done":
            message = f"{task.get('id')} completed with {progress.get('files_changed', 0)} file(s) changed and +{progress.get('additions', 0)} / -{progress.get('deletions', 0)} lines."
        elif status == "waiting_approval":
            severity = "warning"
            message = f"{task.get('id')} is waiting for patch approval before it can count as complete."
        elif status == "failed":
            severity = "error"
            message = f"{task.get('id')} failed. Review terminal/jobs evidence before continuing."
        elif status in {"typed", "accepted", "running"}:
            severity = "warning"
            message = f"{task.get('id')} is in progress and needs a final receipt/check."
        findings.append({
            "task_id": task.get("id"),
            "title": task.get("title"),
            "severity": severity,
            "status": status,
            "message": message,
            "approval_state": evidence.get("approval_state"),
        })
    if notes:
        findings.append({"task_id": None, "title": "Review notes", "severity": "info", "status": "noted", "message": notes})
    return findings


def _delivery_package(state: CodeProjectOrchestration, session, target: str = "pull_request") -> dict[str, Any]:
    tasks = state.tasks or []
    architecture = state.architecture_document or {}
    progress = (state.implementation_plan or {}).get("progress") or {}
    findings = state.review_findings or []
    completed = [task for task in tasks if task.get("status") == "done"]
    waiting = [task for task in tasks if task.get("status") == "waiting_approval"]
    failed = [task for task in tasks if task.get("status") == "failed"]
    files_changed: list[dict[str, Any]] = []
    total_additions = 0
    total_deletions = 0
    commands: list[Any] = []
    checks: list[Any] = []
    for task in tasks:
        evidence = task.get("execution_evidence") or {}
        for file_item in evidence.get("files_changed") or []:
            if isinstance(file_item, dict):
                files_changed.append(file_item)
                total_additions += int(file_item.get("additions") or 0)
                total_deletions += int(file_item.get("deletions") or 0)
        for command in evidence.get("commands") or []:
            commands.append(command)
        for check in evidence.get("checks") or []:
            checks.append(check)

    title_base = architecture.get("title") or state.clarified_problem or state.original_problem or "Arceus engineering update"
    pr_title = f"{title_base}".strip()[:88]
    checklist = [
        {"label": "Architecture approved", "done": bool((architecture.get("approval") or {}).get("approved"))},
        {"label": "Execution tasks synced", "done": bool((state.implementation_plan or {}).get("last_synced_at"))},
        {"label": "No failed engineering tasks", "done": not failed},
        {"label": "No pending approval tasks", "done": not waiting},
        {"label": "Review board completed", "done": bool(findings)},
    ]
    risk_summary = [
        finding.get("message")
        for finding in findings
        if finding.get("severity") in {"warning", "error"}
    ] or ["No review-board blockers recorded."]
    changed_lines = f"+{total_additions} / -{total_deletions}"
    body_lines = [
        "## Summary",
        state.clarified_problem or state.original_problem or "Prepared reviewed Arceus Code workspace changes.",
        "",
        "## Engineering Plan",
        f"- Stage: {state.stage}",
        f"- Architecture: {architecture.get('title') or 'Selected architecture'}",
        f"- Progress: {progress.get('completed', 0)}/{progress.get('total', len(tasks))} tasks complete ({progress.get('percent', 0)}%)",
        "",
        "## Task Evidence",
        *[
            f"- {task.get('id')}: {task.get('title')} — {task.get('status')} ({(task.get('progress') or {}).get('files_changed', 0)} files)"
            for task in tasks
        ],
        "",
        "## Impact",
        f"- Files changed: {len(files_changed)}",
        f"- Line impact: {changed_lines}",
        f"- Commands/checks captured: {len(commands)} commands, {len(checks)} checks",
        "",
        "## Review Board",
        *[f"- [{item.get('severity', 'info')}] {item.get('message')}" for item in findings[:10]],
        "",
        "## Checklist",
        *[f"- [{'x' if item['done'] else ' '}] {item['label']}" for item in checklist],
    ]
    release_notes = [
        "### Changed",
        *[f"- {task.get('title')}" for task in completed[:8]],
        "",
        "### Validation",
        f"- Captured {len(checks)} check item(s) and {len(commands)} command item(s).",
        "",
        "### Risks",
        *[f"- {item}" for item in risk_summary[:6]],
    ]
    return {
        "target": target,
        "title": pr_title,
        "commit_message": pr_title[:72],
        "body": "\n".join(body_lines).strip(),
        "release_notes": "\n".join(release_notes).strip(),
        "checklist": checklist,
        "risk_summary": risk_summary,
        "impact": {
            "files_changed": len(files_changed),
            "additions": total_additions,
            "deletions": total_deletions,
            "commands": len(commands),
            "checks": len(checks),
        },
        "ready": all(item["done"] for item in checklist),
        "session_id": str(session.id),
        "created_at": _now(),
    }


@router.get("/state")
def get_orchestration_state(project_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    get_code_project(db, user_id, project_id)
    state = _get_or_create_state(db, user_id, project_id)
    return _serialize_state(db, state)


@router.post("/analyze", status_code=201)
def analyze_project_problem(
    project_id: UUID,
    request: OrchestrationAnalyzeRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    get_code_project(db, user_id, project_id)
    state = _get_or_create_state(db, user_id, project_id)
    domain = _infer_domain(request.problem)
    state.stage = "waiting_for_user"
    state.original_problem = request.problem.strip()
    state.clarified_problem = f"Build a production-minded solution for: {request.problem.strip()}"
    state.business_goal = request.business_goal or "Deliver a useful, testable first version with clear approval gates."
    state.target_users = request.target_users
    state.constraints = [*request.constraints, *([f"Budget: {request.budget}"] if request.budget else []), *([f"Deadline: {request.deadline}"] if request.deadline else [])]
    state.acceptance_criteria = _criteria(request)
    state.metadata_json = {"domain": domain, "proposal_judge": "weighted_static_v1", "updated_at": _now()}
    db.add(state)
    db.query(CodeSolutionProposal).filter(CodeSolutionProposal.orchestration_id == state.id).delete()
    db.flush()
    for perspective in PERSPECTIVES:
        payload = _proposal_for(request, perspective, domain)
        score, reason = _score_proposal(payload, request, perspective["key"])
        db.add(CodeSolutionProposal(
            orchestration_id=state.id,
            project_id=project_id,
            user_id=user_id,
            perspective=perspective["key"],
            score=score,
            judge_summary=reason,
            metadata_json={"lens": perspective["lens"], "domain": domain},
            **payload,
        ))
    db.add(AuditLog(
        user_id=user_id,
        event_type="code.orchestration.analyze",
        entity_type="code_project",
        entity_id=project_id,
        actor_type="user",
        actor_id=str(user_id),
        action="Generated three engineering proposals",
        new_value={"problem": request.problem, "domain": domain},
    ))
    db.commit()
    db.refresh(state)
    return _serialize_state(db, state)


@router.get("/proposals")
def list_project_proposals(project_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    get_code_project(db, user_id, project_id)
    state = _get_or_create_state(db, user_id, project_id)
    return {"project_id": str(project_id), "proposals": _serialize_state(db, state)["proposals"]}


@router.post("/proposals/{proposal_id}/select")
def select_project_proposal(
    project_id: UUID,
    proposal_id: UUID,
    request: ProposalSelectionRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    get_code_project(db, user_id, project_id)
    state = _get_or_create_state(db, user_id, project_id)
    proposal = (
        db.query(CodeSolutionProposal)
        .filter(CodeSolutionProposal.id == proposal_id, CodeSolutionProposal.orchestration_id == state.id)
        .first()
    )
    if not proposal:
        raise HTTPException(status_code=404, detail="Proposal not found")
    state.selected_proposal_id = proposal.id
    state.stage = "architecture"
    state.architecture_document = _architecture_from(proposal, state)
    state.implementation_plan = {
        "title": f"Execution plan for {proposal.title}",
        "task_order": ["T1", "T2", "T3", "T4"],
        "parallelizable": [],
        "approval_required": True,
        "created_at": _now(),
    }
    state.tasks = _tasks_from(proposal, state)
    decision = CodeProjectDecision(
        orchestration_id=state.id,
        project_id=project_id,
        user_id=user_id,
        decision_type="proposal_selection",
        title=f"Selected {proposal.title}",
        selected_option_id=proposal.id,
        rationale=request.rationale or proposal.judge_summary or "User selected this proposal.",
        payload={"proposal": _serialize_proposal(proposal)},
    )
    decisions = list(state.decisions or [])
    decisions.append({"type": decision.decision_type, "proposal_id": str(proposal.id), "title": decision.title, "created_at": _now()})
    state.decisions = decisions[-40:]
    db.add(decision)
    db.add(AuditLog(
        user_id=user_id,
        event_type="code.orchestration.select_proposal",
        entity_type="code_project",
        entity_id=project_id,
        actor_type="user",
        actor_id=str(user_id),
        action="Selected engineering proposal",
        new_value={"proposal_id": str(proposal.id), "title": proposal.title},
    ))
    db.commit()
    db.refresh(state)
    return _serialize_state(db, state)


@router.post("/architecture/approve")
def approve_project_architecture(
    project_id: UUID,
    request: ArchitectureApprovalRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    get_code_project(db, user_id, project_id)
    state = _get_or_create_state(db, user_id, project_id)
    if not state.selected_proposal_id:
        raise HTTPException(status_code=409, detail="Select a proposal before approving architecture")
    state.stage = "planning" if request.approved else "waiting_for_user"
    architecture = dict(state.architecture_document or {})
    architecture["approval"] = {"approved": request.approved, "notes": request.notes, "decided_at": _now()}
    state.architecture_document = architecture
    db.add(CodeProjectDecision(
        orchestration_id=state.id,
        project_id=project_id,
        user_id=user_id,
        decision_type="architecture_approval",
        title="Architecture approved" if request.approved else "Architecture sent back",
        selected_option_id=state.selected_proposal_id,
        rationale=request.notes,
        payload={"approved": request.approved, "architecture": architecture},
    ))
    db.commit()
    db.refresh(state)
    return _serialize_state(db, state)


@router.post("/tasks/materialize")
def materialize_project_tasks(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    session = _ensure_active_session(db, user_id, project_id)
    state = _get_or_create_state(db, user_id, project_id)
    if not state.selected_proposal_id or not (state.architecture_document or {}).get("approval", {}).get("approved"):
        raise HTTPException(status_code=409, detail="Approve an architecture before materializing execution tasks")
    materialized = []
    tasks = list(state.tasks or [])
    for index, task in enumerate(tasks):
        payload = _workspace_task_payload(state, task)
        workspace_task = upsert_workspace_task(db, user_id, session, payload, status=task.get("workspace_status") or "suggested")
        task = {
            **task,
            "workspace_task_id": workspace_task["id"],
            "workspace_session_id": str(session.id),
            "suggested_prompt": payload["suggested_prompt"],
            "workspace_status": workspace_task["status"],
            "handoff_ready": True,
            "updated_at": _now(),
        }
        tasks[index] = task
        materialized.append(workspace_task)
    state.stage = "execution_ready"
    state.tasks = tasks
    state.implementation_plan = {
        **(state.implementation_plan or {}),
        "workspace_session_id": str(session.id),
        "materialized_at": _now(),
        "task_count": len(materialized),
    }
    db.add(AuditLog(
        user_id=user_id,
        event_type="code.orchestration.materialize_tasks",
        entity_type="code_project",
        entity_id=project_id,
        actor_type="user",
        actor_id=str(user_id),
        action="Materialized engineering tasks into workspace task rail",
        new_value={"session_id": str(session.id), "task_count": len(materialized)},
    ))
    db.commit()
    db.refresh(state)
    return {
        "session_id": str(session.id),
        "workspace_tasks": materialized,
        "orchestration": _serialize_state(db, state),
    }


@router.post("/tasks/type")
def type_project_execution_task(
    project_id: UUID,
    request: ExecutionTaskRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    if request.status not in {"typed", "accepted"}:
        raise HTTPException(status_code=400, detail="Task handoff status must be typed or accepted")
    session = _ensure_active_session(db, user_id, project_id)
    state = _get_or_create_state(db, user_id, project_id)
    if not state.selected_proposal_id:
        raise HTTPException(status_code=409, detail="Select a proposal before handing off execution")
    task = next((item for item in (state.tasks or []) if str(item.get("id")) == request.task_id), None)
    if not task:
        raise HTTPException(status_code=404, detail="Engineering task not found")
    if task.get("status") == "blocked":
        raise HTTPException(status_code=409, detail="This engineering task is blocked by an earlier dependency")
    payload = _workspace_task_payload(state, task)
    workspace_task = upsert_workspace_task(db, user_id, session, payload, status=request.status)
    updated_task = _update_task_in_state(state, request.task_id, {
        "workspace_task_id": workspace_task["id"],
        "workspace_session_id": str(session.id),
        "suggested_prompt": payload["suggested_prompt"],
        "workspace_status": workspace_task["status"],
        "status": "typed" if request.status == "typed" else "running",
        "handoff_ready": True,
        "last_handoff_at": _now(),
    })
    state.stage = "execution"
    db.add(CodeProjectDecision(
        orchestration_id=state.id,
        project_id=project_id,
        user_id=user_id,
        decision_type="task_handoff",
        title=f"Typed {updated_task.get('id')}: {updated_task.get('title')}",
        selected_option_id=state.selected_proposal_id,
        rationale="Prepared this engineering task for agent execution.",
        payload={"workspace_task": workspace_task, "engineering_task": updated_task},
    ))
    db.commit()
    db.refresh(state)
    return {
        "session_id": str(session.id),
        "workspace_task": workspace_task,
        "engineering_task": updated_task,
        "orchestration": _serialize_state(db, state),
    }


@router.post("/tasks/sync-progress")
def sync_project_execution_progress(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    session = _ensure_active_session(db, user_id, project_id)
    state = _get_or_create_state(db, user_id, project_id)
    progress = _sync_tasks_from_workspace(state, session)
    db.add(AuditLog(
        user_id=user_id,
        event_type="code.orchestration.sync_progress",
        entity_type="code_project",
        entity_id=project_id,
        actor_type="user",
        actor_id=str(user_id),
        action="Synced orchestration progress from workspace receipts",
        new_value={"session_id": str(session.id), "progress": progress},
    ))
    db.commit()
    db.refresh(state)
    return {
        "session_id": str(session.id),
        "progress": progress,
        "orchestration": _serialize_state(db, state),
    }


@router.post("/review-board")
def run_project_review_board(
    project_id: UUID,
    request: ReviewBoardRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    session = _ensure_active_session(db, user_id, project_id)
    state = _get_or_create_state(db, user_id, project_id)
    progress = _sync_tasks_from_workspace(state, session)
    findings = _review_board_findings(state, request.notes)
    blockers = [item for item in findings if item.get("severity") == "error"]
    warnings = [item for item in findings if item.get("severity") == "warning"]
    state.review_findings = findings
    state.stage = "ready_for_pr" if request.approve_ready and not blockers and not warnings else "review"
    db.add(CodeProjectDecision(
        orchestration_id=state.id,
        project_id=project_id,
        user_id=user_id,
        decision_type="review_board",
        title="Review board completed",
        selected_option_id=state.selected_proposal_id,
        rationale=request.notes or "Review board synthesized task, receipt, and check evidence.",
        payload={
            "approved_ready": request.approve_ready and not blockers and not warnings,
            "progress": progress,
            "findings": findings,
        },
    ))
    db.add(AuditLog(
        user_id=user_id,
        event_type="code.orchestration.review_board",
        entity_type="code_project",
        entity_id=project_id,
        actor_type="user",
        actor_id=str(user_id),
        action="Ran engineering review board",
        new_value={"findings": len(findings), "blockers": len(blockers), "warnings": len(warnings)},
    ))
    db.commit()
    db.refresh(state)
    return {
        "session_id": str(session.id),
        "progress": progress,
        "findings": findings,
        "blockers": len(blockers),
        "warnings": len(warnings),
        "orchestration": _serialize_state(db, state),
    }


@router.post("/delivery-package")
def prepare_project_delivery_package(
    project_id: UUID,
    request: DeliveryPackageRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
):
    session = _ensure_active_session(db, user_id, project_id)
    state = _get_or_create_state(db, user_id, project_id)
    progress = _sync_tasks_from_workspace(state, session)
    if not state.review_findings:
        state.review_findings = _review_board_findings(state)
    package = _delivery_package(state, session, request.target)
    state.stage = "delivery_ready" if package["ready"] else "delivery_review"
    state.implementation_plan = {
        **(state.implementation_plan or {}),
        "progress": progress,
        "delivery_package": package,
        "delivery_prepared_at": _now(),
    }
    db.add(CodeProjectDecision(
        orchestration_id=state.id,
        project_id=project_id,
        user_id=user_id,
        decision_type="delivery_package",
        title=f"Prepared {request.target} package",
        selected_option_id=state.selected_proposal_id,
        rationale="Generated delivery package from architecture, task receipts, review findings, and checks.",
        payload=package,
    ))
    db.add(AuditLog(
        user_id=user_id,
        event_type="code.orchestration.delivery_package",
        entity_type="code_project",
        entity_id=project_id,
        actor_type="user",
        actor_id=str(user_id),
        action="Prepared orchestration delivery package",
        new_value={"ready": package["ready"], "impact": package["impact"], "target": request.target},
    ))
    db.commit()
    db.refresh(state)
    return {
        "session_id": str(session.id),
        "delivery_package": package,
        "orchestration": _serialize_state(db, state),
    }
