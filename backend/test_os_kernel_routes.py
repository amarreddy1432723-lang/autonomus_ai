from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.agent.routes_os_kernel import router, runtime


def make_client() -> TestClient:
    runtime.events._events.clear()
    runtime.events._idempotency_index.clear()
    runtime.missions.missions.clear()
    runtime.organizations.clear()
    runtime.workflows.clear()
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_os_kernel_health_route_reports_ready():
    client = make_client()

    response = client.get("/api/v1/os/system/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["runtime"] == "in_memory_generation_1"
    assert body["capabilities"] >= 5


def test_mission_api_creates_transitions_and_replays_events():
    client = make_client()
    created = client.post(
        "/api/v1/os/missions",
        json={
            "tenant_id": "tenant",
            "owner_id": "founder",
            "title": "Improve repo",
            "objective": "Analyze repository and implement a safe change",
            "success_criteria": ["Tests pass"],
        },
    )
    mission_id = created.json()["mission"]["mission_id"]

    assert created.status_code == 200
    assert client.post(f"/api/v1/os/missions/{mission_id}/transition", json={"state": "DISCOVERY"}).status_code == 200
    assert client.post(f"/api/v1/os/missions/{mission_id}/transition", json={"state": "PLANNING"}).status_code == 200
    assert client.post(f"/api/v1/os/missions/{mission_id}/transition", json={"state": "READY"}).status_code == 200

    events = client.get(f"/api/v1/os/missions/{mission_id}/events").json()["events"]

    assert [event["event_type"] for event in events][:4] == [
        "MISSION_CREATED",
        "MISSION_UPDATED",
        "MISSION_UPDATED",
        "MISSION_APPROVED",
    ]


def test_mission_compile_route_returns_aml_and_execution_graph_without_creating_mission():
    client = make_client()

    response = client.post(
        "/api/v1/os/missions/compile",
        headers={"x-user-id": "founder"},
        json={
            "tenant_id": "tenant",
            "project_id": "project-admin",
            "objective": "Add a health-status card to the admin interface using the existing health endpoint",
            "repository_ids": ["repo-web"],
            "constraints": ["Use the existing health endpoint"],
            "desired_outcomes": ["Admin users can see service health at a glance"],
        },
    )

    body = response.json()

    assert response.status_code == 200
    assert body["state"] == "COMPILED"
    assert body["aml"]["version"] == "1.0"
    assert body["definition"]["project_id"] == "project-admin"
    assert "react_development" in body["definition"]["required_capabilities"]
    assert any(node["node_type"] == "verification" for node in body["definition"]["execution_graph"]["nodes"])
    assert client.get("/api/v1/os/missions").json()["missions"] == []


def test_mission_compile_route_returns_clarification_required_for_material_auth_unknown():
    client = make_client()

    response = client.post(
        "/api/v1/os/missions/compile",
        json={
            "tenant_id": "tenant",
            "project_id": "project-auth",
            "objective": "Add Google OAuth login to the desktop and web applications",
            "constraints": ["Do not expose secrets in the desktop renderer"],
            "desired_outcomes": ["Users can sign in through Google"],
        },
    )

    body = response.json()

    assert response.status_code == 200
    assert body["state"] == "CLARIFICATION_REQUIRED"
    assert body["intent"]["execution_allowed"] is False
    assert "OAuth provider configuration and callback ownership must be confirmed." in body["definition"]["unknowns"]
    assert any(node["node_type"] == "human_action" for node in body["definition"]["execution_graph"]["nodes"])


def test_mission_compile_store_persists_mission_and_compiled_artifact_events():
    client = make_client()

    response = client.post(
        "/api/v1/os/missions/compile-store",
        headers={"x-user-id": "founder"},
        json={
            "tenant_id": "tenant",
            "project_id": "project-admin",
            "objective": "Add a compact health status card to admin using the existing readiness endpoint",
            "constraints": ["Use the existing readiness endpoint"],
            "desired_outcomes": ["Admins can see service readiness"],
            "idempotency_key": "compile-admin-health-card",
        },
    )

    body = response.json()
    mission_id = body["mission"]["mission_id"]
    events = client.get(f"/api/v1/os/missions/{mission_id}/events").json()["events"]

    assert response.status_code == 200
    assert body["duplicate"] is False
    assert body["mission"]["state"] == "PLANNING"
    assert body["compiled"]["state"] == "COMPILED"
    assert [event["event_type"] for event in events] == ["MISSION_CREATED", "ARTIFACT_CREATED"]
    assert events[1]["payload"]["artifact_type"] == "compiled_mission"
    assert client.get("/api/v1/os/missions").json()["missions"][0]["mission_id"] == mission_id


def test_mission_compile_store_is_idempotent_on_retry():
    client = make_client()
    payload = {
        "tenant_id": "tenant",
        "project_id": "project-admin",
        "objective": "Add a compact health status card to admin using the existing readiness endpoint",
        "idempotency_key": "compile-admin-health-card",
    }

    first = client.post("/api/v1/os/missions/compile-store", json=payload)
    second = client.post("/api/v1/os/missions/compile-store", json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["duplicate"] is True
    assert second.json()["mission"]["mission_id"] == first.json()["mission"]["mission_id"]
    assert len(client.get("/api/v1/os/missions").json()["missions"]) == 1


def test_mission_compile_store_blocks_clarification_required_mission():
    client = make_client()

    response = client.post(
        "/api/v1/os/missions/compile-store",
        json={
            "tenant_id": "tenant",
            "project_id": "project-auth",
            "objective": "Add Google OAuth login to the desktop and web applications",
            "constraints": ["Do not expose secrets in the desktop renderer"],
            "idempotency_key": "compile-google-oauth",
        },
    )

    body = response.json()
    event_types = [event["event_type"] for event in body["events"]]

    assert response.status_code == 200
    assert body["mission"]["state"] == "BLOCKED"
    assert body["compiled"]["state"] == "CLARIFICATION_REQUIRED"
    assert event_types == ["MISSION_CREATED", "ARTIFACT_CREATED", "MISSION_UPDATED"]
    assert body["events"][-1]["payload"]["reason"] == "clarification_required"


def test_mission_sync_payload_includes_compiled_artifact_and_cursor():
    client = make_client()
    mission_id = client.post(
        "/api/v1/os/missions/compile-store",
        json={
            "tenant_id": "tenant",
            "project_id": "project-admin",
            "objective": "Add a compact health status card to admin using the existing readiness endpoint",
            "idempotency_key": "compile-admin-health-card",
        },
    ).json()["mission"]["mission_id"]

    response = client.get(f"/api/v1/os/missions/{mission_id}/sync")
    body = response.json()

    assert response.status_code == 200
    assert body["mission"]["mission_id"] == mission_id
    assert body["compiled_mission"]["artifact_type"] == "compiled_mission"
    assert body["compiled_mission"]["aml"]["version"] == "1.0"
    assert body["cursor"] == body["events"][-1]["event_id"]


def test_desktop_claim_records_idempotent_mission_sync_event():
    client = make_client()
    mission_id = client.post(
        "/api/v1/os/missions/compile-store",
        json={
            "tenant_id": "tenant",
            "project_id": "project-admin",
            "objective": "Add a compact health status card to admin using the existing readiness endpoint",
            "idempotency_key": "compile-admin-health-card",
        },
    ).json()["mission"]["mission_id"]

    first = client.post(
        f"/api/v1/os/missions/{mission_id}/desktop-claim",
        headers={"x-user-id": "founder"},
        json={"desktop_id": "desktop-1", "local_workspace_path": "C:/repo", "app_version": "1.0.0"},
    )
    second = client.post(
        f"/api/v1/os/missions/{mission_id}/desktop-claim",
        headers={"x-user-id": "founder"},
        json={"desktop_id": "desktop-1", "local_workspace_path": "C:/repo", "app_version": "1.0.0"},
    )
    sync = client.get(f"/api/v1/os/missions/{mission_id}/sync").json()
    desktop_claim_events = [event for event in sync["events"] if event["payload"].get("desktop_claimed")]

    assert first.status_code == 200
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "duplicate_operation"
    assert desktop_claim_events[0]["payload"]["desktop_id"] == "desktop-1"


def test_invalid_transition_returns_conflict():
    client = make_client()
    created = client.post("/api/v1/os/missions", json={"title": "Mission", "objective": "Build"})
    mission_id = created.json()["mission"]["mission_id"]

    response = client.post(f"/api/v1/os/missions/{mission_id}/transition", json={"state": "COMPLETED"})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "invalid_transition"


def test_workflow_api_requires_passing_evidence():
    client = make_client()
    mission_id = client.post("/api/v1/os/missions", json={"title": "Mission", "objective": "Build"}).json()["mission"]["mission_id"]
    workflow = client.post(f"/api/v1/os/missions/{mission_id}/workflow").json()["workflow"]
    step = workflow["steps"][0]

    failed = client.post(
        f"/api/v1/os/workflows/{workflow['run_id']}/steps/{step['step_id']}/complete",
        json={"output": {"status": "ok"}, "evidence": {}},
    )
    passed = client.post(
        f"/api/v1/os/workflows/{workflow['run_id']}/steps/{step['step_id']}/complete",
        json={"output": {"status": "ok"}, "evidence": {"kind": "analysis", "status": "passed"}},
    )

    assert failed.status_code == 409
    assert passed.status_code == 200
    assert passed.json()["step"]["state"] == "COMPLETED"


def test_tool_policy_route_blocks_unapproved_production_change():
    client = make_client()
    mission_id = client.post("/api/v1/os/missions", json={"title": "Mission", "objective": "Build"}).json()["mission"]["mission_id"]

    response = client.post(
        f"/api/v1/os/missions/{mission_id}/tool-policy",
        json={
            "actor_id": "implementation-agent",
            "tenant_id": "tenant",
            "role": "engineer",
            "environment": "production",
            "approved": False,
            "category": "PRODUCTION_CHANGE",
            "risk_level": "high",
            "author_id": "implementation-agent",
        },
    )

    assert response.status_code == 200
    assert response.json()["allowed"] is False
    assert response.json()["requires_human_approval"] is True


def test_pause_route_sets_user_pause_state():
    client = make_client()
    mission_id = client.post("/api/v1/os/missions", json={"title": "Mission", "objective": "Build"}).json()["mission"]["mission_id"]
    client.post(f"/api/v1/os/missions/{mission_id}/transition", json={"state": "DISCOVERY"})
    client.post(f"/api/v1/os/missions/{mission_id}/transition", json={"state": "PLANNING"})
    client.post(f"/api/v1/os/missions/{mission_id}/transition", json={"state": "READY"})

    response = client.post(f"/api/v1/os/missions/{mission_id}/pause")

    assert response.status_code == 200
    assert response.json()["mission"]["state"] == "PAUSED"
    assert response.json()["mission"]["paused_by_user"] is True
