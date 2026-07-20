from services.agent.arceus_runtime.civilization.service import (
    build_state,
    constitution,
    detect_capability_gaps,
    evolve_civilization,
    metrics,
    propose_organization,
    simulate_civilization,
)


def test_constitution_preserves_human_authority_and_verification():
    result = constitution()

    assert "define_vision" in result["human_authority"]
    assert "capability_promotion_requires_evidence" in result["approval_rules"]
    assert "verify_before_promotion" in result["evolution_constraints"]


def test_capability_gap_detection_uses_required_capabilities_and_current_orgs():
    gaps = detect_capability_gaps(
        {
            "goal": "Launch secure production deployment automation",
            "required_capabilities": ["security_review", "cloud_operations"],
            "current_organizations": [{"capabilities": ["cloud_operations"]}],
        }
    )

    assert [gap["capability"] for gap in gaps] == ["security_review"]
    assert gaps[0]["severity"] == "high"


def test_organization_proposal_documents_specialists_and_governance():
    result = propose_organization(
        {
            "goal": "Create an AI evaluation organization for model routing",
            "domain": "artificial_intelligence",
            "required_capabilities": ["model_orchestration", "evaluation_pipeline"],
            "current_organizations": [],
            "budget_limit": 200,
        }
    )

    assert result["status"] == "needs_governance_review"
    assert result["proposed_organization"]["policy_controlled"] is True
    assert len(result["specialists"]) == 2
    assert result["governance_review"]["ai_approval_counts_as_human"] is False
    assert "ORGANIZATION_PROPOSED" in result["events"]


def test_organization_proposal_blocks_when_budget_is_too_low():
    result = propose_organization(
        {
            "goal": "Create a broad research organization",
            "required_capabilities": ["research_planning", "evidence_validation", "simulation_engineering"],
            "budget_limit": 1,
        }
    )

    assert result["status"] == "blocked_by_budget"


def test_simulation_blocks_constitutional_violations():
    result = simulate_civilization(
        {
            "scenario": "Expand federation but bypass approval and disable audit for speed",
            "evolution_type": "strategic_expansion",
            "affected_domains": ["finance"],
            "affected_organizations": ["engineering", "governance"],
        }
    )

    assert result["status"] == "blocked"
    assert result["risk_analysis"]["constitutional_risk"] is True
    assert "constitutional_violation" in result["risk_analysis"]["blocked_reasons"]


def test_evolution_requires_evidence_and_human_approval_for_strategy():
    result = evolve_civilization(
        {
            "objective": "Create a new healthcare AI organization",
            "evolution_type": "strategic_expansion",
            "target_state": "healthcare_ai_department",
            "evidence_ids": [],
        }
    )

    assert result["status"] == "blocked"
    assert "evidence_required" in result["blocked_reasons"]
    assert "human_approval_required" in result["blocked_reasons"]
    assert result["promotion_ready"] is False


def test_evolution_promotes_when_evidence_and_approval_are_present():
    result = evolve_civilization(
        {
            "objective": "Promote progressive migration rollout as platform standard",
            "evolution_type": "capability",
            "target_state": "platform_standard",
            "evidence_ids": ["ev1", "ev2", "ev3"],
            "human_approval_id": "approval_1",
        }
    )

    assert result["status"] == "ready_for_promotion"
    assert result["promotion_ready"] is True
    assert "CAPABILITY_PROMOTED" in result["events"]


def test_state_includes_proposed_organizations_and_events():
    proposal = propose_organization(
        {
            "goal": "Create security organization",
            "required_capabilities": ["security_review"],
        }
    )
    state = build_state(
        [
            {"content_type": "civilization_organization_proposal", "content": proposal},
            {"content_type": "civilization_evolution", "content": {"evolution_id": "evo1", "status": "blocked", "events": ["ECOSYSTEM_HEALTH_UPDATED"]}},
        ],
        "tenant-a",
    )

    assert state["status"] == "needs_governance_attention"
    assert any(org["organization_id"] == proposal["proposed_organization"]["organization_id"] for org in state["organizations"])
    assert "ECOSYSTEM_HEALTH_UPDATED" in state["latest_events"]


def test_metrics_aggregate_civilization_memory_signals():
    result = metrics(
        [
            {"content_type": "civilization_organization_proposal", "content": {"events": ["ORGANIZATION_PROPOSED"]}},
            {"content_type": "civilization_evolution", "content": {"events": ["CAPABILITY_PROMOTED"]}},
            {"content_type": "civilization_simulation", "content": {"events": ["CIVILIZATION_SIMULATED"]}},
            {"content_type": "civilization_research_signal", "content": {"events": ["RESEARCH_PROJECT_CREATED"]}},
        ]
    )

    assert result["knowledge_growth"] == 4
    assert result["innovation_rate"] > 0
    assert result["operational_resilience"] > 0.76
