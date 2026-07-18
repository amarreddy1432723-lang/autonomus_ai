"""Arceus Core Mission Compiler.

The compiler is the first stable kernel boundary: raw user objectives become a
versioned mission definition and execution graph before anything can run.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .core import new_id, utc_now


RiskLevel = Literal["low", "medium", "high", "critical"]
Complexity = Literal["small", "medium", "large"]
GraphNodeType = Literal[
    "requirement",
    "decision",
    "task",
    "approval",
    "tool_execution",
    "human_action",
    "review",
    "verification",
    "artifact",
    "deployment",
    "observation",
]
GraphEdgeType = Literal[
    "DEPENDS_ON",
    "BLOCKED_BY",
    "PRODUCES",
    "REQUIRES",
    "REVIEWS",
    "VERIFIES",
    "APPROVES",
    "SUPERSEDES",
    "TRIGGERS",
    "ROLLS_BACK",
]
MissionState = Literal[
    "DRAFT",
    "COMPILING",
    "CLARIFICATION_REQUIRED",
    "COMPILED",
    "ORGANIZING",
    "PLAN_PENDING",
    "AWAITING_PLAN_APPROVAL",
    "READY",
    "RUNNING",
    "PAUSED",
    "BLOCKED",
    "FAILED",
    "REVIEWING",
    "VERIFYING",
    "AWAITING_COMPLETION_APPROVAL",
    "COMPLETED",
    "CANCELLED",
    "ARCHIVED",
]


MATERIAL_UNKNOWN_TERMS = {
    "authentication": ["auth", "authentication", "login", "oauth", "sso", "session", "clerk"],
    "billing": ["billing", "payment", "stripe", "invoice", "subscription"],
    "deployment": ["deploy", "production", "staging", "railway", "vercel", "cloud"],
    "data_integrity": ["database", "migration", "delete", "user data", "tenant"],
    "security": ["secret", "token", "permission", "authorization", "security"],
}

ALLOWED_MISSION_TRANSITIONS: dict[MissionState, set[MissionState]] = {
    "DRAFT": {"COMPILING", "CANCELLED"},
    "COMPILING": {"CLARIFICATION_REQUIRED", "COMPILED", "FAILED"},
    "CLARIFICATION_REQUIRED": {"COMPILING", "CANCELLED"},
    "COMPILED": {"ORGANIZING", "CANCELLED"},
    "ORGANIZING": {"PLAN_PENDING", "FAILED", "CANCELLED"},
    "PLAN_PENDING": {"AWAITING_PLAN_APPROVAL", "FAILED", "CANCELLED"},
    "AWAITING_PLAN_APPROVAL": {"READY", "PLAN_PENDING", "CANCELLED"},
    "READY": {"RUNNING", "CANCELLED"},
    "RUNNING": {"PAUSED", "BLOCKED", "FAILED", "REVIEWING", "CANCELLED"},
    "PAUSED": {"RUNNING", "CANCELLED"},
    "BLOCKED": {"RUNNING", "FAILED", "CANCELLED"},
    "FAILED": {"READY", "CANCELLED", "ARCHIVED"},
    "REVIEWING": {"VERIFYING", "BLOCKED", "FAILED", "CANCELLED"},
    "VERIFYING": {"AWAITING_COMPLETION_APPROVAL", "BLOCKED", "FAILED", "CANCELLED"},
    "AWAITING_COMPLETION_APPROVAL": {"COMPLETED", "REVIEWING", "CANCELLED"},
    "COMPLETED": {"ARCHIVED"},
    "CANCELLED": {"ARCHIVED"},
    "ARCHIVED": set(),
}


@dataclass(slots=True)
class MissionCompileRequest:
    project_id: str
    objective: str
    repository_ids: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    desired_outcomes: list[str] = field(default_factory=list)
    budget: dict[str, Any] = field(default_factory=dict)
    actor_id: str = "user"
    tenant_id: str = "tenant"
    request_id: str = field(default_factory=new_id)


@dataclass(slots=True)
class IntentFrame:
    objective: str
    scope: list[str]
    constraints: list[str]
    unknowns: list[str]
    deliverables: list[str]
    risk_level: RiskLevel
    execution_allowed: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "scope": self.scope,
            "constraints": self.constraints,
            "unknowns": self.unknowns,
            "deliverables": self.deliverables,
            "risk_level": self.risk_level,
            "execution_allowed": self.execution_allowed,
        }


@dataclass(slots=True)
class RiskProfile:
    level: RiskLevel
    categories: list[str]
    reasons: list[str]
    clarification_required: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "categories": self.categories,
            "reasons": self.reasons,
            "clarification_required": self.clarification_required,
        }


@dataclass(slots=True)
class ExecutionGraphNode:
    node_type: GraphNodeType
    title: str
    handler_key: str | None = None
    risk_level: RiskLevel = "low"
    payload: dict[str, Any] = field(default_factory=dict)
    status: Literal["pending", "ready", "blocked"] = "pending"
    node_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "title": self.title,
            "handler_key": self.handler_key,
            "risk_level": self.risk_level,
            "payload": self.payload,
            "status": self.status,
        }


@dataclass(slots=True)
class ExecutionGraphEdge:
    source_id: str
    target_id: str
    edge_type: GraphEdgeType
    edge_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "edge_type": self.edge_type,
        }


@dataclass(slots=True)
class ExecutionGraph:
    nodes: list[ExecutionGraphNode]
    edges: list[ExecutionGraphEdge]
    graph_id: str = field(default_factory=new_id)

    def validate(self) -> None:
        node_ids = {node.node_id for node in self.nodes}
        for edge in self.edges:
            if edge.source_id not in node_ids or edge.target_id not in node_ids:
                raise ValueError("Execution graph edge references an unknown node.")
        if not any(node.node_type == "requirement" for node in self.nodes):
            raise ValueError("Execution graph requires at least one requirement node.")
        if not any(node.node_type == "verification" for node in self.nodes):
            raise ValueError("Execution graph requires at least one verification node.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "graph_id": self.graph_id,
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


@dataclass(slots=True)
class MissionDefinition:
    title: str
    objective: str
    project_id: str
    problem_statement: str
    deliverables: list[str]
    requirements: list[str]
    constraints: list[str]
    unknowns: list[str]
    assumptions: list[str]
    success_criteria: list[str]
    risk_profile: RiskProfile
    required_capabilities: list[str]
    execution_policy: dict[str, Any]
    approval_policy: dict[str, Any]
    verification_plan: dict[str, Any]
    estimated_complexity: Complexity
    execution_graph: ExecutionGraph
    mission_definition_version: str = "1.0"
    compiled_at: str = field(default_factory=utc_now)

    @property
    def clarification_required(self) -> bool:
        return self.risk_profile.clarification_required

    def to_aml(self) -> dict[str, Any]:
        return {
            "version": self.mission_definition_version,
            "mission": {
                "id": None,
                "title": self.title,
                "project_id": self.project_id,
                "risk": self.risk_profile.level,
            },
            "objective": {
                "primary": self.objective,
                "outcomes": self.success_criteria,
            },
            "constraints": {
                "technical": self.constraints,
                "security": [item for item in self.constraints if _contains_any(item, MATERIAL_UNKNOWN_TERMS["security"])],
                "product": [],
            },
            "capabilities": {"required": self.required_capabilities},
            "approvals": self.approval_policy,
            "verification": self.verification_plan,
            "execution_graph": self.execution_graph.to_dict(),
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission_definition_version": self.mission_definition_version,
            "title": self.title,
            "objective": self.objective,
            "project_id": self.project_id,
            "problem_statement": self.problem_statement,
            "deliverables": self.deliverables,
            "requirements": self.requirements,
            "constraints": self.constraints,
            "unknowns": self.unknowns,
            "assumptions": self.assumptions,
            "success_criteria": self.success_criteria,
            "risk_profile": self.risk_profile.to_dict(),
            "required_capabilities": self.required_capabilities,
            "execution_policy": self.execution_policy,
            "approval_policy": self.approval_policy,
            "verification_plan": self.verification_plan,
            "estimated_complexity": self.estimated_complexity,
            "execution_graph": self.execution_graph.to_dict(),
            "compiled_at": self.compiled_at,
        }


@dataclass(slots=True)
class CompiledMission:
    request: MissionCompileRequest
    intent: IntentFrame
    definition: MissionDefinition
    state: MissionState
    events: list[dict[str, Any]]
    compiled_mission_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "compiled_mission_id": self.compiled_mission_id,
            "request_id": self.request.request_id,
            "state": self.state,
            "intent": self.intent.to_dict(),
            "definition": self.definition.to_dict(),
            "aml": self.definition.to_aml(),
            "events": self.events,
        }


class MissionStateMachine:
    def can_transition(self, current: MissionState, target: MissionState) -> bool:
        return target in ALLOWED_MISSION_TRANSITIONS[current]

    def transition(self, current: MissionState, target: MissionState) -> MissionState:
        if not self.can_transition(current, target):
            raise ValueError(f"Invalid mission transition {current} -> {target}")
        return target


class MissionCompiler:
    def compile(self, request: MissionCompileRequest) -> CompiledMission:
        objective = request.objective.strip()
        if not objective:
            raise ValueError("Mission objective is required.")

        risk = self._classify_risk(objective, request.constraints)
        capabilities = self._extract_capabilities(objective, request.constraints)
        requirements = self._extract_requirements(objective, request.desired_outcomes)
        unknowns = self._detect_unknowns(objective, request.constraints)
        clarification_required = self._requires_clarification(risk, unknowns)
        risk.clarification_required = clarification_required
        success_criteria = self._success_criteria(objective, request.desired_outcomes, risk)
        verification_plan = self._verification_plan(capabilities, risk)
        graph = self._execution_graph(requirements, capabilities, risk, verification_plan, clarification_required)
        graph.validate()
        intent = IntentFrame(
            objective=objective,
            scope=self._scope(objective),
            constraints=request.constraints,
            unknowns=unknowns,
            deliverables=self._deliverables(capabilities),
            risk_level=risk.level,
            execution_allowed=not clarification_required and risk.level == "low",
        )
        definition = MissionDefinition(
            title=self._title(objective),
            objective=objective,
            project_id=request.project_id,
            problem_statement=self._problem_statement(objective),
            deliverables=intent.deliverables,
            requirements=requirements,
            constraints=request.constraints,
            unknowns=unknowns,
            assumptions=[] if clarification_required else self._assumptions(risk),
            success_criteria=success_criteria,
            risk_profile=risk,
            required_capabilities=capabilities,
            execution_policy={
                "tools_require_policy_evaluation": True,
                "repository_writes_path_scoped": True,
                "execution_allowed_without_plan_approval": risk.level == "low" and not clarification_required,
            },
            approval_policy={
                "plan": {"required": risk.level in {"medium", "high", "critical"} or clarification_required},
                "execution": {"required_for": self._approval_required_for(capabilities, risk)},
                "completion": {"required": True},
                "minimum_human_approvals": 1,
            },
            verification_plan=verification_plan,
            estimated_complexity=self._complexity(capabilities),
            execution_graph=graph,
        )
        state: MissionState = "CLARIFICATION_REQUIRED" if clarification_required else "COMPILED"
        events = [
            self._event("MISSION_COMPILE_STARTED", request, {"objective": objective}),
            self._event(
                "MISSION_CLARIFICATION_REQUESTED" if clarification_required else "MISSION_COMPILED",
                request,
                {"title": definition.title, "risk_level": risk.level, "unknowns": unknowns},
            ),
        ]
        return CompiledMission(request=request, intent=intent, definition=definition, state=state, events=events)

    def _classify_risk(self, objective: str, constraints: list[str]) -> RiskProfile:
        text = " ".join([objective, *constraints]).lower()
        categories = [category for category, terms in MATERIAL_UNKNOWN_TERMS.items() if _contains_any(text, terms)]
        if any(category in categories for category in ["billing", "deployment", "data_integrity"]):
            level: RiskLevel = "high"
        elif any(category in categories for category in ["authentication", "security"]):
            level = "high"
        elif any(term in text for term in ["delete", "remove user", "production"]):
            level = "critical"
        else:
            level = "low"
        reasons = [f"Detected {category} impact." for category in categories] or ["No sensitive domain detected."]
        return RiskProfile(level=level, categories=categories, reasons=reasons)

    def _extract_capabilities(self, objective: str, constraints: list[str]) -> list[str]:
        text = " ".join([objective, *constraints]).lower()
        capabilities = ["requirement_analysis"]
        if _contains_any(text, ["health", "admin", "card", "interface", "ui", "frontend"]):
            capabilities.extend(["react_development", "responsive_ui", "frontend_testing", "build_verification"])
        if _contains_any(text, ["auth", "authentication", "login", "oauth", "session", "google"]):
            capabilities.extend(["authentication_review", "api_architecture", "backend_api_development", "security_review", "integration_testing"])
        if _contains_any(text, ["desktop", "electron", "renderer"]):
            capabilities.extend(["desktop_security", "integration_testing"])
        if _contains_any(text, ["billing", "payment", "stripe", "subscription"]):
            capabilities.extend(["subscription_billing", "payment_security", "webhook_reliability"])
        if _contains_any(text, ["deploy", "production", "staging", "railway", "vercel"]):
            capabilities.extend(["cloud_deployment", "rollback_design", "observability"])
        if _contains_any(text, ["database", "migration", "tenant"]):
            capabilities.extend(["relational_modeling", "database_migration", "tenant_isolation"])
        return list(dict.fromkeys(capabilities))

    def _extract_requirements(self, objective: str, desired_outcomes: list[str]) -> list[str]:
        requirements = [f"Implement objective: {objective}"]
        requirements.extend(desired_outcomes)
        return list(dict.fromkeys(requirements))

    def _detect_unknowns(self, objective: str, constraints: list[str]) -> list[str]:
        text = " ".join([objective, *constraints]).lower()
        unknowns: list[str] = []
        if _contains_any(text, ["google", "oauth"]) and not _contains_any(text, ["client id", "client secret", "clerk", "provider configured"]):
            unknowns.append("OAuth provider configuration and callback ownership must be confirmed.")
        if _contains_any(text, ["production", "deploy"]) and not _contains_any(text, ["staging", "rollback", "approval"]):
            unknowns.append("Deployment environment, rollback, and approval authority must be confirmed.")
        if _contains_any(text, ["billing", "stripe"]) and not _contains_any(text, ["price id", "webhook secret", "test mode"]):
            unknowns.append("Billing provider credentials, webhook secret, and test/live mode must be confirmed.")
        if _contains_any(text, ["delete", "user data"]) and "retention" not in text:
            unknowns.append("Data retention and deletion policy must be confirmed.")
        return unknowns

    def _requires_clarification(self, risk: RiskProfile, unknowns: list[str]) -> bool:
        return bool(unknowns and risk.level in {"high", "critical"})

    def _success_criteria(self, objective: str, desired_outcomes: list[str], risk: RiskProfile) -> list[str]:
        criteria = desired_outcomes[:] or [f"Objective is satisfied: {objective}"]
        criteria.append("Required evidence is attached.")
        criteria.append("Work receipt summarizes changed artifacts and verification.")
        if risk.level in {"medium", "high", "critical"}:
            criteria.append("Independent review is completed.")
        return list(dict.fromkeys(criteria))

    def _verification_plan(self, capabilities: list[str], risk: RiskProfile) -> dict[str, Any]:
        required = ["evidence_validation"]
        if any(capability in capabilities for capability in ["react_development", "responsive_ui"]):
            required.extend(["frontend_build", "frontend_tests"])
        if any(capability in capabilities for capability in ["backend_api_development", "authentication_review"]):
            required.extend(["backend_tests", "integration_tests"])
        if any(capability in capabilities for capability in ["security_review", "desktop_security", "payment_security"]):
            required.append("security_review")
        if any(capability in capabilities for capability in ["cloud_deployment"]):
            required.extend(["deployment_smoke_test", "rollback_check"])
        if risk.level in {"high", "critical"}:
            required.append("human_review")
        return {"required": list(dict.fromkeys(required)), "evidence_before_completion": True}

    def _execution_graph(
        self,
        requirements: list[str],
        capabilities: list[str],
        risk: RiskProfile,
        verification_plan: dict[str, Any],
        clarification_required: bool,
    ) -> ExecutionGraph:
        requirement = ExecutionGraphNode("requirement", requirements[0], risk_level=risk.level, payload={"requirements": requirements}, status="ready")
        decision = ExecutionGraphNode("decision", "Confirm implementation plan", "plan.confirm", risk_level=risk.level)
        approval = ExecutionGraphNode("approval", "Approve mission plan", "approval.plan", risk_level=risk.level)
        task = ExecutionGraphNode("task", "Execute scoped implementation", "implementation.execute", risk_level=risk.level, payload={"capabilities": capabilities})
        review = ExecutionGraphNode("review", "Independent review", "review.independent", risk_level=risk.level)
        verification = ExecutionGraphNode("verification", "Run verification plan", "verification.run", risk_level=risk.level, payload=verification_plan)
        completion = ExecutionGraphNode("approval", "Approve completion", "approval.completion", risk_level=risk.level)
        nodes = [requirement, decision, approval, task, review, verification, completion]
        if clarification_required:
            human_action = ExecutionGraphNode("human_action", "Clarify material unknowns", "human.clarify", risk_level=risk.level, status="ready")
            nodes.insert(1, human_action)
            edges = [
                ExecutionGraphEdge(requirement.node_id, human_action.node_id, "REQUIRES"),
                ExecutionGraphEdge(human_action.node_id, decision.node_id, "DEPENDS_ON"),
            ]
        else:
            edges = [ExecutionGraphEdge(requirement.node_id, decision.node_id, "REQUIRES")]
        edges.extend(
            [
                ExecutionGraphEdge(decision.node_id, approval.node_id, "REQUIRES"),
                ExecutionGraphEdge(approval.node_id, task.node_id, "APPROVES"),
                ExecutionGraphEdge(task.node_id, review.node_id, "PRODUCES"),
                ExecutionGraphEdge(review.node_id, verification.node_id, "REVIEWS"),
                ExecutionGraphEdge(verification.node_id, completion.node_id, "VERIFIES"),
            ]
        )
        return ExecutionGraph(nodes=nodes, edges=edges)

    def _scope(self, objective: str) -> list[str]:
        text = objective.lower()
        scope = []
        if _contains_any(text, ["admin", "ui", "card", "frontend"]):
            scope.append("frontend")
        if _contains_any(text, ["auth", "api", "backend", "login"]):
            scope.append("backend")
        if _contains_any(text, ["desktop", "electron"]):
            scope.append("desktop")
        return scope or ["project"]

    def _deliverables(self, capabilities: list[str]) -> list[str]:
        deliverables = ["mission_plan", "work_receipt", "evidence"]
        if any(capability.endswith("development") or capability in {"react_development", "backend_api_development"} for capability in capabilities):
            deliverables.append("code")
        if any("testing" in capability or "verification" in capability for capability in capabilities):
            deliverables.append("tests")
        return list(dict.fromkeys(deliverables))

    def _approval_required_for(self, capabilities: list[str], risk: RiskProfile) -> list[str]:
        required_for = []
        if risk.level in {"high", "critical"}:
            required_for.append("high_risk_execution")
        if any(capability in capabilities for capability in ["authentication_review", "desktop_security"]):
            required_for.extend(["authentication_changes", "secret_configuration"])
        if any(capability in capabilities for capability in ["cloud_deployment"]):
            required_for.append("deployment")
        return list(dict.fromkeys(required_for))

    def _complexity(self, capabilities: list[str]) -> Complexity:
        if len(capabilities) >= 8:
            return "large"
        if len(capabilities) >= 5:
            return "medium"
        return "small"

    def _title(self, objective: str) -> str:
        title = objective.strip().rstrip(".")
        if len(title) <= 64:
            return title[0].upper() + title[1:]
        return title[:61].rstrip() + "..."

    def _problem_statement(self, objective: str) -> str:
        return f"The project requires a controlled implementation for: {objective}"

    def _assumptions(self, risk: RiskProfile) -> list[str]:
        if risk.level == "low":
            return ["No material security, billing, deployment, or data-integrity unknowns detected."]
        return []

    def _event(self, event_type: str, request: MissionCompileRequest, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "event_id": new_id(),
            "tenant_id": request.tenant_id,
            "aggregate_type": "mission_compile_request",
            "aggregate_id": request.request_id,
            "event_type": event_type,
            "payload": payload,
            "actor_type": "human",
            "actor_id": request.actor_id,
            "correlation_id": request.request_id,
            "schema_version": 1,
            "occurred_at": utc_now(),
        }


def _contains_any(text: str, terms: list[str]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)

