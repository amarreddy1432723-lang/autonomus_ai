import json
from pathlib import Path

from fastapi.testclient import TestClient

from services.agent.main import app as agent_app
from services.auth.main import app as auth_app
from services.goals.main import app as goals_app
from services.shared.roadmap import get_roadmap_manifest


ROOT = Path(__file__).resolve().parents[1]


def test_roadmap_manifest_defines_phase_12_release_sequence():
    roadmap = get_roadmap_manifest()

    assert roadmap["phase"] == 12
    assert roadmap["horizon_weeks"] == 24
    assert [release["name"] for release in roadmap["release_plan"]] == [
        "MVP Local",
        "Private Alpha",
        "Beta",
        "General Availability",
    ]
    assert len(roadmap["weekly_plan"]) == 8
    assert roadmap["verification"]["backend_tests"] == "python -m pytest backend -q"


def test_roadmap_phase_sequence_marks_previous_work_implemented_and_phase_13_next():
    phases = {entry["phase"]: entry for entry in get_roadmap_manifest()["phase_sequence"]}

    for phase in range(4, 13):
        assert phases[phase]["status"] == "implemented"
    assert phases[14]["status"] == "next"
    assert phases[13]["name"] == "Future Roadmap"
    assert phases[13]["status"] == "implemented_as_blueprint"


def test_roadmap_records_manual_user_actions_before_alpha_and_beta():
    actions = " ".join(action["action"] for action in get_roadmap_manifest()["manual_actions"]).lower()

    assert "llm credentials" in actions
    assert "hosting" in actions
    assert "domain" in actions
    assert "production secret" in actions
    assert "alpha users" in actions


def test_roadmap_endpoint_is_exposed_by_all_backend_services():
    for service_name, app in {
        "auth-service": auth_app,
        "goals-service": goals_app,
        "agent-service": agent_app,
    }.items():
        response = TestClient(app).get("/api/v1/roadmap")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["service"] == service_name
        assert body["roadmap"]["phase"] == 12
        assert body["roadmap"]["phase_sequence"][-1]["phase"] == 14


def test_readme_stack_and_roadmap_contract_are_aligned():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    stack = json.loads((ROOT / "stack.json").read_text(encoding="utf-8"))
    roadmap = json.loads((ROOT / "roadmap.json").read_text(encoding="utf-8"))

    assert stack["phase"] == 13
    assert roadmap["phase"] == 12
    assert stack["current_completed_phase"] == 13
    assert stack["next_phase"] == "private_alpha_launch"
    assert "roadmap.json" in readme
    assert "/api/v1/roadmap" in readme
    assert "Private Alpha" in readme
    assert "8006" not in readme
