from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.shared import rate_limiter
from services.shared.rate_limiter import RateLimitHeaderMiddleware, rate_limit_policy_report, route_limit_profile


class FakeRedis:
    def __init__(self, allowed):
        self.allowed = list(allowed)

    def ping(self):
        return True

    def eval(self, *_args):
        if self.allowed:
            return self.allowed.pop(0)
        return [0, 0]


def test_rate_limit_policy_report_exposes_route_classes(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setenv("RATE_LIMIT_FAIL_CLOSED", "true")
    monkeypatch.setattr(rate_limiter, "redis_client", FakeRedis([[1, 10]]))

    report = rate_limit_policy_report()
    profiles = {item["name"]: item for item in report["profiles"]}

    assert report["enabled"] is True
    assert report["enforcing"] is True
    assert report["mode"] == "enforced"
    assert report["fail_closed"] is True
    assert {"auth", "model", "upload", "code_runtime", "pa", "interview", "admin", "default"}.issubset(profiles)
    assert "/api/v1/code/sessions/{id}/stream" in profiles["model"]["examples"]
    assert profiles["code_runtime"]["env"]["burst"] == "RATE_LIMIT_CODE_RUNTIME_BURST"


def test_rate_limit_middleware_returns_structured_429(monkeypatch):
    monkeypatch.setenv("RATE_LIMIT_ENABLED", "true")
    monkeypatch.setattr(rate_limiter, "redis_client", FakeRedis([[0, 0]]))

    app = FastAPI()
    app.add_middleware(RateLimitHeaderMiddleware)

    @app.post("/api/v1/code/terminal/abc/input")
    def terminal_input():
        return {"ok": True}

    response = TestClient(app).post("/api/v1/code/terminal/abc/input", headers={"x-user-id": "user-1"})

    assert response.status_code == 429
    body = response.json()
    assert body["code"] == "RATE_LIMITED"
    assert body["route_class"] == "code_runtime"
    assert response.headers["X-RateLimit-Policy"] == "code_runtime"
    assert response.headers["X-RateLimit-Remaining"] == "0"
    assert "Retry-After" in response.headers


def test_route_limit_profiles_cover_admin_and_expensive_routes():
    assert route_limit_profile("/api/v1/admin/rate-limits").name == "admin"
    assert route_limit_profile("/api/v1/github/sessions/123/create-pr").name == "code_runtime"
    assert route_limit_profile("/api/v1/code/sessions/123/suggest-next").name == "model"
    assert route_limit_profile("/api/v1/pa/reminders").name == "pa"
