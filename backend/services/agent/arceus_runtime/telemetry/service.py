from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal
import json
import os
import re
import smtplib
from email.message import EmailMessage
from typing import Any
from urllib import request as urllib_request
from urllib.error import URLError

from services.shared.security import scrub_mapping

from .api_schemas import (
    AlertCreateRequest,
    AlertDeliveryChannelRequest,
    AlertResponse,
    ExporterConfigRequest,
    ExporterConfigResponse,
    IncidentCreateRequest,
    IncidentResponse,
    MetricRecordRequest,
    MetricSummaryResponse,
    ProviderHealthRecordRequest,
    ProviderHealthResponse,
    RecoveryActionRequest,
    RecoveryActionResponse,
    TelemetryLogIngestRequest,
    TelemetryLogResponse,
)


SECRET_VALUE_RE = re.compile(r"(sk-|Bearer\s+|password=|token=|secret=)[^\s,\]\}\)]+", re.IGNORECASE)
LOW_RISK_RECOVERY_ACTIONS = {
    "retry_failed_check",
    "restart_preview",
    "reroute_model_provider",
    "clear_context_cache",
    "refresh_github_checks",
    "requeue_worker_job",
}


def redact_sensitive(value: Any) -> Any:
    scrubbed = scrub_mapping(value)
    if isinstance(scrubbed, str):
        return SECRET_VALUE_RE.sub("[REDACTED]", scrubbed)
    if isinstance(scrubbed, dict):
        return {key: redact_sensitive(item) for key, item in scrubbed.items()}
    if isinstance(scrubbed, list):
        return [redact_sensitive(item) for item in scrubbed]
    return scrubbed


def redact_log(payload: TelemetryLogIngestRequest) -> TelemetryLogResponse:
    scrubbed_message = redact_sensitive(payload.message)
    scrubbed_metadata = redact_sensitive(payload.metadata)
    redacted = scrubbed_message != payload.message or scrubbed_metadata != payload.metadata
    return TelemetryLogResponse(
        trace_id=payload.trace_id,
        level=payload.level,
        service=payload.service,
        message=scrubbed_message,
        metadata=scrubbed_metadata,
        redacted=redacted,
        occurred_at=payload.occurred_at,
    )


def metric_summary(samples: list[MetricRecordRequest]) -> list[MetricSummaryResponse]:
    grouped: dict[str, list[MetricRecordRequest]] = defaultdict(list)
    for sample in samples:
        grouped[sample.metric_key].append(sample)
    summaries: list[MetricSummaryResponse] = []
    for metric_key, items in sorted(grouped.items()):
        values = [item.value for item in items]
        latest = sorted(items, key=lambda item: item.observed_at)[-1]
        summaries.append(
            MetricSummaryResponse(
                metric_key=metric_key,
                count=len(items),
                latest_value=latest.value,
                average_value=round(sum(values) / len(values), 4) if values else None,
                maximum_value=max(values) if values else None,
                unit=latest.unit,
            )
        )
    return summaries


def classify_provider_health(payload: ProviderHealthRecordRequest) -> ProviderHealthResponse:
    if payload.rate_limited:
        status = "rate_limited"
        recommendation = "Route latency-sensitive workloads to a non-rate-limited provider."
    elif payload.availability < 0.5 or payload.error_rate >= 0.5:
        status = "down"
        recommendation = "Fail over to the healthiest compatible provider immediately."
    elif payload.availability < 0.95 or payload.error_rate > 0.05 or payload.latency_ms > 5000:
        status = "degraded"
        recommendation = "Prefer alternate providers for high-priority missions until health recovers."
    else:
        status = "healthy"
        recommendation = "Provider is healthy."
    return ProviderHealthResponse(
        provider_key=payload.provider_key,
        model_key=payload.model_key,
        status=status,
        availability=payload.availability,
        latency_ms=payload.latency_ms,
        error_rate=payload.error_rate,
        reroute_recommended=status in {"degraded", "down", "rate_limited"},
        recommendation=recommendation,
    )


def alert_response(payload: AlertCreateRequest) -> AlertResponse:
    return AlertResponse(
        alert_key=payload.alert_key,
        severity=payload.severity,
        status="firing",
        title=payload.title,
        description=payload.description,
        labels=redact_sensitive(payload.labels),
        fired_at=datetime.now(timezone.utc),
    )


def incident_recommendations(payload: IncidentCreateRequest) -> list[str]:
    text = f"{payload.title} {payload.summary}".lower()
    recommendations: list[str] = []
    if "provider" in text or "model" in text or "rate limit" in text:
        recommendations.append("Switch affected missions to a healthier model provider.")
    if "queue" in text or "worker" in text:
        recommendations.append("Scale workers or restart the unhealthy worker pool.")
    if "database" in text or "postgres" in text:
        recommendations.append("Check database readiness, connection pool saturation, and recent migrations.")
    if "cost" in text or "token" in text:
        recommendations.append("Apply model routing budget caps and investigate token-heavy workflows.")
    if "security" in text or "secret" in text:
        recommendations.append("Escalate to Security Reviewer and preserve audit evidence.")
    if not recommendations:
        recommendations.append("Triage recent traces, logs, alerts, and deployment changes for a likely cause.")
    if payload.severity in {"P0", "P1"}:
        recommendations.append("Create a postmortem draft after resolution and promote validated lessons to memory.")
    return recommendations


def incident_response(payload: IncidentCreateRequest) -> IncidentResponse:
    return IncidentResponse(
        incident_key=payload.incident_key,
        severity=payload.severity,
        status="detected",
        title=payload.title,
        summary=redact_sensitive(payload.summary),
        aiops_recommendations=incident_recommendations(payload),
        opened_at=datetime.now(timezone.utc),
    )


def to_float(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    if value is None:
        return 0.0
    return float(value)


def dashboard_recommendations(*, active_alerts: int, open_incidents: int, degraded_providers: int, total_cost: float, failed_missions: int) -> list[str]:
    recommendations: list[str] = []
    if active_alerts:
        recommendations.append("Review active alerts before approving new deployments.")
    if open_incidents:
        recommendations.append("Assign owners for open incidents and collect trace-linked evidence.")
    if degraded_providers:
        recommendations.append("Reroute model traffic away from degraded providers.")
    if total_cost > 100:
        recommendations.append("Inspect model cost by mission and enable cheaper fallback routing where quality allows.")
    if failed_missions:
        recommendations.append("Run failure clustering to identify repeated workflow or tool issues.")
    if not recommendations:
        recommendations.append("Operations are stable; continue monitoring latency, cost, and mission success trends.")
    return recommendations


def emit_otel_span(*, trace_id: str, span_id: str, name: str, service: str, span_type: str, status: str, attributes: dict[str, Any] | None = None) -> dict[str, Any]:
    """Emit an optional OpenTelemetry SDK span when the SDK is installed.

    Arceus always persists span rows in Postgres. This helper mirrors the same
    event to configured OTEL exporters without making OpenTelemetry a hard
    dependency for local development.
    """
    try:
        from opentelemetry import trace  # type: ignore
        from opentelemetry.trace import Status, StatusCode  # type: ignore
    except Exception:
        return {"emitted": False, "reason": "opentelemetry_sdk_unavailable"}

    tracer = trace.get_tracer(service)
    safe_attributes = redact_sensitive(attributes or {})
    with tracer.start_as_current_span(name, attributes={**safe_attributes, "arceus.trace_id": trace_id, "arceus.span_id": span_id, "arceus.span_type": span_type}) as span:
        if status == "error":
            span.set_status(Status(StatusCode.ERROR))
        else:
            span.set_status(Status(StatusCode.OK))
    return {"emitted": True, "trace_id": trace_id, "span_id": span_id}


def exporter_response(payload: ExporterConfigRequest, *, exporter_id=None, status: str = "configured") -> ExporterConfigResponse:
    return ExporterConfigResponse(
        exporter_id=exporter_id,
        exporter_key=payload.exporter_key,
        exporter_type=payload.exporter_type,
        target=payload.target,
        status=status,
        signal_types=payload.signal_types or default_signals(payload.exporter_type),
        sample_rate=payload.sample_rate,
        active=payload.active,
    )


def default_signals(exporter_type: str) -> list[str]:
    if exporter_type == "prometheus":
        return ["metrics"]
    if exporter_type == "loki":
        return ["logs"]
    if exporter_type == "tempo":
        return ["traces"]
    return ["logs", "metrics", "traces"]


def delivery_channel_matches(channel, severity: str) -> bool:
    if not getattr(channel, "active", True) or getattr(channel, "status", "active") != "active":
        return False
    allowed = getattr(channel, "severity_filter", None) or []
    return not allowed or severity in allowed


def recovery_policy_decision(payload: RecoveryActionRequest) -> RecoveryActionResponse:
    low_risk = payload.risk_level == "low" and payload.action_type in LOW_RISK_RECOVERY_ACTIONS
    if payload.risk_level in {"high", "critical"}:
        policy_status = "denied" if payload.auto_execute else "needs_approval"
        execution_status = "blocked" if payload.auto_execute else "proposed"
        approval_required = True
        result = {"reason": "High-risk recovery requires explicit human approval."}
    elif low_risk:
        policy_status = "allowed"
        execution_status = "executed" if payload.auto_execute else "proposed"
        approval_required = False
        result = {"reason": "Low-risk recovery action is allowed by policy.", "auto_executed": payload.auto_execute}
    else:
        policy_status = "needs_approval"
        execution_status = "proposed"
        approval_required = True
        result = {"reason": "Recovery action needs policy approval before execution."}
    return RecoveryActionResponse(
        action_key=payload.action_key,
        title=payload.title,
        risk_level=payload.risk_level,
        policy_status=policy_status,
        execution_status=execution_status,
        action_type=payload.action_type,
        approval_required=approval_required,
        result=result,
    )


def build_alert_delivery_payload(*, alert, channel) -> dict[str, Any]:
    payload = {
        "title": getattr(alert, "title", "Arceus alert"),
        "text": getattr(alert, "description", ""),
        "severity": getattr(alert, "severity", "P3"),
        "alert_key": getattr(alert, "alert_key", None),
        "source": getattr(alert, "source", "arceus"),
        "labels": redact_sensitive(getattr(alert, "labels", {}) or {}),
    }
    if getattr(channel, "channel_type", "") in {"slack", "teams"}:
        return {
            "text": f"[{payload['severity']}] {payload['title']}",
            "attachments": [{"text": payload["text"], "fields": [{"title": "Alert", "value": payload["alert_key"] or "unknown", "short": True}]}],
        }
    return payload


def deliver_alert_attempt(*, alert, channel, timeout_seconds: float = 5.0) -> dict[str, Any]:
    if getattr(channel, "status", "active") != "active" or not getattr(channel, "active", True):
        return {"status": "suppressed", "response": {}, "error": {"reason": "channel_disabled"}}

    target = getattr(channel, "target", "") or ""
    channel_type = getattr(channel, "channel_type", "")
    payload = build_alert_delivery_payload(alert=alert, channel=channel)

    if target.startswith("vault://") or getattr(channel, "secret_ref", None):
        return {
            "status": "failed",
            "response": {},
            "error": {"reason": "secret_resolution_not_configured", "next_action": "Configure vault-backed delivery secret worker."},
        }

    if channel_type in {"webhook", "slack", "teams"}:
        if not target.startswith(("https://", "http://")):
            return {"status": "failed", "response": {}, "error": {"reason": "invalid_webhook_target"}}
        try:
            body = json.dumps(redact_sensitive(payload)).encode("utf-8")
            req = urllib_request.Request(target, data=body, headers={"Content-Type": "application/json"}, method="POST")
            with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
                return {
                    "status": "sent" if 200 <= response.status < 300 else "failed",
                    "response": {"status_code": response.status, "reason": response.reason},
                    "error": {} if 200 <= response.status < 300 else {"reason": "non_2xx_response"},
                }
        except URLError as exc:
            return {"status": "failed", "response": {}, "error": {"reason": "delivery_error", "detail": redact_sensitive(str(exc))}}

    if channel_type == "email":
        smtp_host = os.getenv("ARCEUS_SMTP_HOST")
        smtp_port = int(os.getenv("ARCEUS_SMTP_PORT", "587"))
        smtp_user = os.getenv("ARCEUS_SMTP_USER")
        smtp_password = os.getenv("ARCEUS_SMTP_PASSWORD")
        sender = os.getenv("ARCEUS_ALERT_FROM_EMAIL")
        if not smtp_host or not sender:
            return {"status": "failed", "response": {}, "error": {"reason": "smtp_not_configured"}}
        message = EmailMessage()
        message["Subject"] = f"[{payload['severity']}] {payload['title']}"
        message["From"] = sender
        message["To"] = target
        message.set_content(f"{payload['text']}\n\nAlert: {payload['alert_key']}")
        try:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout_seconds) as smtp:
                smtp.starttls()
                if smtp_user and smtp_password:
                    smtp.login(smtp_user, smtp_password)
                smtp.send_message(message)
            return {"status": "sent", "response": {"transport": "smtp"}, "error": {}}
        except Exception as exc:
            return {"status": "failed", "response": {}, "error": {"reason": "smtp_delivery_error", "detail": redact_sensitive(str(exc))}}

    return {"status": "failed", "response": {}, "error": {"reason": f"unsupported_channel_type:{channel_type}"}}


def execute_safe_recovery_action(*, action_type: str, parameters: dict[str, Any]) -> dict[str, Any]:
    if action_type not in LOW_RISK_RECOVERY_ACTIONS:
        return {"executed": False, "reason": "Action type is not in the low-risk executor allowlist."}
    safe_parameters = redact_sensitive(parameters or {})
    if action_type == "retry_failed_check":
        return {"executed": True, "operation": "retry_failed_check", "queued": True, "parameters": safe_parameters}
    if action_type == "restart_preview":
        return {"executed": True, "operation": "restart_preview", "queued": True, "parameters": safe_parameters}
    if action_type == "reroute_model_provider":
        return {"executed": True, "operation": "reroute_model_provider", "policy": "prefer_healthiest_compatible_provider", "parameters": safe_parameters}
    if action_type == "clear_context_cache":
        return {"executed": True, "operation": "clear_context_cache", "cache_scope": safe_parameters.get("scope", "mission")}
    if action_type == "refresh_github_checks":
        return {"executed": True, "operation": "refresh_github_checks", "queued": True, "parameters": safe_parameters}
    if action_type == "requeue_worker_job":
        return {"executed": True, "operation": "requeue_worker_job", "queued": True, "parameters": safe_parameters}
    return {"executed": False, "reason": "No executor implemented for action type."}


def otel_exporter_runtime_status() -> dict[str, Any]:
    configured = {
        "OTEL_EXPORTER_OTLP_ENDPOINT": bool(os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")),
        "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT": bool(os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT")),
        "OTEL_EXPORTER_OTLP_METRICS_ENDPOINT": bool(os.getenv("OTEL_EXPORTER_OTLP_METRICS_ENDPOINT")),
        "OTEL_EXPORTER_OTLP_LOGS_ENDPOINT": bool(os.getenv("OTEL_EXPORTER_OTLP_LOGS_ENDPOINT")),
    }
    try:
        import opentelemetry  # type: ignore  # noqa: F401

        sdk_installed = True
    except Exception:
        sdk_installed = False
    ready = sdk_installed and any(configured.values())
    return {
        "ready": ready,
        "sdk_installed": sdk_installed,
        "configured_env": configured,
        "next_action": None if ready else "Install OpenTelemetry exporter packages and set OTLP endpoint environment variables.",
    }
