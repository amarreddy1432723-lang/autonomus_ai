"""Generation 1 Arceus OS software-engineering mission runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .capabilities import CapabilityRegistry, default_software_engineering_registry
from .context_compiler import ContextCompiler, ContextRequest
from .events import Actor, AppendOnlyEventStore, EventMetadata, KernelEvent
from .missions import MissionBudget, MissionService, MissionState, OSMission
from .policies import AuthorityContext, evaluate_tool_policy
from .resources import ResourceBudget
from .scheduler import MissionScheduler
from .workflows import WorkflowRun, WorkflowStep
from .world_model import KnowledgeItem, WorldModel


@dataclass(slots=True)
class EngineeringOrganization:
    mission_id: str
    tenant_id: str
    lead: str = "Engineering Manager"
    specialists: list[str] = field(
        default_factory=lambda: [
            "Engineering Manager",
            "Architect",
            "Implementation Engineer",
            "Security Reviewer",
            "QA Reviewer",
        ]
    )
    budget: ResourceBudget = field(default_factory=lambda: ResourceBudget(token_budget=100_000, cost_budget=25.0, tool_calls=100, model_calls=50))

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "tenant_id": self.tenant_id,
            "lead": self.lead,
            "specialists": self.specialists,
            "budget": self.budget.summary(),
        }


class ArceusOSRuntime:
    """A minimal durable loop for software-engineering missions."""

    def __init__(self, event_store: AppendOnlyEventStore | None = None, *, rebuild: bool = True) -> None:
        self.events = event_store or AppendOnlyEventStore()
        self.missions = MissionService(self.events)
        self.scheduler = MissionScheduler()
        self.capabilities: CapabilityRegistry = default_software_engineering_registry()
        self.world_model = WorldModel()
        self.context_compiler = ContextCompiler(self.world_model, self.capabilities)
        self.organizations: dict[str, EngineeringOrganization] = {}
        self.workflows: dict[str, WorkflowRun] = {}
        if rebuild:
            self.rebuild_from_events()

    def rebuild_from_events(self) -> None:
        """Rebuild current projections from the append-only event log."""

        self.missions.missions.clear()
        self.organizations.clear()
        self.world_model.knowledge.clear()

        for event in self.events.all():
            if event.event_type == "MISSION_CREATED":
                payload = event.payload
                budget_payload = payload.get("budget") or {}
                mission = OSMission(
                    tenant_id=payload.get("tenant_id") or "default",
                    owner_id=payload.get("owner_id") or "local-user",
                    title=payload.get("title") or "Untitled mission",
                    objective=payload.get("objective") or "",
                    business_priority=float(payload.get("business_priority") or 0.5),
                    urgency=float(payload.get("urgency") or 0.5),
                    dependency_impact=float(payload.get("dependency_impact") or 0.0),
                    user_importance=float(payload.get("user_importance") or 0.5),
                    risk_reduction_value=float(payload.get("risk_reduction_value") or 0.0),
                    estimated_cost=float(payload.get("estimated_cost") or 0.0),
                    resource_contention=float(payload.get("resource_contention") or 0.0),
                    risk_level=payload.get("risk_level") or "medium",
                    dependencies=list(payload.get("dependencies") or []),
                    success_criteria=list(payload.get("success_criteria") or []),
                    budget=MissionBudget(
                        maximum_cost=float(budget_payload.get("maximum_cost") or 0.0),
                        token_budget=int(budget_payload.get("token_budget") or 0),
                    ),
                    state=payload.get("state") or "DRAFT",
                    paused_by_user=bool(payload.get("paused_by_user") or False),
                    mission_id=payload.get("mission_id") or event.aggregate_id,
                    created_at=payload.get("created_at") or event.created_at,
                    updated_at=payload.get("updated_at") or event.created_at,
                )
                self.missions.missions[mission.mission_id] = mission
                self.world_model.write(
                    KnowledgeItem(
                        tenant_id=mission.tenant_id,
                        kind="CLAIM",
                        content=mission.objective,
                        source="mission_intake_replay",
                        author=event.actor.id,
                        scope="mission",
                        confidence=0.7,
                        verification_status="UNVERIFIED",
                    )
                )
                continue

            if event.event_type in {
                "MISSION_UPDATED",
                "MISSION_APPROVED",
                "MISSION_PAUSED",
                "MISSION_RESUMED",
                "MISSION_CANCELLED",
                "MISSION_COMPLETED",
            }:
                mission_id = event.mission_id or event.aggregate_id
                mission = self.missions.missions.get(mission_id)
                if mission and event.payload.get("to"):
                    mission.state = event.payload["to"]  # type: ignore[assignment]
                    mission.paused_by_user = event.event_type == "MISSION_PAUSED" or mission.paused_by_user
                    mission.updated_at = event.created_at
                continue

            if event.event_type == "ORGANIZATION_FORMED":
                payload = event.payload
                mission_id = event.mission_id or payload.get("mission_id")
                if mission_id:
                    self.organizations[mission_id] = EngineeringOrganization(
                        mission_id=mission_id,
                        tenant_id=payload.get("tenant_id") or self.missions.missions.get(mission_id, OSMission("default", "local-user", "Unknown", "")).tenant_id,
                        lead=payload.get("lead") or "Engineering Manager",
                        specialists=list(payload.get("specialists") or []),
                    )
                continue

            if event.event_type == "LESSON_RECORDED":
                mission_id = event.mission_id or event.aggregate_id
                org = self.organizations.get(mission_id)
                if org:
                    self.world_model.write(
                        KnowledgeItem(
                            tenant_id=org.tenant_id,
                            kind="FACT",
                            content=event.payload.get("lesson") or "Approved mission lesson",
                            source="event_replay",
                            author=event.actor.id,
                            scope="organization",
                            confidence=0.9,
                            verification_status="APPROVED",
                        )
                    )

    def submit_software_mission(self, mission: OSMission, actor: Actor) -> OSMission:
        self.missions.intake(mission, actor, idempotency_key=f"mission:{mission.mission_id}:created")
        self.world_model.write(
            KnowledgeItem(
                tenant_id=mission.tenant_id,
                kind="CLAIM",
                content=mission.objective,
                source="mission_intake",
                author=actor.id,
                scope="mission",
                confidence=0.7,
                verification_status="UNVERIFIED",
            )
        )
        return mission

    def form_engineering_organization(self, mission_id: str, actor: Actor) -> EngineeringOrganization:
        mission = self.missions.missions[mission_id]
        org = EngineeringOrganization(mission_id=mission_id, tenant_id=mission.tenant_id)
        self.organizations[mission_id] = org
        self.events.append(
            KernelEvent(
                event_type="ORGANIZATION_FORMED",
                aggregate_type="organization",
                aggregate_id=mission_id,
                mission_id=mission_id,
                actor=actor,
                payload=org.to_dict(),
                metadata=EventMetadata(correlation_id=mission_id, idempotency_key=f"org:{mission_id}:formed"),
            )
        )
        for specialist in org.specialists:
            self.events.append(
                KernelEvent(
                    event_type="AGENT_CREATED",
                    aggregate_type="agent",
                    aggregate_id=f"{mission_id}:{specialist}",
                    mission_id=mission_id,
                    actor=actor,
                    payload={"role": specialist},
                    metadata=EventMetadata(correlation_id=mission_id),
                )
            )
        return org

    def create_implementation_workflow(self, mission_id: str) -> WorkflowRun:
        steps = [
            WorkflowStep("Repository analysis", "Architect", {"kind": "repo"}, {"analysis": "structured"}, 300, f"{mission_id}:analyze"),
            WorkflowStep("Implementation plan", "Engineering Manager", {"kind": "plan"}, {"plan": "approved"}, 300, f"{mission_id}:plan", required_approvals=["mission_owner"]),
            WorkflowStep("Isolated branch implementation", "Implementation Engineer", {"kind": "patch"}, {"patch": "created"}, 900, f"{mission_id}:implement"),
            WorkflowStep("Independent security review", "Security Reviewer", {"kind": "review"}, {"verdict": "approved"}, 600, f"{mission_id}:security-review"),
            WorkflowStep("Independent QA review", "QA Reviewer", {"kind": "tests"}, {"tests": "passed"}, 600, f"{mission_id}:qa-review"),
            WorkflowStep("User merge approval", "Mission Owner", {"kind": "approval"}, {"approval": "granted"}, 86400, f"{mission_id}:merge-approval", required_approvals=["mission_owner"]),
            WorkflowStep("Mission lesson storage", "Learning Engine", {"kind": "lesson"}, {"lesson": "approved"}, 300, f"{mission_id}:lesson"),
        ]
        run = WorkflowRun(mission_id=mission_id, steps=steps)
        self.workflows[run.run_id] = run
        for step in steps:
            self.events.append(
                KernelEvent(
                    event_type="TASK_CREATED",
                    aggregate_type="task",
                    aggregate_id=step.step_id,
                    mission_id=mission_id,
                    actor=Actor("system", "os-kernel"),
                    payload={"name": step.name, "owner": step.owner, "idempotency_key": step.idempotency_key},
                    metadata=EventMetadata(correlation_id=mission_id),
                )
            )
        return run

    def execute_workflow_step(self, run_id: str, step_id: str, output: dict[str, Any], evidence: dict[str, Any]) -> WorkflowStep:
        run = self.workflows[run_id]
        step = run.execute_step(step_id, output, evidence)
        self.events.append(
            KernelEvent(
                event_type="TASK_COMPLETED",
                aggregate_type="task",
                aggregate_id=step.step_id,
                mission_id=run.mission_id,
                actor=Actor("agent", step.owner),
                payload={"name": step.name, "output": output, "evidence": evidence},
                metadata=EventMetadata(correlation_id=run.mission_id, idempotency_key=f"task:{step.step_id}:completed"),
            )
        )
        if step.name == "Mission lesson storage":
            self.world_model.write(
                KnowledgeItem(
                    tenant_id=self.organizations[run.mission_id].tenant_id,
                    kind="FACT",
                    content=evidence.get("lesson", "Approved mission lesson"),
                    source="mission_completion",
                    author=step.owner,
                    scope="organization",
                    confidence=0.9,
                    verification_status="APPROVED",
                )
            )
            self.events.append(
                KernelEvent(
                    event_type="LESSON_RECORDED",
                    aggregate_type="mission",
                    aggregate_id=run.mission_id,
                    mission_id=run.mission_id,
                    actor=Actor("system", "learning-engine"),
                    payload={"lesson": evidence.get("lesson", "Approved mission lesson")},
                    metadata=EventMetadata(correlation_id=run.mission_id),
                )
            )
        return step

    def request_tool_action(self, mission_id: str, context: AuthorityContext, category: str, risk_level: str, *, author_id: str | None = None) -> dict[str, Any]:
        decision = evaluate_tool_policy(context, category, risk_level, author_id=author_id)  # type: ignore[arg-type]
        self.events.append(
            KernelEvent(
                event_type="TOOL_REQUESTED" if decision.allowed else "POLICY_VIOLATION",
                aggregate_type="mission",
                aggregate_id=mission_id,
                mission_id=mission_id,
                actor=Actor("agent", context.actor_id),
                payload={"category": category, "risk_level": risk_level, "allowed": decision.allowed, "reason": decision.reason},
                metadata=EventMetadata(correlation_id=mission_id),
            )
        )
        return {"allowed": decision.allowed, "reason": decision.reason, "requires_human_approval": decision.requires_human_approval}

    def compile_context_for_task(self, mission_id: str, task_title: str, task_description: str, *, has_secret_authority: bool = False) -> dict[str, Any]:
        mission = self.missions.missions[mission_id]
        return self.context_compiler.compile(
            ContextRequest(
                tenant_id=mission.tenant_id,
                agent_role="Implementation Engineer",
                task_title=task_title,
                task_description=task_description,
                mission=mission,
                has_secret_authority=has_secret_authority,
            )
        )
