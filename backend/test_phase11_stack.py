import json
from pathlib import Path

from fastapi.testclient import TestClient

from services.agent.config import settings as agent_settings
from services.agent.main import app as agent_app
from services.auth.main import app as auth_app
from services.goals.main import app as goals_app
from services.shared.stack import get_stack_manifest


ROOT = Path(__file__).resolve().parents[1]


def test_stack_manifest_matches_local_service_ports_and_ai_defaults():
    manifest = get_stack_manifest()

    assert manifest["phase"] == 13
    assert manifest["current_completed_phase"] == 13
    assert manifest["next_phase"] == "private_alpha_launch"
    assert manifest["services"]["auth"]["port"] == 8001
    assert manifest["services"]["goals"]["port"] == 8002
    assert manifest["services"]["agent"]["port"] == 8003
    assert manifest["services"]["frontend"]["port"] == 3004
    assert manifest["ai"]["embedding_model"] == "text-embedding-3-small"
    assert manifest["data"]["primary_database"] == "PostgreSQL 16 + pgvector"
    assert agent_settings.AGENT_PORT == 8003


def test_stack_endpoint_is_exposed_by_all_backend_services():
    for service_name, app in {
        "auth-service": auth_app,
        "goals-service": goals_app,
        "agent-service": agent_app,
    }.items():
        response = TestClient(app).get("/api/v1/stack")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["service"] == service_name
        assert body["stack"]["phase"] == 13
        assert body["stack"]["services"]["agent"]["port"] == 8003


def test_docker_compose_uses_postgres_16_pgvector_and_redis_7():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert "pgvector/pgvector:pg16" in compose
    assert "redis:7-alpine" in compose
    assert "5432:5432" in compose
    assert "6379:6379" in compose


def test_readme_and_manifest_do_not_reference_stale_agent_port():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "stack.json").read_text(encoding="utf-8"))

    assert "8006" not in readme
    assert manifest["services"]["agent"]["port"] == 8003
    assert "/api/v1/stack" in readme
    assert "/api/v1/roadmap" in readme
    assert "/api/v1/production/readiness" in readme
