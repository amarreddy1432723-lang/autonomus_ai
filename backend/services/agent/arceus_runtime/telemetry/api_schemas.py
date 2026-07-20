from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


LogLevel = Literal["TRACE", "DEBUG", "INFO", "WARN", "ERROR", "FATAL"]
MetricType = Literal["counter", "gauge", "histogram", "summary"]
SpanType = Literal["http", "database", "model_call", "tool_execution", "verification", "planning", "compilation", "deployment", "background_task"]
TraceStatus = Literal["running", "ok", "error", "cancelled"]
AlertSeverity = Literal["P0", "P1", "P2", "P3"]
AlertStatus = Literal["firing", "acknowledged", "resolved", "suppressed"]
IncidentStatus = Literal["detected", "classified", "assigned", "investigating", "resolved", "postmortem"]
ExporterType = Literal["prometheus", "loki", "tempo", "otlp_http", "otlp_grpc", "sentry"]
AlertChannelType = Literal["slack", "email", "teams", "webhook"]
DeliveryStatus = Literal["queued", "sent", "failed", "suppressed"]
RecoveryRiskLevel = Literal["low", "moderate", "high", "critical"]
RecoveryPolicyStatus = Literal["pending_policy", "allowed", "needs_approval", "denied"]
RecoveryExecutionStatus = Literal["proposed", "queued", "executed", "failed", "cancelled", "blocked"]


class TelemetrySchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class TelemetryLogIngestRequest(TelemetrySchema):
    trace_id: str = Field(default_factory=lambda: f"trace_{uuid4().hex[:16]}", max_length=160)
    span_id: str | None = Field(default=None, max_length=160)
    mission_id: UUID | None = None
    workflow_id: UUID | None = None
    agent_id: str | None = Field(default=None, max_length=160)
    service: str = Field(default="agent", max_length=160)
    level: LogLevel = "INFO"
    message: str = Field(min_length=1, max_length=5000)
    metadata: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TelemetryLogResponse(TelemetrySchema):
    log_id: UUID | None = None
    trace_id: str
    level: LogLevel
    service: str
    message: str
    metadata: dict[str, Any]
    redacted: bool
    occurred_at: datetime


class MetricRecordRequest(TelemetrySchema):
    metric_key: str = Field(min_length=1, max_length=160)
    metric_type: MetricType = "gauge"
    value: float
    unit: str = Field(default="count", max_length=80)
    service: str | None = Field(default=None, max_length=160)
    mission_id: UUID | None = None
    workflow_id: UUID | None = None
    model_key: str | None = Field(default=None, max_length=160)
    provider_key: str | None = Field(default=None, max_length=160)
    labels: dict[str, Any] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MetricSummaryResponse(TelemetrySchema):
    metric_key: str
    count: int
    latest_value: float | None
    average_value: float | None
    maximum_value: float | None
    unit: str | None


class SpanRecordRequest(TelemetrySchema):
    trace_id: str = Field(min_length=1, max_length=160)
    span_id: str = Field(default_factory=lambda: f"span_{uuid4().hex[:12]}", max_length=160)
    parent_span_id: str | None = Field(default=None, max_length=160)
    span_type: SpanType
    name: str = Field(min_length=1, max_length=500)
    service: str = Field(default="agent", max_length=160)
    mission_id: UUID | None = None
    workflow_id: UUID | None = None
    node_id: str | None = Field(default=None, max_length=160)
    agent_id: str | None = Field(default=None, max_length=160)
    status: TraceStatus = "ok"
    duration_ms: float | None = Field(default=None, ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)


class TraceResponse(TelemetrySchema):
    trace_id: str
    mission_id: UUID | None
    service: str
    name: str
    status: TraceStatus
    duration_ms: float | None
    span_count: int
    error_span_count: int
    spans: list[dict[str, Any]]


class AlertCreateRequest(TelemetrySchema):
    alert_key: str = Field(min_length=1, max_length=160)
    severity: AlertSeverity
    title: str = Field(min_length=1, max_length=500)
    description: str = Field(min_length=1, max_length=2000)
    source: str = Field(default="arceus", max_length=160)
    trace_id: str | None = Field(default=None, max_length=160)
    mission_id: UUID | None = None
    labels: dict[str, Any] = Field(default_factory=dict)
    annotations: dict[str, Any] = Field(default_factory=dict)


class AlertResponse(TelemetrySchema):
    alert_id: UUID | None = None
    alert_key: str
    severity: AlertSeverity
    status: AlertStatus
    title: str
    description: str
    labels: dict[str, Any]
    fired_at: datetime


class IncidentCreateRequest(TelemetrySchema):
    incident_key: str = Field(default_factory=lambda: f"incident_{uuid4().hex[:12]}", max_length=160)
    severity: AlertSeverity
    title: str = Field(min_length=1, max_length=500)
    summary: str = Field(min_length=1, max_length=5000)
    related_alert_ids: list[str] = Field(default_factory=list, max_length=100)
    trace_id: str | None = Field(default=None, max_length=160)
    mission_id: UUID | None = None


class IncidentResponse(TelemetrySchema):
    incident_id: UUID | None = None
    incident_key: str
    severity: AlertSeverity
    status: IncidentStatus
    title: str
    summary: str
    aiops_recommendations: list[str]
    opened_at: datetime


class ProviderHealthRecordRequest(TelemetrySchema):
    provider_key: str = Field(min_length=1, max_length=160)
    model_key: str | None = Field(default=None, max_length=160)
    availability: float = Field(default=1.0, ge=0, le=1)
    latency_ms: float = Field(default=0.0, ge=0)
    error_rate: float = Field(default=0.0, ge=0, le=1)
    rate_limited: bool = False
    cost_per_1k_tokens: float = Field(default=0.0, ge=0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderHealthResponse(TelemetrySchema):
    provider_key: str
    model_key: str | None
    status: Literal["healthy", "degraded", "down", "rate_limited"]
    availability: float
    latency_ms: float
    error_rate: float
    reroute_recommended: bool
    recommendation: str


class MissionStatisticRecordRequest(TelemetrySchema):
    mission_id: UUID
    status: str = Field(max_length=60)
    duration_ms: float = Field(default=0.0, ge=0)
    retry_count: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0)
    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    success: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class CostStatisticRecordRequest(TelemetrySchema):
    scope_type: str = Field(max_length=80)
    scope_id: str = Field(max_length=160)
    cost_type: str = Field(max_length=80)
    amount_usd: float = Field(default=0.0, ge=0)
    units: float = Field(default=0.0, ge=0)
    provider_key: str | None = Field(default=None, max_length=160)
    model_key: str | None = Field(default=None, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DashboardResponse(TelemetrySchema):
    dashboard_key: str
    health_score: float
    mission_summary: dict[str, Any]
    ai_usage: dict[str, Any]
    cost_summary: dict[str, Any]
    active_alerts: list[dict[str, Any]]
    open_incidents: list[dict[str, Any]]
    provider_health: list[dict[str, Any]]
    aiops_recommendations: list[str]


class ExporterConfigRequest(TelemetrySchema):
    exporter_key: str = Field(min_length=1, max_length=160)
    exporter_type: ExporterType
    target: str = Field(min_length=1, max_length=2000)
    signal_types: list[Literal["logs", "metrics", "traces"]] = Field(default_factory=list, max_length=10)
    headers: dict[str, Any] = Field(default_factory=dict)
    sample_rate: float = Field(default=1.0, ge=0, le=1)
    metadata: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class ExporterConfigResponse(TelemetrySchema):
    exporter_id: UUID | None = None
    exporter_key: str
    exporter_type: ExporterType
    target: str
    status: Literal["configured", "active", "disabled", "error"]
    signal_types: list[str]
    sample_rate: float
    active: bool


class AlertDeliveryChannelRequest(TelemetrySchema):
    channel_key: str = Field(min_length=1, max_length=160)
    channel_type: AlertChannelType
    display_name: str = Field(min_length=1, max_length=500)
    target: str = Field(min_length=1, max_length=2000)
    severity_filter: list[AlertSeverity] = Field(default_factory=list, max_length=4)
    secret_ref: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)
    active: bool = True


class AlertDeliveryChannelResponse(TelemetrySchema):
    channel_id: UUID | None = None
    channel_key: str
    channel_type: AlertChannelType
    display_name: str
    target: str
    severity_filter: list[AlertSeverity]
    status: Literal["active", "disabled", "error"]
    active: bool


class AlertDeliveryAttemptResponse(TelemetrySchema):
    attempt_id: UUID | None = None
    alert_id: UUID
    channel_id: UUID
    channel_type: AlertChannelType | None = None
    status: DeliveryStatus
    attempt_number: int
    response: dict[str, Any]
    error: dict[str, Any]


class RecoveryActionRequest(TelemetrySchema):
    action_key: str = Field(default_factory=lambda: f"recovery_{uuid4().hex[:12]}", max_length=160)
    title: str = Field(min_length=1, max_length=500)
    trigger_alert_key: str | None = Field(default=None, max_length=160)
    incident_id: UUID | None = None
    risk_level: RecoveryRiskLevel = "low"
    action_type: str = Field(min_length=1, max_length=120)
    parameters: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    auto_execute: bool = False


class RecoveryActionResponse(TelemetrySchema):
    recovery_action_id: UUID | None = None
    action_key: str
    title: str
    risk_level: RecoveryRiskLevel
    policy_status: RecoveryPolicyStatus
    execution_status: RecoveryExecutionStatus
    action_type: str
    approval_required: bool
    result: dict[str, Any]


class MissionControlObservabilityResponse(TelemetrySchema):
    traces: list[dict[str, Any]]
    logs: list[dict[str, Any]]
    alerts: list[dict[str, Any]]
    incidents: list[dict[str, Any]]
    exporters: list[dict[str, Any]]
    delivery_channels: list[dict[str, Any]]
    recovery_actions: list[dict[str, Any]]
    aiops_recommendations: list[str]
