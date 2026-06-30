from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from services.agent.planner import build_structured_plan, calculate_plan_health, validate_no_cycles
from services.goals.main import app
from services.shared.database import SessionLocal, verify_default_user
from services.shared.models import Goal


USER_ID = UUID("00000000-0000-0000-0000-000000000000")


@pytest.fixture()
def db():
    session = SessionLocal()
    verify_default_user(session)
    session.query(Goal).filter(Goal.user_id == USER_ID, Goal.title.like("Phase5 test%")).delete()
    session.commit()
    try:
        yield session
    finally:
        session.query(Goal).filter(Goal.user_id == USER_ID, Goal.title.like("Phase5 test%")).delete()
        session.commit()
        session.close()


def test_structured_plan_contains_roadmap_projects_and_critical_path():
    plan = build_structured_plan(
        USER_ID,
        "Phase5 test build AI study planner",
        "Create a planning engine that breaks learning goals into projects and tasks.",
    )

    assert plan["formal_goal"]["category"] in {"software", "learning"}
    assert plan["roadmap"]
    assert plan["projects"]
    assert plan["tasks"]
    assert plan["estimated_hours_total"] > 0
    assert all("project_title" in task for task in plan["tasks"])


def test_cycle_validation_rejects_circular_dependencies():
    tasks = [
        {"title": "A", "dependencies": ["B"]},
        {"title": "B", "dependencies": ["A"]},
    ]
    assert validate_no_cycles(tasks) is False


def test_plan_health_counts_blocked_and_critical_tasks():
    health = calculate_plan_health([
        {"title": "A", "status": "done", "is_critical": True},
        {"title": "B", "status": "blocked", "is_critical": True},
    ])

    assert health["total_tasks"] == 2
    assert health["completed_tasks"] == 1
    assert health["blocked_tasks"] == 1
    assert health["score"] < 1.0


def test_goal_api_persists_phase5_plan_projects_tasks_and_replan(db):
    client = TestClient(app)
    headers = {"x-user-id": str(USER_ID)}
    response = client.post(
        "/api/v1/goals",
        headers=headers,
        json={
            "title": "Phase5 test launch planning engine",
            "description": "Build a planning engine with roadmap, project grouping, critical path, and health checks.",
        },
    )
    assert response.status_code == 201, response.text
    created = response.json()

    assert created["current_plan"]["roadmap"]
    assert created["projects"]
    assert created["tasks"]
    assert created["estimated_hours_total"] > 0

    plan_response = client.get(f"/api/v1/goals/{created['id']}/plan", headers=headers)
    assert plan_response.status_code == 200, plan_response.text
    assert plan_response.json()["critical_path"]

    health_response = client.get(f"/api/v1/goals/{created['id']}/health", headers=headers)
    assert health_response.status_code == 200, health_response.text
    assert health_response.json()["total_tasks"] == len(created["tasks"])

    replan_response = client.post(
        f"/api/v1/goals/{created['id']}/replan",
        headers=headers,
        json={"trigger": "test_delay", "strategy": "hybrid"},
    )
    assert replan_response.status_code == 200, replan_response.text
    replanned = replan_response.json()
    assert replanned["plan_version"] == 2
    assert replanned["proposal"]["recommended_strategy"] == "hybrid"
