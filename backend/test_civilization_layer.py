import pytest

from services.agent.civilization_layer import (
    CapabilityOffer,
    CivilizationOrganization,
    GovernancePolicy,
    OrganizationDNA,
    TrustedKnowledge,
    civilization_manifest,
    create_engineering_civilization_seed,
)


def test_civilization_seed_contains_engineering_and_research_organizations():
    civ = create_engineering_civilization_seed()

    names = {organization.name for organization in civ.organizations.values()}

    assert "Engineering Organization" in names
    assert "Research Lab" in names
    assert len(civ.relationships) == 1
    assert civ.marketplace.find_best("software_engineering", ["security"]) is not None


def test_organization_dna_and_policy_gate_knowledge_sharing():
    civ = create_engineering_civilization_seed()
    engineering = next(org for org in civ.organizations.values() if org.name == "Engineering Organization")
    research = next(org for org in civ.organizations.values() if org.name == "Research Lab")

    unverified = civ.publish_knowledge(
        TrustedKnowledge(
            title="Unverified lesson",
            content="Maybe skip review for small changes",
            source="agent",
            owner_organization_id=engineering.organization_id,
            verification="unverified",
            confidence=0.4,
            risk=0.8,
        )
    )
    approved = civ.publish_knowledge(
        TrustedKnowledge(
            title="Approved lesson",
            content="Use idempotency before tool execution",
            source="mission",
            owner_organization_id=engineering.organization_id,
            verification="approved",
            confidence=0.92,
            evidence=["mission replay"],
            usage_count=5,
            popularity=0.7,
            risk=0.1,
        )
    )

    shared = civ.shareable_knowledge_for(research.organization_id)

    assert unverified not in shared
    assert approved in shared
    assert approved.trust_score > unverified.trust_score


def test_governance_policy_requires_review_for_low_trust_knowledge():
    org = CivilizationOrganization(
        name="Legal Organization",
        kind="legal",
        dna=OrganizationDNA(
            mission="Review compliance",
            knowledge_domains=["law"],
            policies=["approved_only"],
            capabilities=["policy_review"],
            experts=["Legal Reviewer"],
            learning_loops=["case_review"],
            performance_metrics=["risk_reduction"],
        ),
    )
    policy = GovernancePolicy("High Trust Only", "Low trust knowledge cannot be shared.", required_trust_score=0.8)
    knowledge = TrustedKnowledge(
        title="Weak claim",
        content="Untested legal pattern",
        source="external",
        owner_organization_id=org.organization_id,
        verification="unverified",
        confidence=0.4,
    )

    verdict, reason = policy.evaluate(knowledge, org)

    assert verdict == "requires_review"
    assert "below policy threshold" in reason


def test_capability_marketplace_schedules_best_value_offer():
    civ = create_engineering_civilization_seed()
    engineering = next(org for org in civ.organizations.values() if org.name == "Engineering Organization")
    civ.marketplace.publish(
        CapabilityOffer(
            engineering.organization_id,
            "Low Quality Security Review",
            "Cheap but unreliable security review",
            ["software_engineering", "security"],
            cost=0.05,
            latency=0.1,
            quality=0.2,
            reliability=0.2,
        )
    )

    scheduled = civ.schedule_best_capability("software_engineering", "security review")

    assert scheduled["scheduled"] is True
    assert scheduled["capability"]["name"] == "Security Review"


def test_universal_simulation_covers_civilization_dimensions():
    civ = create_engineering_civilization_seed()

    domains = {result.domain for result in civ.simulate("Build a civilization layer")}

    assert {"market", "architecture", "security", "scaling", "costs", "failures", "competition", "growth", "users"} == domains


def test_ai_university_only_teaches_from_trusted_knowledge():
    civ = create_engineering_civilization_seed()
    engineering = next(org for org in civ.organizations.values() if org.name == "Engineering Organization")
    weak = civ.publish_knowledge(
        TrustedKnowledge(
            title="Weak lesson",
            content="No evidence",
            source="agent",
            owner_organization_id=engineering.organization_id,
            verification="proposed",
            confidence=0.2,
        )
    )
    trusted = civ.publish_knowledge(
        TrustedKnowledge(
            title="Trusted lesson",
            content="Review and evidence are required",
            source="mission",
            owner_organization_id=engineering.organization_id,
            verification="approved",
            confidence=0.95,
            usage_count=10,
            evidence=["tests"],
            risk=0.1,
        )
    )

    with pytest.raises(ValueError):
        civ.teach_from_lesson(weak.knowledge_id)

    lesson = civ.teach_from_lesson(trusted.knowledge_id)

    assert lesson.source_knowledge_id == trusted.knowledge_id
    assert lesson.expected_capability_gain > 0


def test_self_evolution_proposal_uses_civilization_metrics():
    civ = create_engineering_civilization_seed()
    engineering = next(org for org in civ.organizations.values() if org.name == "Engineering Organization")
    proposal = civ.propose_evolution(engineering.organization_id, civ.metrics())

    assert proposal.target_organization_id == engineering.organization_id
    assert proposal.validation_plan
    assert proposal.rollback_plan


def test_global_intelligence_graph_links_knowledge_neighborhood():
    civ = create_engineering_civilization_seed()
    org = next(org for org in civ.organizations.values() if org.name == "Engineering Organization")
    knowledge = civ.publish_knowledge(
        TrustedKnowledge(
            title="Graph lesson",
            content="Idea to requirement to architecture to lesson stays connected",
            source="mission",
            owner_organization_id=org.organization_id,
            verification="approved",
            confidence=0.9,
        )
    )

    node = next(node for node in civ.graph.nodes if node.title == "Graph lesson")

    assert knowledge.trust_score > 0.7
    assert node.kind == "knowledge"


def test_civilization_manifest_exposes_generation_six_systems():
    manifest = civilization_manifest()

    assert manifest["generation"] == 6
    assert "global_intelligence_graph" in manifest["core_systems"]
    assert "ai_university" in manifest["core_systems"]
    assert "knowledge_growth" in manifest["metrics"]
