from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
from typing import Any, Literal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field

from services.shared.arceus_core_models import (
    ArceusDecision,
    ArceusEvent,
    ArceusMission,
    ArceusMissionVersion,
    ArceusOutboxMessage,
    ArceusProject,
    ArceusTask,
    ArceusTaskDependency,
)
from services.shared.database import get_db

from .arceus_runtime.api.dependencies import RequestContext, require_permission
from .arceus_runtime.application.idempotency import calculate_request_hash
from .arceus_runtime.mission_runtime.api_schemas import RuntimeTaskSpec
from .arceus_runtime.mission_runtime.service import validate_task_dag


router = APIRouter(prefix="/api/v1/missions", tags=["cognitive-execution"])


IntentType = Literal["feature", "bugfix", "refactor", "test", "documentation", "deployment", "investigation"]


class RepositoryContext(BaseModel):
    repository_id: str | None = None
    root_path: str | None = Field(default=None, max_length=2_000)
    summary: str | None = None
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    package_managers: list[str] = Field(default_factory=list)
    entry_points: list[str] = Field(default_factory=list)
    services: list[str] = Field(default_factory=list)
    test_commands: list[str] = Field(default_factory=list)
    database_usage: list[str] = Field(default_factory=list)
    authentication: list[str] = Field(default_factory=list)
    architecture_style: str | None = None


class CognitiveCompileRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=5_000)
    workspace_id: str = Field(default="local-workspace", min_length=1, max_length=240)
    repository: RepositoryContext | None = None
    approval_mode: Literal["preview", "auto_safe", "manual"] = "preview"


class PersistMissionRequest(BaseModel):
    goal: str = Field(min_length=3, max_length=5_000)
    workspace_id: str = Field(default="local-workspace", min_length=1, max_length=240)
    repository: RepositoryContext
    constraints: dict[str, Any] = Field(default_factory=dict)


class MissionApprovalRequest(BaseModel):
    expected_version: int = Field(ge=1)
    approval_note: str | None = Field(default=None, max_length=2_000)


class MissionRejectRequest(BaseModel):
    expected_version: int = Field(ge=1)
    reason: str = Field(default="Rejected by user.", max_length=2_000)


class PersistedMissionTask(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    id: str
    version: int
    task_key: str
    title: str
    task_type: str
    status: str
    agent_role: str | None = None
    model_hint: str | None = None
    dependencies: list[str] = Field(default_factory=list)


class PersistedMissionEvent(BaseModel):
    id: str
    sequence: int
    event_type: str
    payload: dict[str, Any]
    occurred_at: str


class PersistedMissionResponse(BaseModel):
    mission_id: str
    status: str
    display_status: str
    version: int
    goal: str
    task_count: int
    dependency_count: int
    agents: list[str]
    confidence: float
    warnings: list[str]
    approval_required: bool
    compiled_plan: dict[str, Any]
    tasks: list[PersistedMissionTask] = Field(default_factory=list)
    events: list[PersistedMissionEvent] = Field(default_factory=list)


class MissionGraphResponse(BaseModel):
    mission_id: str
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]


class GoalUnderstanding(BaseModel):
    intent: IntentType
    domain: str
    priority: Literal["low", "normal", "high", "critical"]
    repository_scope: list[str]
    requires_database: bool
    requires_ui: bool
    requires_tests: bool
    risk_level: Literal["low", "medium", "high"]
    unknowns: list[str] = Field(default_factory=list)


class AgentAssignment(BaseModel):
    task_id: str
    role: str
    model: str
    estimated_tokens: int
    reason: str


class ContextPackagePlan(BaseModel):
    task_id: str
    sources: list[str]
    citations: list[str]
    estimated_tokens: int
    confidence: float


class DecisionRecord(BaseModel):
    decision_id: str
    title: str
    reason: str
    alternatives_rejected: list[str]
    affected_files: list[str]
    verification_expected: list[str]


class MissionTimelineEvent(BaseModel):
    at: str
    title: str
    detail: str
    status: Literal["completed", "queued", "blocked"]


class MissionReportPreview(BaseModel):
    mission: str
    status: Literal["awaiting_approval", "blocked"]
    estimated_duration_minutes: int
    files_likely_modified: int
    tests_planned: list[str]
    warnings: list[str]
    rollback_available: bool
    confidence: float


class CognitiveCompileResponse(BaseModel):
    mission_id: str
    workspace_id: str
    state: Literal["AWAITING_APPROVAL", "CLARIFICATION_REQUIRED"]
    goal: str
    understanding: GoalUnderstanding
    tasks: list[RuntimeTaskSpec]
    dependency_graph: dict[str, Any]
    agents: list[AgentAssignment]
    context_packages: list[ContextPackagePlan]
    decisions: list[DecisionRecord]
    recovery_strategy: list[str]
    timeline: list[MissionTimelineEvent]
    report: MissionReportPreview
    generated_at: str


def _contains_any(text: str, words: set[str]) -> bool:
    return any(word in text for word in words)


def _understand_goal(goal: str, repo: RepositoryContext | None) -> GoalUnderstanding:
    text = goal.lower()
    if _contains_any(text, {"fix", "bug", "error", "crash", "broken", "failing"}):
        intent: IntentType = "bugfix"
    elif _contains_any(text, {"implement", "add", "create", "build", "support", "integrate"}):
        intent = "feature"
    elif _contains_any(text, {"refactor", "cleanup", "split", "simplify"}):
        intent = "refactor"
    elif _contains_any(text, {"test", "coverage", "spec"}):
        intent = "test"
    elif _contains_any(text, {"deploy", "release", "railway", "vercel", "docker"}):
        intent = "deployment"
    elif _contains_any(text, {"document", "docs", "readme"}):
        intent = "documentation"
    elif _contains_any(text, {"investigate", "analyze", "audit", "review"}):
        intent = "investigation"
    else:
        intent = "feature"

    auth_words = {"auth", "oauth", "login", "signin", "sign-in", "clerk", "jwt", "session"}
    db_words = {"database", "postgres", "sql", "migration", "schema", "redis", "cache"}
    ui_words = {"ui", "frontend", "page", "screen", "button", "component", "design"}
    test_words = {"test", "verify", "lint", "build", "quality", "qa"}
    domain = "authentication" if _contains_any(text, auth_words) else "data" if _contains_any(text, db_words) else "frontend" if _contains_any(text, ui_words) else "software_engineering"
    services = set(repo.services if repo else [])
    scope = []
    if _contains_any(text, ui_words) or "frontend" in services:
        scope.append("frontend")
    if _contains_any(text, auth_words | db_words) or "backend" in services:
        scope.append("backend")
    if _contains_any(text, {"desktop", "electron", "terminal", "folder"}):
        scope.append("desktop")
    if not scope:
        scope = sorted(services.intersection({"frontend", "backend", "desktop"})) or ["repository"]

    requires_database = _contains_any(text, db_words) or bool(repo and repo.database_usage and domain in {"data", "authentication"})
    requires_ui = _contains_any(text, ui_words) or "frontend" in scope
    requires_tests = intent != "documentation" or _contains_any(text, test_words)
    priority = "critical" if _contains_any(text, {"production down", "security breach", "data loss"}) else "high" if _contains_any(text, {"urgent", "security", "payment", "auth"}) else "normal"
    risk_level = "high" if priority in {"critical", "high"} or requires_database else "medium" if requires_ui or intent in {"feature", "refactor"} else "low"
    unknowns = []
    if not repo or not repo.repository_id:
        unknowns.append("Repository analysis is not attached yet.")
    if intent == "feature" and domain == "software_engineering":
        unknowns.append("Exact product behavior and acceptance criteria need confirmation before execution.")
    return GoalUnderstanding(
        intent=intent,
        domain=domain,
        priority=priority,
        repository_scope=scope,
        requires_database=requires_database,
        requires_ui=requires_ui,
        requires_tests=requires_tests,
        risk_level=risk_level,
        unknowns=unknowns,
    )


def _task(key: str, title: str, task_type: str, deps: list[str], risk: str, minutes: int, criteria: list[str], metadata: dict[str, Any] | None = None) -> RuntimeTaskSpec:
    return RuntimeTaskSpec(
        task_key=key,
        title=title,
        task_type=task_type,
        dependencies=deps,
        risk_level=risk,
        estimated_seconds=minutes * 60,
        priority=80 if risk == "high" else 65 if risk == "medium" else 50,
        acceptance_criteria=criteria,
        metadata=metadata or {},
    )


def _build_tasks(goal: str, understanding: GoalUnderstanding, repo: RepositoryContext | None) -> list[RuntimeTaskSpec]:
    tasks = [
        _task("repo_context", "Assemble repository context", "analysis", [], "low", 2, ["Repository summary, entry points, services, and checks are available."]),
        _task("architecture_review", "Review architecture impact", "architecture", ["repo_context"], understanding.risk_level, 4, ["Affected services and trade-offs are identified."]),
        _task("implementation_plan", "Produce implementation plan", "planning", ["architecture_review"], understanding.risk_level, 5, ["Plan includes files, risks, rollback path, and verification steps."]),
        _task("approval_gate", "Human approval before execution", "approval", ["implementation_plan"], "low", 1, ["User approves or requests changes before code execution."]),
    ]
    if understanding.requires_database:
        tasks.append(_task("data_changes", "Design data and migration changes", "database", ["approval_gate"], "high", 8, ["Schema/cache changes are reversible and migration-safe."]))
    if understanding.requires_ui:
        deps = ["approval_gate"] + (["data_changes"] if understanding.requires_database else [])
        tasks.append(_task("frontend_changes", "Implement frontend changes", "frontend", deps, understanding.risk_level, 12, ["UI behavior matches the approved plan.", "Accessible states are covered."]))
    if "backend" in understanding.repository_scope or understanding.domain in {"authentication", "data"}:
        deps = ["approval_gate"] + (["data_changes"] if understanding.requires_database else [])
        tasks.append(_task("backend_changes", "Implement backend changes", "backend", deps, understanding.risk_level, 12, ["API behavior matches the approved plan.", "Errors are structured and recoverable."]))
    if understanding.requires_tests:
        test_deps = [task.task_key for task in tasks if task.task_key.endswith("_changes") or task.task_key == "data_changes"]
        tasks.append(_task("verification", "Run verification checks", "verification", test_deps or ["approval_gate"], "medium", 8, ["Build, lint, and relevant tests produce evidence."]))
    tasks.append(_task("mission_report", "Generate mission report and rollback plan", "report", ["verification"] if understanding.requires_tests else ["approval_gate"], "low", 2, ["Timeline, decisions, evidence, and rollback status are visible."]))
    return tasks


def _role_for_task(task: RuntimeTaskSpec) -> str:
    return {
        "analysis": "Repository Analyst",
        "architecture": "Solution Architect",
        "planning": "Engineering Manager",
        "approval": "Human Approval Gate",
        "database": "Database Engineer",
        "frontend": "Frontend Engineer",
        "backend": "Backend Engineer",
        "verification": "QA Reviewer",
        "report": "Mission Reporter",
    }.get(task.task_type, "Mission Specialist")


def _model_for_task(task: RuntimeTaskSpec) -> str:
    return {
        "analysis": "fast-context-model",
        "architecture": "strong-reasoning-model",
        "planning": "strong-reasoning-model",
        "approval": "policy-gate",
        "database": "code-generation-model",
        "frontend": "code-generation-model",
        "backend": "code-generation-model",
        "verification": "analysis-focused-model",
        "report": "lightweight-summary-model",
    }.get(task.task_type, "adaptive-model")


def compile_cognitive_mission(payload: CognitiveCompileRequest) -> CognitiveCompileResponse:
    repo = payload.repository or RepositoryContext()
    understanding = _understand_goal(payload.goal, repo)
    tasks = _build_tasks(payload.goal, understanding, repo)
    validation = validate_task_dag(tasks)
    state = "CLARIFICATION_REQUIRED" if understanding.unknowns and not repo.repository_id else "AWAITING_APPROVAL"
    agents = [
        AgentAssignment(
            task_id=task.task_key,
            role=_role_for_task(task),
            model=_model_for_task(task),
            estimated_tokens=max(1_000, min(24_000, 900 + len(task.acceptance_criteria) * 300 + len(task.dependencies) * 250)),
            reason=f"{task.task_type} work requires {', '.join(task.acceptance_criteria[:1]) or 'specialized execution'}.",
        )
        for task in tasks
    ]
    context_sources = [
        "user_goal",
        "repository_summary",
        "entry_points",
        "services",
        "test_commands",
    ]
    context_packages = [
        ContextPackagePlan(
            task_id=task.task_key,
            sources=context_sources + (["database_usage"] if understanding.requires_database else []) + (["authentication"] if understanding.domain == "authentication" else []),
            citations=(repo.entry_points[:4] + repo.services[:4] + repo.test_commands[:3])[:8],
            estimated_tokens=max(1_200, min(32_000, 1_500 + len(repo.entry_points) * 180 + len(repo.services) * 160)),
            confidence=0.9 if repo.repository_id else 0.55,
        )
        for task in tasks
    ]
    decisions = [
        DecisionRecord(
            decision_id=f"dec_{uuid4().hex[:10]}",
            title="Use approval-first mission execution",
            reason="The runtime should compile a plan, expose risks, and wait for user approval before modifying files.",
            alternatives_rejected=["Direct chat-to-code execution", "Unscoped whole-repository context"],
            affected_files=repo.entry_points[:6],
            verification_expected=repo.test_commands[:4] or ["Run relevant local checks"],
        )
    ]
    timeline_titles = [
        ("Repository opened", repo.summary or "Repository context received."),
        ("Goal understood", f"{understanding.intent} / {understanding.domain} / {understanding.risk_level} risk."),
        ("Task graph generated", f"{len(tasks)} task nodes, {validation.edge_count} dependency edges."),
        ("Agents assigned", f"{len(agents)} specialist assignments prepared."),
        ("Awaiting approval", "Execution graph will be created after human approval."),
    ]
    now = datetime.now(timezone.utc).isoformat()
    timeline = [
        MissionTimelineEvent(at=now, title=title, detail=detail, status="completed" if index < 4 else "queued")
        for index, (title, detail) in enumerate(timeline_titles)
    ]
    warnings = list(understanding.unknowns)
    if understanding.risk_level == "high":
        warnings.append("High-risk changes require explicit review and rollback evidence.")
    if not repo.test_commands:
        warnings.append("No test commands detected; verification will need manual check configuration.")
    confidence = 0.92 if repo.repository_id and validation.valid else 0.68
    report = MissionReportPreview(
        mission=payload.goal,
        status="awaiting_approval" if state == "AWAITING_APPROVAL" else "blocked",
        estimated_duration_minutes=max(1, sum(task.estimated_seconds for task in tasks) // 60),
        files_likely_modified=max(1, min(12, len(repo.entry_points) + len(understanding.repository_scope))),
        tests_planned=repo.test_commands[:5],
        warnings=warnings,
        rollback_available=True,
        confidence=confidence,
    )
    return CognitiveCompileResponse(
        mission_id=f"mission_{uuid4().hex[:12]}",
        workspace_id=payload.workspace_id,
        state=state,
        goal=payload.goal,
        understanding=understanding,
        tasks=tasks,
        dependency_graph={
            "valid": validation.valid,
            "errors": validation.errors,
            "topological_order": validation.topological_order,
            "critical_path": validation.critical_path,
            "critical_path_seconds": validation.critical_path_seconds,
            "edge_count": validation.edge_count,
        },
        agents=agents,
        context_packages=context_packages,
        decisions=decisions,
        recovery_strategy=["retry_transient_failure", "rebuild_context", "switch_model", "pause_for_human_review", "rollback_applied_changes"],
        timeline=timeline,
        report=report,
        generated_at=now,
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _next_event_sequence(db: Session, *, tenant_id: UUID, mission_id: UUID) -> int:
    current = (
        db.query(func.max(ArceusEvent.aggregate_version))
        .filter(ArceusEvent.tenant_id == tenant_id, ArceusEvent.aggregate_type == "mission", ArceusEvent.aggregate_id == mission_id)
        .scalar()
        or 0
    )
    return int(current) + 1


def _append_event(
    db: Session,
    *,
    tenant_id: UUID,
    mission_id: UUID,
    event_type: str,
    actor_id: str,
    payload: dict[str, Any],
    correlation_id: UUID,
    idempotency_key: str,
    outbox_topic: str | None = None,
    task_id: UUID | None = None,
) -> ArceusEvent:
    event = ArceusEvent(
        tenant_id=tenant_id,
        aggregate_type="mission",
        aggregate_id=mission_id,
        aggregate_version=_next_event_sequence(db, tenant_id=tenant_id, mission_id=mission_id),
        event_type=event_type,
        actor_type="human",
        actor_id=actor_id,
        payload={**payload, **({"task_id": str(task_id)} if task_id else {})},
        metadata_json={"correlation_id": str(correlation_id), "idempotency_key": idempotency_key},
    )
    db.add(event)
    db.flush()
    if outbox_topic:
        db.add(
            ArceusOutboxMessage(
                tenant_id=tenant_id,
                event_id=event.id,
                topic=outbox_topic,
                payload={
                    "event_id": str(event.id),
                    "mission_id": str(mission_id),
                    "task_id": str(task_id) if task_id else None,
                    "event_type": event_type,
                    **payload,
                },
            )
        )
    return event


def _project_for_desktop_code(db: Session, context: RequestContext) -> ArceusProject:
    project = (
        db.query(ArceusProject)
        .filter(ArceusProject.tenant_id == context.tenant_id, ArceusProject.slug == "arceus-code-desktop")
        .first()
    )
    if project is not None:
        return project
    project = ArceusProject(
        tenant_id=context.tenant_id,
        name="Arceus Code Desktop",
        slug="arceus-code-desktop",
        description="System project for local desktop code missions.",
        status="active",
        settings={"system": True, "source_surface": "arceus_code_desktop"},
        created_by=context.user_id,
    )
    db.add(project)
    db.flush()
    return project


def _mission_plan_dict(compiled: CognitiveCompileResponse) -> dict[str, Any]:
    return compiled.model_dump(mode="json")


def _tasks_for_mission(db: Session, *, tenant_id: UUID, mission_id: UUID) -> list[ArceusTask]:
    return (
        db.query(ArceusTask)
        .filter(ArceusTask.tenant_id == tenant_id, ArceusTask.mission_id == mission_id)
        .order_by(ArceusTask.created_at.asc(), ArceusTask.id.asc())
        .all()
    )


def _dependencies_for_mission(db: Session, *, tenant_id: UUID, tasks: list[ArceusTask]) -> list[ArceusTaskDependency]:
    if not tasks:
        return []
    return (
        db.query(ArceusTaskDependency)
        .filter(ArceusTaskDependency.tenant_id == tenant_id, ArceusTaskDependency.task_id.in_([task.id for task in tasks]))
        .all()
    )


def _event_summaries(db: Session, *, tenant_id: UUID, mission_id: UUID, limit: int = 30) -> list[PersistedMissionEvent]:
    rows = (
        db.query(ArceusEvent)
        .filter(ArceusEvent.tenant_id == tenant_id, ArceusEvent.aggregate_type == "mission", ArceusEvent.aggregate_id == mission_id)
        .order_by(ArceusEvent.aggregate_version.asc())
        .limit(limit)
        .all()
    )
    return [
        PersistedMissionEvent(
            id=str(row.id),
            sequence=int(row.aggregate_version),
            event_type=row.event_type,
            payload=row.payload or {},
            occurred_at=row.occurred_at.isoformat(),
        )
        for row in rows
    ]


def _task_summaries(tasks: list[ArceusTask], dependencies: list[ArceusTaskDependency]) -> list[PersistedMissionTask]:
    task_by_id = {task.id: task for task in tasks}
    deps_by_task: dict[UUID, list[str]] = {}
    for dep in dependencies:
        parent = task_by_id.get(dep.depends_on_task_id)
        if parent:
            deps_by_task.setdefault(dep.task_id, []).append(parent.task_key)
    return [
        PersistedMissionTask(
            id=str(task.id),
            version=int(task.version_number or 1),
            task_key=task.task_key,
            title=task.title,
            task_type=task.task_type,
            status=task.status,
            agent_role=(task.input_contract or {}).get("agent_role"),
            model_hint=(task.input_contract or {}).get("model_hint"),
            dependencies=sorted(deps_by_task.get(task.id, [])),
        )
        for task in tasks
    ]


def _response_for_mission(db: Session, *, tenant_id: UUID, mission: ArceusMission) -> PersistedMissionResponse:
    metadata = mission.metadata_json or {}
    compiled_plan = metadata.get("compiled_plan") or {}
    tasks = _tasks_for_mission(db, tenant_id=tenant_id, mission_id=mission.id)
    dependencies = _dependencies_for_mission(db, tenant_id=tenant_id, tasks=tasks)
    agents = sorted({agent.get("role") for agent in compiled_plan.get("agents", []) if agent.get("role")})
    return PersistedMissionResponse(
        mission_id=str(mission.id),
        status=mission.status,
        display_status="awaiting_approval" if mission.status == "awaiting_plan_approval" else "queued" if mission.status == "ready" else mission.status,
        version=int(mission.version_number or 1),
        goal=mission.objective,
        task_count=len(tasks) or len(compiled_plan.get("tasks", [])),
        dependency_count=len(dependencies) or int((compiled_plan.get("dependency_graph") or {}).get("edge_count") or 0),
        agents=agents,
        confidence=float((compiled_plan.get("report") or {}).get("confidence") or 0),
        warnings=list((compiled_plan.get("report") or {}).get("warnings") or []),
        approval_required=mission.status == "awaiting_plan_approval",
        compiled_plan=compiled_plan,
        tasks=_task_summaries(tasks, dependencies),
        events=_event_summaries(db, tenant_id=tenant_id, mission_id=mission.id),
    )


def create_persisted_mission(
    *,
    db: Session,
    context: RequestContext,
    payload: PersistMissionRequest,
    idempotency_key: str,
) -> PersistedMissionResponse:
    request_hash = calculate_request_hash("mission.persisted.create", payload.model_dump(mode="json"))
    existing = None
    if idempotency_key:
        recent_missions = (
            db.query(ArceusMission)
            .filter(ArceusMission.tenant_id == context.tenant_id)
            .order_by(ArceusMission.created_at.desc())
            .limit(250)
            .all()
        )
        existing = next(
            (mission for mission in recent_missions if (mission.metadata_json or {}).get("persist_idempotency_key") == idempotency_key),
            None,
        )
    if existing is not None:
        if (existing.metadata_json or {}).get("persist_request_hash") != request_hash:
            raise HTTPException(status_code=409, detail={"error": {"code": "IDEMPOTENCY_CONFLICT", "message": "Idempotency key was already used with different mission input.", "retryable": False}})
        return _response_for_mission(db, tenant_id=context.tenant_id, mission=existing)

    compiled = compile_cognitive_mission(
        CognitiveCompileRequest(
            goal=payload.goal,
            workspace_id=payload.workspace_id,
            repository=payload.repository,
            approval_mode="preview",
        )
    )
    project = _project_for_desktop_code(db, context)
    compiled_plan = _mission_plan_dict(compiled)
    mission = ArceusMission(
        tenant_id=context.tenant_id,
        project_id=project.id,
        created_by=context.user_id,
        title=payload.goal.strip()[:160],
        objective=payload.goal,
        status="awaiting_plan_approval",
        risk_level=compiled.understanding.risk_level,
        priority=4 if compiled.understanding.priority in {"high", "critical"} else 3,
        maximum_budget_amount=Decimal("0"),
        budget_currency="USD",
        metadata_json={
            "created_from": "cognitive_execution",
            "workspace_id": payload.workspace_id,
            "repository": payload.repository.model_dump(mode="json"),
            "normalized_intent": compiled.understanding.model_dump(mode="json"),
            "repository_scope": compiled.understanding.repository_scope,
            "compiled_plan": compiled_plan,
            "warnings": compiled.report.warnings,
            "confidence": compiled.report.confidence,
            "constraints": payload.constraints,
            "persist_idempotency_key": idempotency_key,
            "persist_request_hash": request_hash,
        },
    )
    db.add(mission)
    db.flush()
    source_hash = sha256(str(compiled_plan).encode("utf-8")).hexdigest()
    version = ArceusMissionVersion(
        tenant_id=context.tenant_id,
        mission_id=mission.id,
        version=1,
        compiled_by=context.user_id,
        objective_snapshot=mission.objective,
        mission_contract=compiled_plan,
        intent_frame=compiled.understanding.model_dump(mode="json"),
        risk_profile={"risk_level": compiled.understanding.risk_level, "warnings": compiled.report.warnings},
        execution_graph=compiled.dependency_graph,
        source_hash=source_hash,
    )
    db.add(version)
    db.flush()
    mission.current_version_id = version.id
    for decision in compiled.decisions:
        db.add(
            ArceusDecision(
                tenant_id=context.tenant_id,
                mission_id=mission.id,
                decision_key=decision.decision_id,
                title=decision.title,
                summary=decision.reason,
                selected_option=decision.model_dump(mode="json"),
                alternatives=decision.alternatives_rejected,
                rationale=decision.reason,
                status="proposed",
            )
        )
    _append_event(db, tenant_id=context.tenant_id, mission_id=mission.id, event_type="mission.created", actor_id=str(context.user_id), payload={"goal": payload.goal}, correlation_id=context.correlation_id, idempotency_key=idempotency_key)
    _append_event(db, tenant_id=context.tenant_id, mission_id=mission.id, event_type="mission.compiled", actor_id=str(context.user_id), payload={"task_count": len(compiled.tasks), "confidence": compiled.report.confidence}, correlation_id=context.correlation_id, idempotency_key=idempotency_key)
    _append_event(db, tenant_id=context.tenant_id, mission_id=mission.id, event_type="approval.requested", actor_id=str(context.user_id), payload={"status": "awaiting_approval"}, correlation_id=context.correlation_id, idempotency_key=idempotency_key)
    db.commit()
    db.refresh(mission)
    return _response_for_mission(db, tenant_id=context.tenant_id, mission=mission)


def _materialize_tasks_once(
    db: Session,
    *,
    context: RequestContext,
    mission: ArceusMission,
    idempotency_key: str,
) -> tuple[list[ArceusTask], list[ArceusTaskDependency], bool]:
    existing = _tasks_for_mission(db, tenant_id=context.tenant_id, mission_id=mission.id)
    if existing:
        return existing, _dependencies_for_mission(db, tenant_id=context.tenant_id, tasks=existing), False
    compiled_plan = (mission.metadata_json or {}).get("compiled_plan") or {}
    task_specs = [RuntimeTaskSpec(**item) for item in compiled_plan.get("tasks", [])]
    validation = validate_task_dag(task_specs)
    if not validation.valid:
        _append_event(db, tenant_id=context.tenant_id, mission_id=mission.id, event_type="graph.validation_failed", actor_id=str(context.user_id), payload={"errors": validation.errors}, correlation_id=context.correlation_id, idempotency_key=idempotency_key)
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_DAG", "message": "Compiled mission DAG is invalid.", "errors": validation.errors, "retryable": False}})
    agents_by_task = {item.get("task_id"): item for item in compiled_plan.get("agents", [])}
    created: dict[str, ArceusTask] = {}
    for spec in task_specs:
        agent = agents_by_task.get(spec.task_key) or {}
        task = ArceusTask(
            tenant_id=context.tenant_id,
            mission_id=mission.id,
            task_key=spec.task_key,
            title=spec.title,
            task_type=spec.task_type,
            status="pending",
            input_contract={
                "agent_role": agent.get("role"),
                "model_hint": agent.get("model"),
                "dependencies": spec.dependencies,
                "context_sources": next((pkg.get("sources") for pkg in compiled_plan.get("context_packages", []) if pkg.get("task_id") == spec.task_key), []),
                "estimates": {"seconds": spec.estimated_seconds},
                "risk_level": spec.risk_level,
                "priority": spec.priority,
            },
            output_contract={"expected_output": spec.metadata, "acceptance_criteria": spec.acceptance_criteria},
            acceptance_criteria=spec.acceptance_criteria,
        )
        db.add(task)
        db.flush()
        created[spec.task_key] = task
        _append_event(db, tenant_id=context.tenant_id, mission_id=mission.id, task_id=task.id, event_type="task.created", actor_id=str(context.user_id), payload={"task_key": task.task_key, "title": task.title}, correlation_id=context.correlation_id, idempotency_key=idempotency_key)
    dependencies: list[ArceusTaskDependency] = []
    for spec in task_specs:
        task = created[spec.task_key]
        for parent_key in spec.dependencies:
            parent = created[parent_key]
            dependency = ArceusTaskDependency(tenant_id=context.tenant_id, task_id=task.id, depends_on_task_id=parent.id, dependency_type="hard")
            db.add(dependency)
            dependencies.append(dependency)
    db.flush()
    root_keys = set(validation.ready_task_keys or [key for key in validation.topological_order if not created[key].input_contract.get("dependencies")])
    for task_key, task in created.items():
        if task_key in root_keys:
            task.status = "ready"
            task.version_number = int(task.version_number or 1) + 1
            event = _append_event(db, tenant_id=context.tenant_id, mission_id=mission.id, task_id=task.id, event_type="task.ready", actor_id=str(context.user_id), payload={"task_key": task.task_key, "agent_role": task.input_contract.get("agent_role")}, correlation_id=context.correlation_id, idempotency_key=idempotency_key, outbox_topic="arceus.mission.task.ready")
            _append_event(db, tenant_id=context.tenant_id, mission_id=mission.id, task_id=task.id, event_type="task.queued", actor_id=str(context.user_id), payload={"task_key": task.task_key, "outbox_event_id": str(event.id)}, correlation_id=context.correlation_id, idempotency_key=idempotency_key)
        else:
            task.status = "blocked"
            _append_event(db, tenant_id=context.tenant_id, mission_id=mission.id, task_id=task.id, event_type="task.blocked", actor_id=str(context.user_id), payload={"task_key": task.task_key, "dependencies": task.input_contract.get("dependencies", [])}, correlation_id=context.correlation_id, idempotency_key=idempotency_key)
    _append_event(db, tenant_id=context.tenant_id, mission_id=mission.id, event_type="graph.materialized", actor_id=str(context.user_id), payload={"task_count": len(created), "dependency_count": len(dependencies), "root_task_keys": sorted(root_keys)}, correlation_id=context.correlation_id, idempotency_key=idempotency_key)
    return list(created.values()), dependencies, True


def approve_persisted_mission(
    *,
    db: Session,
    context: RequestContext,
    mission_id: UUID,
    payload: MissionApprovalRequest,
    idempotency_key: str,
) -> PersistedMissionResponse:
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.id == mission_id).first()
    if mission is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MISSION_NOT_FOUND", "message": "Mission not found.", "retryable": False}})
    if mission.status in {"ready", "running"}:
        return _response_for_mission(db, tenant_id=context.tenant_id, mission=mission)
    if int(mission.version_number or 1) != payload.expected_version:
        raise HTTPException(status_code=409, detail={"error": {"code": "MISSION_VERSION_CONFLICT", "message": "The mission was updated by another session.", "retryable": True, "current_version": int(mission.version_number or 1)}})
    if mission.status != "awaiting_plan_approval":
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_MISSION_STATE", "message": f"Mission cannot be approved from {mission.status}.", "retryable": False}})
    _materialize_tasks_once(db, context=context, mission=mission, idempotency_key=idempotency_key)
    mission.status = "ready"
    mission.version_number = int(mission.version_number or 1) + 1
    metadata = dict(mission.metadata_json or {})
    metadata["approved_by"] = str(context.user_id)
    metadata["approved_at"] = _now().isoformat()
    metadata["approval_note"] = payload.approval_note
    mission.metadata_json = metadata
    for decision in db.query(ArceusDecision).filter(ArceusDecision.tenant_id == context.tenant_id, ArceusDecision.mission_id == mission.id).all():
        if decision.status == "proposed":
            decision.status = "approved"
            decision.version_number = int(decision.version_number or 1) + 1
    _append_event(db, tenant_id=context.tenant_id, mission_id=mission.id, event_type="approval.granted", actor_id=str(context.user_id), payload={"approval_note": payload.approval_note}, correlation_id=context.correlation_id, idempotency_key=idempotency_key)
    _append_event(db, tenant_id=context.tenant_id, mission_id=mission.id, event_type="mission.queued", actor_id=str(context.user_id), payload={"status": "ready"}, correlation_id=context.correlation_id, idempotency_key=idempotency_key)
    db.commit()
    db.refresh(mission)
    return _response_for_mission(db, tenant_id=context.tenant_id, mission=mission)


def reject_persisted_mission(
    *,
    db: Session,
    context: RequestContext,
    mission_id: UUID,
    payload: MissionRejectRequest,
    idempotency_key: str,
) -> PersistedMissionResponse:
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.id == mission_id).first()
    if mission is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MISSION_NOT_FOUND", "message": "Mission not found.", "retryable": False}})
    if int(mission.version_number or 1) != payload.expected_version:
        raise HTTPException(status_code=409, detail={"error": {"code": "MISSION_VERSION_CONFLICT", "message": "The mission was updated by another session.", "retryable": True, "current_version": int(mission.version_number or 1)}})
    if mission.status not in {"awaiting_plan_approval", "draft", "compiled"}:
        raise HTTPException(status_code=409, detail={"error": {"code": "INVALID_MISSION_STATE", "message": f"Mission cannot be rejected from {mission.status}.", "retryable": False}})
    mission.status = "cancelled"
    mission.failure_reason = payload.reason
    mission.version_number = int(mission.version_number or 1) + 1
    _append_event(db, tenant_id=context.tenant_id, mission_id=mission.id, event_type="approval.rejected", actor_id=str(context.user_id), payload={"reason": payload.reason}, correlation_id=context.correlation_id, idempotency_key=idempotency_key)
    db.commit()
    db.refresh(mission)
    return _response_for_mission(db, tenant_id=context.tenant_id, mission=mission)


@router.post("/compile-cognitive", response_model=CognitiveCompileResponse)
def compile_cognitive_mission_endpoint(payload: CognitiveCompileRequest):
    return compile_cognitive_mission(payload)


@router.post("/persisted", response_model=PersistedMissionResponse, status_code=status.HTTP_201_CREATED)
def create_persisted_mission_endpoint(
    payload: PersistMissionRequest,
    context: RequestContext = Depends(require_permission("mission.create")),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    key = idempotency_key or f"mission-{sha256(payload.model_dump_json().encode('utf-8')).hexdigest()[:24]}"
    result = create_persisted_mission(db=db, context=context, payload=payload, idempotency_key=key)
    return result


@router.get("/persisted/{mission_id}", response_model=PersistedMissionResponse)
def get_persisted_mission_endpoint(
    mission_id: UUID,
    context: RequestContext = Depends(require_permission("mission.view")),
    db: Session = Depends(get_db),
):
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.id == mission_id).first()
    if mission is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MISSION_NOT_FOUND", "message": "Mission not found.", "retryable": False}})
    return _response_for_mission(db, tenant_id=context.tenant_id, mission=mission)


@router.post("/persisted/{mission_id}/approve", response_model=PersistedMissionResponse)
def approve_persisted_mission_endpoint(
    mission_id: UUID,
    payload: MissionApprovalRequest,
    context: RequestContext = Depends(require_permission("mission.approve_plan")),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    result = approve_persisted_mission(db=db, context=context, mission_id=mission_id, payload=payload, idempotency_key=idempotency_key or f"approve-{mission_id}-{payload.expected_version}")
    return result


@router.post("/persisted/{mission_id}/reject", response_model=PersistedMissionResponse)
def reject_persisted_mission_endpoint(
    mission_id: UUID,
    payload: MissionRejectRequest,
    context: RequestContext = Depends(require_permission("mission.approve_plan")),
    db: Session = Depends(get_db),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    result = reject_persisted_mission(db=db, context=context, mission_id=mission_id, payload=payload, idempotency_key=idempotency_key or f"reject-{mission_id}-{payload.expected_version}")
    return result


@router.get("/persisted/{mission_id}/graph", response_model=MissionGraphResponse)
def get_persisted_mission_graph_endpoint(
    mission_id: UUID,
    context: RequestContext = Depends(require_permission("mission.view")),
    db: Session = Depends(get_db),
):
    mission = db.query(ArceusMission).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.id == mission_id).first()
    if mission is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "MISSION_NOT_FOUND", "message": "Mission not found.", "retryable": False}})
    tasks = _tasks_for_mission(db, tenant_id=context.tenant_id, mission_id=mission.id)
    deps = _dependencies_for_mission(db, tenant_id=context.tenant_id, tasks=tasks)
    task_by_id = {task.id: task for task in tasks}
    graph = MissionGraphResponse(
        mission_id=str(mission.id),
        nodes=[
            {
                "id": str(task.id),
                "task_key": task.task_key,
                "title": task.title,
                "status": task.status,
                "agent_role": (task.input_contract or {}).get("agent_role"),
                "model_hint": (task.input_contract or {}).get("model_hint"),
            }
            for task in tasks
        ],
        edges=[
            {
                "from": str(dep.depends_on_task_id),
                "to": str(dep.task_id),
                "from_key": task_by_id[dep.depends_on_task_id].task_key if dep.depends_on_task_id in task_by_id else None,
                "to_key": task_by_id[dep.task_id].task_key if dep.task_id in task_by_id else None,
                "type": "hard",
            }
            for dep in deps
        ],
    )
    return graph
