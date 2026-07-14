from services.agent.routes_admin import _release_readiness_report
from services.agent.routes_public import get_public_production_readiness


def test_release_readiness_includes_runbook_commands(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")

    report = _release_readiness_report()

    assert "runbook" in report
    assert report["runbook"]["verify_command"].startswith(".\\scripts\\full-verify.ps1")
    assert report["runbook"]["release_gate_command"].startswith(".\\scripts\\verify-release-gate.ps1")
    assert report["runbook"]["deploy_command"].startswith(".\\scripts\\deploy-railway.ps1")
    assert report["summary"]["checks"] == len(report["checks"])
    assert all("action" in item for item in report["checks"])


def test_public_production_readiness_is_sanitized(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")

    payload = get_public_production_readiness()

    assert payload["service"] == "agent-service"
    assert payload["status"] in {"ready", "blocked"}
    assert "summary" in payload
    assert "runbook" not in payload
    assert all(set(item.keys()) == {"name", "ok", "severity"} for item in payload["checks"])
