"""Generation 2 dynamic organization and project-memory contracts.

Generation 2 extends the fixed Generation 1 engineering organization into a
capability-driven, persistent, measurable engineering organization.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .core import clamp_score, new_id, utc_now


RiskLevel = Literal["low", "medium", "high", "critical"]
DefinitionStatus = Literal["experimental", "active", "deprecated"]
OrganizationPlanStatus = Literal["proposed", "approved", "rejected", "superseded"]
OrganizationState = Literal["PROPOSED", "FORMING", "ACTIVE", "REORGANIZING", "DEGRADED", "PAUSED", "COMPLETING", "DISSOLVED", "ARCHIVED"]
OrganizationChangeType = Literal[
    "ADD_SPECIALIST",
    "REMOVE_SPECIALIST",
    "REPLACE_SPECIALIST",
    "MERGE_ROLES",
    "SPLIT_ROLE",
    "CREATE_TEAM",
    "DISSOLVE_TEAM",
    "CHANGE_REPORTING_LINE",
    "REALLOCATE_BUDGET",
    "CHANGE_MODEL_POLICY",
    "CHANGE_TOOL_PERMISSION",
    "ADD_REVIEW_COUNCIL",
    "REASSIGN_TASK",
]
KnowledgeStatus = Literal["proposed", "active", "superseded", "rejected", "archived"]
KnowledgeTrust = Literal["unverified", "peer_reviewed", "tool_verified", "human_approved", "environment_observed"]
KnowledgeType = Literal["fact", "claim", "assumption", "preference", "decision", "pattern", "lesson", "risk", "prediction"]
MemoryScope = Literal["task", "mission", "project", "organization", "global"]
Sensitivity = Literal["public", "internal", "confidential", "restricted"]


RISK_ORDER = {"low": 0, "medium": 1, "high": 2, "critical": 3}
TRUST_ORDER = {"unverified": 0, "peer_reviewed": 1, "tool_verified": 2, "human_approved": 3, "environment_observed": 4}


@dataclass(slots=True)
class CapabilityDefinition:
    key: str
    name: str
    description: str
    category: str
    domains: list[str]
    required_tools: list[str] = field(default_factory=list)
    recommended_tools: list[str] = field(default_factory=list)
    required_permissions: list[str] = field(default_factory=list)
    recommended_models: list[str] = field(default_factory=list)
    verification_methods: list[str] = field(default_factory=list)
    risk_level: RiskLevel = "medium"
    independent_review_required: bool = False
    prerequisite_capability_ids: list[str] = field(default_factory=list)
    incompatible_capability_ids: list[str] = field(default_factory=list)
    version: str = "1.0.0"
    status: DefinitionStatus = "active"
    historical_effectiveness: float = 0.75
    capability_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def matches(self, query: str) -> bool:
        lowered = query.lower()
        haystack = " ".join([self.key, self.name, self.description, self.category, *self.domains]).lower()
        return lowered in haystack or any(part in haystack for part in lowered.split("_"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "capability_id": self.capability_id,
            "key": self.key,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "domains": self.domains,
            "required_tools": self.required_tools,
            "recommended_tools": self.recommended_tools,
            "required_permissions": self.required_permissions,
            "recommended_models": self.recommended_models,
            "verification_methods": self.verification_methods,
            "risk_level": self.risk_level,
            "independent_review_required": self.independent_review_required,
            "prerequisite_capability_ids": self.prerequisite_capability_ids,
            "incompatible_capability_ids": self.incompatible_capability_ids,
            "version": self.version,
            "status": self.status,
            "historical_effectiveness": self.historical_effectiveness,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class CapabilityCatalog:
    def __init__(self, capabilities: list[CapabilityDefinition] | None = None) -> None:
        self.capabilities: dict[str, CapabilityDefinition] = {}
        for capability in capabilities or []:
            self.register(capability)

    def register(self, capability: CapabilityDefinition) -> CapabilityDefinition:
        self.capabilities[capability.capability_id] = capability
        return capability

    def search(
        self,
        *,
        query: str | None = None,
        domains: list[str] | None = None,
        risk_at_most: RiskLevel | None = None,
        verification_method: str | None = None,
    ) -> list[CapabilityDefinition]:
        results = [capability for capability in self.capabilities.values() if capability.status == "active"]
        if query:
            results = [capability for capability in results if capability.matches(query)]
        if domains:
            domain_set = set(domains)
            results = [capability for capability in results if domain_set.intersection(capability.domains)]
        if risk_at_most:
            results = [capability for capability in results if RISK_ORDER[capability.risk_level] <= RISK_ORDER[risk_at_most]]
        if verification_method:
            results = [capability for capability in results if verification_method in capability.verification_methods]
        return sorted(results, key=lambda capability: capability.historical_effectiveness, reverse=True)

    def by_key(self, key: str) -> CapabilityDefinition | None:
        return next((capability for capability in self.capabilities.values() if capability.key == key and capability.status == "active"), None)


@dataclass(slots=True)
class SpecialistProfileDefinition:
    key: str
    display_name: str
    description: str
    primary_domain: str
    capability_keys: list[str]
    default_responsibilities: list[str]
    default_tools: list[str] = field(default_factory=list)
    default_memory_scope: dict[str, Any] = field(default_factory=dict)
    default_authority: dict[str, bool] = field(default_factory=dict)
    review_incompatibilities: list[str] = field(default_factory=list)
    model_requirements: dict[str, Any] = field(default_factory=dict)
    minimum_context_budget: int = 4000
    risk_ceiling: RiskLevel = "high"
    version: str = "1.0.0"
    status: DefinitionStatus = "active"
    historical_effectiveness: float = 0.75
    profile_id: str = field(default_factory=new_id)

    def covers(self, required_capabilities: set[str]) -> set[str]:
        return set(self.capability_keys).intersection(required_capabilities)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "key": self.key,
            "display_name": self.display_name,
            "description": self.description,
            "primary_domain": self.primary_domain,
            "capability_keys": self.capability_keys,
            "default_responsibilities": self.default_responsibilities,
            "default_tools": self.default_tools,
            "default_memory_scope": self.default_memory_scope,
            "default_authority": self.default_authority,
            "review_incompatibilities": self.review_incompatibilities,
            "model_requirements": self.model_requirements,
            "minimum_context_budget": self.minimum_context_budget,
            "risk_ceiling": self.risk_ceiling,
            "version": self.version,
            "status": self.status,
            "historical_effectiveness": self.historical_effectiveness,
        }


class SpecialistProfileLibrary:
    def __init__(self, profiles: list[SpecialistProfileDefinition] | None = None) -> None:
        self.profiles: dict[str, SpecialistProfileDefinition] = {}
        for profile in profiles or []:
            self.register(profile)

    def register(self, profile: SpecialistProfileDefinition) -> SpecialistProfileDefinition:
        self.profiles[profile.profile_id] = profile
        return profile

    def candidates_for(self, required_capabilities: set[str]) -> list[SpecialistProfileDefinition]:
        return sorted(
            [profile for profile in self.profiles.values() if profile.status == "active" and profile.covers(required_capabilities)],
            key=lambda profile: (len(profile.covers(required_capabilities)), profile.historical_effectiveness),
            reverse=True,
        )


@dataclass(slots=True)
class OrganizationSpecialistAssignment:
    profile_key: str
    display_name: str
    capability_keys: list[str]
    responsibilities: list[str]
    tools: list[str]
    model_policy: dict[str, Any]
    authority: dict[str, bool]
    reviewers: list[str]
    rationale: list[str]
    estimated_cost: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_key": self.profile_key,
            "display_name": self.display_name,
            "capability_keys": self.capability_keys,
            "responsibilities": self.responsibilities,
            "tools": self.tools,
            "model_policy": self.model_policy,
            "authority": self.authority,
            "reviewers": self.reviewers,
            "rationale": self.rationale,
            "estimated_cost": self.estimated_cost,
        }


@dataclass(slots=True)
class CandidateOrganizationStructure:
    name: str
    mission_lead: OrganizationSpecialistAssignment
    specialists: list[OrganizationSpecialistAssignment]
    review_councils: list[dict[str, Any]]
    reporting_lines: list[dict[str, str]]
    communication_channels: list[str]
    authority_assignments: list[dict[str, Any]]
    budget_allocations: list[dict[str, Any]]
    coverage_score: float
    reviewer_independence: float
    expected_quality: float
    historical_effectiveness: float
    parallelization_value: float
    estimated_cost: float
    communication_overhead: float
    responsibility_overlap: float
    coordination_risk: float
    known_gaps: list[str] = field(default_factory=list)

    @property
    def organization_score(self) -> float:
        return round(
            self.coverage_score
            + self.reviewer_independence
            + self.expected_quality
            + self.historical_effectiveness
            + self.parallelization_value
            - self.estimated_cost
            - self.communication_overhead
            - self.responsibility_overlap
            - self.coordination_risk,
            4,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "mission_lead": self.mission_lead.to_dict(),
            "specialists": [specialist.to_dict() for specialist in self.specialists],
            "review_councils": self.review_councils,
            "reporting_lines": self.reporting_lines,
            "communication_channels": self.communication_channels,
            "authority_assignments": self.authority_assignments,
            "budget_allocations": self.budget_allocations,
            "coverage_score": self.coverage_score,
            "reviewer_independence": self.reviewer_independence,
            "expected_quality": self.expected_quality,
            "historical_effectiveness": self.historical_effectiveness,
            "parallelization_value": self.parallelization_value,
            "estimated_cost": self.estimated_cost,
            "communication_overhead": self.communication_overhead,
            "responsibility_overlap": self.responsibility_overlap,
            "coordination_risk": self.coordination_risk,
            "organization_score": self.organization_score,
            "known_gaps": self.known_gaps,
        }


@dataclass(slots=True)
class OrganizationPlan:
    mission_id: str
    detected_domains: list[str]
    required_capabilities: list[str]
    complexity: RiskLevel
    risk_level: RiskLevel
    candidate_structures: list[CandidateOrganizationStructure]
    selected_structure: CandidateOrganizationStructure
    coverage_score: float
    estimated_cost: float
    estimated_duration: str | None
    known_gaps: list[str]
    assumptions: list[str]
    rationale: list[str]
    requires_human_approval: bool
    status: OrganizationPlanStatus = "proposed"
    organization_plan_id: str = field(default_factory=new_id)

    def approve(self) -> None:
        self.status = "approved"

    def to_dict(self) -> dict[str, Any]:
        return {
            "organization_plan_id": self.organization_plan_id,
            "mission_id": self.mission_id,
            "detected_domains": self.detected_domains,
            "required_capabilities": self.required_capabilities,
            "complexity": self.complexity,
            "risk_level": self.risk_level,
            "candidate_structures": [candidate.to_dict() for candidate in self.candidate_structures],
            "selected_structure": self.selected_structure.to_dict(),
            "coverage_score": self.coverage_score,
            "estimated_cost": self.estimated_cost,
            "estimated_duration": self.estimated_duration,
            "known_gaps": self.known_gaps,
            "assumptions": self.assumptions,
            "rationale": self.rationale,
            "requires_human_approval": self.requires_human_approval,
            "status": self.status,
        }


class DynamicOrganizationBuilder:
    def __init__(self, catalog: CapabilityCatalog, profiles: SpecialistProfileLibrary) -> None:
        self.catalog = catalog
        self.profiles = profiles

    def detect_capabilities(self, objective: str) -> tuple[list[str], list[str], RiskLevel]:
        lowered = objective.lower()
        capabilities = ["requirement_analysis"]
        domains = ["software_engineering"]
        risk: RiskLevel = "low"
        if any(term in lowered for term in ["roadmap", "story", "acceptance", "requirement", "product", "workflow", "feature"]):
            domains.append("product")
            capabilities.extend(["user_story_design", "acceptance_criteria_definition", "product_risk_analysis"])
            risk = "medium"
        if any(term in lowered for term in ["frontend", "react", "next", "next.js", "user interface", "button", "component", "css", "responsive", "screen"]):
            domains.append("frontend")
            capabilities.extend(["react_development", "nextjs_development", "responsive_ui", "accessibility_review", "frontend_testing", "build_verification"])
            risk = "medium"
        if any(term in lowered for term in ["auth", "authentication", "authorization", "login", "session", "oauth", "sso", "clerk", "permission"]):
            domains.extend(["architecture", "backend", "database", "security"])
            capabilities.extend([
                "requirement_analysis",
                "user_story_design",
                "acceptance_criteria_definition",
                "product_risk_analysis",
                "system_architecture",
                "api_architecture",
                "data_architecture",
                "architecture_tradeoff_analysis",
                "python_backend_development",
                "fastapi_development",
                "api_design",
                "relational_modeling",
                "postgresql_design",
                "tenant_isolation",
                "threat_modeling",
                "authentication_review",
                "authorization_review",
                "secrets_review",
                "input_validation_review",
                "unit_test_design",
                "integration_testing",
                "evidence_validation",
            ])
            risk = "high"
        if any(term in lowered for term in ["subscription", "billing", "stripe", "payment", "webhook"]):
            domains.extend(["payments", "fintech"])
            capabilities.extend([
                "payment_gateway_integration",
                "subscription_billing",
                "webhook_reliability",
                "payment_security",
                "reconciliation",
                "refund_workflows",
                "api_design",
                "background_job_design",
                "relational_modeling",
                "postgresql_design",
                "authentication_review",
                "authorization_review",
                "secrets_review",
                "dependency_security",
                "integration_testing",
                "build_verification",
                "cloud_deployment",
                "observability",
                "rollback_design",
            ])
            risk = "high"
        if any(term in lowered for term in ["ai", "model", "agent", "retrieval", "rag", "embedding", "vector", "prompt"]):
            domains.append("ai_development")
            capabilities.extend([
                "user_story_design",
                "acceptance_criteria_definition",
                "retrieval_architecture",
                "model_integration",
                "model_routing",
                "structured_output_design",
                "agent_orchestration",
                "evaluation_pipeline",
                "prompt_injection_defense",
                "api_design",
                "data_architecture",
                "relational_modeling",
                "secure_code_review",
                "unit_test_design",
                "integration_testing",
                "evidence_validation",
            ])
            risk = "high" if any(term in lowered for term in ["agent", "prompt injection", "autonomous"]) else max(risk, "medium", key=lambda item: RISK_ORDER[item])
        if any(term in lowered for term in ["cloud", "deploy", "railway", "docker", "release", "rollback", "incident", "monitoring"]):
            domains.append("cloud_infrastructure")
            capabilities.extend(["docker_configuration", "ci_cd_design", "cloud_deployment", "observability", "incident_response", "release_management", "rollback_design"])
            risk = max(risk, "medium", key=lambda item: RISK_ORDER[item])
        return list(dict.fromkeys(capabilities)), list(dict.fromkeys(domains)), risk

    def build_plan(self, mission_id: str, objective: str, mission_budget: float = 2.5) -> OrganizationPlan:
        required, domains, risk = self.detect_capabilities(objective)
        required_set = set(required)
        available_keys = {capability.key for capability in self.catalog.capabilities.values() if capability.status == "active"}
        missing_catalog_capabilities = sorted(required_set - available_keys)
        plannable_required = required_set.intersection(available_keys)
        candidates = self.profiles.candidates_for(required_set)
        lead_profile = next((profile for profile in self.profiles.profiles.values() if profile.key == "mission_lead"), None) or candidates[0]
        structure_a = self._structure("Focused capability team", lead_profile, candidates, plannable_required, mission_budget)
        structure_b = self._structure("Expanded independent review team", lead_profile, candidates[: max(1, len(candidates))], plannable_required, mission_budget, force_reviewers=True)
        candidate_structures = [structure_a, structure_b]
        selected = max(candidate_structures, key=lambda candidate: candidate.organization_score)
        known_gaps = sorted(set(selected.known_gaps + missing_catalog_capabilities))
        return OrganizationPlan(
            mission_id=mission_id,
            detected_domains=domains,
            required_capabilities=required,
            complexity="high" if len(required) >= 8 else "medium",
            risk_level=risk,
            candidate_structures=candidate_structures,
            selected_structure=selected,
            coverage_score=selected.coverage_score,
            estimated_cost=selected.estimated_cost,
            estimated_duration="1-2 weeks" if risk in {"medium", "high"} else "3-5 days",
            known_gaps=known_gaps,
            assumptions=["Capability definitions do not grant authority; policy assigns authority."],
            rationale=[
                "Specialists are selected by capability coverage, not fixed titles.",
                "Reviewers are separated from implementers.",
                "Known gaps remain visible instead of being pretended away.",
            ],
            requires_human_approval=risk in {"high", "critical"} or bool(known_gaps),
        )

    def _structure(
        self,
        name: str,
        lead_profile: SpecialistProfileDefinition,
        profiles: list[SpecialistProfileDefinition],
        required: set[str],
        mission_budget: float,
        *,
        force_reviewers: bool = False,
    ) -> CandidateOrganizationStructure:
        selected_profiles: list[SpecialistProfileDefinition] = [lead_profile]
        covered: set[str] = set(lead_profile.capability_keys).intersection(required)
        for profile in profiles:
            if profile.key == lead_profile.key:
                continue
            new_coverage = profile.covers(required) - covered
            requires_named_owner = (
                profile.key == "authentication_engineer"
                and bool(required.intersection({"authentication_review", "authorization_review", "authentication_integration"}))
            ) or (
                profile.key == "data_engineer"
                and "retrieval_architecture" in required
                and bool(required.intersection({"data_architecture", "query_optimization", "relational_modeling"}))
            )
            needs_independent_review = any(
                capability.independent_review_required
                for capability in self.catalog.capabilities.values()
                if capability.key in required and capability.key in profile.capability_keys
            )
            if new_coverage or requires_named_owner or (force_reviewers and needs_independent_review):
                selected_profiles.append(profile)
                covered.update(profile.covers(required))
        gaps = sorted(required - covered)
        assignments = [self._assignment(profile, required) for profile in selected_profiles]
        lead = assignments[0]
        specialists = assignments[1:]
        reviewer_independence = 1.0 if self._has_independent_review(assignments) else 0.2
        coverage = len(covered) / max(1, len(required))
        estimated_cost = min(1.0, len(assignments) * 0.08 + (0.1 if force_reviewers else 0))
        return CandidateOrganizationStructure(
            name=name,
            mission_lead=lead,
            specialists=specialists,
            review_councils=[{"name": "Security and QA Review", "members": [item.profile_key for item in assignments if "review" in item.profile_key or "qa" in item.profile_key or "security" in item.profile_key]}],
            reporting_lines=[{"from": item.profile_key, "to": lead.profile_key} for item in specialists],
            communication_channels=["mission-leadership", "architecture", "implementation", "security", "quality", "approvals"],
            authority_assignments=[{"profile": item.profile_key, "authority": item.authority} for item in assignments],
            budget_allocations=[{"profile": item.profile_key, "estimated_cost": item.estimated_cost} for item in assignments],
            coverage_score=round(coverage, 4),
            reviewer_independence=reviewer_independence,
            expected_quality=round(sum(profile.historical_effectiveness for profile in selected_profiles) / max(1, len(selected_profiles)), 4),
            historical_effectiveness=round(sum(profile.historical_effectiveness for profile in selected_profiles) / max(1, len(selected_profiles)), 4),
            parallelization_value=clamp_score(len(assignments) / 10),
            estimated_cost=estimated_cost,
            communication_overhead=clamp_score(max(0, len(assignments) - 5) * 0.05),
            responsibility_overlap=0.05 if len(selected_profiles) == len({profile.key for profile in selected_profiles}) else 0.3,
            coordination_risk=clamp_score(len(assignments) * 0.03),
            known_gaps=gaps if estimated_cost <= mission_budget else [*gaps, "mission_budget_exceeded"],
        )

    def _assignment(self, profile: SpecialistProfileDefinition, required: set[str]) -> OrganizationSpecialistAssignment:
        covered = sorted(profile.covers(required))
        return OrganizationSpecialistAssignment(
            profile_key=profile.key,
            display_name=profile.display_name,
            capability_keys=covered,
            responsibilities=profile.default_responsibilities,
            tools=profile.default_tools,
            model_policy=profile.model_requirements,
            authority=profile.default_authority,
            reviewers=[key for key in profile.review_incompatibilities],
            rationale=[f"Covers {', '.join(covered) if covered else 'mission leadership and coordination'}"],
            estimated_cost=round(0.08 + (0.02 * len(covered)), 4),
        )

    def _has_independent_review(self, assignments: list[OrganizationSpecialistAssignment]) -> bool:
        keys = {assignment.profile_key for assignment in assignments}
        implementers = {
            "authentication_engineer",
            "backend_engineer",
            "data_engineer",
            "database_engineer",
            "devops_engineer",
            "frontend_engineer",
            "payments_engineer",
        }
        reviewers = {"accessibility_reviewer", "evaluation_engineer", "qa_engineer", "security_reviewer"}
        return bool(keys.intersection(implementers)) and bool(keys.intersection(reviewers))


@dataclass(slots=True)
class OrganizationChange:
    organization_id: str
    change_type: Literal[
        "ADD_SPECIALIST",
        "REMOVE_SPECIALIST",
        "REPLACE_SPECIALIST",
        "MERGE_ROLES",
        "SPLIT_ROLE",
        "CREATE_TEAM",
        "DISSOLVE_TEAM",
        "CHANGE_REPORTING_LINE",
        "REALLOCATE_BUDGET",
        "CHANGE_MODEL_POLICY",
        "CHANGE_TOOL_PERMISSION",
        "ADD_REVIEW_COUNCIL",
        "REASSIGN_TASK",
    ]
    reason: str
    evidence: list[str]
    expected_effect: str
    cost_impact: float
    risk_impact: RiskLevel
    affected_tasks: list[str]
    rollback_plan: list[str]
    approval_required: bool = False
    approved: bool = False
    change_id: str = field(default_factory=new_id)

    def __post_init__(self) -> None:
        high_impact = self.change_type in {"REMOVE_SPECIALIST", "REPLACE_SPECIALIST", "CHANGE_MODEL_POLICY", "CHANGE_TOOL_PERMISSION", "REALLOCATE_BUDGET"} or self.risk_impact in {"high", "critical"}
        self.approval_required = self.approval_required or high_impact

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "organization_id": self.organization_id,
            "change_type": self.change_type,
            "reason": self.reason,
            "evidence": self.evidence,
            "expected_effect": self.expected_effect,
            "cost_impact": self.cost_impact,
            "risk_impact": self.risk_impact,
            "affected_tasks": self.affected_tasks,
            "approval_required": self.approval_required,
            "approved": self.approved,
            "rollback_plan": self.rollback_plan,
        }


@dataclass(slots=True)
class Handoff:
    task_id: str
    from_agent_id: str
    to_agent_id: str
    summary: str
    completed_work: list[str]
    remaining_work: list[str]
    decisions: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    known_risks: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)
    required_next_actions: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    handoff_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class ProjectKnowledge:
    tenant_id: str
    project_id: str
    knowledge_type: KnowledgeType
    title: str
    content: dict[str, Any]
    source_type: Literal["human", "agent", "tool", "document", "repository", "external"]
    source_id: str
    created_by: str
    mission_id: str | None = None
    confidence: float = 0.5
    trust_level: KnowledgeTrust = "unverified"
    scope: MemoryScope = "project"
    applicability: dict[str, Any] = field(default_factory=dict)
    freshness_policy: dict[str, Any] = field(default_factory=dict)
    sensitivity: Sensitivity = "internal"
    status: KnowledgeStatus = "proposed"
    supersedes_id: str | None = None
    valid_from: str = field(default_factory=utc_now)
    valid_until: str | None = None
    knowledge_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    @property
    def active_and_trusted(self) -> bool:
        return self.status == "active" and TRUST_ORDER[self.trust_level] >= TRUST_ORDER["human_approved"]

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_id": self.knowledge_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "mission_id": self.mission_id,
            "knowledge_type": self.knowledge_type,
            "title": self.title,
            "content": self.content,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "created_by": self.created_by,
            "confidence": self.confidence,
            "trust_level": self.trust_level,
            "scope": self.scope,
            "applicability": self.applicability,
            "freshness_policy": self.freshness_policy,
            "sensitivity": self.sensitivity,
            "status": self.status,
            "supersedes_id": self.supersedes_id,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "created_at": self.created_at,
        }


class ProjectMemoryStore:
    def __init__(self) -> None:
        self.items: dict[str, ProjectKnowledge] = {}

    def promote(self, item: ProjectKnowledge) -> ProjectKnowledge:
        if TRUST_ORDER[item.trust_level] < TRUST_ORDER["human_approved"]:
            raise ValueError("Only human-approved or environment-observed knowledge can become active project memory.")
        item.status = "active"
        self.items[item.knowledge_id] = item
        return item

    def supersede(self, previous_id: str, replacement: ProjectKnowledge) -> ProjectKnowledge:
        previous = self.items[previous_id]
        previous.status = "superseded"
        replacement.supersedes_id = previous_id
        return self.promote(replacement)

    def retrieve(
        self,
        *,
        tenant_id: str,
        project_id: str,
        objective: str,
        include_uncertain: bool = False,
        sensitivity_allowed: set[Sensitivity] | None = None,
    ) -> list[ProjectKnowledge]:
        sensitivity_allowed = sensitivity_allowed or {"public", "internal"}
        objective_terms = {term.lower() for term in objective.split()}
        results = []
        for item in self.items.values():
            if item.tenant_id != tenant_id or item.project_id != project_id:
                continue
            if item.sensitivity not in sensitivity_allowed:
                continue
            if item.status == "superseded":
                continue
            if item.status != "active" and not include_uncertain:
                continue
            haystack = " ".join([item.title, str(item.content), *item.applicability.get("components", [])]).lower()
            if objective_terms.intersection(haystack.split()) or not objective_terms:
                results.append(item)
        return sorted(results, key=lambda item: (item.active_and_trusted, item.confidence), reverse=True)


@dataclass(slots=True)
class Lesson:
    project_id: str
    mission_id: str
    title: str
    situation: dict[str, Any]
    action_taken: dict[str, Any]
    result: dict[str, Any]
    what_worked: list[str]
    what_failed: list[str]
    root_causes: list[str]
    applicability_conditions: list[str]
    anti_applicability_conditions: list[str]
    supporting_evidence: list[str]
    confidence: float
    review_status: Literal["unverified", "reviewed", "approved"] = "unverified"
    reuse_count: int = 0
    successful_reuse_count: int = 0
    status: Literal["experimental", "active", "deprecated"] = "experimental"
    lesson_id: str = field(default_factory=new_id)

    def applies_to(self, objective: str) -> bool:
        lowered = objective.lower()
        if any(condition.lower() in lowered for condition in self.anti_applicability_conditions):
            return False
        return any(condition.lower() in lowered for condition in self.applicability_conditions)


@dataclass(slots=True)
class PerformanceRecord:
    subject_type: Literal["specialist_profile", "agent_instance", "model", "tool", "organization"]
    subject_key: str
    task_type: str
    success: bool
    evidence_quality: float = 0.5
    cost: float = 0.0
    latency_ms: int = 0
    rework_required: bool = False
    validation_passed: bool = True
    record_id: str = field(default_factory=new_id)

    @property
    def score(self) -> float:
        return round(clamp_score((0.35 if self.success else 0) + (self.evidence_quality * 0.25) + (0.2 if self.validation_passed else 0) + (0.1 if not self.rework_required else 0) + max(0, 0.1 - self.cost)), 4)


class PerformanceLedger:
    def __init__(self) -> None:
        self.records: list[PerformanceRecord] = []

    def record(self, record: PerformanceRecord) -> PerformanceRecord:
        self.records.append(record)
        return record

    def aggregate(self, subject_type: str, subject_key: str) -> dict[str, Any]:
        selected = [record for record in self.records if record.subject_type == subject_type and record.subject_key == subject_key]
        if not selected:
            return {"subject_type": subject_type, "subject_key": subject_key, "count": 0, "score": 0.0}
        return {
            "subject_type": subject_type,
            "subject_key": subject_key,
            "count": len(selected),
            "score": round(sum(record.score for record in selected) / len(selected), 4),
            "success_rate": round(sum(1 for record in selected if record.success) / len(selected), 4),
            "average_latency_ms": round(sum(record.latency_ms for record in selected) / len(selected), 2),
            "total_cost": round(sum(record.cost for record in selected), 4),
        }


def initial_generation2_capability_catalog() -> CapabilityCatalog:
    def cap(
        key: str,
        name: str,
        category: str,
        domains: list[str],
        verification_methods: list[str],
        *,
        risk_level: RiskLevel = "medium",
        independent_review_required: bool = False,
        description: str | None = None,
    ) -> CapabilityDefinition:
        return CapabilityDefinition(
            key,
            name,
            description or f"Perform {name.lower()} with explicit evidence and reviewable outputs.",
            category,
            domains,
            verification_methods=verification_methods,
            risk_level=risk_level,
            independent_review_required=independent_review_required,
        )

    capabilities = [
        # Product
        cap("requirement_analysis", "Requirement Analysis", "product", ["software_engineering", "product"], ["requirements_review"], risk_level="low"),
        cap("user_story_design", "User Story Design", "product", ["software_engineering", "product"], ["product_review"], risk_level="low"),
        cap("acceptance_criteria_definition", "Acceptance Criteria Definition", "product", ["software_engineering", "product"], ["acceptance_review"], risk_level="low"),
        cap("product_risk_analysis", "Product Risk Analysis", "product", ["software_engineering", "product"], ["risk_review"], risk_level="medium", independent_review_required=True),
        cap("roadmap_planning", "Roadmap Planning", "product", ["software_engineering", "product"], ["roadmap_review"], risk_level="medium"),
        # Architecture
        cap("system_architecture", "System Architecture", "architecture", ["software_engineering", "architecture"], ["architecture_review"], risk_level="medium", independent_review_required=True),
        cap("api_architecture", "API Architecture", "architecture", ["software_engineering", "architecture", "backend"], ["api_contract_review"], risk_level="medium"),
        cap("data_architecture", "Data Architecture", "architecture", ["software_engineering", "architecture", "data_engineering"], ["data_model_review"], risk_level="medium"),
        cap("integration_architecture", "Integration Architecture", "architecture", ["software_engineering", "architecture"], ["integration_review"], risk_level="medium"),
        cap("architecture_tradeoff_analysis", "Architecture Tradeoff Analysis", "architecture", ["software_engineering", "architecture"], ["tradeoff_review"], risk_level="medium"),
        # Frontend
        cap("react_development", "React Development", "frontend", ["software_engineering", "frontend"], ["component_test"], risk_level="medium"),
        cap("nextjs_development", "Next.js Development", "frontend", ["software_engineering", "frontend"], ["build_verification"], risk_level="medium"),
        cap("responsive_ui", "Responsive UI", "frontend", ["software_engineering", "frontend"], ["viewport_review"], risk_level="low"),
        cap("accessibility_review", "Accessibility Review", "frontend", ["software_engineering", "frontend", "accessibility"], ["accessibility_audit"], risk_level="low", independent_review_required=True),
        cap("frontend_testing", "Frontend Testing", "frontend", ["software_engineering", "frontend", "quality"], ["frontend_test_run"], risk_level="low", independent_review_required=True),
        cap("frontend_performance", "Frontend Performance", "frontend", ["software_engineering", "frontend"], ["performance_budget_check"], risk_level="medium"),
        # Backend
        cap("python_backend_development", "Python Backend Development", "backend", ["software_engineering", "backend"], ["unit_test"], risk_level="medium"),
        cap("fastapi_development", "FastAPI Development", "backend", ["software_engineering", "backend"], ["route_smoke_test"], risk_level="medium"),
        cap("api_design", "API Design", "backend", ["software_engineering", "backend"], ["api_contract_review"], risk_level="medium"),
        cap("background_job_design", "Background Job Design", "backend", ["software_engineering", "backend", "operations"], ["job_replay_test"], risk_level="medium"),
        cap("caching_strategy", "Caching Strategy", "backend", ["software_engineering", "backend", "operations"], ["cache_invalidation_review"], risk_level="medium"),
        cap("websocket_architecture", "WebSocket Architecture", "backend", ["software_engineering", "backend"], ["connection_lifecycle_test"], risk_level="medium"),
        # Database
        cap("relational_modeling", "Relational Modeling", "database", ["software_engineering", "database"], ["schema_review"], risk_level="medium"),
        cap("postgresql_design", "PostgreSQL Design", "database", ["software_engineering", "database"], ["query_plan_review"], risk_level="medium"),
        cap("database_migration", "Database Migration", "database", ["software_engineering", "database"], ["migration_test"], risk_level="high", independent_review_required=True),
        cap("query_optimization", "Query Optimization", "database", ["software_engineering", "database"], ["query_benchmark"], risk_level="medium"),
        cap("tenant_isolation", "Tenant Isolation", "database", ["software_engineering", "database", "security"], ["tenant_isolation_test"], risk_level="high", independent_review_required=True),
        cap("backup_and_recovery", "Backup and Recovery", "database", ["software_engineering", "database", "operations"], ["restore_drill"], risk_level="high", independent_review_required=True),
        # Security
        cap("threat_modeling", "Threat Modeling", "security", ["software_engineering", "security"], ["threat_model_review"], risk_level="high", independent_review_required=True),
        cap("authentication_review", "Authentication Review", "security", ["software_engineering", "security"], ["auth_flow_test"], risk_level="high", independent_review_required=True),
        cap("authorization_review", "Authorization Review", "security", ["software_engineering", "security"], ["permission_matrix_review"], risk_level="high", independent_review_required=True),
        cap("secrets_review", "Secrets Review", "security", ["software_engineering", "security"], ["secret_scan"], risk_level="high", independent_review_required=True),
        cap("dependency_security", "Dependency Security", "security", ["software_engineering", "security"], ["dependency_scan"], risk_level="medium", independent_review_required=True),
        cap("input_validation_review", "Input Validation Review", "security", ["software_engineering", "security"], ["negative_input_test"], risk_level="high", independent_review_required=True),
        cap("secure_code_review", "Secure Code Review", "security", ["software_engineering", "security"], ["secure_code_review"], risk_level="high", independent_review_required=True),
        # AI
        cap("model_integration", "Model Integration", "ai", ["software_engineering", "ai_development"], ["provider_smoke_test"], risk_level="medium"),
        cap("model_routing", "Model Routing", "ai", ["software_engineering", "ai_development"], ["routing_eval"], risk_level="medium"),
        cap("structured_output_design", "Structured Output Design", "ai", ["software_engineering", "ai_development"], ["schema_validation"], risk_level="medium"),
        cap("retrieval_architecture", "Retrieval Architecture", "ai", ["software_engineering", "ai_development", "data_engineering"], ["retrieval_eval"], risk_level="high", independent_review_required=True),
        cap("agent_orchestration", "Agent Orchestration", "ai", ["software_engineering", "ai_development"], ["workflow_replay"], risk_level="high", independent_review_required=True),
        cap("evaluation_pipeline", "Evaluation Pipeline", "ai", ["software_engineering", "ai_development", "quality"], ["eval_run"], risk_level="medium", independent_review_required=True),
        cap("prompt_injection_defense", "Prompt Injection Defense", "ai", ["software_engineering", "ai_development", "security"], ["prompt_injection_test"], risk_level="high", independent_review_required=True),
        # Quality
        cap("unit_test_design", "Unit Test Design", "quality", ["software_engineering", "quality"], ["unit_test"], risk_level="low", independent_review_required=True),
        cap("integration_testing", "Integration Testing", "quality", ["software_engineering", "quality"], ["integration_test"], risk_level="medium", independent_review_required=True),
        cap("end_to_end_testing", "End-to-End Testing", "quality", ["software_engineering", "quality"], ["e2e_test"], risk_level="medium", independent_review_required=True),
        cap("regression_testing", "Regression Testing", "quality", ["software_engineering", "quality"], ["regression_test"], risk_level="medium", independent_review_required=True),
        cap("build_verification", "Build Verification", "quality", ["software_engineering", "quality"], ["build_run"], risk_level="low", independent_review_required=True),
        cap("evidence_validation", "Evidence Validation", "quality", ["software_engineering", "quality"], ["evidence_review"], risk_level="low", independent_review_required=True),
        # Operations
        cap("docker_configuration", "Docker Configuration", "operations", ["software_engineering", "cloud_infrastructure"], ["container_smoke_test"], risk_level="medium"),
        cap("ci_cd_design", "CI/CD Design", "operations", ["software_engineering", "cloud_infrastructure"], ["pipeline_dry_run"], risk_level="medium"),
        cap("cloud_deployment", "Cloud Deployment", "operations", ["software_engineering", "cloud_infrastructure"], ["deployment_smoke_test"], risk_level="high", independent_review_required=True),
        cap("observability", "Observability", "operations", ["software_engineering", "cloud_infrastructure"], ["runtime_health_check"], risk_level="medium"),
        cap("incident_response", "Incident Response", "operations", ["software_engineering", "cloud_infrastructure"], ["runbook_review"], risk_level="medium"),
        cap("release_management", "Release Management", "operations", ["software_engineering", "cloud_infrastructure"], ["release_gate"], risk_level="high", independent_review_required=True),
        cap("rollback_design", "Rollback Design", "operations", ["software_engineering", "cloud_infrastructure"], ["rollback_drill"], risk_level="high", independent_review_required=True),
        # Payments
        cap("payment_gateway_integration", "Payment Gateway Integration", "payments", ["software_engineering", "payments", "fintech"], ["payment_sandbox_test"], risk_level="high", independent_review_required=True),
        cap("subscription_billing", "Subscription Billing", "payments", ["software_engineering", "payments", "fintech"], ["billing_integration_test"], risk_level="high", independent_review_required=True),
        cap("webhook_reliability", "Webhook Reliability", "payments", ["software_engineering", "payments"], ["webhook_replay_test"], risk_level="medium"),
        cap("payment_security", "Payment Security", "payments", ["software_engineering", "payments", "security"], ["security_review"], risk_level="high", independent_review_required=True),
        cap("reconciliation", "Reconciliation", "payments", ["software_engineering", "payments", "fintech"], ["ledger_reconciliation_test"], risk_level="high", independent_review_required=True),
        cap("refund_workflows", "Refund Workflows", "payments", ["software_engineering", "payments"], ["refund_sandbox_test"], risk_level="medium", independent_review_required=True),
        # Compatibility aliases for existing missions and persisted plans.
        cap("product_requirement_analysis", "Product Requirement Analysis", "product", ["software_engineering", "product"], ["requirements_review"], risk_level="low"),
        cap("payment_architecture", "Payment Architecture", "payments", ["software_engineering", "payments", "fintech"], ["architecture_review"], risk_level="high", independent_review_required=True),
        cap("backend_api_design", "Backend API Design", "backend", ["software_engineering", "backend"], ["api_contract_review"], risk_level="medium"),
        cap("relational_data_modeling", "Relational Data Modeling", "database", ["software_engineering", "database"], ["migration_test"], risk_level="medium"),
        cap("authentication_integration", "Authentication Integration", "security", ["software_engineering", "security"], ["auth_flow_test"], risk_level="high", independent_review_required=True),
        cap("payment_security_review", "Payment Security Review", "security", ["software_engineering", "payments", "security"], ["security_review"], risk_level="high", independent_review_required=True),
        cap("automated_testing", "Automated Testing", "quality", ["software_engineering", "quality"], ["test_run"], risk_level="low", independent_review_required=True),
        cap("deployment_configuration", "Deployment Configuration", "operations", ["software_engineering", "cloud_infrastructure"], ["smoke_test"], risk_level="medium"),
        cap("ai_system_design", "AI System Design", "ai", ["software_engineering", "ai_development"], ["structured_output_validation"], risk_level="medium"),
        cap("model_evaluation", "Model Evaluation", "ai", ["software_engineering", "ai_development"], ["benchmark"], risk_level="low"),
    ]
    return CapabilityCatalog(capabilities)


def initial_generation2_profile_library() -> SpecialistProfileLibrary:
    profiles = [
        SpecialistProfileDefinition("mission_lead", "Mission Lead", "Coordinates mission execution and decisions.", "software_engineering", ["requirement_analysis", "product_requirement_analysis"], ["Own mission coordination", "Escalate decisions", "Maintain capability map"], default_authority={"can_propose": True, "can_execute": False, "can_approve": False}, historical_effectiveness=0.82),
        SpecialistProfileDefinition("product_analyst", "Product Analyst", "Analyzes users, requirements, risks, and acceptance criteria.", "product", ["user_story_design", "acceptance_criteria_definition", "product_risk_analysis", "roadmap_planning"], ["Extract requirements", "Identify unknowns", "Define acceptance criteria"], historical_effectiveness=0.84),
        SpecialistProfileDefinition("solution_architect", "Solution Architect", "Owns system, API, data, integration, and tradeoff architecture.", "architecture", ["system_architecture", "api_architecture", "data_architecture", "integration_architecture", "architecture_tradeoff_analysis", "payment_architecture"], ["Select architecture", "Document tradeoffs", "Coordinate implementers"], default_tools=["file_reader", "architecture_renderer"], default_authority={"can_propose": True, "can_execute": False, "can_approve": False}, historical_effectiveness=0.87),
        SpecialistProfileDefinition("frontend_engineer", "Frontend Engineer", "Builds React and Next.js UI changes.", "frontend", ["react_development", "nextjs_development", "responsive_ui", "frontend_performance"], ["Implement UI", "Preserve responsive behavior"], default_tools=["file_reader", "scoped_file_writer", "build_runner"], review_incompatibilities=["accessibility_reviewer", "qa_engineer"], historical_effectiveness=0.86),
        SpecialistProfileDefinition("accessibility_reviewer", "Accessibility Reviewer", "Independently reviews accessibility and interaction states.", "frontend", ["accessibility_review"], ["Audit keyboard and screen-reader behavior", "Block inaccessible UX"], default_tools=["accessibility_checker"], default_authority={"can_review": True, "can_block": True, "can_execute": False, "can_approve": False}, historical_effectiveness=0.88),
        SpecialistProfileDefinition("payments_engineer", "Payments Engineer", "Designs and implements secure payment integrations.", "payments", ["payment_gateway_integration", "subscription_billing", "webhook_reliability", "reconciliation", "refund_workflows", "payment_architecture"], ["Design payment flow", "Implement webhook plan", "Validate financial edge cases"], default_tools=["file_reader", "scoped_file_writer"], review_incompatibilities=["security_reviewer", "qa_engineer"], risk_ceiling="high", historical_effectiveness=0.86),
        SpecialistProfileDefinition("authentication_engineer", "Authentication Engineer", "Designs and implements authentication and authorization flows.", "security", ["authentication_review", "authorization_review", "authentication_integration"], ["Implement auth flow", "Define permission boundaries"], default_tools=["file_reader", "scoped_file_writer", "test_runner"], review_incompatibilities=["security_reviewer", "qa_engineer"], risk_ceiling="high", historical_effectiveness=0.85),
        SpecialistProfileDefinition("backend_engineer", "Backend Engineer", "Builds backend APIs, jobs, caching, and WebSocket surfaces.", "backend", ["python_backend_development", "fastapi_development", "api_design", "background_job_design", "caching_strategy", "websocket_architecture", "backend_api_design"], ["Implement backend API", "Connect background workflows", "Protect contracts"], default_tools=["file_reader", "scoped_file_writer", "test_runner"], review_incompatibilities=["security_reviewer", "qa_engineer"], risk_ceiling="high", historical_effectiveness=0.85),
        SpecialistProfileDefinition("database_engineer", "Database Engineer", "Designs relational storage, migrations, tenancy, and recovery.", "database", ["relational_modeling", "postgresql_design", "database_migration", "query_optimization", "tenant_isolation", "backup_and_recovery", "relational_data_modeling"], ["Design schema", "Validate migrations", "Prove tenant isolation"], default_tools=["file_reader", "static_analyzer"], review_incompatibilities=["security_reviewer", "qa_engineer"], historical_effectiveness=0.8),
        SpecialistProfileDefinition("data_engineer", "Data Engineer", "Builds retrieval data flows and durable knowledge storage.", "data_engineering", ["data_architecture", "query_optimization"], ["Model retrieval data", "Validate query performance"], default_tools=["file_reader", "static_analyzer"], review_incompatibilities=["security_reviewer", "evaluation_engineer", "qa_engineer"], historical_effectiveness=0.81),
        SpecialistProfileDefinition("security_reviewer", "Security Reviewer", "Independently reviews security-sensitive changes.", "security", ["threat_modeling", "authentication_review", "authorization_review", "secrets_review", "dependency_security", "input_validation_review", "secure_code_review", "prompt_injection_defense", "payment_security", "payment_security_review", "authentication_integration"], ["Review security", "Block unsafe changes", "Validate secrets and policy boundaries"], default_authority={"can_review": True, "can_block": True, "can_execute": False, "can_approve": False}, historical_effectiveness=0.9),
        SpecialistProfileDefinition("qa_engineer", "QA Engineer", "Defines and validates deterministic evidence.", "quality", ["unit_test_design", "integration_testing", "end_to_end_testing", "regression_testing", "build_verification", "evidence_validation", "frontend_testing", "automated_testing"], ["Run tests", "Validate evidence", "Prevent completion on failed checks"], default_tools=["test_runner", "build_runner"], default_authority={"can_review": True, "can_execute": True, "can_approve": False}, historical_effectiveness=0.88),
        SpecialistProfileDefinition("devops_engineer", "DevOps Engineer", "Validates deployment, release, observability, and rollback paths.", "cloud_infrastructure", ["docker_configuration", "ci_cd_design", "cloud_deployment", "observability", "incident_response", "release_management", "rollback_design", "deployment_configuration"], ["Validate environment", "Check smoke tests", "Maintain rollback readiness"], default_tools=["build_runner", "artifact_uploader"], risk_ceiling="medium", historical_effectiveness=0.82),
        SpecialistProfileDefinition("ai_architect", "AI Architect", "Designs model routing, retrieval, structured outputs, and agent orchestration.", "ai_development", ["model_integration", "model_routing", "structured_output_design", "retrieval_architecture", "agent_orchestration", "ai_system_design"], ["Design AI architecture", "Control model/tool boundaries", "Plan retrieval quality"], default_tools=["model_router"], review_incompatibilities=["security_reviewer", "evaluation_engineer", "qa_engineer"], historical_effectiveness=0.84),
        SpecialistProfileDefinition("evaluation_engineer", "Evaluation Engineer", "Independently validates model, retrieval, and agent quality.", "ai_development", ["evaluation_pipeline", "model_evaluation", "evidence_validation"], ["Run model evals", "Validate retrieval evidence", "Track quality regressions"], default_tools=["model_router", "test_runner"], default_authority={"can_review": True, "can_block": True, "can_execute": True, "can_approve": False}, historical_effectiveness=0.86),
    ]
    return SpecialistProfileLibrary(profiles)


def generation2_manifest() -> dict[str, Any]:
    return {
        "name": "Arceus Generation 2 Dynamic Organization Runtime",
        "objective": "Create capability-driven persistent engineering organizations with project memory and measurable performance.",
        "vertical_slice": "Add secure subscription billing to an existing application.",
        "preferred_organization_type": "HYBRID",
        "core_modules": [
            "capability_catalog",
            "specialist_profile_library",
            "dynamic_organization_builder",
            "organization_lifecycle",
            "project_memory",
            "lessons",
            "performance_ledger",
            "organization_health",
        ],
    }
