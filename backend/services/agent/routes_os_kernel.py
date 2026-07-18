"""Arceus OS Kernel API routes.

Generation 1 exposes a small, isolated surface for software-engineering
missions. The runtime is intentionally in-memory for now; the route contracts
are stable so PostgreSQL-backed persistence can replace the store later.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from .os_kernel.events import Actor, EventMetadata, JsonlEventStore, KernelEvent
from .os_kernel.mission_compiler import MissionCompileRequest as KernelMissionCompileRequest
from .os_kernel.mission_compiler import MissionCompiler
from .os_kernel.missions import MissionState, OSMission
from .os_kernel.policies import AuthorityContext
from .os_kernel.runtime import ArceusOSRuntime


router = APIRouter(prefix="/api/v1/os", tags=["arceus-os"])


def _create_runtime() -> ArceusOSRuntime:
    event_log = os.getenv("ARCEUS_OS_EVENT_LOG")
    if event_log:
        return ArceusOSRuntime(JsonlEventStore(event_log))
    return ArceusOSRuntime()


runtime = _create_runtime()


class MissionCreateRequest(BaseModel):
    tenant_id: str = "default"
    owner_id: str = "local-user"
    title: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=10000)
    success_criteria: list[str] = Field(default_factory=list)
    business_priority: float = Field(default=0.5, ge=0, le=1)
    urgency: float = Field(default=0.5, ge=0, le=1)
    dependency_impact: float = Field(default=0.0, ge=0, le=1)
    user_importance: float = Field(default=0.5, ge=0, le=1)
    risk_reduction_value: float = Field(default=0.0, ge=0, le=1)
    estimated_cost: float = Field(default=0.0, ge=0)
    resource_contention: float = Field(default=0.0, ge=0)
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"


class MissionCompileRequest(BaseModel):
    tenant_id: str = "default"
    actor_id: str = "local-user"
    project_id: str = Field(min_length=1, max_length=200)
    objective: str = Field(min_length=1, max_length=10000)
    repository_ids: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    desired_outcomes: list[str] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=200)


class MissionTransitionRequest(BaseModel):
    state: MissionState


class MissionDesktopClaimRequest(BaseModel):
    desktop_id: str = Field(default="local-desktop", min_length=1, max_length=200)
    local_workspace_path: str | None = Field(default=None, max_length=2000)
    app_version: str | None = Field(default=None, max_length=100)


class ToolPolicyRequest(BaseModel):
    actor_id: str = "agent"
    tenant_id: str = "default"
    role: str = "engineer"
    environment: Literal["local", "development", "staging", "production"] = "development"
    approved: bool = False
    reviewer_ids: list[str] = Field(default_factory=list)
    category: Literal[
        "READ_ONLY",
        "LOCAL_WRITE",
        "NETWORK_ACCESS",
        "EXTERNAL_COMMUNICATION",
        "INFRASTRUCTURE_CHANGE",
        "PRODUCTION_CHANGE",
        "FINANCIAL_ACTION",
        "DESTRUCTIVE_ACTION",
    ]
    risk_level: Literal["low", "medium", "high", "critical"] = "medium"
    author_id: str | None = None


class WorkflowStepCompleteRequest(BaseModel):
    output: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)


class ContextCompileRequest(BaseModel):
    task_title: str = Field(min_length=1, max_length=300)
    task_description: str = Field(default="", max_length=5000)
    has_secret_authority: bool = False


class LessonCreateRequest(BaseModel):
    content: str = Field(min_length=1, max_length=5000)


def _actor(user_id: str | None) -> Actor:
    return Actor("human", user_id or "local-user")


def _mission_or_404(mission_id: str) -> OSMission:
    mission = runtime.missions.missions.get(mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail={"code": "mission_not_found", "message": "Mission not found."})
    return mission


def _compile_request(request: MissionCompileRequest, actor_id: str | None):
    return MissionCompiler().compile(
        KernelMissionCompileRequest(
            tenant_id=request.tenant_id,
            actor_id=actor_id or request.actor_id,
            project_id=request.project_id,
            objective=request.objective,
            repository_ids=request.repository_ids,
            constraints=request.constraints,
            desired_outcomes=request.desired_outcomes,
            budget=request.budget,
        )
    )


def _find_mission_by_idempotency_key(idempotency_key: str) -> OSMission | None:
    for event in runtime.events.all():
        if event.metadata.idempotency_key == idempotency_key and event.mission_id:
            return runtime.missions.missions.get(event.mission_id)
    return None


@router.get("/system/health")
def system_health():
    event_count = len(runtime.events.all())
    active_missions = [mission for mission in runtime.missions.missions.values() if mission.state not in {"COMPLETED", "FAILED", "CANCELLED", "ARCHIVED"}]
    return {
        "service": "arceus-os-kernel",
        "status": "ready",
        "runtime": "in_memory_generation_1",
        "events": event_count,
        "missions": len(runtime.missions.missions),
        "active_missions": len(active_missions),
        "organizations": len(runtime.organizations),
        "workflows": len(runtime.workflows),
        "capabilities": len(runtime.capabilities.discover()),
    }


@router.post("/missions")
def create_mission(request: MissionCreateRequest, x_user_id: str | None = Header(default=None)):
    mission = OSMission(
        tenant_id=request.tenant_id,
        owner_id=request.owner_id,
        title=request.title,
        objective=request.objective,
        success_criteria=request.success_criteria,
        business_priority=request.business_priority,
        urgency=request.urgency,
        dependency_impact=request.dependency_impact,
        user_importance=request.user_importance,
        risk_reduction_value=request.risk_reduction_value,
        estimated_cost=request.estimated_cost,
        resource_contention=request.resource_contention,
        risk_level=request.risk_level,
    )
    runtime.submit_software_mission(mission, _actor(x_user_id))
    return {"mission": mission.to_dict()}


@router.post("/missions/compile")
def compile_mission(request: MissionCompileRequest, x_user_id: str | None = Header(default=None)):
    try:
        compiled = _compile_request(request, x_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "mission_compile_failed", "message": str(exc)}) from exc
    return compiled.to_dict()


@router.post("/missions/compile-store")
def compile_and_store_mission(request: MissionCompileRequest, x_user_id: str | None = Header(default=None)):
    idempotency_key = request.idempotency_key or f"mission-compile:{request.tenant_id}:{request.project_id}:{request.objective.strip().lower()}"
    existing = _find_mission_by_idempotency_key(idempotency_key)
    if existing:
        return {"mission": existing.to_dict(), "duplicate": True, "events": [event.to_dict() for event in runtime.events.by_mission(existing.mission_id)]}

    try:
        compiled = _compile_request(request, x_user_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": "mission_compile_failed", "message": str(exc)}) from exc

    definition = compiled.definition
    mission = OSMission(
        tenant_id=request.tenant_id,
        owner_id=x_user_id or request.actor_id,
        title=definition.title,
        objective=definition.objective,
        success_criteria=definition.success_criteria,
        risk_level=definition.risk_profile.level,
        estimated_cost=float((request.budget or {}).get("maximum") or 0.0),
        state="BLOCKED" if compiled.state == "CLARIFICATION_REQUIRED" else "PLANNING",
    )
    runtime.missions.intake(mission, _actor(x_user_id), idempotency_key=idempotency_key)
    runtime.events.append(
        KernelEvent(
            event_type="ARTIFACT_CREATED",
            aggregate_type="artifact",
            aggregate_id=compiled.compiled_mission_id,
            mission_id=mission.mission_id,
            actor=Actor("system", "mission-compiler"),
            payload={
                "artifact_type": "compiled_mission",
                "compiled_mission_id": compiled.compiled_mission_id,
                "state": compiled.state,
                "intent": compiled.intent.to_dict(),
                "definition": definition.to_dict(),
                "aml": definition.to_aml(),
            },
            metadata=EventMetadata(correlation_id=mission.mission_id, idempotency_key=f"{idempotency_key}:compiled-artifact"),
        )
    )
    if compiled.state == "CLARIFICATION_REQUIRED":
        runtime.events.append(
            KernelEvent(
                event_type="MISSION_UPDATED",
                aggregate_type="mission",
                aggregate_id=mission.mission_id,
                mission_id=mission.mission_id,
                actor=Actor("system", "mission-compiler"),
                payload={"to": "BLOCKED", "reason": "clarification_required", "unknowns": definition.unknowns},
                metadata=EventMetadata(correlation_id=mission.mission_id, idempotency_key=f"{idempotency_key}:blocked"),
            )
        )

    return {
        "mission": mission.to_dict(),
        "compiled": compiled.to_dict(),
        "duplicate": False,
        "events": [event.to_dict() for event in runtime.events.by_mission(mission.mission_id)],
    }


@router.get("/missions")
def list_missions():
    return {"missions": [mission.to_dict() for mission in runtime.missions.missions.values()]}


@router.get("/missions/{mission_id}")
def get_mission(mission_id: str):
    return {"mission": _mission_or_404(mission_id).to_dict()}


@router.get("/missions/{mission_id}/sync")
def sync_mission(mission_id: str):
    mission = _mission_or_404(mission_id)
    events = [event.to_dict() for event in runtime.events.by_mission(mission_id)]
    compiled_artifacts = [
        event.payload
        for event in runtime.events.by_mission(mission_id)
        if event.event_type == "ARTIFACT_CREATED" and event.payload.get("artifact_type") == "compiled_mission"
    ]
    workflow = next((run for run in runtime.workflows.values() if run.mission_id == mission_id), None)
    return {
        "mission": mission.to_dict(),
        "compiled_mission": compiled_artifacts[-1] if compiled_artifacts else None,
        "organization": runtime.organizations.get(mission_id).to_dict() if mission_id in runtime.organizations else None,
        "workflow": {
            "run_id": workflow.run_id,
            "state": workflow.state,
            "steps": [
                {
                    "step_id": step.step_id,
                    "name": step.name,
                    "owner": step.owner,
                    "state": step.state,
                    "required_approvals": step.required_approvals,
                }
                for step in workflow.steps
            ],
        } if workflow else None,
        "events": events,
        "cursor": events[-1]["event_id"] if events else None,
    }


@router.post("/missions/{mission_id}/desktop-claim")
def claim_mission_for_desktop(mission_id: str, request: MissionDesktopClaimRequest, x_user_id: str | None = Header(default=None)):
    mission = _mission_or_404(mission_id)
    actor = _actor(x_user_id)
    try:
        runtime.events.append(
            KernelEvent(
                event_type="MISSION_UPDATED",
                aggregate_type="mission",
                aggregate_id=mission_id,
                mission_id=mission_id,
                actor=actor,
                payload={
                    "desktop_claimed": True,
                    "desktop_id": request.desktop_id,
                    "local_workspace_path": request.local_workspace_path,
                    "app_version": request.app_version,
                },
                metadata=EventMetadata(correlation_id=mission_id, idempotency_key=f"desktop-claim:{mission_id}:{request.desktop_id}"),
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"code": "duplicate_operation", "message": str(exc)}) from exc
    return {"mission": mission.to_dict(), "claimed": True, "sync_url": f"/api/v1/os/missions/{mission_id}/sync"}


@router.post("/missions/{mission_id}/transition")
def transition_mission(mission_id: str, request: MissionTransitionRequest, x_user_id: str | None = Header(default=None)):
    _mission_or_404(mission_id)
    try:
        mission = runtime.missions.transition(mission_id, request.state, _actor(x_user_id))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"code": "invalid_transition", "message": str(exc)}) from exc
    return {"mission": mission.to_dict()}


@router.post("/missions/{mission_id}/pause")
def pause_mission(mission_id: str, x_user_id: str | None = Header(default=None)):
    _mission_or_404(mission_id)
    mission = runtime.missions.pause_immediately(mission_id, _actor(x_user_id))
    return {"mission": mission.to_dict()}


@router.post("/missions/{mission_id}/organization")
def form_organization(mission_id: str, x_user_id: str | None = Header(default=None)):
    _mission_or_404(mission_id)
    try:
        organization = runtime.form_engineering_organization(mission_id, _actor(x_user_id))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"code": "duplicate_operation", "message": str(exc)}) from exc
    return {"organization": organization.to_dict()}


@router.post("/missions/{mission_id}/workflow")
def create_workflow(mission_id: str):
    _mission_or_404(mission_id)
    workflow = runtime.create_implementation_workflow(mission_id)
    return {
        "workflow": {
            "run_id": workflow.run_id,
            "mission_id": workflow.mission_id,
            "state": workflow.state,
            "steps": [
                {
                    "step_id": step.step_id,
                    "name": step.name,
                    "owner": step.owner,
                    "state": step.state,
                    "idempotency_key": step.idempotency_key,
                    "required_approvals": step.required_approvals,
                }
                for step in workflow.steps
            ],
        }
    }


@router.post("/workflows/{run_id}/steps/{step_id}/complete")
def complete_workflow_step(run_id: str, step_id: str, request: WorkflowStepCompleteRequest):
    if run_id not in runtime.workflows:
        raise HTTPException(status_code=404, detail={"code": "workflow_not_found", "message": "Workflow run not found."})
    try:
        step = runtime.execute_workflow_step(run_id, step_id, request.output, request.evidence)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"code": "step_completion_failed", "message": str(exc)}) from exc
    return {"step": {"step_id": step.step_id, "name": step.name, "state": step.state, "evidence": step.evidence}}


@router.get("/missions/{mission_id}/events")
def mission_events(mission_id: str):
    _mission_or_404(mission_id)
    return {"events": [event.to_dict() for event in runtime.events.by_mission(mission_id)]}


@router.get("/events/replay")
def replay_events(aggregate_type: str | None = None, aggregate_id: str | None = None):
    return {"events": runtime.events.replay(aggregate_type=aggregate_type, aggregate_id=aggregate_id)}  # type: ignore[arg-type]


@router.get("/capabilities")
def list_capabilities(domain: str | None = None, category: str | None = None):
    domains = [domain] if domain else None
    return {"capabilities": [capability.to_dict() for capability in runtime.capabilities.discover(domains=domains, category=category)]}


@router.post("/missions/{mission_id}/tool-policy")
def evaluate_tool(mission_id: str, request: ToolPolicyRequest):
    _mission_or_404(mission_id)
    return runtime.request_tool_action(
        mission_id,
        AuthorityContext(
            actor_id=request.actor_id,
            tenant_id=request.tenant_id,
            role=request.role,
            environment=request.environment,
            approved=request.approved,
            reviewer_ids=request.reviewer_ids,
        ),
        request.category,
        request.risk_level,
        author_id=request.author_id,
    )


@router.post("/missions/{mission_id}/context")
def compile_context(mission_id: str, request: ContextCompileRequest):
    _mission_or_404(mission_id)
    return runtime.compile_context_for_task(
        mission_id,
        request.task_title,
        request.task_description,
        has_secret_authority=request.has_secret_authority,
    )
