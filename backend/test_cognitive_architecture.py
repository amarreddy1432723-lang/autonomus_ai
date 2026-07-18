from services.agent.cognitive_architecture import (
    IntelligenceGraphNode,
    UniversalIntelligenceGraph,
    cognitive_architecture_manifest,
    collect_research,
    evaluate_organization_health,
    generate_strategy_options,
    run_cognitive_pass,
    simulate_strategy,
    understand_objective,
)


def test_understanding_detects_domains_constraints_and_risks():
    assessment = understand_objective(
        "Build a production desktop AI platform with OAuth security, Stripe billing, and deployment monitoring",
        {"target_users": ["developers"], "success_criteria": ["User can launch the desktop workflow"]},
    )

    assert assessment.ready_for_strategy is True
    assert "software_engineering" in assessment.domains
    assert "security" in assessment.domains
    assert "finance" in assessment.domains
    assert "cloud_infrastructure" in assessment.domains
    assert "Must work as a desktop application." in assessment.constraints
    assert assessment.risks


def test_short_objective_stays_low_confidence_with_unknowns():
    assessment = understand_objective("build app")

    assert assessment.confidence_band == "low"
    assert assessment.ready_for_strategy is False
    assert "Objective is too short to infer full scope." in assessment.unknowns
    assert "Target users are not explicitly defined." in assessment.unknowns


def test_research_collects_security_and_production_findings():
    assessment = understand_objective(
        "Deploy production app with OAuth security",
        {"target_users": ["admins"], "success_criteria": ["Ready endpoint passes"]},
    )
    findings = collect_research(assessment)
    topics = {finding.topic for finding in findings}

    assert "Existing organizational memory" in topics
    assert "Security posture" in topics
    assert "Production operations" in topics
    assert all(finding.confidence > 0.7 for finding in findings)


def test_strategy_generation_selects_highest_scoring_option_in_full_pass():
    result = run_cognitive_pass(
        "Implement Arceus cognitive architecture with research, simulation, debate, decision intelligence, and learning",
        {"target_users": ["founder"], "success_criteria": ["Cognitive pass is inspectable and tested"]},
    )

    strategies = result["strategies"]
    decision = result["decision"]
    selected = next(strategy for strategy in strategies if strategy["strategy_id"] == decision["selected_strategy_id"])

    assert len(strategies) == 3
    assert selected["score"] == max(strategy["score"] for strategy in strategies)
    assert decision["verdict"] == "recommended"
    assert result["reflection"]["reusable_lessons"]


def test_simulation_pressure_tests_core_failure_modes():
    assessment = understand_objective(
        "Build secure production AI deployment workflow",
        {"target_users": ["developers"], "success_criteria": ["Deploy gate passes"]},
    )
    strategy = generate_strategy_options(assessment, collect_research(assessment))[0]
    scenarios = {simulation.scenario for simulation in simulate_strategy(strategy)}

    assert {
        "normal_conditions",
        "peak_traffic",
        "network_failure",
        "security_attack",
        "database_failure",
        "rollback",
        "unexpected_user_behavior",
    }.issubset(scenarios)


def test_debate_preserves_minority_opinion_for_high_risk_strategy():
    result = run_cognitive_pass(
        "Run broad autonomous execution for security-sensitive production infrastructure",
        {"target_users": ["operators"], "success_criteria": ["High throughput"]},
    )

    assert any(
        position["minority_opinion"]
        for debate in result["debates"]
        for position in debate["positions"]
    )


def test_organization_health_reports_bottlenecks_and_recommendations():
    health = evaluate_organization_health(
        {
            "mission_health": 0.6,
            "agent_health": 0.55,
            "task_health": 0.5,
            "risk_health": 0.45,
        },
        bottlenecks=["Review council overloaded"],
    )

    assert health.status in {"at_risk", "blocked"}
    assert "Review council overloaded" in health.bottlenecks
    assert any("organizational review" in item for item in health.recommendations)


def test_universal_intelligence_graph_links_nodes_and_related_context():
    graph = UniversalIntelligenceGraph()
    mission = graph.add_node(IntelligenceGraphNode("mission", "Build Arceus", "Build the engineering OS"))
    decision = graph.add_node(IntelligenceGraphNode("decision", "Use cognitive architecture", "Understand before executing"))
    graph.connect(decision, mission, "supports", ["Decision intelligence"])

    related = graph.related_to(mission.node_id)

    assert related[0]["node"]["title"] == "Use cognitive architecture"
    assert related[0]["edge"]["relationship"] == "supports"


def test_manifest_exposes_generation_two_stages():
    manifest = cognitive_architecture_manifest()

    assert manifest["generation"] == 2
    assert "cognitive_engine" in manifest["stages"]
    assert "universal_intelligence_graph" in manifest["stages"]
    assert "future_readiness" in manifest["organizational_health_dimensions"]
