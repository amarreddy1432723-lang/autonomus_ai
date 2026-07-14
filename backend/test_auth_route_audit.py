from fastapi.testclient import TestClient

from services.agent.main import app


def _route_dependencies(path: str, method: str = "GET") -> set[str]:
    for route in app.routes:
        if getattr(route, "path", None) != path:
            continue
        methods = getattr(route, "methods", set()) or set()
        if method.upper() not in methods:
            continue
        dependant = getattr(route, "dependant", None)
        if not dependant:
            return set()
        return {getattr(dep.call, "__name__", str(dep.call)) for dep in dependant.dependencies}
    raise AssertionError(f"Route not found: {method} {path}")


def test_core_product_routes_require_authenticated_user_dependency():
    protected_samples = [
        ("GET", "/api/v1/code/projects"),
        ("POST", "/api/v1/code/sessions"),
        ("POST", "/api/v1/code/sessions/{session_id}/run-checks"),
        ("GET", "/api/v1/code/jobs"),
        ("GET", "/api/v1/github/status"),
        ("GET", "/api/v1/files"),
        ("POST", "/api/v1/files"),
        ("GET", "/api/v1/pa/today"),
        ("POST", "/api/v1/pa/command"),
        ("POST", "/api/v1/interview/plan"),
        ("GET", "/api/v1/billing/summary"),
        ("GET", "/api/v1/admin/summary"),
        ("POST", "/api/v1/memories/compress"),
    ]

    for method, path in protected_samples:
        assert "get_current_user_id" in _route_dependencies(path, method), f"{method} {path} is missing auth dependency"


def test_public_routes_stay_anonymous():
    public_samples = [
        ("GET", "/api/v1/health"),
        ("GET", "/api/v1/ready"),
        ("GET", "/api/v1/production/readiness"),
        ("POST", "/api/v1/billing/webhook"),
        ("GET", "/api/v1/github/callback"),
        ("GET", "/api/v1/downloads/latest"),
    ]

    for method, path in public_samples:
        assert "get_current_user_id" not in _route_dependencies(path, method), f"{method} {path} should remain public"


def test_memory_compression_rejects_anonymous_requests():
    response = TestClient(app).post(
        "/api/v1/memories/compress",
        json={"user_id": "00000000-0000-0000-0000-000000000000"},
    )

    assert response.status_code == 401
