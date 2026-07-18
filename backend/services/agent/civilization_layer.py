"""Generation 6 Arceus Civilization Layer.

The Civilization Layer sits above the Intelligence Kernel and Arceus OS. It
coordinates many organizations, departments, teams, research labs, policies,
knowledge networks, capabilities, and humans as one evolving intelligence
ecosystem.

This module is intentionally deterministic and storage-agnostic. It defines the
contracts Arceus needs before persistence, UI, model providers, or distributed
execution are wired in.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


OrganizationKind = Literal["engineering", "research", "healthcare", "finance", "manufacturing", "legal", "robotics", "education", "operations", "governance"]
RelationshipKind = Literal["cooperates_with", "competes_with", "independent_from", "provides_capability_to", "governs", "learns_from"]
KnowledgeTrustState = Literal["proposed", "unverified", "verified", "reviewed", "approved", "superseded", "rejected", "archived"]
GraphNodeKind = Literal[
    "person",
    "organization",
    "department",
    "team",
    "project",
    "goal",
    "meeting",
    "requirement",
    "task",
    "knowledge",
    "research",
    "architecture",
    "code",
    "test",
    "deployment",
    "incident",
    "lesson",
    "model",
    "tool",
    "policy",
    "capability",
]
SimulationDomain = Literal["market", "architecture", "security", "users", "scaling", "costs", "failures", "competition", "growth"]
GovernanceVerdict = Literal["allowed", "requires_review", "blocked"]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid4())


def clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def average(values: list[float]) -> float:
    return round(sum(values) / len(values), 4) if values else 0.0


@dataclass(slots=True)
class OrganizationDNA:
    mission: str
    knowledge_domains: list[str]
    policies: list[str]
    capabilities: list[str]
    experts: list[str]
    learning_loops: list[str]
    performance_metrics: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "mission": self.mission,
            "knowledge_domains": self.knowledge_domains,
            "policies": self.policies,
            "capabilities": self.capabilities,
            "experts": self.experts,
            "learning_loops": self.learning_loops,
            "performance_metrics": self.performance_metrics,
        }


@dataclass(slots=True)
class CivilizationOrganization:
    name: str
    kind: OrganizationKind
    dna: OrganizationDNA
    goals: list[str] = field(default_factory=list)
    resource_budget: float = 1.0
    knowledge_sharing_policy: Literal["private", "approved_only", "organization", "civilization"] = "approved_only"
    performance_score: float = 0.75
    health_score: float = 0.75
    organization_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    def can_share_knowledge(self, trust_state: KnowledgeTrustState) -> bool:
        if self.knowledge_sharing_policy == "private":
            return False
        if self.knowledge_sharing_policy == "approved_only":
            return trust_state == "approved"
        if self.knowledge_sharing_policy in {"organization", "civilization"}:
            return trust_state in {"verified", "reviewed", "approved"}
        return False

    def to_dict(self) -> dict[str, Any]:
        return {
            "organization_id": self.organization_id,
            "name": self.name,
            "kind": self.kind,
            "dna": self.dna.to_dict(),
            "goals": self.goals,
            "resource_budget": self.resource_budget,
            "knowledge_sharing_policy": self.knowledge_sharing_policy,
            "performance_score": self.performance_score,
            "health_score": self.health_score,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class CivilizationRelationship:
    source_organization_id: str
    target_organization_id: str
    relationship: RelationshipKind
    policy: str = "default"
    trust_level: float = 0.7
    relationship_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "relationship_id": self.relationship_id,
            "source_organization_id": self.source_organization_id,
            "target_organization_id": self.target_organization_id,
            "relationship": self.relationship,
            "policy": self.policy,
            "trust_level": self.trust_level,
        }


@dataclass(slots=True)
class TrustedKnowledge:
    title: str
    content: str
    source: str
    owner_organization_id: str
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.5
    verification: KnowledgeTrustState = "proposed"
    freshness: float = 1.0
    popularity: float = 0.0
    usage_count: int = 0
    risk: float = 0.3
    knowledge_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    @property
    def trust_score(self) -> float:
        state_score = {
            "proposed": 0.1,
            "unverified": 0.2,
            "verified": 0.65,
            "reviewed": 0.78,
            "approved": 0.92,
            "superseded": 0.15,
            "rejected": 0.0,
            "archived": 0.25,
        }[self.verification]
        return round(clamp((state_score * 0.45) + (self.confidence * 0.25) + (self.freshness * 0.12) + (self.popularity * 0.08) + (min(self.usage_count, 50) / 50 * 0.1) - (self.risk * 0.12)), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_id": self.knowledge_id,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "owner_organization_id": self.owner_organization_id,
            "evidence": self.evidence,
            "confidence": self.confidence,
            "verification": self.verification,
            "freshness": self.freshness,
            "popularity": self.popularity,
            "usage_count": self.usage_count,
            "risk": self.risk,
            "trust_score": self.trust_score,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class CivilizationGraphNode:
    kind: GraphNodeKind
    title: str
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)
    node_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {"node_id": self.node_id, "kind": self.kind, "title": self.title, "summary": self.summary, "metadata": self.metadata}


@dataclass(slots=True)
class CivilizationGraphEdge:
    source_id: str
    target_id: str
    relationship: str
    evidence: list[str] = field(default_factory=list)
    edge_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {"edge_id": self.edge_id, "source_id": self.source_id, "target_id": self.target_id, "relationship": self.relationship, "evidence": self.evidence}


@dataclass(slots=True)
class GlobalIntelligenceGraph:
    nodes: list[CivilizationGraphNode] = field(default_factory=list)
    edges: list[CivilizationGraphEdge] = field(default_factory=list)

    def add_node(self, node: CivilizationGraphNode) -> CivilizationGraphNode:
        self.nodes.append(node)
        return node

    def connect(self, source: CivilizationGraphNode, target: CivilizationGraphNode, relationship: str, evidence: list[str] | None = None) -> CivilizationGraphEdge:
        edge = CivilizationGraphEdge(source.node_id, target.node_id, relationship, evidence or [])
        self.edges.append(edge)
        return edge

    def neighborhood(self, node_id: str) -> list[dict[str, Any]]:
        node_map = {node.node_id: node for node in self.nodes}
        related: list[dict[str, Any]] = []
        for edge in self.edges:
            if edge.source_id == node_id or edge.target_id == node_id:
                other_id = edge.target_id if edge.source_id == node_id else edge.source_id
                if other_id in node_map:
                    related.append({"node": node_map[other_id].to_dict(), "edge": edge.to_dict()})
        return related

    def to_dict(self) -> dict[str, Any]:
        return {"nodes": [node.to_dict() for node in self.nodes], "edges": [edge.to_dict() for edge in self.edges]}


@dataclass(slots=True)
class CapabilityOffer:
    organization_id: str
    name: str
    description: str
    domains: list[str]
    cost: float
    latency: float
    quality: float
    reliability: float
    demand: float = 0.0
    supply: float = 1.0
    offer_id: str = field(default_factory=new_id)

    @property
    def value_score(self) -> float:
        return round(clamp((self.quality * 0.35) + (self.reliability * 0.3) + ((1 - self.cost) * 0.16) + ((1 - self.latency) * 0.1) + (self.supply * 0.05) + (self.demand * 0.04)), 4)

    def to_dict(self) -> dict[str, Any]:
        return {
            "offer_id": self.offer_id,
            "organization_id": self.organization_id,
            "name": self.name,
            "description": self.description,
            "domains": self.domains,
            "cost": self.cost,
            "latency": self.latency,
            "quality": self.quality,
            "reliability": self.reliability,
            "demand": self.demand,
            "supply": self.supply,
            "value_score": self.value_score,
        }


@dataclass(slots=True)
class CapabilityMarketplace:
    offers: list[CapabilityOffer] = field(default_factory=list)

    def publish(self, offer: CapabilityOffer) -> CapabilityOffer:
        self.offers.append(offer)
        return offer

    def find_best(self, domain: str, objective_keywords: list[str] | None = None) -> CapabilityOffer | None:
        keywords = {item.lower() for item in objective_keywords or []}
        candidates = [offer for offer in self.offers if domain in offer.domains]
        if keywords:
            candidates = [
                offer
                for offer in candidates
                if keywords.intersection({offer.name.lower(), offer.description.lower(), *[part.lower() for part in offer.name.split()]})
            ] or candidates
        return max(candidates, key=lambda offer: offer.value_score, default=None)


@dataclass(slots=True)
class CivilizationMetrics:
    knowledge_growth: float = 0.0
    organization_health: float = 0.0
    mission_success: float = 0.0
    innovation: float = 0.0
    learning_speed: float = 0.0
    cost_efficiency: float = 0.0
    research_quality: float = 0.0
    reliability: float = 0.0
    user_happiness: float = 0.0
    impact: float = 0.0

    @property
    def civilization_score(self) -> float:
        return average([
            self.knowledge_growth,
            self.organization_health,
            self.mission_success,
            self.innovation,
            self.learning_speed,
            self.cost_efficiency,
            self.research_quality,
            self.reliability,
            self.user_happiness,
            self.impact,
        ])

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_growth": self.knowledge_growth,
            "organization_health": self.organization_health,
            "mission_success": self.mission_success,
            "innovation": self.innovation,
            "learning_speed": self.learning_speed,
            "cost_efficiency": self.cost_efficiency,
            "research_quality": self.research_quality,
            "reliability": self.reliability,
            "user_happiness": self.user_happiness,
            "impact": self.impact,
            "civilization_score": self.civilization_score,
        }


@dataclass(slots=True)
class SimulationResult:
    domain: SimulationDomain
    forecast: str
    risks: list[str]
    opportunities: list[str]
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {"domain": self.domain, "forecast": self.forecast, "risks": self.risks, "opportunities": self.opportunities, "confidence": self.confidence}


@dataclass(slots=True)
class GovernancePolicy:
    name: str
    rule: str
    restricted_domains: list[str] = field(default_factory=list)
    required_trust_score: float = 0.75
    policy_id: str = field(default_factory=new_id)

    def evaluate(self, knowledge: TrustedKnowledge, requesting_org: CivilizationOrganization) -> tuple[GovernanceVerdict, str]:
        if knowledge.trust_score < self.required_trust_score:
            return "requires_review", "Knowledge trust is below policy threshold."
        if self.restricted_domains and requesting_org.kind in self.restricted_domains:
            return "requires_review", "Restricted domain requires governance review."
        if requesting_org.can_share_knowledge(knowledge.verification):
            return "allowed", "Knowledge sharing is allowed by organization policy."
        return "blocked", "Organization policy blocks sharing this knowledge."


@dataclass(slots=True)
class UniversityLesson:
    source_knowledge_id: str
    title: str
    training_plan: list[str]
    simulation: str
    certification: str
    expected_capability_gain: float
    lesson_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lesson_id": self.lesson_id,
            "source_knowledge_id": self.source_knowledge_id,
            "title": self.title,
            "training_plan": self.training_plan,
            "simulation": self.simulation,
            "certification": self.certification,
            "expected_capability_gain": self.expected_capability_gain,
        }


@dataclass(slots=True)
class EvolutionProposal:
    target_organization_id: str
    reason: str
    improvement: str
    evidence: list[str]
    validation_plan: list[str]
    rollback_plan: list[str]
    stage: Literal["experimental", "evaluating", "approved", "production", "deprecated", "rolled_back"] = "experimental"
    proposal_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "target_organization_id": self.target_organization_id,
            "reason": self.reason,
            "improvement": self.improvement,
            "evidence": self.evidence,
            "validation_plan": self.validation_plan,
            "rollback_plan": self.rollback_plan,
            "stage": self.stage,
        }


class ArceusCivilization:
    def __init__(self) -> None:
        self.organizations: dict[str, CivilizationOrganization] = {}
        self.relationships: list[CivilizationRelationship] = []
        self.knowledge: dict[str, TrustedKnowledge] = {}
        self.graph = GlobalIntelligenceGraph()
        self.marketplace = CapabilityMarketplace()
        self.policies: list[GovernancePolicy] = []
        self.university_lessons: list[UniversityLesson] = []
        self.evolution_proposals: list[EvolutionProposal] = []

    def add_organization(self, organization: CivilizationOrganization) -> CivilizationOrganization:
        self.organizations[organization.organization_id] = organization
        self.graph.add_node(CivilizationGraphNode("organization", organization.name, organization.dna.mission, {"kind": organization.kind}))
        return organization

    def relate(self, source_id: str, target_id: str, relationship: RelationshipKind, policy: str = "default") -> CivilizationRelationship:
        if source_id not in self.organizations or target_id not in self.organizations:
            raise ValueError("Both organizations must exist before creating a relationship.")
        relation = CivilizationRelationship(source_id, target_id, relationship, policy)
        self.relationships.append(relation)
        return relation

    def publish_knowledge(self, item: TrustedKnowledge) -> TrustedKnowledge:
        if item.owner_organization_id not in self.organizations:
            raise ValueError("Knowledge owner organization does not exist.")
        self.knowledge[item.knowledge_id] = item
        self.graph.add_node(CivilizationGraphNode("knowledge", item.title, item.content, {"trust_score": item.trust_score}))
        return item

    def shareable_knowledge_for(self, requesting_organization_id: str) -> list[TrustedKnowledge]:
        requesting = self.organizations[requesting_organization_id]
        allowed: list[TrustedKnowledge] = []
        for item in self.knowledge.values():
            owner = self.organizations[item.owner_organization_id]
            if item.owner_organization_id == requesting_organization_id:
                allowed.append(item)
                continue
            if not owner.can_share_knowledge(item.verification):
                continue
            if self.policies:
                verdicts = [policy.evaluate(item, owner)[0] for policy in self.policies]
                if "blocked" in verdicts or "requires_review" in verdicts:
                    continue
            allowed.append(item)
        return allowed

    def schedule_best_capability(self, mission_domain: str, objective: str) -> dict[str, Any]:
        offer = self.marketplace.find_best(mission_domain, objective.split())
        if not offer:
            return {"scheduled": False, "reason": "No matching capability offer found."}
        organization = self.organizations[offer.organization_id]
        return {
            "scheduled": True,
            "organization": organization.to_dict(),
            "capability": offer.to_dict(),
            "reason": "Selected highest value capability for mission domain.",
        }

    def simulate(self, objective: str) -> list[SimulationResult]:
        return [
            SimulationResult("market", "Demand depends on how clearly the product improves real workflows.", ["Weak differentiation"], ["Narrow wedge positioning"], 0.78),
            SimulationResult("architecture", "Modular organizations reduce coupling across missions.", ["Over-abstraction"], ["Reusable capability marketplace"], 0.84),
            SimulationResult("security", "Knowledge sharing must be gated by trust and policy.", ["Cross-organization leakage"], ["Approved-only sharing"], 0.88),
            SimulationResult("scaling", "Global scheduling scales if capabilities are measured by quality, latency, cost, and reliability.", ["Scheduler complexity"], ["Start with software engineering only"], 0.81),
            SimulationResult("costs", "Capability economy prevents expensive specialists from handling low-value work.", ["Hidden model spend"], ["Cost-aware routing"], 0.79),
            SimulationResult("failures", "Organizations can recover if lessons and incidents are connected in the graph.", ["Stale lessons"], ["Freshness scoring"], 0.8),
            SimulationResult("competition", "Civilization memory is a stronger moat than isolated coding agents.", ["Competitors can copy UI"], ["Preserve graph and learning loops"], 0.86),
            SimulationResult("growth", "AI University turns lessons into certified capabilities.", ["Low-quality lessons"], ["Review before certification"], 0.82),
            SimulationResult("users", "Humans trust the system when governance and evidence are visible.", ["Too much complexity"], ["Executive-level summaries"], 0.83),
        ]

    def teach_from_lesson(self, knowledge_id: str) -> UniversityLesson:
        item = self.knowledge[knowledge_id]
        if item.trust_score < 0.75:
            raise ValueError("Only trusted knowledge can become university training.")
        lesson = UniversityLesson(
            source_knowledge_id=knowledge_id,
            title=f"Certification from {item.title}",
            training_plan=["Study evidence", "Run simulation", "Apply to sandbox mission", "Pass review"],
            simulation="Replay the source mission with controlled variations.",
            certification="Capability is certified after review and measurable improvement.",
            expected_capability_gain=round(clamp(item.trust_score * 0.18), 4),
        )
        self.university_lessons.append(lesson)
        return lesson

    def propose_evolution(self, organization_id: str, metrics: CivilizationMetrics) -> EvolutionProposal:
        if organization_id not in self.organizations:
            raise ValueError("Organization does not exist.")
        if metrics.civilization_score >= 0.82:
            reason = "Organization is healthy; optimize selectively."
            improvement = "Document winning patterns and publish reusable capabilities."
        else:
            reason = "Civilization metrics indicate improvement is required."
            improvement = "Tune specialist mix, model routing, context retrieval, and review depth."
        proposal = EvolutionProposal(
            target_organization_id=organization_id,
            reason=reason,
            improvement=improvement,
            evidence=[f"civilization_score={metrics.civilization_score}"],
            validation_plan=["Run controlled evaluation", "Compare mission success", "Measure cost and reliability"],
            rollback_plan=["Revert organization configuration", "Restore prior routing policy"],
        )
        self.evolution_proposals.append(proposal)
        return proposal

    def metrics(self) -> CivilizationMetrics:
        approved_knowledge = [item for item in self.knowledge.values() if item.verification == "approved"]
        org_scores = [org.health_score for org in self.organizations.values()]
        return CivilizationMetrics(
            knowledge_growth=clamp(len(approved_knowledge) / 10),
            organization_health=average(org_scores),
            mission_success=average([org.performance_score for org in self.organizations.values()]),
            innovation=clamp(len(self.marketplace.offers) / 10),
            learning_speed=clamp(len(self.university_lessons) / 10),
            cost_efficiency=0.75,
            research_quality=average([item.trust_score for item in approved_knowledge]),
            reliability=average([offer.reliability for offer in self.marketplace.offers]),
            user_happiness=0.8,
            impact=clamp((len(self.organizations) + len(self.relationships)) / 10),
        )


def create_engineering_civilization_seed() -> ArceusCivilization:
    civ = ArceusCivilization()
    engineering = civ.add_organization(
        CivilizationOrganization(
            name="Engineering Organization",
            kind="engineering",
            dna=OrganizationDNA(
                mission="Build, review, verify, deploy, and evolve software systems.",
                knowledge_domains=["architecture", "code", "testing", "deployment", "security"],
                policies=["evidence_required", "review_before_merge", "approved_knowledge_only"],
                capabilities=["architecture_review", "security_review", "api_design", "testing", "deployment"],
                experts=["Engineering Manager", "Architect", "Implementation Engineer", "Security Reviewer", "QA Reviewer"],
                learning_loops=["mission_retrospective", "incident_lessons", "capability_evaluation"],
                performance_metrics=["mission_success", "quality", "cost", "reliability", "learning_speed"],
            ),
            goals=["Deliver safe software changes", "Preserve reusable engineering knowledge"],
            health_score=0.86,
            performance_score=0.84,
        )
    )
    research = civ.add_organization(
        CivilizationOrganization(
            name="Research Lab",
            kind="research",
            dna=OrganizationDNA(
                mission="Turn questions into experiments, benchmarks, and reusable knowledge.",
                knowledge_domains=["benchmarks", "experiments", "model evaluation"],
                policies=["review_before_global_knowledge", "experiment_reproducibility"],
                capabilities=["research_planning", "benchmarking", "evidence_synthesis"],
                experts=["Research Lead", "Benchmark Scientist", "Evaluation Reviewer"],
                learning_loops=["experiment_result", "benchmark_update"],
                performance_metrics=["research_quality", "evidence_strength", "reuse_rate"],
            ),
            goals=["Improve model/tool decisions", "Certify reusable lessons"],
            health_score=0.82,
            performance_score=0.8,
        )
    )
    civ.relate(engineering.organization_id, research.organization_id, "cooperates_with")
    civ.policies.append(GovernancePolicy("Approved Knowledge Sharing", "Only approved knowledge may cross organization boundaries."))
    civ.marketplace.publish(CapabilityOffer(engineering.organization_id, "Security Review", "Review software changes for auth, secrets, policy, and abuse risk.", ["software_engineering", "security"], 0.35, 0.3, 0.88, 0.9, demand=0.7))
    civ.marketplace.publish(CapabilityOffer(engineering.organization_id, "Architecture Review", "Evaluate modularity, scalability, maintainability, and migration risk.", ["software_engineering", "architecture"], 0.4, 0.35, 0.9, 0.88, demand=0.8))
    civ.marketplace.publish(CapabilityOffer(research.organization_id, "Model Benchmark", "Benchmark model reliability, cost, latency, and structured output quality.", ["research", "artificial_intelligence"], 0.45, 0.5, 0.86, 0.84, demand=0.6))
    return civ


def civilization_manifest() -> dict[str, Any]:
    return {
        "name": "Arceus Civilization Layer",
        "generation": 6,
        "purpose": "Coordinate many evolving organizations into one policy-governed intelligence ecosystem.",
        "principle": "Organizations evolve independently while contributing approved knowledge to the civilization.",
        "hierarchy": ["civilization", "organizations", "departments", "teams", "missions", "specialists", "knowledge"],
        "core_systems": [
            "global_intelligence_graph",
            "organization_dna",
            "capability_marketplace",
            "ai_economy",
            "global_scheduler",
            "knowledge_trust",
            "research_civilization",
            "universal_simulation",
            "ai_university",
            "governance",
            "civilization_memory",
            "self_evolution",
        ],
        "metrics": [
            "knowledge_growth",
            "organization_health",
            "mission_success",
            "innovation",
            "learning_speed",
            "cost_efficiency",
            "research_quality",
            "reliability",
            "user_happiness",
            "impact",
        ],
    }
