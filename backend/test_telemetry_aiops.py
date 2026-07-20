from decimal import Decimal
from uuid import uuid4

from services.agent.arceus_runtime.telemetry.api_schemas import (
    AlertCreateRequest,
    AlertDeliveryChannelRequest,
    CostStatisticRecordRequest,
    ExporterConfigRequest,
    IncidentCreateRequest,
    MetricRecordRequest,
    ProviderHealthRecordRequest,
    RecoveryActionRequest,
    TelemetryLogIngestRequest,
)
from services.agent.arceus_runtime.telemetry.service import (
    alert_response,
    classify_provider_health,
    dashboard_recommendations,
    deliver_alert_attempt,
    delivery_channel_matches,
    emit_otel_span,
    execute_safe_recovery_action,
    exporter_response,
    incident_response,
    metric_summary,
    otel_exporter_runtime_status,
    redact_log,
    recovery_policy_decision,
    to_float,
)
from services.shared.arceus_core_models import (
    ArceusAlert,
    ArceusAlertDeliveryAttempt,
    ArceusAlertDeliveryChannel,
    ArceusCostStatistic,
    ArceusIncident,
    ArceusMetricSample,
    ArceusProviderHealth,
    ArceusRecoveryAction,
    ArceusSpan,
    ArceusTelemetryLog,
    ArceusTelemetryExporterConfig,
    ArceusTrace,
)


def test_log_redaction_removes_common_secret_patterns() -> None:
    response = redact_log(
        TelemetryLogIngestRequest(
            trace_id="trace-1",
            level="ERROR",
            message="failed with Bearer abc123 token=secret password=hunter2 sk-live",
            metadata={"api_key": "sk-test", "nested": {"secret": "secret=value"}},
        )
    )

    assert "abc123" not in response.message
    assert "hunter2" not in response.message
    assert "sk-live" not in response.message
    assert response.metadata["api_key"] == "[REDACTED]"
    assert response.redacted is True


def test_metric_summary_groups_samples() -> None:
    summaries = metric_summary(
        [
            MetricRecordRequest(metric_key="model_latency_ms", value=100, unit="ms"),
            MetricRecordRequest(metric_key="model_latency_ms", value=300, unit="ms"),
            MetricRecordRequest(metric_key="mission_cost_usd", value=2.5, unit="usd"),
        ]
    )

    by_key = {item.metric_key: item for item in summaries}
    assert by_key["model_latency_ms"].average_value == 200
    assert by_key["model_latency_ms"].maximum_value == 300
    assert by_key["mission_cost_usd"].latest_value == 2.5


def test_provider_health_recommends_reroute_for_degraded_provider() -> None:
    response = classify_provider_health(
        ProviderHealthRecordRequest(provider_key="openai", model_key="gpt-x", availability=0.9, latency_ms=6500, error_rate=0.08)
    )

    assert response.status == "degraded"
    assert response.reroute_recommended is True
    assert "alternate providers" in response.recommendation


def test_incident_response_adds_aiops_recommendations() -> None:
    response = incident_response(
        IncidentCreateRequest(
            severity="P1",
            title="Model provider rate limit",
            summary="Provider is rate limited and queue is growing.",
            related_alert_ids=["alert-1"],
        )
    )

    assert response.status == "detected"
    assert any("provider" in item.lower() for item in response.aiops_recommendations)
    assert any("postmortem" in item.lower() for item in response.aiops_recommendations)


def test_dashboard_recommendations_cover_alerts_incidents_cost_and_failures() -> None:
    recommendations = dashboard_recommendations(
        active_alerts=1,
        open_incidents=1,
        degraded_providers=1,
        total_cost=125,
        failed_missions=2,
    )

    assert any("alerts" in item.lower() for item in recommendations)
    assert any("incidents" in item.lower() for item in recommendations)
    assert any("cost" in item.lower() for item in recommendations)
    assert any("failure" in item.lower() for item in recommendations)


def test_alert_labels_are_redacted() -> None:
    response = alert_response(
        AlertCreateRequest(
            alert_key="token_leak",
            severity="P0",
            title="Token leak",
            description="Sensitive token appeared in logs.",
            labels={"token": "token=abc"},
        )
    )

    assert response.labels["token"] == "[REDACTED]"


def test_observability_persistence_models_have_correlation_fields() -> None:
    mission_id = uuid4()
    log = ArceusTelemetryLog(trace_id="trace-1", mission_id=mission_id, service="agent", level="INFO", message="ok")
    metric = ArceusMetricSample(metric_key="mission_cost", value=1.2, mission_id=mission_id, unit="usd")
    trace = ArceusTrace(trace_id="trace-1", mission_id=mission_id, service="agent", name="mission")
    span = ArceusSpan(trace_id="trace-1", span_id="span-1", span_type="model_call", name="call", service="agent", mission_id=mission_id)
    alert = ArceusAlert(alert_key="queue_depth", severity="P2", title="Queue depth", description="Queue high")
    incident = ArceusIncident(incident_key="inc-1", severity="P1", title="Provider outage", summary="Provider unavailable")
    provider = ArceusProviderHealth(provider_key="openai", availability=0.5, latency_ms=1000, error_rate=0.2)
    cost = ArceusCostStatistic(scope_type="mission", scope_id=str(mission_id), cost_type="model", amount_usd=Decimal("1.25"))
    exporter = ArceusTelemetryExporterConfig(exporter_key="tempo", exporter_type="tempo", target="http://tempo:4318", signal_types=["traces"])
    channel = ArceusAlertDeliveryChannel(channel_key="slack-p1", channel_type="slack", display_name="Slack P1", target="vault://slack", severity_filter=["P0", "P1"])
    attempt = ArceusAlertDeliveryAttempt(alert_id=uuid4(), channel_id=uuid4(), status="queued")
    recovery = ArceusRecoveryAction(action_key="retry-check", title="Retry check", action_type="retry_failed_check", policy_status="allowed")

    assert log.trace_id == "trace-1"
    assert metric.mission_id == mission_id
    assert span.trace_id == trace.trace_id
    assert alert.status is None or alert.status == "firing"
    assert incident.status is None or incident.status == "detected"
    assert provider.provider_key == "openai"
    assert to_float(cost.amount_usd) == 1.25
    assert exporter.exporter_type == "tempo"
    assert channel.channel_type == "slack"
    assert attempt.status == "queued"
    assert recovery.policy_status == "allowed"


def test_exporter_response_defaults_signals_by_backend() -> None:
    prometheus = exporter_response(ExporterConfigRequest(exporter_key="prom", exporter_type="prometheus", target="http://prometheus:9090"))
    loki = exporter_response(ExporterConfigRequest(exporter_key="loki", exporter_type="loki", target="http://loki:3100"))
    tempo = exporter_response(ExporterConfigRequest(exporter_key="tempo", exporter_type="tempo", target="http://tempo:3200"))

    assert prometheus.signal_types == ["metrics"]
    assert loki.signal_types == ["logs"]
    assert tempo.signal_types == ["traces"]


def test_alert_channel_filters_by_severity() -> None:
    channel = ArceusAlertDeliveryChannel(channel_type="teams", status="active", active=True, severity_filter=["P0", "P1"])

    assert delivery_channel_matches(channel, "P1") is True
    assert delivery_channel_matches(channel, "P3") is False


def test_low_risk_recovery_can_auto_execute_but_high_risk_blocks() -> None:
    low = recovery_policy_decision(
        RecoveryActionRequest(title="Retry failed check", action_type="retry_failed_check", risk_level="low", auto_execute=True)
    )
    high = recovery_policy_decision(
        RecoveryActionRequest(title="Rotate production secret", action_type="rotate_secret", risk_level="critical", auto_execute=True)
    )

    assert low.policy_status == "allowed"
    assert low.execution_status == "executed"
    assert low.approval_required is False
    assert high.policy_status == "denied"
    assert high.execution_status == "blocked"


def test_otel_span_emission_degrades_when_sdk_unavailable_or_unconfigured() -> None:
    result = emit_otel_span(trace_id="trace-1", span_id="span-1", name="verification", service="agent", span_type="verification", status="ok")

    assert "emitted" in result


def test_alert_delivery_worker_fails_cleanly_without_secret_resolution() -> None:
    alert = ArceusAlert(alert_key="queue_depth", severity="P1", title="Queue depth high", description="Worker queue is high.")
    channel = ArceusAlertDeliveryChannel(channel_key="slack", channel_type="slack", display_name="Slack", target="vault://slack-webhook", active=True, status="active")

    result = deliver_alert_attempt(alert=alert, channel=channel)

    assert result["status"] == "failed"
    assert result["error"]["reason"] == "secret_resolution_not_configured"


def test_alert_delivery_worker_rejects_invalid_webhook_target() -> None:
    alert = ArceusAlert(alert_key="queue_depth", severity="P1", title="Queue depth high", description="Worker queue is high.")
    channel = ArceusAlertDeliveryChannel(channel_key="webhook", channel_type="webhook", display_name="Webhook", target="not-a-url", active=True, status="active")

    result = deliver_alert_attempt(alert=alert, channel=channel)

    assert result["status"] == "failed"
    assert result["error"]["reason"] == "invalid_webhook_target"


def test_safe_recovery_executor_runs_only_allowlisted_actions() -> None:
    safe = execute_safe_recovery_action(action_type="clear_context_cache", parameters={"scope": "mission", "token": "secret-value"})
    unsafe = execute_safe_recovery_action(action_type="rotate_secret", parameters={})

    assert safe["executed"] is True
    assert safe["cache_scope"] == "mission"
    assert unsafe["executed"] is False


def test_otel_exporter_runtime_status_is_structured() -> None:
    status = otel_exporter_runtime_status()

    assert "ready" in status
    assert "sdk_installed" in status
    assert "configured_env" in status
