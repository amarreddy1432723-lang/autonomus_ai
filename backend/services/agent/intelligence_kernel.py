"""Arceus Intelligence Kernel.

The Kernel coordinates intelligence processes before dynamic organizations and
specialists are created. It is intentionally deterministic and serializable so
mission state can be persisted, inspected, tested, and rendered in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


KernelStage = Literal[
    "received",
    "understanding",
    "knowledge_extraction",
    "domain_detection",
    "research",
    "knowledge_graph",
    "organization_creation",
    "strategy",
    "review",
    "approval",
    "execution",
    "validation",
    "deployment",
    "monitoring",
    "improvement",
    "learning",
]


MISSION_PIPELINE: tuple[KernelStage, ...] = (
    "received",
    "understanding",
    "knowledge_extraction",
    "domain_detection",
    "research",
    "knowledge_graph",
    "organization_creation",
    "strategy",
    "review",
    "approval",
    "execution",
    "validation",
    "deployment",
    "monitoring",
    "improvement",
    "learning",
)


INTELLIGENCE_BUS_ENGINES: list[dict[str, str]] = [
    {"id": "mission_manager", "name": "Mission Manager", "purpose": "Understands objective, constraints, unknowns, success criteria, and work packages."},
    {"id": "domain_intelligence", "name": "Domain Intelligence", "purpose": "Detects one or more professional domains and required expertise."},
    {"id": "research_engine", "name": "Research Engine", "purpose": "Searches prior work, standards, documentation, best practices, and uncertainty."},
    {"id": "knowledge_graph", "name": "Knowledge Graph", "purpose": "Links requirements, decisions, documents, lessons, incidents, deployments, and patterns."},
    {"id": "memory_engine", "name": "Memory Engine", "purpose": "Maintains durable organizational memory and user preferences."},
    {"id": "reasoning_engine", "name": "Reasoning Engine", "purpose": "Creates alternatives, compares evidence, and produces defensible recommendations."},
    {"id": "planning_engine", "name": "Planning Engine", "purpose": "Turns mission into milestones, epics, tasks, subtasks, and verification gates."},
    {"id": "simulation_engine", "name": "Simulation Engine", "purpose": "Tests assumptions and forecasts risk, cost, performance, and timeline."},
    {"id": "review_council", "name": "Review Council", "purpose": "Reviews architecture, security, performance, compliance, cost, UX, and evolution."},
    {"id": "conflict_resolver", "name": "Conflict Resolver", "purpose": "Collects disagreements, evaluates trade-offs, documents compromise and rationale."},
    {"id": "execution_engine", "name": "Execution Engine", "purpose": "Coordinates action, verification, merge, deployment, and rollback."},
    {"id": "learning_engine", "name": "Learning Engine", "purpose": "Turns outcomes into reusable knowledge, benchmarks, patterns, and lessons."},
    {"id": "model_router", "name": "Model Router", "purpose": "Chooses the best model for each specialist, task, risk, and cost target."},
    {"id": "tool_router", "name": "Tool Router", "purpose": "Selects safe tools, permissions, sandboxes, previews, and external integrations."},
    {"id": "policy_engine", "name": "Policy Engine", "purpose": "Applies safety, compliance, privacy, auth, billing, and approval constraints."},
    {"id": "meta_intelligence", "name": "Meta Intelligence", "purpose": "Measures Arceus itself: success, latency, cost, accuracy, agent/tool/model quality."},
    {"id": "evolution_engine", "name": "Evolution Engine", "purpose": "Improves organization, kernel, agents, workflows, models, tools, and UX after every mission."},
]


@dataclass(slots=True)
class MissionPlan:
    objective: str
    success_criteria: list[str]
    constraints: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    deliverables: list[str] = field(default_factory=list)
    priority: Literal["low", "normal", "high", "critical"] = "normal"
    stage: KernelStage = "received"
    mission_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.mission_id,
            "objective": self.objective,
            "success_criteria": self.success_criteria,
            "constraints": self.constraints,
            "unknowns": self.unknowns,
            "risks": self.risks,
            "resources": self.resources,
            "deliverables": self.deliverables,
            "priority": self.priority,
            "stage": self.stage,
            "created_at": self.created_at,
            "pipeline": list(MISSION_PIPELINE),
        }


def create_mission_plan(
    objective: str,
    *,
    success_criteria: list[str] | None = None,
    constraints: list[str] | None = None,
    unknowns: list[str] | None = None,
    risks: list[str] | None = None,
    resources: list[str] | None = None,
    deliverables: list[str] | None = None,
    priority: Literal["low", "normal", "high", "critical"] = "normal",
) -> dict[str, Any]:
    """Create a serializable mission plan for kernel orchestration."""

    return MissionPlan(
        objective=objective.strip() or "Unspecified mission",
        success_criteria=success_criteria or ["Validated solution", "Reviewed implementation", "Documented outcome"],
        constraints=constraints or [],
        unknowns=unknowns or [],
        risks=risks or [],
        resources=resources or [],
        deliverables=deliverables or [],
        priority=priority,
    ).to_dict()


def kernel_architecture() -> dict[str, Any]:
    """Return the canonical Arceus Intelligence Kernel architecture."""

    return {
        "name": "Arceus Intelligence Kernel",
        "mission": "Convert any human objective into an optimized, validated, executable mission.",
        "rule": "Understand first. Reason second. Execute third. Improve forever.",
        "pipeline": list(MISSION_PIPELINE),
        "engines": INTELLIGENCE_BUS_ENGINES,
        "execution_hierarchy": ["Mission", "Milestone", "Epic", "Task", "Subtask", "Action", "Verification", "Merge", "Deployment"],
        "meta_metrics": [
            "success",
            "failure",
            "latency",
            "accuracy",
            "cost",
            "user_satisfaction",
            "agent_performance",
            "model_performance",
            "tool_performance",
            "memory_usage",
            "communication_quality",
            "organization_efficiency",
        ],
    }


def summarize_kernel_health(engine_states: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    states = engine_states or [{"id": engine["id"], "status": "ready"} for engine in INTELLIGENCE_BUS_ENGINES]
    total = len(states)
    ready = sum(1 for state in states if state.get("status") in {"ready", "active", "healthy"})
    blocked = sum(1 for state in states if state.get("status") in {"blocked", "failed"})
    return {
        "total_engines": total,
        "ready_engines": ready,
        "blocked_engines": blocked,
        "health": "healthy" if blocked == 0 else "needs_attention",
        "readiness": round((ready / total) * 100, 2) if total else 0,
    }
