from __future__ import annotations

from backend.services.agent.arceus_runtime.multi_agent.service import score_agent_candidate, select_best_agent


def test_agent_candidate_scoring_prefers_capability_match() -> None:
    backend = score_agent_candidate(
        agent_capabilities=[{"capability_key": "fastapi_development"}, {"capability_key": "api_design"}],
        required_capabilities=["fastapi_development", "api_design"],
        status="available",
        performance_score=0.8,
        cost_score=0.8,
        active_task_count=0,
    )
    frontend = score_agent_candidate(
        agent_capabilities=[{"capability_key": "react_development"}],
        required_capabilities=["fastapi_development", "api_design"],
        status="available",
        performance_score=1.0,
        cost_score=1.0,
        active_task_count=0,
    )

    assert backend["score"] > frontend["score"]
    assert backend["matched_capabilities"] == ["api_design", "fastapi_development"]
    assert frontend["missing_capabilities"] == ["api_design", "fastapi_development"]


def test_agent_candidate_scoring_penalizes_unavailable_agents() -> None:
    available = score_agent_candidate(
        agent_capabilities=["security_review"],
        required_capabilities=["security_review"],
        status="available",
    )
    offline = score_agent_candidate(
        agent_capabilities=["security_review"],
        required_capabilities=["security_review"],
        status="offline",
    )

    assert available["score"] > offline["score"]


def test_select_best_agent_ignores_blocked_statuses() -> None:
    selected = select_best_agent(
        [
            {"agent_id": "disabled", "name": "Disabled", "score": 1.0, "status": "suspended", "active_task_count": 0},
            {"agent_id": "available", "name": "Available", "score": 0.6, "status": "available", "active_task_count": 0},
        ]
    )

    assert selected is not None
    assert selected["agent_id"] == "available"


def test_select_best_agent_uses_workload_as_tiebreaker() -> None:
    selected = select_best_agent(
        [
            {"agent_id": "busy", "name": "Busy", "score": 0.8, "status": "available", "active_task_count": 3},
            {"agent_id": "calm", "name": "Calm", "score": 0.8, "status": "available", "active_task_count": 0},
        ]
    )

    assert selected is not None
    assert selected["agent_id"] == "calm"
