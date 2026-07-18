"""Generation 1 multi-agent collaboration runtime primitives.

This module is intentionally provider-independent. It defines the durable shapes
and deterministic helpers that let Arceus represent missions, temporary
organizations, scoped agents, structured communication, review councils, tasks,
decisions, and context selection before any LLM or tool execution happens.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


Priority = Literal["low", "medium", "high", "critical"]
MemoryLevel = Literal["global", "organization", "mission", "agent_working"]
RuntimeEventType = Literal[
    "mission_created",
    "mission_updated",
    "organization_created",
    "task_created",
    "task_transitioned",
    "message_published",
    "review_recorded",
    "approval_recorded",
    "verification_recorded",
    "mission_report_created",
    "lesson_recorded",
]
MissionStatus = Literal["discovery", "planning", "review", "approved", "executing", "validating", "completed", "failed"]
MissionType = Literal["build", "investigate", "repair", "research", "optimize", "plan"]
OrganizationStatus = Literal["forming", "active", "paused", "completed"]
AgentStatus = Literal["available", "working", "waiting", "reviewing", "blocked"]
Seniority = Literal["associate", "senior", "staff", "principal", "distinguished", "domain_expert"]
TaskStatus = Literal["backlog", "ready", "in_progress", "blocked", "review", "rejected", "approved", "completed"]
TaskType = Literal["research", "design", "implementation", "review", "testing", "deployment", "monitoring"]
RiskLevel = Literal["low", "medium", "high", "critical"]
DecisionStatus = Literal["proposed", "under_review", "approved", "rejected", "superseded"]
DecisionType = Literal["architecture", "product", "security", "implementation", "infrastructure", "policy"]
ReviewVerdict = Literal["approve", "approve_with_conditions", "reject", "needs_information"]
MessageType = Literal["request", "response", "proposal", "finding", "objection", "decision", "approval", "rejection", "escalation", "update"]
RecipientType = Literal["agent", "team", "council", "broadcast"]
ExecutionMode = Literal["observer", "collaborator", "engineer", "autonomous"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


@dataclass(slots=True)
class Budget:
    currency: str = "USD"
    maximum_cost: float | None = None
    token_budget: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "maximum_cost": self.maximum_cost,
            "token_budget": self.token_budget,
        }


@dataclass(slots=True)
class Mission:
    title: str
    description: str
    mission_type: MissionType = "build"
    domains: list[str] = field(default_factory=lambda: ["software_engineering"])
    objectives: list[str] = field(default_factory=list)
    success_criteria: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    resources: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    priority: Priority = "medium"
    budget: Budget = field(default_factory=Budget)
    deadline: str | None = None
    status: MissionStatus = "discovery"
    mission_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def can_enter_execution(self) -> bool:
        return bool(self.objectives and self.success_criteria and self.status in {"approved", "executing"})

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_id": self.mission_id,
            "title": self.title,
            "description": self.description,
            "mission_type": self.mission_type,
            "domains": self.domains,
            "objectives": self.objectives,
            "success_criteria": self.success_criteria,
            "constraints": self.constraints,
            "assumptions": self.assumptions,
            "unknowns": self.unknowns,
            "resources": self.resources,
            "risks": self.risks,
            "priority": self.priority,
            "budget": self.budget.to_dict(),
            "deadline": self.deadline,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class ModelPolicy:
    preferred_models: list[str] = field(default_factory=list)
    fallback_models: list[str] = field(default_factory=list)
    maximum_cost_per_task: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "preferred_models": self.preferred_models,
            "fallback_models": self.fallback_models,
            "maximum_cost_per_task": self.maximum_cost_per_task,
        }


@dataclass(slots=True)
class MemoryScope:
    mission_memory: bool = True
    organization_memory: bool = True
    private_scratchpad: bool = True
    global_memory: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "mission_memory": self.mission_memory,
            "organization_memory": self.organization_memory,
            "private_scratchpad": self.private_scratchpad,
            "global_memory": self.global_memory,
        }


@dataclass(slots=True)
class Authority:
    can_propose: bool = True
    can_execute: bool = False
    can_approve: bool = False
    can_block: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "can_propose": self.can_propose,
            "can_execute": self.can_execute,
            "can_approve": self.can_approve,
            "can_block": self.can_block,
        }


@dataclass(slots=True)
class AgentProfile:
    organization_id: str
    name: str
    role: str
    domain: str
    seniority: Seniority = "staff"
    responsibilities: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    model_policy: ModelPolicy = field(default_factory=ModelPolicy)
    memory_scope: MemoryScope = field(default_factory=MemoryScope)
    authority: Authority = field(default_factory=Authority)
    status: AgentStatus = "available"
    agent_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "organization_id": self.organization_id,
            "name": self.name,
            "role": self.role,
            "domain": self.domain,
            "seniority": self.seniority,
            "responsibilities": self.responsibilities,
            "capabilities": self.capabilities,
            "tools": self.tools,
            "model_policy": self.model_policy.to_dict(),
            "memory_scope": self.memory_scope.to_dict(),
            "authority": self.authority.to_dict(),
            "status": self.status,
        }


@dataclass(slots=True)
class DynamicOrganization:
    mission_id: str
    name: str
    lead_agent_id: str
    agents: list[AgentProfile]
    organization_type: Literal["temporary", "persistent"] = "temporary"
    review_councils: list[dict[str, Any]] = field(default_factory=list)
    communication_policy: dict[str, Any] = field(default_factory=dict)
    approval_policy: dict[str, Any] = field(default_factory=dict)
    status: OrganizationStatus = "forming"
    organization_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "organization_id": self.organization_id,
            "mission_id": self.mission_id,
            "name": self.name,
            "organization_type": self.organization_type,
            "lead_agent_id": self.lead_agent_id,
            "agents": [agent.to_dict() for agent in self.agents],
            "review_councils": self.review_councils,
            "communication_policy": self.communication_policy,
            "approval_policy": self.approval_policy,
            "status": self.status,
        }


@dataclass(slots=True)
class MessageRecipient:
    type: RecipientType
    ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "ids": self.ids}


@dataclass(slots=True)
class MessageEnvelope:
    mission_id: str
    organization_id: str
    from_agent_id: str
    to: MessageRecipient
    message_type: MessageType
    topic: str
    summary: str
    content: dict[str, Any] = field(default_factory=dict)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    confidence: float = 0.75
    priority: Priority = "medium"
    requires_response: bool = False
    response_deadline: str | None = None
    related_task_ids: list[str] = field(default_factory=list)
    related_decision_ids: list[str] = field(default_factory=list)
    message_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "mission_id": self.mission_id,
            "organization_id": self.organization_id,
            "from_agent_id": self.from_agent_id,
            "to": self.to.to_dict(),
            "message_type": self.message_type,
            "topic": self.topic,
            "summary": self.summary,
            "content": self.content,
            "evidence": self.evidence,
            "assumptions": self.assumptions,
            "risks": self.risks,
            "confidence": max(0.0, min(1.0, float(self.confidence))),
            "priority": self.priority,
            "requires_response": self.requires_response,
            "response_deadline": self.response_deadline,
            "related_task_ids": self.related_task_ids,
            "related_decision_ids": self.related_decision_ids,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class Task:
    mission_id: str
    title: str
    description: str
    task_type: TaskType
    assigned_agent_id: str
    reviewer_agent_ids: list[str] = field(default_factory=list)
    parent_task_id: str | None = None
    dependencies: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    risk_level: RiskLevel = "medium"
    approval_required: bool = False
    status: TaskStatus = "backlog"
    attempt_count: int = 0
    maximum_attempts: int = 3
    task_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)
    completed_at: str | None = None

    def has_completion_evidence(self) -> bool:
        return bool(self.evidence)

    def can_complete(self) -> bool:
        return self.status in {"approved", "completed"} and self.has_completion_evidence()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "mission_id": self.mission_id,
            "parent_task_id": self.parent_task_id,
            "title": self.title,
            "description": self.description,
            "task_type": self.task_type,
            "assigned_agent_id": self.assigned_agent_id,
            "reviewer_agent_ids": self.reviewer_agent_ids,
            "dependencies": self.dependencies,
            "inputs": self.inputs,
            "expected_outputs": self.expected_outputs,
            "acceptance_criteria": self.acceptance_criteria,
            "evidence": self.evidence,
            "risk_level": self.risk_level,
            "approval_required": self.approval_required,
            "status": self.status,
            "attempt_count": self.attempt_count,
            "maximum_attempts": self.maximum_attempts,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }


@dataclass(slots=True)
class DecisionAlternative:
    name: str
    advantages: list[str] = field(default_factory=list)
    disadvantages: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    estimated_cost: float | None = None
    estimated_time: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "advantages": self.advantages,
            "disadvantages": self.disadvantages,
            "risks": self.risks,
            "estimated_cost": self.estimated_cost,
            "estimated_time": self.estimated_time,
        }


@dataclass(slots=True)
class ReviewResult:
    reviewer: str
    verdict: ReviewVerdict
    findings: list[str] = field(default_factory=list)
    blocking_issues: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    confidence: float = 0.75
    evidence: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewer": self.reviewer,
            "verdict": self.verdict,
            "findings": self.findings,
            "blocking_issues": self.blocking_issues,
            "recommendations": self.recommendations,
            "confidence": max(0.0, min(1.0, float(self.confidence))),
            "evidence": self.evidence,
        }


@dataclass(slots=True)
class Decision:
    mission_id: str
    title: str
    problem: str
    decision_type: DecisionType
    proposed_by: str
    alternatives: list[DecisionAlternative] = field(default_factory=list)
    selected_option: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    reviewers: list[str] = field(default_factory=list)
    review_results: list[ReviewResult] = field(default_factory=list)
    confidence: float = 0.0
    status: DecisionStatus = "proposed"
    requires_human_approval: bool = False
    decision_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "mission_id": self.mission_id,
            "title": self.title,
            "problem": self.problem,
            "decision_type": self.decision_type,
            "proposed_by": self.proposed_by,
            "alternatives": [alternative.to_dict() for alternative in self.alternatives],
            "selected_option": self.selected_option,
            "evidence": self.evidence,
            "assumptions": self.assumptions,
            "reviewers": self.reviewers,
            "review_results": [review.to_dict() for review in self.review_results],
            "confidence": max(0.0, min(1.0, float(self.confidence))),
            "status": self.status,
            "requires_human_approval": self.requires_human_approval,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class WorkspaceArtifact:
    kind: str
    title: str
    content: Any
    memory_level: MemoryLevel = "mission"
    confidentiality: Literal["public", "mission", "organization", "private"] = "mission"
    freshness: int = 100
    relevance_tags: list[str] = field(default_factory=list)
    artifact_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    def to_context_item(self) -> dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "kind": self.kind,
            "title": self.title,
            "content": self.content,
            "memory_level": self.memory_level,
            "confidentiality": self.confidentiality,
            "freshness": self.freshness,
            "relevance_tags": self.relevance_tags,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class SharedWorkspace:
    mission: Mission
    requirements: list[WorkspaceArtifact] = field(default_factory=list)
    decisions: list[Decision] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    artifacts: list[WorkspaceArtifact] = field(default_factory=list)
    risks: list[WorkspaceArtifact] = field(default_factory=list)
    reviews: list[ReviewResult] = field(default_factory=list)
    metrics: list[WorkspaceArtifact] = field(default_factory=list)
    lessons: list[WorkspaceArtifact] = field(default_factory=list)

    def select_context(
        self,
        *,
        task: Task | None = None,
        tags: list[str] | None = None,
        authority: Authority | None = None,
        allowed_memory_levels: set[MemoryLevel] | None = None,
        limit: int = 12,
    ) -> dict[str, Any]:
        tags_set = {tag.lower() for tag in (tags or [])}
        if task:
            tags_set.update(term.lower() for term in [task.task_type, task.title, *task.inputs])

        pool: list[WorkspaceArtifact] = [
            *self.requirements,
            *self.artifacts,
            *self.risks,
            *self.metrics,
            *self.lessons,
        ]
        confidentiality_allowed = {"public", "mission", "organization"}
        memory_allowed = allowed_memory_levels or {"global", "organization", "mission"}
        if authority and authority.can_approve:
            confidentiality_allowed.add("private")
            memory_allowed.add("agent_working")

        scored: list[tuple[int, WorkspaceArtifact]] = []
        for artifact in pool:
            if artifact.confidentiality not in confidentiality_allowed:
                continue
            if artifact.memory_level not in memory_allowed:
                continue
            overlap = tags_set.intersection(tag.lower() for tag in artifact.relevance_tags)
            score = len(overlap) * 10 + artifact.freshness
            scored.append((score, artifact))
        scored.sort(key=lambda item: item[0], reverse=True)

        return {
            "mission_summary": {
                "mission_id": self.mission.mission_id,
                "title": self.mission.title,
                "objectives": self.mission.objectives,
                "success_criteria": self.mission.success_criteria,
                "constraints": self.mission.constraints,
                "risks": self.mission.risks,
            },
            "task": task.to_dict() if task else None,
            "relevant_decisions": [decision.to_dict() for decision in self.decisions[:5]],
            "related_artifacts": [artifact.to_context_item() for _, artifact in scored[:limit]],
            "known_risks": [risk.to_context_item() for risk in self.risks[:5]],
            "required_output_format": "structured evidence-first response with assumptions, risks, and verification evidence",
        }


@dataclass(slots=True)
class RuntimeEvent:
    mission_id: str
    event_type: RuntimeEventType
    summary: str
    actor_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "mission_id": self.mission_id,
            "event_type": self.event_type,
            "summary": self.summary,
            "actor_id": self.actor_id,
            "payload": self.payload,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class MissionReport:
    mission_id: str
    status: MissionStatus
    summary: str
    completed_tasks: list[dict[str, Any]]
    open_tasks: list[dict[str, Any]]
    decisions: list[dict[str, Any]]
    evidence: list[dict[str, Any]]
    lessons: list[dict[str, Any]]
    report_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "report_id": self.report_id,
            "mission_id": self.mission_id,
            "status": self.status,
            "summary": self.summary,
            "completed_tasks": self.completed_tasks,
            "open_tasks": self.open_tasks,
            "decisions": self.decisions,
            "evidence": self.evidence,
            "lessons": self.lessons,
            "created_at": self.created_at,
        }


def default_generation_one_agents(organization_id: str, domain: str = "software_engineering") -> list[AgentProfile]:
    return [
        AgentProfile(
            organization_id=organization_id,
            name="Product Analyst",
            role="product_analyst",
            domain=domain,
            responsibilities=["Clarify objective", "Define success criteria", "Identify user and business risks"],
            capabilities=["requirements_analysis", "market_reasoning", "prioritization"],
        ),
        AgentProfile(
            organization_id=organization_id,
            name="Solution Architect",
            role="solution_architect",
            domain=domain,
            seniority="principal",
            responsibilities=["Design architecture", "Compare alternatives", "Resolve technical conflicts"],
            capabilities=["architecture", "scalability", "tradeoff_analysis"],
            authority=Authority(can_propose=True, can_execute=False, can_approve=True, can_block=True),
        ),
        AgentProfile(
            organization_id=organization_id,
            name="Implementation Engineer",
            role="implementation_engineer",
            domain=domain,
            responsibilities=["Prepare implementation plan", "Create reviewable patches", "Collect verification evidence"],
            capabilities=["coding", "debugging", "tests"],
            tools=["file_read", "code_search", "sandbox_checks"],
            authority=Authority(can_propose=True, can_execute=True, can_approve=False, can_block=False),
        ),
        AgentProfile(
            organization_id=organization_id,
            name="Security Reviewer",
            role="security_reviewer",
            domain=domain,
            responsibilities=["Threat model", "Review auth/data/security impacts", "Block unsafe changes"],
            capabilities=["security_review", "compliance", "secrets_detection"],
            authority=Authority(can_propose=True, can_execute=False, can_approve=True, can_block=True),
        ),
        AgentProfile(
            organization_id=organization_id,
            name="QA Reviewer",
            role="qa_reviewer",
            domain=domain,
            responsibilities=["Define tests", "Review evidence", "Validate completion"],
            capabilities=["test_design", "regression_analysis", "evidence_review"],
            authority=Authority(can_propose=True, can_execute=False, can_approve=True, can_block=True),
        ),
    ]


def build_generation_one_organization(mission: Mission, domain: str = "software_engineering") -> DynamicOrganization:
    organization_id = new_id()
    agents = default_generation_one_agents(organization_id, domain)
    lead = next(agent for agent in agents if agent.role == "product_analyst")
    return DynamicOrganization(
        organization_id=organization_id,
        mission_id=mission.mission_id,
        name=f"{mission.title} Organization",
        lead_agent_id=lead.agent_id,
        agents=agents,
        status="active",
        communication_policy={
            "message_envelope_required": True,
            "freeform_allowed_inside_content": True,
            "high_priority_requires_response": True,
        },
        approval_policy=approval_policy_for_risk("medium"),
        review_councils=[review_council_for_risk("medium")],
    )


def approval_policy_for_risk(risk: RiskLevel, mode: ExecutionMode = "engineer") -> dict[str, Any]:
    thresholds = {
        "low": {"independent_approvals": 1, "human_approval": False},
        "medium": {"independent_approvals": 2, "human_approval": False},
        "high": {"independent_approvals": 3, "human_approval": True},
        "critical": {"independent_approvals": 4, "human_approval": True},
    }
    destructive_actions = [
        "production_deployment",
        "destructive_database_migration",
        "secret_rotation",
        "financial_transaction",
        "external_communication",
        "delete_user_data",
        "auth_or_authorization_change",
        "infrastructure_modification",
        "publishing_release",
        "high_impact_security_change",
        "legal_or_medical_consequence",
    ]
    return {
        "risk": risk,
        "execution_mode": mode,
        **thresholds[risk],
        "always_require_human_approval": destructive_actions,
    }


def review_council_for_risk(risk: RiskLevel) -> dict[str, Any]:
    base = ["architecture", "security", "qa"]
    if risk in {"medium", "high", "critical"}:
        base.extend(["performance", "maintainability"])
    if risk in {"high", "critical"}:
        base.extend(["privacy", "compliance", "business_impact"])
    if risk == "critical":
        base.extend(["domain_safety", "human_approval"])
    return {
        "risk_level": risk,
        "perspectives": base,
        "independent_review_first": True,
        "groupthink_reduction": "Reviewers submit initial findings before seeing other conclusions.",
    }


def decompose_mission_to_tasks(mission: Mission, organization: DynamicOrganization) -> list[Task]:
    agent_by_role = {agent.role: agent for agent in organization.agents}
    product = agent_by_role["product_analyst"]
    architect = agent_by_role["solution_architect"]
    implementer = agent_by_role["implementation_engineer"]
    security = agent_by_role["security_reviewer"]
    qa = agent_by_role["qa_reviewer"]
    return [
        Task(
            mission_id=mission.mission_id,
            title="Clarify mission requirements",
            description="Convert mission description into objectives, success criteria, constraints, unknowns, and risks.",
            task_type="research",
            assigned_agent_id=product.agent_id,
            reviewer_agent_ids=[architect.agent_id],
            expected_outputs=["requirements_summary", "unknowns", "success_criteria"],
            acceptance_criteria=["Objectives and success criteria are explicit."],
            risk_level="low",
            status="ready",
        ),
        Task(
            mission_id=mission.mission_id,
            title="Design solution strategy",
            description="Generate architecture and implementation strategy with alternatives and trade-offs.",
            task_type="design",
            assigned_agent_id=architect.agent_id,
            reviewer_agent_ids=[security.agent_id, qa.agent_id],
            dependencies=[],
            expected_outputs=["strategy", "alternatives", "tradeoffs"],
            acceptance_criteria=["At least two alternatives are compared.", "Risks and mitigation are documented."],
            risk_level="medium",
            approval_required=True,
            status="backlog",
        ),
        Task(
            mission_id=mission.mission_id,
            title="Prepare implementation work package",
            description="Create scoped implementation tasks and verification plan.",
            task_type="implementation",
            assigned_agent_id=implementer.agent_id,
            reviewer_agent_ids=[architect.agent_id, security.agent_id, qa.agent_id],
            expected_outputs=["patch_plan", "verification_commands", "rollback_plan"],
            acceptance_criteria=["Implementation has evidence requirements and rollback path."],
            risk_level="medium",
            approval_required=True,
            status="backlog",
        ),
    ]


def mission_lifecycle_state_machine() -> dict[str, list[str]]:
    return {
        "discovery": ["planning", "failed"],
        "planning": ["review", "failed"],
        "review": ["approved", "planning", "failed"],
        "approved": ["executing", "planning"],
        "executing": ["validating", "failed"],
        "validating": ["completed", "executing", "failed"],
        "completed": [],
        "failed": ["planning"],
    }


def task_lifecycle_state_machine() -> dict[str, list[str]]:
    return {
        "backlog": ["ready", "blocked"],
        "ready": ["in_progress", "blocked"],
        "in_progress": ["review", "blocked"],
        "blocked": ["ready", "rejected"],
        "review": ["approved", "rejected", "blocked"],
        "rejected": ["ready"],
        "approved": ["completed"],
        "completed": [],
    }


class CollaborationRuntime:
    """In-memory Generation 1 mission runtime.

    This runtime is deliberately deterministic and storage-agnostic. API routes,
    workers, or database repositories can persist its serializable outputs later.
    """

    def __init__(self, mission: Mission):
        self.mission = mission
        self.organization: DynamicOrganization | None = None
        self.workspace = SharedWorkspace(mission=mission)
        self.messages: list[MessageEnvelope] = []
        self.events: list[RuntimeEvent] = [
            RuntimeEvent(
                mission_id=mission.mission_id,
                event_type="mission_created",
                summary=f"Mission created: {mission.title}",
                payload=mission.to_dict(),
            )
        ]

    def emit(self, event_type: RuntimeEventType, summary: str, *, actor_id: str | None = None, payload: dict[str, Any] | None = None) -> RuntimeEvent:
        event = RuntimeEvent(
            mission_id=self.mission.mission_id,
            event_type=event_type,
            summary=summary,
            actor_id=actor_id,
            payload=payload or {},
        )
        self.events.append(event)
        return event

    def extract_goals(self) -> Mission:
        """Mission Manager: create basic objectives and success criteria if absent."""

        if not self.mission.objectives:
            self.mission.objectives = [self.mission.description.strip() or self.mission.title]
        if not self.mission.success_criteria:
            self.mission.success_criteria = [
                "Problem is understood with explicit assumptions.",
                "Solution strategy is reviewed by independent specialists.",
                "Completion includes measurable evidence.",
            ]
        if not self.mission.unknowns:
            self.mission.unknowns = ["Exact domain constraints require confirmation."]
        self.mission.status = "planning"
        self.mission.updated_at = utc_now()
        self.emit("mission_updated", "Mission Manager extracted objectives, success criteria, constraints, and unknowns.", payload=self.mission.to_dict())
        return self.mission

    def classify_domains(self) -> list[str]:
        text = f"{self.mission.title} {self.mission.description}".lower()
        domains: list[str] = []
        if any(term in text for term in ["security", "auth", "oauth", "threat", "compliance"]):
            domains.append("cyber_security")
        if any(term in text for term in ["ai", "llm", "model", "machine learning", "rag"]):
            domains.append("ai_ml")
        if any(term in text for term in ["health", "medical", "clinic", "patient"]):
            domains.append("healthcare")
        if any(term in text for term in ["payment", "finance", "bank", "fraud"]):
            domains.append("finance")
        if any(term in text for term in ["cloud", "deploy", "kubernetes", "infra", "docker"]):
            domains.append("cloud_infrastructure")
        if any(term in text for term in ["app", "software", "api", "frontend", "backend", "code", "product"]):
            domains.append("software_engineering")
        self.mission.domains = domains or self.mission.domains or ["software_engineering"]
        self.emit("mission_updated", "Domain Classifier detected mission domains.", payload={"domains": self.mission.domains})
        return self.mission.domains

    def build_organization(self) -> DynamicOrganization:
        primary_domain = self.mission.domains[0] if self.mission.domains else "software_engineering"
        self.organization = build_generation_one_organization(self.mission, domain=primary_domain)
        self.emit("organization_created", "Organization Builder assembled Generation 1 specialist team.", payload=self.organization.to_dict())
        return self.organization

    def orchestrate_tasks(self) -> list[Task]:
        if not self.organization:
            self.build_organization()
        assert self.organization is not None
        tasks = decompose_mission_to_tasks(self.mission, self.organization)
        self.workspace.tasks.extend(tasks)
        for task in tasks:
            self.emit("task_created", f"Task created: {task.title}", actor_id=task.assigned_agent_id, payload=task.to_dict())
        return tasks

    def transition_task(self, task_id: str, new_status: TaskStatus, *, evidence: dict[str, Any] | None = None) -> Task:
        transitions = task_lifecycle_state_machine()
        task = next((item for item in self.workspace.tasks if item.task_id == task_id), None)
        if task is None:
            raise ValueError(f"Unknown task: {task_id}")
        if new_status not in transitions[task.status]:
            raise ValueError(f"Invalid task transition: {task.status} -> {new_status}")
        if evidence:
            task.evidence.append(evidence)
        if new_status == "completed" and not task.has_completion_evidence():
            raise ValueError("Task completion requires evidence.")
        task.status = new_status
        if new_status == "completed":
            task.completed_at = utc_now()
        self.emit("task_transitioned", f"Task transitioned to {new_status}: {task.title}", actor_id=task.assigned_agent_id, payload=task.to_dict())
        return task

    def publish_message(self, message: MessageEnvelope) -> MessageEnvelope:
        if message.mission_id != self.mission.mission_id:
            raise ValueError("Message mission does not match runtime mission.")
        self.messages.append(message)
        self.emit("message_published", f"{message.message_type.title()} published: {message.topic}", actor_id=message.from_agent_id, payload=message.to_dict())
        return message

    def run_review(self, decision: Decision, reviews: list[ReviewResult]) -> Decision:
        decision.review_results.extend(reviews)
        decision.reviewers = list({review.reviewer for review in decision.review_results})
        if any(review.verdict == "reject" or review.blocking_issues for review in reviews):
            decision.status = "under_review"
        elif self.review_threshold_met(decision):
            decision.status = "approved"
        else:
            decision.status = "under_review"
        self.workspace.decisions.append(decision)
        self.emit("review_recorded", f"Review council updated decision: {decision.title}", actor_id=decision.proposed_by, payload=decision.to_dict())
        return decision

    def review_threshold_met(self, decision: Decision) -> bool:
        risk: RiskLevel = "high" if decision.requires_human_approval else "medium"
        policy = approval_policy_for_risk(risk)
        approvals = sum(1 for review in decision.review_results if review.verdict in {"approve", "approve_with_conditions"})
        return approvals >= policy["independent_approvals"] and not any(review.blocking_issues for review in decision.review_results)

    def approve_mission(self, *, human_approved: bool = False) -> Mission:
        if not self.mission.objectives or not self.mission.success_criteria:
            raise ValueError("Mission cannot be approved without objectives and success criteria.")
        if self.mission.priority == "critical" and not human_approved:
            raise ValueError("Critical mission requires explicit human approval.")
        self.mission.status = "approved"
        self.mission.updated_at = utc_now()
        self.emit("approval_recorded", "Approval Engine approved mission for execution.", payload={"human_approved": human_approved})
        return self.mission

    def verify_mission(self) -> dict[str, Any]:
        completed = [task for task in self.workspace.tasks if task.status == "completed"]
        open_tasks = [task for task in self.workspace.tasks if task.status != "completed"]
        evidence = [evidence for task in completed for evidence in task.evidence]
        result = {
            "passed": bool(completed) and not any(task.risk_level in {"high", "critical"} and not task.has_completion_evidence() for task in completed),
            "completed_tasks": len(completed),
            "open_tasks": len(open_tasks),
            "evidence_count": len(evidence),
        }
        self.emit("verification_recorded", "Verification Engine evaluated mission evidence.", payload=result)
        return result

    def create_mission_report(self) -> dict[str, Any]:
        completed = [task.to_dict() for task in self.workspace.tasks if task.status == "completed"]
        open_tasks = [task.to_dict() for task in self.workspace.tasks if task.status != "completed"]
        evidence = [evidence for task in self.workspace.tasks for evidence in task.evidence]
        lessons = [lesson.to_context_item() for lesson in self.workspace.lessons]
        report = MissionReport(
            mission_id=self.mission.mission_id,
            status=self.mission.status,
            summary=f"{self.mission.title}: {len(completed)} completed task(s), {len(open_tasks)} open task(s).",
            completed_tasks=completed,
            open_tasks=open_tasks,
            decisions=[decision.to_dict() for decision in self.workspace.decisions],
            evidence=evidence,
            lessons=lessons,
        )
        self.emit("mission_report_created", "Mission report created.", payload=report.to_dict())
        return report.to_dict()

    def record_lesson(self, title: str, content: Any, *, tags: list[str] | None = None, confidence: int = 80) -> WorkspaceArtifact:
        lesson = WorkspaceArtifact(
            kind="lesson",
            title=title,
            content=content,
            memory_level="global",
            confidentiality="organization",
            freshness=confidence,
            relevance_tags=tags or [],
        )
        self.workspace.lessons.append(lesson)
        self.emit("lesson_recorded", f"Learning Engine recorded lesson: {title}", payload=lesson.to_context_item())
        return lesson

    def timeline(self) -> list[dict[str, Any]]:
        return [event.to_dict() for event in self.events]
