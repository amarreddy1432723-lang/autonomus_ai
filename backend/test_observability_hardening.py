import json
from pathlib import Path

from services.agent.routes_admin import _observability_health_report


def test_observability_health_reports_alert_dashboard_and_runbook(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_RELEASE", "arceus-test-release")
    monkeypatch.setenv("SENTRY_DSN", "https://example@sentry.invalid/1")
    monkeypatch.setenv("NEXT_PUBLIC_SENTRY_DSN", "https://example@sentry.invalid/2")
    monkeypatch.setenv("PROMETHEUS_METRICS_ENABLED", "true")

    report = _observability_health_report()

    assert report["release"] == "arceus-test-release"
    assert report["metrics_endpoint"] == "/metrics"
    assert report["sentry"]["backend_configured"] is True
    assert report["sentry"]["frontend_configured"] is True
    assert report["grafana"]["dashboard_ready"] is True
    assert report["grafana"]["datasource_path"] == "ops/grafana/provisioning/datasources/prometheus.yml"
    assert report["grafana"]["provider_path"] == "ops/grafana/provisioning/dashboards/arceus.yml"
    assert report["runbook"]["verify"].startswith(".\\scripts\\verify-observability.ps1")
    assert report["runbook"]["setup"].startswith("docker compose")
    assert {item["name"] for item in report["prometheus"]["alert_coverage"]} == {
        "ArceusServiceDown",
        "ArceusApiHighErrorRate",
        "ArceusApiP99LatencyHigh",
        "ArceusWorkerQueueDepthHigh",
        "ArceusWorkerDown",
        "ArceusDeadLetterJobs",
    }
    assert all(item["present"] for item in report["prometheus"]["alert_coverage"])


def test_observability_ops_files_are_importable():
    root = Path(__file__).resolve().parents[1]
    alert_rules = (root / "ops" / "prometheus" / "arceus-alerts.yml").read_text(encoding="utf-8")
    dashboard = json.loads((root / "ops" / "grafana" / "arceus-code-overview.json").read_text(encoding="utf-8"))

    for alert_name in [
        "ArceusServiceDown",
        "ArceusApiHighErrorRate",
        "ArceusApiP99LatencyHigh",
        "ArceusWorkerQueueDepthHigh",
        "ArceusWorkerDown",
        "ArceusDeadLetterJobs",
    ]:
        assert alert_name in alert_rules

    assert dashboard["title"] == "Arceus Code Overview"
    assert dashboard["uid"] == "arceus-code-overview"
    assert any(panel["title"] == "Worker Health" for panel in dashboard["panels"])
    assert (root / "ops" / "grafana" / "provisioning" / "datasources" / "prometheus.yml").exists()
    assert (root / "ops" / "grafana" / "provisioning" / "dashboards" / "arceus.yml").exists()
