from pathlib import Path

from fastapi.testclient import TestClient

from services.agent.config import settings as agent_settings
from services.agent.main import app as agent_app
from services.auth.main import app as auth_app
from services.goals.main import app as goals_app
from services.shared.phase13 import get_phase13_manifest
from services.shared.production import production_readiness


ROOT = Path(__file__).resolve().parents[1]


def test_phase13_manifest_defines_future_roadmap_blueprint():
    manifest = get_phase13_manifest()

    assert manifest["phase"] == 13
    assert manifest["name"] == "future roadmap"
    assert manifest["status"] == "implemented_as_blueprint"
    assert manifest["strategic_vision"]["title"] == "The Sovereign Agent"
    assert {track["id"] for track in manifest["roadmap_tracks"]} == {
        "voice_ambient_interfaces",
        "sovereign_digital_identity",
        "agent_protocol_suite",
        "memory_portability",
        "decentralized_agent_networks",
    }
    assert manifest["north_star"]["title"] == "The Cognitive Extension"


def test_future_roadmap_evaluation_and_readiness_endpoints_are_exposed_by_all_services():
    for service_name, app in {
        "auth-service": auth_app,
        "goals-service": goals_app,
        "agent-service": agent_app,
    }.items():
        future = TestClient(app).get("/api/v1/future-roadmap")
        evaluation = TestClient(app).get("/api/v1/evaluation/status")
        readiness = TestClient(app).get("/api/v1/production/readiness")

        assert future.status_code == 200, future.text
        assert future.json()["service"] == service_name
        assert future.json()["future_roadmap"]["strategic_vision"]["title"] == "The Sovereign Agent"

        assert evaluation.status_code == 200, evaluation.text
        assert evaluation.json()["service"] == service_name
        assert evaluation.json()["evaluation"]["phase"] == 13

        assert readiness.status_code == 200, readiness.text
        body = readiness.json()
        assert body["service"] == service_name
        assert body["summary"]["total"] >= 8
        assert body["status"] in {"ready", "needs_attention", "blocked"}


def test_local_readiness_reports_blockers_for_live_launch():
    readiness = production_readiness("test-service")

    check_names = {check["name"] for check in readiness["checks"]}
    assert {"jwt_secret", "field_encryption", "llm_provider", "dev_auth_fallback", "demo_user"} <= check_names
    assert readiness["status"] == "blocked"
    assert readiness["summary"]["critical_failed"] >= 1


def test_phase13_strategic_decisions_match_future_spec():
    manifest = get_phase13_manifest()
    choices = {item["area"]: item["choice"] for item in manifest["strategic_decisions"]}
    tracks = {track["id"]: track for track in manifest["roadmap_tracks"]}

    assert choices["Voice Standard"] == "WebRTC auditory pipeline"
    assert choices["Identity"] == "W3C Decentralized Identifiers"
    assert choices["Trust Verification"] == "zkML"
    assert choices["Data Format"] == "Open Memory Format JSON-LD Graph"
    assert choices["Transaction Protocol"] == "Agent-to-agent micro-transactions"
    assert any("AP-HANDSHAKE" in item for item in tracks["agent_protocol_suite"]["target_capabilities"])
    assert tracks["memory_portability"]["open_memory_format_example"]["@context"] == "https://openmemory.org/context.jsonld"


def test_launch_docs_and_env_examples_are_not_stale():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    frontend_readme = (ROOT / "frontend" / "README.md").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    deployment = (ROOT / "DEPLOYMENT.md").read_text(encoding="utf-8")

    assert "phase13.json" in readme
    assert "DEPLOYMENT.md" in readme
    assert "/api/v1/future-roadmap" in readme
    assert "/api/v1/production/readiness" in readme
    assert "ALLOW_DEMO_USER=false" in readme
    assert "ALLOW_DEV_AUTH_FALLBACK=false" in readme
    assert "8006" not in readme
    assert "8006" not in frontend_readme
    assert "AGENT_PORT=8003" in env_example
    assert "NEXT_PUBLIC_REQUIRE_AUTH=true" in env_example
    assert agent_settings.AGENT_PORT == 8003
    assert "Private Alpha" in deployment
    assert "alembic upgrade head" in deployment
    assert "future roadmap" in deployment
