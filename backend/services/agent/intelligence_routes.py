from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from services.shared.database import get_db
from services.shared.models import (
    AuditLog,
    CodeProject,
    EvidenceRecord,
    ExecutionPlan,
    FounderApproval,
    AgentInstance,
    IntelligenceTask,
    PlanStep,
    ReviewDecision,
    TaskRequirement,
)

from .deps import get_current_user_id
from .intelligence.model_assignment import build_worker_specs
from .intelligence.policies import can_transition
from .intelligence.risk_engine import assess_risk
from .intelligence.schemas import ApprovalRequest, EvidenceCreate, IntelligenceTaskCreate, LifecycleRequest, WorkerAssignmentRequest
from .intelligence.task_intake import default_plan_steps, derive_requirements, normalize_objective
from .intelligence.workflow import phase_for_task_status, workflow_snapshot

router = APIRouter(prefix="/api/v1/intelligence", tags=["intelligence"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid(value: Any) -> str | None:
    return str(value) if value is not None else None


def _audit(
    db: Session,
    *,
    user_id: UUID,
    event_type: str,
    task_id: UUID,
    action: str,
    metadata: dict[str, Any] | None = None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            user_id=user_id,
            event_type=event_type,
            entity_type="intelligence_task",
            entity_id=task_id,
            actor_type="user",
            actor_id=str(user_id),
            action=action,
            old_value=old_value,
            new_value=new_value,
            metadata_json=metadata or {},
        )
    )


def _require_task(db: Session, user_id: UUID, task_id: UUID) -> IntelligenceTask:
    task = (
        db.query(IntelligenceTask)
        .options(
            joinedload(IntelligenceTask.requirements),
            joinedload(IntelligenceTask.plans).joinedload(ExecutionPlan.steps),
            joinedload(IntelligenceTask.evidence_records),
            joinedload(IntelligenceTask.review_decisions),
            joinedload(IntelligenceTask.founder_approvals),
        )
        .filter(IntelligenceTask.id == task_id, IntelligenceTask.user_id == user_id)
        .first()
    )
    if not task:
        raise HTTPException(status_code=404, detail="Intelligence task not found")
    return task


def _latest_plan(task: IntelligenceTask) -> ExecutionPlan | None:
    return sorted(task.plans or [], key=lambda item: (item.version or 0, item.created_at or datetime.min), reverse=True)[0] if task.plans else None


def _transition(task: IntelligenceTask, target: str) -> None:
    if not can_transition(task.status or "created", target):
        raise HTTPException(status_code=409, detail=f"Cannot move task from {task.status} to {target}")
    task.status = target


def _serialize_requirement(item: TaskRequirement) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "type": item.requirement_type,
        "description": item.description,
        "source": item.source,
        "confidence": item.confidence,
        "requires_confirmation": item.requires_confirmation,
        "status": item.status,
    }


def _serialize_step(step: PlanStep) -> dict[str, Any]:
    return {
        "id": str(step.id),
        "parent_step_id": _uuid(step.parent_step_id),
        "title": step.title,
        "description": step.description,
        "assigned_role": step.assigned_role,
        "dependency_ids": step.dependency_ids or [],
        "owned_paths": step.owned_paths or [],
        "acceptance_criteria": step.acceptance_criteria or [],
        "status": step.status,
        "order_index": step.order_index,
    }


def _serialize_plan(plan: ExecutionPlan) -> dict[str, Any]:
    steps = sorted(plan.steps or [], key=lambda item: item.order_index or 0)
    return {
        "id": str(plan.id),
        "version": plan.version,
        "summary": plan.summary,
        "architecture_option": plan.architecture_option,
        "estimated_cost": plan.estimated_cost,
        "estimated_duration": plan.estimated_duration,
        "risk_score": plan.risk_score,
        "status": plan.status,
        "steps": [_serialize_step(step) for step in steps],
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
    }


def _serialize_evidence(item: EvidenceRecord) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "type": item.evidence_type,
        "title": item.title,
        "summary": item.summary,
        "uri": item.uri,
        "payload": item.payload or {},
        "confidence": item.confidence,
        "created_by": item.created_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _task_agents(db: Session, task_id: UUID, user_id: UUID) -> list[AgentInstance]:
    return (
        db.query(AgentInstance)
        .filter(AgentInstance.task_id == task_id, AgentInstance.user_id == user_id)
        .order_by(AgentInstance.created_at.asc(), AgentInstance.id.asc())
        .all()
    )


def _serialize_agent_instance(item: AgentInstance) -> dict[str, Any]:
    metadata = item.metadata_json or {}
    return {
        "id": str(item.id),
        "task_id": _uuid(item.task_id),
        "role": item.role,
        "model_provider": item.model_provider,
        "model_name": item.model_name,
        "status": item.status,
        "capability_profile": item.capability_profile or {},
        "mission": metadata.get("mission"),
        "reviewer_role": metadata.get("reviewer_role"),
        "model_key": metadata.get("model_key"),
        "selection_reason": metadata.get("selection_reason"),
        "estimated_cost": metadata.get("estimated_cost"),
        "estimated_time": metadata.get("estimated_time"),
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


def _serialize_task(task: IntelligenceTask) -> dict[str, Any]:
    plans = sorted(task.plans or [], key=lambda item: item.version or 0)
    latest = _latest_plan(task)
    return {
        "id": str(task.id),
        "user_id": str(task.user_id),
        "project_id": _uuid(task.project_id),
        "workspace_id": _uuid(task.workspace_id),
        "title": task.title,
        "raw_request": task.raw_request,
        "normalized_objective": task.normalized_objective,
        "task_type": task.task_type,
        "planning_depth": task.planning_depth,
        "risk_level": task.risk_level,
        "priority": task.priority,
        "status": task.status,
        "budget_limit": task.budget_limit,
        "metadata": task.metadata_json or {},
        "workflow": workflow_snapshot(phase_for_task_status(task.status)),
        "requirements": [_serialize_requirement(item) for item in task.requirements or []],
        "plans": [_serialize_plan(plan) for plan in plans],
        "latest_plan_id": str(latest.id) if latest else None,
        "evidence": [_serialize_evidence(item) for item in sorted(task.evidence_records or [], key=lambda record: record.created_at or datetime.min)],
        "review_decisions": [
            {
                "id": str(item.id),
                "plan_id": _uuid(item.plan_id),
                "decision_type": item.decision_type,
                "status": item.status,
                "rationale": item.rationale,
                "created_at": item.created_at.isoformat() if item.created_at else None,
                "decided_at": item.decided_at.isoformat() if item.decided_at else None,
            }
            for item in task.review_decisions or []
        ],
        "founder_approvals": [
            {
                "id": str(item.id),
                "plan_id": _uuid(item.plan_id),
                "approval_type": item.approval_type,
                "status": item.status,
                "notes": item.notes,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in task.founder_approvals or []
        ],
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


@router.get("/workflow")
def get_intelligence_workflow() -> dict[str, Any]:
    return workflow_snapshot("launch")


@router.post("/tasks")
def create_intelligence_task(
    request: IntelligenceTaskCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if request.project_id:
        project = db.query(CodeProject).filter(CodeProject.id == request.project_id, CodeProject.user_id == user_id).first()
        if not project:
            raise HTTPException(status_code=404, detail="Code project not found")

    assessment = assess_risk(f"{request.title}\n{request.raw_request}")
    task = IntelligenceTask(
        user_id=user_id,
        created_by=user_id,
        project_id=request.project_id,
        workspace_id=request.workspace_id,
        title=request.title.strip() or "Untitled engineering task",
        raw_request=request.raw_request,
        normalized_objective=normalize_objective(request.title, request.raw_request),
        task_type=assessment.task_type,
        planning_depth=assessment.planning_depth,
        risk_level=assessment.risk_level,
        priority=request.priority,
        budget_limit=request.budget_limit,
        status="created",
        metadata_json={**(request.metadata or {}), "risk_reasons": assessment.reasons},
    )
    db.add(task)
    db.flush()
    _audit(
        db,
        user_id=user_id,
        event_type="intelligence.task.created",
        task_id=task.id,
        action="Created intelligence task",
        new_value={"status": task.status, "risk_level": task.risk_level, "task_type": task.task_type},
    )
    db.commit()
    db.refresh(task)
    return {"task": _serialize_task(_require_task(db, user_id, task.id))}


@router.get("/tasks/{task_id}")
def get_intelligence_task(
    task_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    task = _require_task(db, user_id, task_id)
    return {
        "task": _serialize_task(task),
        "agents": [_serialize_agent_instance(item) for item in _task_agents(db, task.id, user_id)],
    }


@router.post("/tasks/{task_id}/analyze")
def analyze_intelligence_task(
    task_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    task = _require_task(db, user_id, task_id)
    assessment = assess_risk(f"{task.title}\n{task.raw_request}")
    old = {"status": task.status, "risk_level": task.risk_level, "task_type": task.task_type}
    _transition(task, "analyzed")
    task.normalized_objective = normalize_objective(task.title, task.raw_request)
    task.task_type = assessment.task_type
    task.planning_depth = assessment.planning_depth
    task.risk_level = assessment.risk_level
    task.metadata_json = {**(task.metadata_json or {}), "risk_reasons": assessment.reasons, "risk_score": assessment.risk_score}

    if not task.requirements:
        for item in derive_requirements(task.raw_request):
            db.add(TaskRequirement(task_id=task.id, **item))

    _audit(
        db,
        user_id=user_id,
        event_type="intelligence.task.analyzed",
        task_id=task.id,
        action="Analyzed task requirements and risk",
        old_value=old,
        new_value={"status": task.status, "risk_level": task.risk_level, "task_type": task.task_type},
    )
    db.commit()
    return {"task": _serialize_task(_require_task(db, user_id, task_id))}


@router.post("/tasks/{task_id}/plan")
def plan_intelligence_task(
    task_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    task = _require_task(db, user_id, task_id)
    if task.status == "created":
        analyze_intelligence_task(task_id, user_id=user_id, db=db)
        task = _require_task(db, user_id, task_id)

    if task.status not in {"analyzed", "planned"}:
        raise HTTPException(status_code=409, detail=f"Task must be analyzed before planning; current status is {task.status}")

    existing_versions = [plan.version or 0 for plan in task.plans or []]
    version = max(existing_versions, default=0) + 1
    assessment = assess_risk(f"{task.title}\n{task.raw_request}")
    plan = ExecutionPlan(
        task_id=task.id,
        version=version,
        summary=f"Phase 1 execution plan for: {task.normalized_objective or task.title}",
        architecture_option="proof_first_control_plane",
        estimated_cost=0.0,
        estimated_duration="planning only; execution deferred",
        risk_score=assessment.risk_score,
        status="draft",
        metadata_json={"execution_enabled": False, "phase": 1},
    )
    db.add(plan)
    db.flush()
    for index, step in enumerate(default_plan_steps(task.task_type, task.risk_level), start=1):
        db.add(PlanStep(plan_id=plan.id, order_index=index, **step))
    old = {"status": task.status}
    task.status = "planned"
    _audit(
        db,
        user_id=user_id,
        event_type="intelligence.task.planned",
        task_id=task.id,
        action="Created execution plan",
        old_value=old,
        new_value={"status": task.status, "plan_id": str(plan.id), "version": version},
    )
    db.commit()
    return {"task": _serialize_task(_require_task(db, user_id, task_id)), "plan_id": str(plan.id)}


@router.post("/tasks/{task_id}/approve-plan")
def approve_intelligence_plan(
    task_id: UUID,
    request: ApprovalRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    task = _require_task(db, user_id, task_id)
    plan = _latest_plan(task)
    if not plan:
        raise HTTPException(status_code=409, detail="No plan exists for this task")
    if task.status != "planned":
        raise HTTPException(status_code=409, detail=f"Task must be planned before approval; current status is {task.status}")

    old = {"task_status": task.status, "plan_status": plan.status}
    task.status = "plan_approved"
    plan.status = "approved"
    approval = FounderApproval(
        task_id=task.id,
        plan_id=plan.id,
        approval_type=request.approval_type,
        status="approved",
        notes=request.notes,
        approved_by=user_id,
        metadata_json={"phase": 1},
    )
    db.add(approval)
    db.add(
        ReviewDecision(
            task_id=task.id,
            plan_id=plan.id,
            decision_type="plan_approval",
            status="approved",
            rationale=request.notes,
            decided_by=user_id,
            decided_at=_now(),
            payload={"phase": 1},
        )
    )
    _audit(
        db,
        user_id=user_id,
        event_type="intelligence.plan.approved",
        task_id=task.id,
        action="Approved execution plan",
        old_value=old,
        new_value={"task_status": task.status, "plan_status": plan.status, "plan_id": str(plan.id)},
    )
    db.commit()
    return {"task": _serialize_task(_require_task(db, user_id, task_id))}


@router.get("/tasks/{task_id}/workflow")
def get_task_workflow(
    task_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    task = _require_task(db, user_id, task_id)
    return {
        "task_id": str(task.id),
        "status": task.status,
        "workflow": workflow_snapshot(phase_for_task_status(task.status)),
        "agents": [_serialize_agent_instance(item) for item in _task_agents(db, task.id, user_id)],
    }


@router.post("/tasks/{task_id}/assign-workers")
def assign_intelligence_workers(
    task_id: UUID,
    request: WorkerAssignmentRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    task = _require_task(db, user_id, task_id)
    if task.status not in {"plan_approved", "ready_for_execution", "paused"}:
        raise HTTPException(
            status_code=409,
            detail=f"Workers can be assigned after plan approval; current status is {task.status}",
        )

    objective = "\n".join(
        value
        for value in [task.title, task.raw_request, task.normalized_objective, task.task_type]
        if value
    )
    existing_by_role = {item.role: item for item in _task_agents(db, task.id, user_id)}
    assigned: list[AgentInstance] = []

    for spec in build_worker_specs(objective, request.preference):
        metadata = {
            "mission": spec.mission,
            "reviewer_role": spec.reviewer_role,
            "model_key": spec.model_key,
            "selection_reason": spec.reason,
            "estimated_cost": spec.estimated_cost,
            "estimated_time": spec.estimated_time,
            "phase": "model_intelligence",
        }
        capability_profile = {
            "task_type": spec.task_type,
            "can_execute": False,
            "requires_context_package": True,
            "proof_required": True,
        }
        agent = existing_by_role.get(spec.role)
        if agent:
            agent.model_provider = spec.provider
            agent.model_name = spec.model
            agent.status = "planned"
            agent.capability_profile = capability_profile
            agent.metadata_json = metadata
        else:
            agent = AgentInstance(
                user_id=user_id,
                task_id=task.id,
                role=spec.role,
                model_provider=spec.provider,
                model_name=spec.model,
                status="planned",
                capability_profile=capability_profile,
                metadata_json=metadata,
            )
            db.add(agent)
        assigned.append(agent)

    task.metadata_json = {
        **(task.metadata_json or {}),
        "worker_assignment_preference": request.preference,
        "worker_assignment_count": len(assigned),
        "execution_enabled": False,
    }
    _audit(
        db,
        user_id=user_id,
        event_type="intelligence.workforce.assigned",
        task_id=task.id,
        action="Assigned specialist AI workforce",
        new_value={
            "agent_count": len(assigned),
            "preference": request.preference,
            "roles": [item.role for item in assigned],
            "execution_enabled": False,
        },
    )
    db.commit()
    refreshed = _require_task(db, user_id, task.id)
    return {
        "task": _serialize_task(refreshed),
        "agents": [_serialize_agent_instance(item) for item in _task_agents(db, refreshed.id, user_id)],
        "execution_enabled": False,
        "message": "Specialist workers are planned and model-routed. Tool/model execution remains disabled until the execution engine is approved.",
    }


@router.post("/tasks/{task_id}/execute")
def mark_intelligence_task_ready(
    task_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    task = _require_task(db, user_id, task_id)
    if task.status != "plan_approved":
        raise HTTPException(status_code=409, detail=f"Plan must be approved before execution handoff; current status is {task.status}")
    old = {"status": task.status}
    task.status = "ready_for_execution"
    _audit(
        db,
        user_id=user_id,
        event_type="intelligence.task.execution_ready",
        task_id=task.id,
        action="Marked task ready for future execution worker",
        old_value=old,
        new_value={"status": task.status, "execution_enabled": False},
    )
    db.commit()
    return {
        "task": _serialize_task(_require_task(db, user_id, task_id)),
        "execution_enabled": False,
        "message": "Phase 1 control plane recorded the handoff. Model/tool execution is intentionally disabled.",
    }


@router.post("/tasks/{task_id}/pause")
def pause_intelligence_task(task_id: UUID, request: LifecycleRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    task = _require_task(db, user_id, task_id)
    old = {"status": task.status}
    _transition(task, "paused")
    _audit(db, user_id=user_id, event_type="intelligence.task.paused", task_id=task.id, action="Paused intelligence task", old_value=old, new_value={"status": task.status, "reason": request.reason})
    db.commit()
    return {"task": _serialize_task(_require_task(db, user_id, task_id))}


@router.post("/tasks/{task_id}/resume")
def resume_intelligence_task(task_id: UUID, request: LifecycleRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    task = _require_task(db, user_id, task_id)
    old = {"status": task.status}
    _transition(task, "ready_for_execution")
    _audit(db, user_id=user_id, event_type="intelligence.task.resumed", task_id=task.id, action="Resumed intelligence task", old_value=old, new_value={"status": task.status, "reason": request.reason})
    db.commit()
    return {"task": _serialize_task(_require_task(db, user_id, task_id))}


@router.post("/tasks/{task_id}/cancel")
def cancel_intelligence_task(task_id: UUID, request: LifecycleRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    task = _require_task(db, user_id, task_id)
    old = {"status": task.status}
    if task.status not in {"completed", "cancelled"}:
        task.status = "cancelled"
    _audit(db, user_id=user_id, event_type="intelligence.task.cancelled", task_id=task.id, action="Cancelled intelligence task", old_value=old, new_value={"status": task.status, "reason": request.reason})
    db.commit()
    return {"task": _serialize_task(_require_task(db, user_id, task_id))}


@router.post("/tasks/{task_id}/evidence")
def add_intelligence_evidence(
    task_id: UUID,
    request: EvidenceCreate,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    task = _require_task(db, user_id, task_id)
    evidence = EvidenceRecord(
        task_id=task.id,
        evidence_type=request.evidence_type,
        title=request.title,
        summary=request.summary,
        uri=request.uri,
        payload=request.payload,
        confidence=request.confidence,
        created_by=str(user_id),
    )
    db.add(evidence)
    _audit(
        db,
        user_id=user_id,
        event_type="intelligence.evidence.added",
        task_id=task.id,
        action="Added task evidence",
        new_value={"evidence_type": request.evidence_type, "title": request.title},
    )
    db.commit()
    return {"task": _serialize_task(_require_task(db, user_id, task_id)), "evidence_id": str(evidence.id)}


@router.get("/tasks/{task_id}/evidence")
def list_intelligence_evidence(task_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    task = _require_task(db, user_id, task_id)
    return {"evidence": [_serialize_evidence(item) for item in sorted(task.evidence_records or [], key=lambda record: record.created_at or datetime.min)]}


@router.get("/tasks/{task_id}/timeline")
def get_intelligence_timeline(task_id: UUID, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)) -> dict[str, Any]:
    _require_task(db, user_id, task_id)
    logs = (
        db.query(AuditLog)
        .filter(AuditLog.user_id == user_id, AuditLog.entity_type == "intelligence_task", AuditLog.entity_id == task_id)
        .order_by(AuditLog.occurred_at.asc(), AuditLog.id.asc())
        .all()
    )
    return {
        "timeline": [
            {
                "id": item.id,
                "event_type": item.event_type,
                "action": item.action,
                "old_value": item.old_value,
                "new_value": item.new_value,
                "metadata": item.metadata_json or {},
                "occurred_at": item.occurred_at.isoformat() if item.occurred_at else None,
            }
            for item in logs
        ]
    }


@router.post("/tasks/{task_id}/approve-merge")
def approve_intelligence_merge(
    task_id: UUID,
    request: ApprovalRequest,
    user_id: UUID = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    task = _require_task(db, user_id, task_id)
    plan = _latest_plan(task)
    decision = ReviewDecision(
        task_id=task.id,
        plan_id=plan.id if plan else None,
        decision_type="merge_approval",
        status="approved",
        rationale=request.notes,
        decided_by=user_id,
        decided_at=_now(),
        payload={"approval_type": request.approval_type},
    )
    db.add(decision)
    _audit(
        db,
        user_id=user_id,
        event_type="intelligence.merge.approved",
        task_id=task.id,
        action="Approved merge readiness",
        new_value={"decision_id": str(decision.id), "plan_id": str(plan.id) if plan else None},
    )
    db.commit()
    return {"task": _serialize_task(_require_task(db, user_id, task_id)), "decision_id": str(decision.id)}
