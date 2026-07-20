from services.agent.arceus_runtime.strategy.service import (
    build_key_results,
    calculate_enterprise_health,
    evaluate_executive_decision,
    objective_governance,
    score_portfolio_items,
    simulate_strategy,
)


def test_enterprise_health_scores_all_board_dimensions_and_surfaces_risks():
    result = calculate_enterprise_health(
        {
            "revenue_growth": 0.88,
            "availability": 0.99,
            "test_pass_rate": 0.93,
            "satisfaction": 0.6,
            "security_score": 0.54,
        },
        {"task_statuses": {"failed": 1, "blocked": 2}, "approval_statuses": {"pending": 1}, "stale_processing_outbox": 0},
    )

    assert result["status"] in {"watch", "at_risk"}
    assert set(result["health_dimensions"]) == {"financial", "operational", "engineering", "customer", "security"}
    assert any(risk["risk_key"] == "security_health_low" for risk in result["risks"])
    assert any("failed tasks" in item or "failed" in item for item in result["recommendations"])


def test_objective_compiles_outcomes_into_measurable_key_results_and_governance():
    key_results = build_key_results(
        title="Launch private beta",
        desired_outcomes=["Ten design partners complete onboarding"],
        kpis={"activation_rate": 0.7},
        horizon="quarter",
    )
    governance = objective_governance(priority=5, domain="security", evidence_ids=[])

    assert [item["key"] for item in key_results] == ["activation_rate", "outcome_1"]
    assert key_results[0]["verification"] == "metric_observation_required"
    assert "executive_sponsor" in governance
    assert "domain_risk_reviewer" in governance
    assert "evidence_required_before_execution" in governance


def test_portfolio_prioritizes_evidence_backed_work_and_exposes_blockers():
    portfolio = score_portfolio_items(
        [
            {"id": "a", "title": "Important objective", "priority": 5, "confidence": 0.8, "evidence_ids": ["ev"]},
            {"id": "b", "title": "Blocked objective", "priority": 5, "confidence": 0.8, "status": "blocked"},
        ],
        {"task_statuses": {"ready": 2, "running": 1, "blocked": 3, "reviewing": 1}},
    )

    assert portfolio["priority_queue"][0]["id"] == "a"
    assert portfolio["resource_allocation"]["blocked"] == 3
    assert portfolio["dependencies"][0]["dependency"] == "blocked_tasks"


def test_strategy_simulation_is_evidence_based_advisory_with_uncertainty():
    simulation = simulate_strategy(
        {
            "scenario_name": "Accelerate launch",
            "objective": "Ship MVP faster",
            "assumptions": {"team_capacity": 0.9, "market_demand": 0.8, "verification_depth": 0.7},
            "horizon_months": 4,
            "investment_delta": 10_000,
            "evidence_ids": ["ev1", "ev2"],
        }
    )

    assert simulation["advisory"].startswith("Strategy simulations support decisions")
    assert simulation["confidence"] >= 0.7
    assert "uncertainty" in simulation
    assert simulation["expected_impacts"]["business_value"] > 0.7


def test_executive_decisions_preserve_human_accountability():
    critical = evaluate_executive_decision(
        decision_type="production_deployment",
        expected_impact="critical",
        evidence_ids=[],
        reversible=False,
    )
    low_risk = evaluate_executive_decision(
        decision_type="copy_change",
        expected_impact="low",
        evidence_ids=["evidence"],
        reversible=True,
    )

    assert critical["status"] == "review_required"
    assert "board_or_owner_approval" in critical["required_approvals"]
    assert "supporting_evidence_required" in critical["required_approvals"]
    assert low_risk["status"] == "recorded"
