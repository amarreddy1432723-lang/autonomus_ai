from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.services.agent.arceus_runtime.planning_intelligence.api_schemas import (
    PlanningBudget,
    PlanningConstraint,
    PlanningIntelligenceRequest,
    ReplanRequest,
    SuccessCriterion,
)
from backend.services.agent.arceus_runtime.planning_intelligence.service import (
    build_planning_decision,
    interpret_goal,
    replan_from_evidence,
    validate_planning_response,
)


def test_interprets_goal_with_security_risk_and_success_criteria() -> None:
    payload = PlanningIntelligenceRequest(
        objective="Improve authentication security for Clerk session token validation.",
        success_criteria=[SuccessCriterion(id="auth_secure", description="Invalid tokens are rejected.", type="security", verification_method="security_review")],
    )

    interpreted = interpret_goal(payload)

    assert interpreted["risk_level"] == "critical"
    assert "secure_code_review" in interpreted["required_capabilities"]
    assert interpreted["success_criteria"][0]["id"] == "auth_secure"


def test_generates_multiple_alternatives_and_recommends_one() -> None:
    payload = PlanningIntelligenceRequest(
        objective="Add a Next.js settings page for AI model routing.",
        planning_depth="balanced",
        success_criteria=[SuccessCriterion(id="build", description="Frontend build passes.", type="quality", verification_method="npm run build")],
    )

    decision = build_planning_decision(payload)

    assert len(decision.alternatives) == 3
    assert decision.recommended_strategy_key in {item.strategy_key for item in decision.alternatives}
    assert decision.goal_tree
    assert decision.alternatives[0].decision_score >= decision.alternatives[-1].decision_score


def test_budget_constraint_blocks_next_action() -> None:
    payload = PlanningIntelligenceRequest(
        objective="Implement backend and frontend billing webhook changes.",
        budget=PlanningBudget(max_cost_usd=0.1, max_engineering_hours=0.1, max_tokens=100),
    )

    decision = build_planning_decision(payload)

    assert decision.next_best_action["action"] == "revise_constraints_or_scope"
    assert decision.next_best_action["blocking"] is True


def test_deadline_affects_speed_score() -> None:
    payload = PlanningIntelligenceRequest(
        objective="Create a small UI copy change.",
        deadline=datetime.now(timezone.utc) + timedelta(hours=2),
    )

    decision = build_planning_decision(payload)

    assert all(0 <= item.speed_score <= 1 for item in decision.alternatives)


def test_validate_plan_requires_tasks_and_verification() -> None:
    decision = build_planning_decision(PlanningIntelligenceRequest(objective="Add repository search"))

    valid, errors, warnings = validate_planning_response(decision)

    assert valid is True
    assert errors == []
    assert isinstance(warnings, list)


def test_replan_triggers_on_failed_task_and_policy_block() -> None:
    decision = build_planning_decision(PlanningIntelligenceRequest(objective="Deploy production release"))

    response = replan_from_evidence(ReplanRequest(previous_plan=decision, failed_task_keys=["review.qa"], new_evidence={"policy_blocked": True}))

    assert response.should_replan is True
    assert len(response.recommended_adjustments) >= 2

