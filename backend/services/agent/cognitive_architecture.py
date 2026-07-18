"""Generation 2 Arceus Cognitive Architecture.

This module sits before the collaboration runtime. Its job is to make Arceus
understand, research, compare, simulate, debate, decide, execute, reflect, and
improve like an organization instead of behaving like a single chat session.

The implementation is intentionally deterministic and provider-independent so
it can be tested, persisted, rendered in UI, and later connected to model/tool
routers without changing the public contracts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


ConfidenceBand = Literal["low", "medium", "high"]
Urgency = Literal["low", "normal", "high", "critical"]
KnowledgeSourceType = Literal[
    "global_memory",
    "organization_memory",
    "mission_memory",
    "project_files",
    "documentation",
    "standards",
    "previous_implementation",
    "benchmark",
    "external_research",
    "user_input",
]
SimulationScenarioType = Literal[
    "normal_conditions",
    "peak_traffic",
    "hardware_failure",
    "network_failure",
    "security_attack",
    "dependency_failure",
    "database_failure",
    "rollback",
    "unexpected_user_behavior",
]
DecisionVerdict = Literal["recommended", "accepted", "rejected", "needs_more_evidence"]
HealthStatus = Literal["healthy", "watch", "at_risk", "blocked"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


def _contains_any(text: str, needles: set[str]) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in needles)


def _score_to_band(score: float) -> ConfidenceBand:
    if score >= 0.82:
        return "high"
    if score >= 0.58:
        return "medium"
    return "low"


def _bounded(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _weighted_average(values: list[float]) -> float:
    return round(sum(values) / len(values), 3) if values else 0.0


@dataclass(slots=True)
class CognitiveAssessment:
    """Stage 1: understand intent before solving."""

    objective: str
    user_goal: str
    inferred_intent: str
    domains: list[str]
    success_criteria: list[str]
    constraints: list[str]
    unknowns: list[str]
    assumptions: list[str]
    risks: list[str]
    dependencies: list[str]
    missing_knowledge: list[str]
    urgency: Urgency
    confidence: float
    confidence_band: ConfidenceBand
    ready_for_strategy: bool
    assessment_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "assessment_id": self.assessment_id,
            "objective": self.objective,
            "user_goal": self.user_goal,
            "inferred_intent": self.inferred_intent,
            "domains": self.domains,
            "success_criteria": self.success_criteria,
            "constraints": self.constraints,
            "unknowns": self.unknowns,
            "assumptions": self.assumptions,
            "risks": self.risks,
            "dependencies": self.dependencies,
            "missing_knowledge": self.missing_knowledge,
            "urgency": self.urgency,
            "confidence": self.confidence,
            "confidence_band": self.confidence_band,
            "ready_for_strategy": self.ready_for_strategy,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class ResearchFinding:
    """Stage 2: evidence with source and confidence."""

    topic: str
    source_type: KnowledgeSourceType
    summary: str
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.75
    conflicts: list[str] = field(default_factory=list)
    finding_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "topic": self.topic,
            "source_type": self.source_type,
            "summary": self.summary,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "conflicts": self.conflicts,
        }


@dataclass(slots=True)
class StrategyOption:
    """Stage 3: one viable approach and its trade-offs."""

    name: str
    summary: str
    advantages: list[str]
    tradeoffs: list[str]
    cost: float
    complexity: float
    risk: float
    scalability: float
    maintainability: float
    security: float
    performance: float
    future_evolution: float
    business_impact: float
    assumptions: list[str] = field(default_factory=list)
    strategy_id: str = field(default_factory=new_id)

    @property
    def score(self) -> float:
        positive = _weighted_average(
            [
                self.scalability,
                self.maintainability,
                self.security,
                self.performance,
                self.future_evolution,
                self.business_impact,
            ]
        )
        penalty = _weighted_average([self.cost, self.complexity, self.risk])
        return round(_bounded((positive * 0.72) + ((1.0 - penalty) * 0.28)), 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "summary": self.summary,
            "advantages": self.advantages,
            "tradeoffs": self.tradeoffs,
            "cost": self.cost,
            "complexity": self.complexity,
            "risk": self.risk,
            "scalability": self.scalability,
            "maintainability": self.maintainability,
            "security": self.security,
            "performance": self.performance,
            "future_evolution": self.future_evolution,
            "business_impact": self.business_impact,
            "assumptions": self.assumptions,
            "score": self.score,
        }


@dataclass(slots=True)
class SimulationResult:
    """Stage 4: scenario-based pressure testing."""

    scenario: SimulationScenarioType
    expected_behavior: str
    weaknesses: list[str]
    recommendations: list[str]
    success_probability: float
    severity_if_failed: Literal["low", "medium", "high", "critical"] = "medium"
    simulation_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "simulation_id": self.simulation_id,
            "scenario": self.scenario,
            "expected_behavior": self.expected_behavior,
            "weaknesses": self.weaknesses,
            "recommendations": self.recommendations,
            "success_probability": self.success_probability,
            "severity_if_failed": self.severity_if_failed,
        }


@dataclass(slots=True)
class Prediction:
    """Stage 5: future-state forecast."""

    horizon: Literal["30_days", "90_days", "1_year", "3_years"]
    subject: str
    forecast: str
    assumptions: list[str]
    confidence: float
    warning_signals: list[str] = field(default_factory=list)
    prediction_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "prediction_id": self.prediction_id,
            "horizon": self.horizon,
            "subject": self.subject,
            "forecast": self.forecast,
            "assumptions": self.assumptions,
            "confidence": self.confidence,
            "warning_signals": self.warning_signals,
        }


@dataclass(slots=True)
class DebatePosition:
    """Stage 6: specialist position with evidence and objection."""

    specialist: str
    position: str
    support: list[str]
    objections: list[str]
    recommendation: str
    confidence: float
    minority_opinion: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "specialist": self.specialist,
            "position": self.position,
            "support": self.support,
            "objections": self.objections,
            "recommendation": self.recommendation,
            "confidence": self.confidence,
            "minority_opinion": self.minority_opinion,
        }


@dataclass(slots=True)
class DebateRecord:
    topic: str
    positions: list[DebatePosition]
    unresolved_questions: list[str] = field(default_factory=list)
    consensus: str | None = None
    debate_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "debate_id": self.debate_id,
            "topic": self.topic,
            "positions": [position.to_dict() for position in self.positions],
            "unresolved_questions": self.unresolved_questions,
            "consensus": self.consensus,
        }


@dataclass(slots=True)
class DecisionIntelligence:
    """Stage 7: selected strategy with why, alternatives, and evidence."""

    decision: str
    selected_strategy_id: str
    verdict: DecisionVerdict
    rationale: list[str]
    alternatives_rejected: list[dict[str, Any]]
    evidence_refs: list[str]
    risks: list[str]
    conditions: list[str]
    confidence: float
    decision_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "decision": self.decision,
            "selected_strategy_id": self.selected_strategy_id,
            "verdict": self.verdict,
            "rationale": self.rationale,
            "alternatives_rejected": self.alternatives_rejected,
            "evidence_refs": self.evidence_refs,
            "risks": self.risks,
            "conditions": self.conditions,
            "confidence": self.confidence,
        }


@dataclass(slots=True)
class ReflectionRecord:
    """Stage 9: learn after execution or planning."""

    what_worked: list[str]
    what_failed: list[str]
    surprises: list[str]
    reusable_lessons: list[str]
    model_notes: list[str]
    tool_notes: list[str]
    next_improvements: list[str]
    reflection_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reflection_id": self.reflection_id,
            "what_worked": self.what_worked,
            "what_failed": self.what_failed,
            "surprises": self.surprises,
            "reusable_lessons": self.reusable_lessons,
            "model_notes": self.model_notes,
            "tool_notes": self.tool_notes,
            "next_improvements": self.next_improvements,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class OrganizationHealth:
    """Organizational consciousness: know the state of the AI company."""

    mission_health: float
    agent_health: float
    task_health: float
    risk_health: float
    knowledge_health: float
    performance_health: float
    cost_health: float
    quality_health: float
    user_satisfaction: float
    future_readiness: float
    bottlenecks: list[str] = field(default_factory=list)
    predictions: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    health_id: str = field(default_factory=new_id)

    @property
    def overall_score(self) -> float:
        return round(
            _weighted_average(
                [
                    self.mission_health,
                    self.agent_health,
                    self.task_health,
                    self.risk_health,
                    self.knowledge_health,
                    self.performance_health,
                    self.cost_health,
                    self.quality_health,
                    self.user_satisfaction,
                    self.future_readiness,
                ]
            ),
            3,
        )

    @property
    def status(self) -> HealthStatus:
        if self.bottlenecks and min(
            self.mission_health,
            self.agent_health,
            self.task_health,
            self.risk_health,
            self.knowledge_health,
            self.performance_health,
            self.cost_health,
            self.quality_health,
            self.user_satisfaction,
            self.future_readiness,
        ) < 0.55:
            return "at_risk"
        if self.overall_score >= 0.82 and not self.bottlenecks:
            return "healthy"
        if self.overall_score >= 0.68:
            return "watch"
        if self.overall_score >= 0.5:
            return "at_risk"
        return "blocked"

    def to_dict(self) -> dict[str, Any]:
        return {
            "health_id": self.health_id,
            "mission_health": self.mission_health,
            "agent_health": self.agent_health,
            "task_health": self.task_health,
            "risk_health": self.risk_health,
            "knowledge_health": self.knowledge_health,
            "performance_health": self.performance_health,
            "cost_health": self.cost_health,
            "quality_health": self.quality_health,
            "user_satisfaction": self.user_satisfaction,
            "future_readiness": self.future_readiness,
            "overall_score": self.overall_score,
            "status": self.status,
            "bottlenecks": self.bottlenecks,
            "predictions": self.predictions,
            "recommendations": self.recommendations,
        }


@dataclass(slots=True)
class IntelligenceGraphNode:
    node_type: Literal[
        "mission",
        "requirement",
        "decision",
        "strategy",
        "simulation",
        "risk",
        "artifact",
        "deployment",
        "incident",
        "lesson",
        "research",
    ]
    title: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)
    node_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "title": self.title,
            "summary": self.summary,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class IntelligenceGraphEdge:
    source_id: str
    target_id: str
    relationship: Literal[
        "requires",
        "supports",
        "conflicts_with",
        "decided_by",
        "validated_by",
        "created",
        "improves",
        "caused_by",
        "learned_from",
    ]
    evidence: list[str] = field(default_factory=list)
    edge_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "edge_id": self.edge_id,
            "source_id": self.source_id,
            "target_id": self.target_id,
            "relationship": self.relationship,
            "evidence": self.evidence,
        }


@dataclass(slots=True)
class UniversalIntelligenceGraph:
    """One graph for users, projects, decisions, incidents, lessons, and systems."""

    nodes: list[IntelligenceGraphNode] = field(default_factory=list)
    edges: list[IntelligenceGraphEdge] = field(default_factory=list)

    def add_node(self, node: IntelligenceGraphNode) -> IntelligenceGraphNode:
        self.nodes.append(node)
        return node

    def connect(
        self,
        source: IntelligenceGraphNode,
        target: IntelligenceGraphNode,
        relationship: IntelligenceGraphEdge.__annotations__["relationship"],
        evidence: list[str] | None = None,
    ) -> IntelligenceGraphEdge:
        edge = IntelligenceGraphEdge(source.node_id, target.node_id, relationship, evidence or [])
        self.edges.append(edge)
        return edge

    def related_to(self, node_id: str) -> list[dict[str, Any]]:
        related_edges = [edge for edge in self.edges if edge.source_id == node_id or edge.target_id == node_id]
        node_map = {node.node_id: node for node in self.nodes}
        related: list[dict[str, Any]] = []
        for edge in related_edges:
            other_id = edge.target_id if edge.source_id == node_id else edge.source_id
            if other_id in node_map:
                related.append({"node": node_map[other_id].to_dict(), "edge": edge.to_dict()})
        return related

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [node.to_dict() for node in self.nodes],
            "edges": [edge.to_dict() for edge in self.edges],
        }


def understand_objective(objective: str, context: dict[str, Any] | None = None) -> CognitiveAssessment:
    """Understand the mission before solving it."""

    context = context or {}
    text = objective.strip()
    lowered = text.lower()

    domains = ["software_engineering"]
    if _contains_any(lowered, {"healthcare", "patient", "medical", "clinic", "hipaa"}):
        domains.append("healthcare")
    if _contains_any(lowered, {"payment", "billing", "stripe", "finance", "invoice", "subscription"}):
        domains.append("finance")
    if _contains_any(lowered, {"security", "auth", "oauth", "sso", "encryption", "compliance"}):
        domains.append("security")
    if _contains_any(lowered, {"ai", "agent", "model", "llm", "autonomous"}):
        domains.append("artificial_intelligence")
    if _contains_any(lowered, {"deploy", "railway", "docker", "kubernetes", "cloud", "production"}):
        domains.append("cloud_infrastructure")
    domains = list(dict.fromkeys(domains))

    urgency: Urgency = "normal"
    if _contains_any(lowered, {"urgent", "asap", "critical", "production down", "broken"}):
        urgency = "critical"
    elif _contains_any(lowered, {"soon", "launch", "deadline"}):
        urgency = "high"

    unknowns = []
    if len(text.split()) < 8:
        unknowns.append("Objective is too short to infer full scope.")
    if "user" not in lowered and "customer" not in lowered and not context.get("target_users"):
        unknowns.append("Target users are not explicitly defined.")
    if "success" not in lowered and not context.get("success_criteria"):
        unknowns.append("Success criteria are not explicit.")

    constraints = list(context.get("constraints", []))
    if _contains_any(lowered, {"desktop", "electron", "windows"}):
        constraints.append("Must work as a desktop application.")
    if _contains_any(lowered, {"production", "public launch", "deploy"}):
        constraints.append("Production reliability and observability are required.")

    risks = []
    if "security" in domains or "finance" in domains or "healthcare" in domains:
        risks.append("Regulated or sensitive domain requires stricter review.")
    if "cloud_infrastructure" in domains:
        risks.append("Deployment and runtime dependencies can fail independently.")
    if "artificial_intelligence" in domains:
        risks.append("Model quality, cost, latency, and context limits can affect outcome.")

    success_criteria = list(context.get("success_criteria", [])) or [
        "Objective is decomposed into evidence-backed tasks.",
        "Risks and unknowns are explicitly documented.",
        "Recommended strategy is reviewed before execution.",
    ]
    dependencies = list(context.get("dependencies", []))
    if "cloud_infrastructure" in domains:
        dependencies.extend(["Deployment provider", "Database", "Redis or queue"])
    if "security" in domains:
        dependencies.extend(["Authentication provider", "Secrets management"])
    dependencies = list(dict.fromkeys(dependencies))

    missing_knowledge = [unknown.replace(".", "") for unknown in unknowns]
    if not missing_knowledge:
        missing_knowledge.append("Confirm latest project state before execution.")

    base_confidence = 0.48 + (0.08 * len(domains)) + (0.06 * min(len(success_criteria), 3)) - (0.08 * len(unknowns))
    confidence = round(_bounded(base_confidence), 3)

    return CognitiveAssessment(
        objective=text or "Unspecified mission",
        user_goal=context.get("user_goal") or text or "Clarify the mission.",
        inferred_intent="build_or_improve_system" if _contains_any(lowered, {"build", "implement", "fix", "deploy", "integrate"}) else "understand_and_plan",
        domains=domains,
        success_criteria=success_criteria,
        constraints=list(dict.fromkeys(constraints)),
        unknowns=unknowns,
        assumptions=context.get("assumptions", ["Use evidence-first execution and reversible changes."]),
        risks=risks,
        dependencies=dependencies,
        missing_knowledge=missing_knowledge,
        urgency=urgency,
        confidence=confidence,
        confidence_band=_score_to_band(confidence),
        ready_for_strategy=confidence >= 0.58,
    )


def collect_research(assessment: CognitiveAssessment) -> list[ResearchFinding]:
    """Build an evidence plan before deciding."""

    findings = [
        ResearchFinding(
            topic="Existing organizational memory",
            source_type="organization_memory",
            summary="Reuse prior decisions, conventions, incidents, and known constraints before creating a new plan.",
            evidence=["Cognitive architecture requires memory-first research."],
            confidence=0.88,
        ),
        ResearchFinding(
            topic="Project source of truth",
            source_type="project_files",
            summary="Inspect local project files, tests, workflows, release state, and existing implementation before execution.",
            evidence=["File evidence prevents hallucinated completion."],
            confidence=0.92,
        ),
        ResearchFinding(
            topic="Decision standards",
            source_type="standards",
            summary="Architecture, security, performance, cost, and maintainability standards must be applied to important choices.",
            evidence=["Universal review council is required for significant decisions."],
            confidence=0.9,
        ),
    ]

    if "security" in assessment.domains:
        findings.append(
            ResearchFinding(
                topic="Security posture",
                source_type="standards",
                summary="Sensitive operations need auth, secret redaction, auditability, rollback, and approval gates.",
                evidence=["Security domain detected during intent understanding."],
                confidence=0.86,
            )
        )
    if "cloud_infrastructure" in assessment.domains:
        findings.append(
            ResearchFinding(
                topic="Production operations",
                source_type="previous_implementation",
                summary="Deployment readiness should verify health, queues, database, Redis, observability, release artifacts, and rollback.",
                evidence=["Cloud infrastructure domain detected."],
                confidence=0.84,
            )
        )
    return findings


def generate_strategy_options(assessment: CognitiveAssessment, findings: list[ResearchFinding]) -> list[StrategyOption]:
    """Generate competing strategies instead of one answer."""

    sensitive = any(domain in assessment.domains for domain in {"security", "finance", "healthcare"})
    cloud = "cloud_infrastructure" in assessment.domains
    ai = "artificial_intelligence" in assessment.domains

    return [
        StrategyOption(
            name="Proof-first incremental execution",
            summary="Ship the smallest reversible improvement, collect evidence, then widen scope.",
            advantages=["Fast validation", "Low rollback risk", "Clear user trust surface"],
            tradeoffs=["Requires discipline to avoid broad rewrites", "May take multiple passes"],
            cost=0.32,
            complexity=0.38 + (0.05 if ai else 0),
            risk=0.28 + (0.08 if sensitive else 0),
            scalability=0.78,
            maintainability=0.88,
            security=0.86 if sensitive else 0.78,
            performance=0.76,
            future_evolution=0.9,
            business_impact=0.84,
            assumptions=["Current architecture can accept bounded modules."],
        ),
        StrategyOption(
            name="Platform-first foundation",
            summary="Build foundational runtime, data models, and governance before feature execution.",
            advantages=["Strong long-term architecture", "Better consistency", "Easier enterprise controls"],
            tradeoffs=["Slower user-visible progress", "Higher initial cost"],
            cost=0.62,
            complexity=0.66,
            risk=0.42,
            scalability=0.91,
            maintainability=0.9,
            security=0.88,
            performance=0.72,
            future_evolution=0.94,
            business_impact=0.76,
            assumptions=["The product can tolerate more up-front design time."],
        ),
        StrategyOption(
            name="Autonomous broad execution",
            summary="Let multiple specialists execute in parallel with heavier automation and fewer gates.",
            advantages=["High throughput", "Strong for exploratory prototyping", "Can discover implementation gaps quickly"],
            tradeoffs=["Higher coordination risk", "Requires strong review and rollback", "Cost can grow quickly"],
            cost=0.74,
            complexity=0.78,
            risk=0.68 + (0.08 if sensitive else 0),
            scalability=0.82,
            maintainability=0.68,
            security=0.62 if sensitive else 0.7,
            performance=0.78,
            future_evolution=0.74,
            business_impact=0.86 if cloud else 0.78,
            assumptions=["Review council can catch defects before merge or deploy."],
        ),
    ]


def simulate_strategy(strategy: StrategyOption) -> list[SimulationResult]:
    """Pressure-test a strategy under the core scenarios from the spec."""

    base = strategy.score
    return [
        SimulationResult("normal_conditions", "The organization completes scoped work with standard review.", [], ["Record proof in work receipts."], round(_bounded(base + 0.08), 3), "low"),
        SimulationResult("peak_traffic", "Architecture absorbs load if scaling boundaries are explicit.", ["Capacity assumptions may be wrong."], ["Add load test gate."], round(_bounded((base + strategy.scalability) / 2), 3), "high"),
        SimulationResult("hardware_failure", "Runtime should degrade or fail over without data loss.", ["Local-only flows may need recovery UX."], ["Document restart and recovery behavior."], round(_bounded(base - 0.08), 3), "medium"),
        SimulationResult("network_failure", "Local work should continue while cloud features pause.", ["Cloud agent and PR flows may be unavailable."], ["Use offline_local_only state and retry services."], round(_bounded(base - 0.04), 3), "medium"),
        SimulationResult("security_attack", "Security review should block risky changes before execution.", ["Broad autonomous execution increases exposure."], ["Require auth, audit, sandbox, and approval gates."], round(_bounded((base + strategy.security) / 2), 3), "critical"),
        SimulationResult("dependency_failure", "Model, API, Redis, or GitHub failures should not corrupt project state.", ["External provider reliability is outside direct control."], ["Use fallback providers and durable jobs."], round(_bounded(base - 0.1), 3), "high"),
        SimulationResult("database_failure", "Mission state must be recoverable from durable storage and logs.", ["In-memory state may be lost."], ["Persist tasks, decisions, artifacts, and events."], round(_bounded(base - 0.12), 3), "high"),
        SimulationResult("rollback", "Reversible changes restore prior state when verification fails.", [], ["Snapshot every write before applying."], round(_bounded(base + 0.04), 3), "medium"),
        SimulationResult("unexpected_user_behavior", "The system should constrain actions to mission scope and authority.", ["Ambiguous prompts can trigger wrong scope."], ["Run cognitive assessment before execution."], round(_bounded(base - 0.06), 3), "medium"),
    ]


def predict_future(strategy: StrategyOption) -> list[Prediction]:
    """Forecast long-term consequences and warning signals."""

    return [
        Prediction(
            "30_days",
            "Delivery reliability",
            "Execution quality depends on how consistently receipts, review, rollback, and tests are enforced.",
            ["Initial scope remains focused.", "Users accept review gates for risky work."],
            round(_bounded(strategy.score + 0.04), 3),
            ["Manual review bypassed", "Receipts missing evidence"],
        ),
        Prediction(
            "90_days",
            "Operating cost",
            "Cost remains controlled if model routing assigns expensive models only to high-risk reasoning tasks.",
            ["Model router has per-task budgets.", "Local models handle low-risk work."],
            round(_bounded(1.0 - strategy.cost + 0.18), 3),
            ["Rising token usage", "Repeated failed tool calls"],
        ),
        Prediction(
            "1_year",
            "Scalability",
            "The platform scales if mission memory, task state, and event logs are durable and queryable.",
            ["Durable persistence is implemented.", "Knowledge graph is maintained."],
            round(_bounded(strategy.scalability), 3),
            ["Long-running jobs stuck", "Knowledge retrieval latency"],
        ),
        Prediction(
            "3_years",
            "Organizational evolution",
            "Arceus becomes defensible if it learns from every mission and improves its own specialists and policies.",
            ["Learning engine records outcomes.", "Meta intelligence measures specialist/model/tool quality."],
            round(_bounded(strategy.future_evolution), 3),
            ["No reusable lessons", "Specialists repeat known mistakes"],
        ),
    ]


def run_debate(strategy: StrategyOption) -> DebateRecord:
    """Create independent specialist positions; disagreement is preserved."""

    positions = [
        DebatePosition(
            specialist="Chief Architect",
            position=f"Support {strategy.name} if module boundaries and migration paths are explicit.",
            support=["Architecture remains explainable.", "Future evolution score is measurable."],
            objections=["Avoid hidden coupling between mission runtime and UI."],
            recommendation="Document boundaries before execution.",
            confidence=0.88,
        ),
        DebatePosition(
            specialist="Security Reviewer",
            position="Approve only with auth, audit, sandbox, and rollback gates.",
            support=["Security risks are visible in cognitive assessment."],
            objections=["Autonomous execution can exceed authority without policy checks."],
            recommendation="Require review for destructive, external, or high-risk operations.",
            confidence=0.9,
        ),
        DebatePosition(
            specialist="Product Strategist",
            position="Optimize for user trust and proof-first visible evidence.",
            support=["Users need to see what the AI organization did and why."],
            objections=["Too much internal process can slow first value."],
            recommendation="Show only executive-level evidence in the UI; keep details inspectable.",
            confidence=0.84,
        ),
        DebatePosition(
            specialist="Operations Lead",
            position="Do not consider the mission complete without runtime health checks.",
            support=["Production systems fail through dependencies, not only code."],
            objections=["Broad execution creates more jobs and queues to monitor."],
            recommendation="Track service, worker, Redis, model, and release health.",
            confidence=0.86,
        ),
    ]

    if strategy.risk > 0.6:
        positions.append(
            DebatePosition(
                specialist="Minority Reviewer",
                position="Reject broad autonomous execution until governance is stronger.",
                support=["Risk score is high.", "Coordination failures become costly."],
                objections=["Throughput gain does not justify unsafe authority."],
                recommendation="Constrain to proof-first execution first.",
                confidence=0.79,
                minority_opinion=True,
            )
        )

    return DebateRecord(
        topic=f"Should Arceus use {strategy.name}?",
        positions=positions,
        unresolved_questions=["Which provider/model mix is currently available?", "Which tests prove completion?"],
        consensus="Proceed only with evidence, review, rollback, and durable memory.",
    )


def choose_strategy(
    strategies: list[StrategyOption],
    findings: list[ResearchFinding],
    debates: list[DebateRecord],
) -> DecisionIntelligence:
    """Choose the best strategy and retain rejected alternatives."""

    selected = max(strategies, key=lambda item: item.score)
    alternatives = [
        {
            "strategy_id": strategy.strategy_id,
            "name": strategy.name,
            "score": strategy.score,
            "reason_rejected": "Lower combined evidence, maintainability, risk, and evolution score.",
        }
        for strategy in strategies
        if strategy.strategy_id != selected.strategy_id
    ]
    evidence_refs = [finding.finding_id for finding in findings]
    confidence = round(_bounded((selected.score + _weighted_average([finding.confidence for finding in findings])) / 2), 3)
    return DecisionIntelligence(
        decision=f"Use {selected.name}",
        selected_strategy_id=selected.strategy_id,
        verdict="recommended",
        rationale=[
            "Best weighted trade-off across correctness, maintainability, risk, future evolution, and user trust.",
            "Supports proof-first execution with structured evidence.",
            "Preserves rejected alternatives for future reconsideration.",
        ],
        alternatives_rejected=alternatives,
        evidence_refs=evidence_refs,
        risks=list({objection for debate in debates for position in debate.positions for objection in position.objections}),
        conditions=[
            "Run cognitive assessment before execution.",
            "Create work receipts and rollback evidence for changes.",
            "Require independent review for high-risk decisions.",
        ],
        confidence=confidence,
    )


def evaluate_organization_health(metrics: dict[str, float] | None = None, bottlenecks: list[str] | None = None) -> OrganizationHealth:
    """Measure organizational consciousness from health metrics."""

    metrics = metrics or {}
    bottlenecks = bottlenecks or []
    health = OrganizationHealth(
        mission_health=_bounded(metrics.get("mission_health", 0.86)),
        agent_health=_bounded(metrics.get("agent_health", 0.84)),
        task_health=_bounded(metrics.get("task_health", 0.82)),
        risk_health=_bounded(metrics.get("risk_health", 0.78)),
        knowledge_health=_bounded(metrics.get("knowledge_health", 0.8)),
        performance_health=_bounded(metrics.get("performance_health", 0.82)),
        cost_health=_bounded(metrics.get("cost_health", 0.76)),
        quality_health=_bounded(metrics.get("quality_health", 0.84)),
        user_satisfaction=_bounded(metrics.get("user_satisfaction", 0.8)),
        future_readiness=_bounded(metrics.get("future_readiness", 0.83)),
        bottlenecks=bottlenecks,
    )
    health.predictions.extend(
        [
            "Knowledge gaps will become execution bottlenecks if research findings are not linked to tasks.",
            "Model/tool failures should be tracked as organization health, not isolated errors.",
        ]
    )
    if health.status != "healthy":
        health.recommendations.append("Open an organizational review before expanding autonomous execution.")
    health.recommendations.extend(
        [
            "Keep mission memory scoped and evidence-backed.",
            "Record reusable lessons after every verified outcome.",
        ]
    )
    return health


def build_intelligence_graph(
    assessment: CognitiveAssessment,
    findings: list[ResearchFinding],
    strategies: list[StrategyOption],
    decision: DecisionIntelligence,
) -> UniversalIntelligenceGraph:
    """Link requirements, research, strategies, decisions, risks, and lessons."""

    graph = UniversalIntelligenceGraph()
    mission = graph.add_node(IntelligenceGraphNode("mission", "Mission", assessment.objective, {"domains": assessment.domains}))

    for criterion in assessment.success_criteria:
        node = graph.add_node(IntelligenceGraphNode("requirement", criterion, "Success criterion", {}))
        graph.connect(mission, node, "requires")

    for risk in assessment.risks:
        node = graph.add_node(IntelligenceGraphNode("risk", risk, "Detected during cognitive assessment", {}))
        graph.connect(node, mission, "conflicts_with")

    for finding in findings:
        node = graph.add_node(IntelligenceGraphNode("research", finding.topic, finding.summary, {"confidence": finding.confidence}))
        graph.connect(node, mission, "supports", finding.evidence)

    strategy_nodes: dict[str, IntelligenceGraphNode] = {}
    for strategy in strategies:
        node = graph.add_node(IntelligenceGraphNode("strategy", strategy.name, strategy.summary, {"score": strategy.score}))
        graph.connect(node, mission, "supports")
        strategy_nodes[strategy.strategy_id] = node

    decision_node = graph.add_node(
        IntelligenceGraphNode(
            "decision",
            decision.decision,
            "Decision intelligence selected the recommended strategy.",
            {"confidence": decision.confidence, "conditions": decision.conditions},
        )
    )
    if decision.selected_strategy_id in strategy_nodes:
        graph.connect(decision_node, strategy_nodes[decision.selected_strategy_id], "decided_by", decision.rationale)
    graph.connect(decision_node, mission, "supports")
    return graph


def reflect_on_cognitive_pass(decision: DecisionIntelligence, health: OrganizationHealth) -> ReflectionRecord:
    return ReflectionRecord(
        what_worked=[
            "Objective was converted into explicit domains, unknowns, risks, and success criteria.",
            "Multiple strategies were compared before choosing a recommendation.",
        ],
        what_failed=[] if health.status in {"healthy", "watch"} else ["Organization health indicates risk before execution."],
        surprises=[],
        reusable_lessons=[
            "Do not optimize for answers; optimize for missions and systems.",
            "Keep disagreement visible through debate records.",
        ],
        model_notes=["Model routing should prefer reasoning-specialized models for strategy and review."],
        tool_notes=["Execution tools should remain gated until decision intelligence approves conditions."],
        next_improvements=["Persist cognitive pass output as mission memory.", "Render organization health in Mission Control."],
    )


def run_cognitive_pass(objective: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the full Generation 2 cognitive pipeline for a mission."""

    assessment = understand_objective(objective, context)
    findings = collect_research(assessment)
    strategies = generate_strategy_options(assessment, findings)
    simulations = {strategy.strategy_id: simulate_strategy(strategy) for strategy in strategies}
    predictions = {strategy.strategy_id: predict_future(strategy) for strategy in strategies}
    debates = [run_debate(strategy) for strategy in strategies]
    decision = choose_strategy(strategies, findings, debates)
    health = evaluate_organization_health()
    graph = build_intelligence_graph(assessment, findings, strategies, decision)
    reflection = reflect_on_cognitive_pass(decision, health)

    return {
        "generation": "generation_2_cognitive_architecture",
        "rule": "Understand first. Research before deciding. Simulate before executing. Learn forever.",
        "dna": [
            "Never optimize for answers.",
            "Optimize for organizations.",
            "Never optimize for prompts.",
            "Optimize for missions.",
            "Never optimize for code.",
            "Optimize for systems.",
            "Never optimize for speed.",
            "Optimize for correctness.",
            "Never optimize for completion.",
            "Optimize for continuous evolution.",
        ],
        "assessment": assessment.to_dict(),
        "research": [finding.to_dict() for finding in findings],
        "strategies": [strategy.to_dict() for strategy in strategies],
        "simulations": {
            strategy_id: [simulation.to_dict() for simulation in scenario_results]
            for strategy_id, scenario_results in simulations.items()
        },
        "predictions": {
            strategy_id: [prediction.to_dict() for prediction in prediction_results]
            for strategy_id, prediction_results in predictions.items()
        },
        "debates": [debate.to_dict() for debate in debates],
        "decision": decision.to_dict(),
        "organization_health": health.to_dict(),
        "universal_intelligence_graph": graph.to_dict(),
        "reflection": reflection.to_dict(),
    }


def cognitive_architecture_manifest() -> dict[str, Any]:
    """Return the canonical Generation 2 architecture for UI/API inspection."""

    return {
        "name": "Arceus Cognitive Architecture",
        "generation": 2,
        "purpose": "Transform human objectives into evidence-backed organizational intelligence before execution.",
        "stages": [
            "cognitive_engine",
            "research_intelligence",
            "strategic_thinking",
            "simulation_engine",
            "prediction_engine",
            "debate_engine",
            "decision_intelligence",
            "execution_intelligence",
            "reflection_engine",
            "meta_intelligence",
            "organizational_consciousness",
            "universal_intelligence_graph",
        ],
        "organizational_health_dimensions": [
            "mission_health",
            "agent_health",
            "task_health",
            "risk_health",
            "knowledge_health",
            "performance_health",
            "cost_health",
            "quality_health",
            "user_satisfaction",
            "future_readiness",
        ],
        "memory_rule": "Select only the context each specialist needs; do not flood every agent with everything.",
        "completion_rule": "Completion requires evidence, review, verification, and learning.",
    }
