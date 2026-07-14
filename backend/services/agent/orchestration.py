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

from .code_workspace import get_code_project
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
    return [
        {
            "id": "T1",
            "title": "Confirm requirements and acceptance criteria",
            "assigned_role": "product_lead",
            "depends_on": [],
            "status": "ready",
            "acceptance_criteria": criteria[:4] or ["Problem statement is clarified"],
        },
        {
            "id": "T2",
            "title": "Create architecture skeleton",
            "assigned_role": "solution_architect",
            "depends_on": ["T1"],
            "status": "blocked",
            "acceptance_criteria": ["Architecture matches selected proposal", "Risks and trade-offs are documented"],
        },
        {
            "id": "T3",
            "title": "Implement first bounded task",
            "assigned_role": "coding_agent",
            "depends_on": ["T2"],
            "status": "blocked",
            "acceptance_criteria": ["Files changed are reviewable", "Focused checks pass", "Rollback remains available"],
        },
        {
            "id": "T4",
            "title": "Run review board",
            "assigned_role": "review_board",
            "depends_on": ["T3"],
            "status": "blocked",
            "acceptance_criteria": ["Requirements, security, tests, and maintainability reviewed"],
        },
    ]


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
