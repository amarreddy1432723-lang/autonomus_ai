from pathlib import Path

from fastapi.testclient import TestClient

from services.agent.main import app as agent_app
from services.auth.main import app as auth_app
from services.goals.main import app as goals_app
from services.shared.architecture import get_ai_architecture_manifest, get_system_architecture_manifest


ROOT = Path(__file__).resolve().parents[1]


def test_phase2_system_architecture_manifest_matches_blueprint():
    manifest = get_system_architecture_manifest()

    assert manifest["phase"] == 2
    assert manifest["name"] == "system architecture"
    assert manifest["status"] == "implemented_as_architecture_contract"
    assert set(manifest["architectural_principles"]) >= {
        "Domain-Driven Design",
        "Event-Driven Architecture",
        "Microservices",
        "Clean Architecture",
        "CQRS",
        "Eventual Consistency",
        "Fail-Safe Defaults",
    }
    assert {layer["name"] for layer in manifest["layers"]} >= {
        "client_layer",
        "api_gateway_layer",
        "backend_services_layer",
        "ai_agent_layer",
        "message_bus_event_layer",
        "data_layer",
        "external_integrations",
    }
    assert manifest["deployment_target"]["orchestration"] == "EKS Kubernetes"
    assert manifest["deployment_target"]["service_mesh"] == "Istio"


def test_phase3_ai_architecture_manifest_matches_blueprint():
    manifest = get_ai_architecture_manifest()

    assert manifest["phase"] == 3
    assert manifest["name"] == "ai architecture"
    assert manifest["agent_model"] == "hub-and-spoke"
    assert len(manifest["agents"]) == 12
    assert {agent["id"] for agent in manifest["agents"]} == {
        "central_brain",
        "planner",
        "memory",
        "research",
        "coding",
        "task",
        "scheduler",
        "reflection",
        "learning",
        "notification",
        "execution",
        "approval",
    }
    assert manifest["risk_model"]["safe_default"] == "reject_on_timeout"
    assert "Human Primacy" in manifest["design_principles"]
    assert manifest["communication_map"]["high_risk_calls_route_to_approval"] is True


def test_phase2_phase3_architecture_endpoints_are_exposed_by_all_services():
    for service_name, app in {
        "auth-service": auth_app,
        "goals-service": goals_app,
        "agent-service": agent_app,
    }.items():
        system_response = TestClient(app).get("/api/v1/architecture/system")
        ai_response = TestClient(app).get("/api/v1/architecture/ai")

        assert system_response.status_code == 200, system_response.text
        assert system_response.json()["service"] == service_name
        assert system_response.json()["architecture"]["phase"] == 2

        assert ai_response.status_code == 200, ai_response.text
        assert ai_response.json()["service"] == service_name
        assert ai_response.json()["architecture"]["phase"] == 3


def test_architecture_docs_are_discoverable_without_stale_ports():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    deployment = (ROOT / "DEPLOYMENT.md").read_text(encoding="utf-8")
    stack = (ROOT / "stack.json").read_text(encoding="utf-8")

    assert "phase2.json" in readme
    assert "phase3.json" in readme
    assert "/api/v1/architecture/system" in readme
    assert "/api/v1/architecture/ai" in readme
    assert "/api/v1/architecture/system" in deployment
    assert "/api/v1/architecture/ai" in deployment
    assert "system_architecture" in stack
    assert "ai_architecture" in stack
    assert "8006" not in readme
