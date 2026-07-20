from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusAlert,
    ArceusAlertDeliveryAttempt,
    ArceusAlertDeliveryChannel,
    ArceusCostStatistic,
    ArceusRecoveryAction,
    ArceusIncident,
    ArceusMetricSample,
    ArceusMissionStatistic,
    ArceusProviderHealth,
    ArceusSpan,
    ArceusTelemetryLog,
    ArceusTelemetryExporterConfig,
    ArceusTrace,
)
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    AlertCreateRequest,
    AlertDeliveryChannelRequest,
    CostStatisticRecordRequest,
    DashboardResponse,
    ExporterConfigRequest,
    IncidentCreateRequest,
    MetricRecordRequest,
    MissionControlObservabilityResponse,
    MetricSummaryResponse,
    MissionStatisticRecordRequest,
    ProviderHealthRecordRequest,
    RecoveryActionRequest,
    SpanRecordRequest,
    TelemetryLogIngestRequest,
    TraceResponse,
)
from .service import (
    alert_response,
    classify_provider_health,
    dashboard_recommendations,
    deliver_alert_attempt,
    delivery_channel_matches,
    emit_otel_span,
    execute_safe_recovery_action,
    exporter_response,
    recovery_policy_decision,
    incident_response,
    metric_summary,
    otel_exporter_runtime_status,
    redact_log,
    to_float,
)


router = APIRouter(prefix="/api/v1/telemetry", tags=["telemetry-aiops"])


def _audit(db: Session, context: RequestContext, *, action: str, resource_type: str, resource_id, result: str, metadata: dict) -> None:
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        result=result,
        metadata={**metadata, "correlation_id": str(context.correlation_id)},
    )


@router.post("/logs")
def ingest_log(
    payload: TelemetryLogIngestRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("telemetry.write")),
    db: Session = Depends(get_db),
):
    response = redact_log(payload)
    row = ArceusTelemetryLog(
        tenant_id=context.tenant_id,
        trace_id=payload.trace_id,
        span_id=payload.span_id,
        mission_id=payload.mission_id,
        workflow_id=payload.workflow_id,
        agent_id=payload.agent_id,
        user_id=context.user_id,
        service=payload.service,
        level=payload.level,
        message=response.message,
        metadata_json=response.metadata,
        occurred_at=payload.occurred_at,
    )
    db.add(row)
    db.flush()
    response.log_id = row.id
    _audit(db, context, action="TELEMETRY_LOG_INGESTED", resource_type="telemetry_log", resource_id=row.id, result="stored", metadata={"trace_id": payload.trace_id, "level": payload.level, "redacted": response.redacted})
    db.commit()
    return api_response(response.model_dump(mode="json"), request)


@router.get("/logs")
def list_logs(
    request: Request,
    context: RequestContext = Depends(require_permission("telemetry.view")),
    trace_id: str | None = Query(default=None, max_length=160),
    mission_id: UUID | None = None,
    level: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusTelemetryLog).filter(ArceusTelemetryLog.tenant_id == context.tenant_id)
    if trace_id:
        query = query.filter(ArceusTelemetryLog.trace_id == trace_id)
    if mission_id:
        query = query.filter(ArceusTelemetryLog.mission_id == mission_id)
    if level:
        query = query.filter(ArceusTelemetryLog.level == level.upper())
    rows = query.order_by(ArceusTelemetryLog.occurred_at.desc()).limit(limit).all()
    data = [
        {
            "log_id": str(row.id),
            "trace_id": row.trace_id,
            "span_id": row.span_id,
            "mission_id": str(row.mission_id) if row.mission_id else None,
            "service": row.service,
            "level": row.level,
            "message": row.message,
            "metadata": row.metadata_json,
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        }
        for row in rows
    ]
    return collection_response(data, request)


@router.post("/metrics")
def record_metric(
    payload: MetricRecordRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("telemetry.write")),
    db: Session = Depends(get_db),
):
    row = ArceusMetricSample(
        tenant_id=context.tenant_id,
        metric_key=payload.metric_key,
        metric_type=payload.metric_type,
        value=payload.value,
        unit=payload.unit,
        service=payload.service,
        mission_id=payload.mission_id,
        workflow_id=payload.workflow_id,
        model_key=payload.model_key,
        provider_key=payload.provider_key,
        labels=payload.labels,
        observed_at=payload.observed_at,
    )
    db.add(row)
    db.flush()
    _audit(db, context, action="METRIC_RECORDED", resource_type="metric", resource_id=row.id, result="stored", metadata={"metric_key": payload.metric_key, "value": payload.value, "unit": payload.unit})
    db.commit()
    return api_response({"metric_id": str(row.id), "metric_key": row.metric_key, "value": row.value, "unit": row.unit}, request)


@router.get("/metrics")
def get_metrics(
    request: Request,
    context: RequestContext = Depends(require_permission("telemetry.view")),
    metric_key: str | None = Query(default=None, max_length=160),
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusMetricSample).filter(ArceusMetricSample.tenant_id == context.tenant_id)
    if metric_key:
        query = query.filter(ArceusMetricSample.metric_key == metric_key)
    rows = query.order_by(ArceusMetricSample.observed_at.desc()).limit(limit).all()
    payloads = [
        MetricRecordRequest(
            metric_key=row.metric_key,
            metric_type=row.metric_type,
            value=row.value,
            unit=row.unit,
            service=row.service,
            mission_id=row.mission_id,
            workflow_id=row.workflow_id,
            model_key=row.model_key,
            provider_key=row.provider_key,
            labels=row.labels or {},
            observed_at=row.observed_at,
        )
        for row in rows
    ]
    summaries = [item.model_dump(mode="json") for item in metric_summary(payloads)]
    return api_response({"summaries": summaries, "sample_count": len(rows)}, request)


@router.post("/spans")
def record_span(
    payload: SpanRecordRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("telemetry.write")),
    db: Session = Depends(get_db),
):
    trace = db.query(ArceusTrace).filter(ArceusTrace.tenant_id == context.tenant_id, ArceusTrace.trace_id == payload.trace_id).first()
    if trace is None:
        trace = ArceusTrace(
            tenant_id=context.tenant_id,
            trace_id=payload.trace_id,
            root_span_id=payload.parent_span_id or payload.span_id,
            mission_id=payload.mission_id,
            workflow_id=payload.workflow_id,
            user_id=context.user_id,
            service=payload.service,
            name=payload.name,
            status="running" if payload.status == "ok" else "error",
            duration_ms=payload.duration_ms,
            metadata_json={"created_from_span": payload.span_id},
        )
        db.add(trace)
    if payload.status == "error":
        trace.status = "error"
    if payload.duration_ms is not None:
        trace.duration_ms = max(trace.duration_ms or 0, payload.duration_ms)
    span = ArceusSpan(
        tenant_id=context.tenant_id,
        trace_id=payload.trace_id,
        span_id=payload.span_id,
        parent_span_id=payload.parent_span_id,
        span_type=payload.span_type,
        name=payload.name,
        service=payload.service,
        mission_id=payload.mission_id,
        workflow_id=payload.workflow_id,
        node_id=payload.node_id,
        agent_id=payload.agent_id,
        status=payload.status if payload.status != "running" else "ok",
        duration_ms=payload.duration_ms,
        attributes=payload.attributes,
    )
    db.add(span)
    db.flush()
    otel = emit_otel_span(
        trace_id=payload.trace_id,
        span_id=payload.span_id,
        name=payload.name,
        service=payload.service,
        span_type=payload.span_type,
        status=span.status,
        attributes=payload.attributes,
    )
    _audit(db, context, action="TRACE_SPAN_RECORDED", resource_type="span", resource_id=span.id, result=span.status, metadata={"trace_id": payload.trace_id, "span_type": payload.span_type, "otel": otel})
    db.commit()
    return api_response({"span_id": str(span.id), "trace_id": payload.trace_id, "status": span.status, "otel": otel}, request)


@router.get("/traces/{trace_id}")
def get_trace(
    trace_id: str,
    request: Request,
    context: RequestContext = Depends(require_permission("telemetry.view")),
    db: Session = Depends(get_db),
):
    trace = db.query(ArceusTrace).filter(ArceusTrace.tenant_id == context.tenant_id, ArceusTrace.trace_id == trace_id).first()
    spans = db.query(ArceusSpan).filter(ArceusSpan.tenant_id == context.tenant_id, ArceusSpan.trace_id == trace_id).order_by(ArceusSpan.started_at.asc()).all()
    response = TraceResponse(
        trace_id=trace_id,
        mission_id=trace.mission_id if trace else None,
        service=trace.service if trace else "unknown",
        name=trace.name if trace else "trace",
        status=trace.status if trace else ("error" if any(span.status == "error" for span in spans) else "ok"),
        duration_ms=trace.duration_ms if trace else None,
        span_count=len(spans),
        error_span_count=sum(1 for span in spans if span.status == "error"),
        spans=[
            {
                "span_id": span.span_id,
                "parent_span_id": span.parent_span_id,
                "span_type": span.span_type,
                "name": span.name,
                "service": span.service,
                "status": span.status,
                "duration_ms": span.duration_ms,
                "attributes": span.attributes,
            }
            for span in spans
        ],
    )
    return api_response(response.model_dump(mode="json"), request)


@router.post("/provider-health")
def record_provider_health(
    payload: ProviderHealthRecordRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("telemetry.write")),
    db: Session = Depends(get_db),
):
    response = classify_provider_health(payload)
    row = ArceusProviderHealth(
        tenant_id=context.tenant_id,
        provider_key=payload.provider_key,
        model_key=payload.model_key,
        availability=payload.availability,
        latency_ms=payload.latency_ms,
        error_rate=payload.error_rate,
        rate_limited=payload.rate_limited,
        cost_per_1k_tokens=payload.cost_per_1k_tokens,
        status=response.status,
        metadata_json=payload.metadata,
    )
    db.add(row)
    db.flush()
    _audit(db, context, action="PROVIDER_HEALTH_RECORDED", resource_type="provider_health", resource_id=row.id, result=response.status, metadata=response.model_dump(mode="json"))
    db.commit()
    return api_response(response.model_dump(mode="json"), request)


@router.post("/alerts")
def create_alert(
    payload: AlertCreateRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("alert.manage")),
    db: Session = Depends(get_db),
):
    response = alert_response(payload)
    row = ArceusAlert(
        tenant_id=context.tenant_id,
        alert_key=payload.alert_key,
        severity=payload.severity,
        status="firing",
        title=payload.title,
        description=payload.description,
        source=payload.source,
        trace_id=payload.trace_id,
        mission_id=payload.mission_id,
        labels=response.labels,
        annotations=payload.annotations,
    )
    db.add(row)
    db.flush()
    response.alert_id = row.id
    channels = db.query(ArceusAlertDeliveryChannel).filter(ArceusAlertDeliveryChannel.tenant_id == context.tenant_id).all()
    attempts = []
    for channel in channels:
        status = "queued" if delivery_channel_matches(channel, row.severity) else "suppressed"
        attempt = ArceusAlertDeliveryAttempt(
            tenant_id=context.tenant_id,
            alert_id=row.id,
            channel_id=channel.id,
            status=status,
            attempt_number=1,
            response={"queued": True, "channel_type": channel.channel_type} if status == "queued" else {},
            error={} if status == "queued" else {"reason": "severity_filter_or_channel_disabled"},
        )
        db.add(attempt)
        attempts.append(attempt)
    _audit(db, context, action="ALERT_CREATED", resource_type="alert", resource_id=row.id, result=row.status, metadata={"severity": row.severity, "alert_key": row.alert_key})
    db.commit()
    return api_response(response.model_dump(mode="json"), request, delivery={"attempt_count": len(attempts), "queued": sum(1 for item in attempts if item.status == "queued")})


@router.get("/alerts")
def list_alerts(
    request: Request,
    context: RequestContext = Depends(require_permission("alert.view")),
    status: str | None = Query(default=None, max_length=40),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusAlert).filter(ArceusAlert.tenant_id == context.tenant_id)
    if status:
        query = query.filter(ArceusAlert.status == status)
    rows = query.order_by(ArceusAlert.fired_at.desc()).limit(limit).all()
    return collection_response(
        [
            {"alert_id": str(row.id), "alert_key": row.alert_key, "severity": row.severity, "status": row.status, "title": row.title, "description": row.description, "labels": row.labels, "fired_at": row.fired_at.isoformat() if row.fired_at else None}
            for row in rows
        ],
        request,
    )


@router.post("/incidents")
def create_incident(
    payload: IncidentCreateRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("incident.manage")),
    db: Session = Depends(get_db),
):
    response = incident_response(payload)
    row = ArceusIncident(
        tenant_id=context.tenant_id,
        incident_key=payload.incident_key,
        severity=payload.severity,
        status=response.status,
        title=payload.title,
        summary=response.summary,
        related_alert_ids=payload.related_alert_ids,
        trace_id=payload.trace_id,
        mission_id=payload.mission_id,
        aiops_recommendations=response.aiops_recommendations,
    )
    db.add(row)
    db.flush()
    response.incident_id = row.id
    _audit(db, context, action="INCIDENT_CREATED", resource_type="incident", resource_id=row.id, result=row.status, metadata={"severity": row.severity, "recommendations": row.aiops_recommendations})
    db.commit()
    return api_response(response.model_dump(mode="json"), request)


@router.post("/mission-statistics")
def record_mission_statistic(
    payload: MissionStatisticRecordRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("telemetry.write")),
    db: Session = Depends(get_db),
):
    data = payload.model_dump(mode="python")
    metadata = data.pop("metadata")
    row = ArceusMissionStatistic(tenant_id=context.tenant_id, metadata_json=metadata, **data)
    db.add(row)
    db.flush()
    db.commit()
    return api_response({"mission_statistic_id": str(row.id), "mission_id": str(row.mission_id), "success": row.success}, request)


@router.post("/cost-statistics")
def record_cost_statistic(
    payload: CostStatisticRecordRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("telemetry.write")),
    db: Session = Depends(get_db),
):
    data = payload.model_dump(mode="python")
    metadata = data.pop("metadata")
    row = ArceusCostStatistic(tenant_id=context.tenant_id, metadata_json=metadata, **data)
    db.add(row)
    db.flush()
    db.commit()
    return api_response({"cost_statistic_id": str(row.id), "scope_type": row.scope_type, "amount_usd": float(row.amount_usd)}, request)


@router.get("/dashboard")
def get_dashboard(
    request: Request,
    context: RequestContext = Depends(require_permission("telemetry.dashboard.view")),
    db: Session = Depends(get_db),
):
    mission_rows = db.query(ArceusMissionStatistic).filter(ArceusMissionStatistic.tenant_id == context.tenant_id).all()
    cost_rows = db.query(ArceusCostStatistic).filter(ArceusCostStatistic.tenant_id == context.tenant_id).all()
    alert_rows = db.query(ArceusAlert).filter(ArceusAlert.tenant_id == context.tenant_id, ArceusAlert.status == "firing").order_by(ArceusAlert.fired_at.desc()).limit(20).all()
    incident_rows = db.query(ArceusIncident).filter(ArceusIncident.tenant_id == context.tenant_id, ArceusIncident.status != "resolved").order_by(ArceusIncident.opened_at.desc()).limit(20).all()
    provider_rows = db.query(ArceusProviderHealth).filter(ArceusProviderHealth.tenant_id == context.tenant_id).order_by(ArceusProviderHealth.observed_at.desc()).limit(20).all()
    total_cost = sum(to_float(row.amount_usd) for row in cost_rows)
    failed_missions = sum(1 for row in mission_rows if not row.success)
    degraded_providers = sum(1 for row in provider_rows if row.status != "healthy")
    health_score = max(0.0, round(100 - len(alert_rows) * 8 - len(incident_rows) * 12 - degraded_providers * 6 - failed_missions * 3, 2))
    response = DashboardResponse(
        dashboard_key="operations",
        health_score=health_score,
        mission_summary={"total": len(mission_rows), "failed": failed_missions, "success_rate": round((len(mission_rows) - failed_missions) / len(mission_rows), 4) if mission_rows else None},
        ai_usage={"provider_count": len({row.provider_key for row in provider_rows}), "degraded_providers": degraded_providers},
        cost_summary={"total_usd": round(total_cost, 4), "records": len(cost_rows)},
        active_alerts=[{"alert_id": str(row.id), "severity": row.severity, "title": row.title, "status": row.status} for row in alert_rows],
        open_incidents=[{"incident_id": str(row.id), "severity": row.severity, "title": row.title, "status": row.status} for row in incident_rows],
        provider_health=[{"provider_key": row.provider_key, "model_key": row.model_key, "status": row.status, "latency_ms": row.latency_ms, "error_rate": row.error_rate} for row in provider_rows],
        aiops_recommendations=dashboard_recommendations(active_alerts=len(alert_rows), open_incidents=len(incident_rows), degraded_providers=degraded_providers, total_cost=total_cost, failed_missions=failed_missions),
    )
    return api_response(response.model_dump(mode="json"), request)


@router.post("/exporters")
def configure_exporter(
    payload: ExporterConfigRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("telemetry.write")),
    db: Session = Depends(get_db),
):
    response = exporter_response(payload)
    row = db.query(ArceusTelemetryExporterConfig).filter(
        ArceusTelemetryExporterConfig.tenant_id == context.tenant_id,
        ArceusTelemetryExporterConfig.exporter_key == payload.exporter_key,
    ).first()
    if row is None:
        row = ArceusTelemetryExporterConfig(tenant_id=context.tenant_id, exporter_key=payload.exporter_key)
        db.add(row)
    row.exporter_type = payload.exporter_type
    row.target = payload.target
    row.status = "configured" if payload.active else "disabled"
    row.signal_types = response.signal_types
    row.headers = payload.headers
    row.sample_rate = payload.sample_rate
    row.metadata_json = payload.metadata
    row.active = payload.active
    db.flush()
    response.exporter_id = row.id
    _audit(db, context, action="TELEMETRY_EXPORTER_CONFIGURED", resource_type="telemetry_exporter", resource_id=row.id, result=row.status, metadata={"exporter_type": row.exporter_type})
    db.commit()
    return api_response(response.model_dump(mode="json"), request)


@router.get("/exporters")
def list_exporters(
    request: Request,
    context: RequestContext = Depends(require_permission("telemetry.view")),
    db: Session = Depends(get_db),
):
    rows = db.query(ArceusTelemetryExporterConfig).filter(ArceusTelemetryExporterConfig.tenant_id == context.tenant_id).order_by(ArceusTelemetryExporterConfig.created_at.desc()).all()
    return collection_response(
        [
            {
                "exporter_id": str(row.id),
                "exporter_key": row.exporter_key,
                "exporter_type": row.exporter_type,
                "target": row.target,
                "status": row.status,
                "signal_types": row.signal_types or [],
                "sample_rate": row.sample_rate,
                "active": row.active,
                "last_export_at": row.last_export_at.isoformat() if row.last_export_at else None,
                "last_error": row.last_error or {},
            }
            for row in rows
        ],
        request,
    )


@router.get("/exporters/runtime-status")
def exporter_runtime_status(
    request: Request,
    context: RequestContext = Depends(require_permission("telemetry.view")),
):
    return api_response(otel_exporter_runtime_status(), request)


@router.post("/alert-channels")
def configure_alert_channel(
    payload: AlertDeliveryChannelRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("alert.manage")),
    db: Session = Depends(get_db),
):
    row = db.query(ArceusAlertDeliveryChannel).filter(ArceusAlertDeliveryChannel.tenant_id == context.tenant_id, ArceusAlertDeliveryChannel.channel_key == payload.channel_key).first()
    if row is None:
        row = ArceusAlertDeliveryChannel(tenant_id=context.tenant_id, channel_key=payload.channel_key)
        db.add(row)
    row.channel_type = payload.channel_type
    row.display_name = payload.display_name
    row.target = payload.target
    row.severity_filter = payload.severity_filter
    row.secret_ref = payload.secret_ref
    row.metadata_json = payload.metadata
    row.status = "active" if payload.active else "disabled"
    row.active = payload.active
    db.flush()
    _audit(db, context, action="ALERT_CHANNEL_CONFIGURED", resource_type="alert_channel", resource_id=row.id, result=row.status, metadata={"channel_type": row.channel_type})
    db.commit()
    return api_response(
        {
            "channel_id": str(row.id),
            "channel_key": row.channel_key,
            "channel_type": row.channel_type,
            "display_name": row.display_name,
            "target": row.target,
            "severity_filter": row.severity_filter,
            "status": row.status,
            "active": row.active,
        },
        request,
    )


@router.get("/alert-channels")
def list_alert_channels(
    request: Request,
    context: RequestContext = Depends(require_permission("alert.view")),
    db: Session = Depends(get_db),
):
    rows = db.query(ArceusAlertDeliveryChannel).filter(ArceusAlertDeliveryChannel.tenant_id == context.tenant_id).order_by(ArceusAlertDeliveryChannel.created_at.desc()).all()
    return collection_response(
        [
            {
                "channel_id": str(row.id),
                "channel_key": row.channel_key,
                "channel_type": row.channel_type,
                "display_name": row.display_name,
                "target": row.target,
                "severity_filter": row.severity_filter,
                "status": row.status,
                "active": row.active,
            }
            for row in rows
        ],
        request,
    )


@router.get("/alert-deliveries")
def list_alert_deliveries(
    request: Request,
    alert_id: UUID | None = None,
    context: RequestContext = Depends(require_permission("alert.view")),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusAlertDeliveryAttempt).filter(ArceusAlertDeliveryAttempt.tenant_id == context.tenant_id)
    if alert_id:
        query = query.filter(ArceusAlertDeliveryAttempt.alert_id == alert_id)
    rows = query.order_by(ArceusAlertDeliveryAttempt.created_at.desc()).limit(200).all()
    return collection_response(
        [
            {
                "attempt_id": str(row.id),
                "alert_id": str(row.alert_id),
                "channel_id": str(row.channel_id),
                "status": row.status,
                "attempt_number": row.attempt_number,
                "response": row.response or {},
                "error": row.error or {},
            }
            for row in rows
        ],
        request,
    )


@router.post("/alert-deliveries/{attempt_id}/send")
def send_alert_delivery(
    attempt_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("alert.manage")),
    db: Session = Depends(get_db),
):
    attempt = (
        db.query(ArceusAlertDeliveryAttempt)
        .filter(ArceusAlertDeliveryAttempt.tenant_id == context.tenant_id, ArceusAlertDeliveryAttempt.id == attempt_id)
        .first()
    )
    if attempt is None:
        return api_response({"status": "failed", "error": {"reason": "attempt_not_found"}}, request)
    alert = db.query(ArceusAlert).filter(ArceusAlert.tenant_id == context.tenant_id, ArceusAlert.id == attempt.alert_id).first()
    channel = db.query(ArceusAlertDeliveryChannel).filter(ArceusAlertDeliveryChannel.tenant_id == context.tenant_id, ArceusAlertDeliveryChannel.id == attempt.channel_id).first()
    if alert is None or channel is None:
        attempt.status = "failed"
        attempt.error = {"reason": "missing_alert_or_channel"}
        db.commit()
        return api_response({"attempt_id": str(attempt.id), "status": attempt.status, "error": attempt.error}, request)

    result = deliver_alert_attempt(alert=alert, channel=channel)
    attempt.status = result["status"]
    attempt.response = result.get("response", {})
    attempt.error = result.get("error", {})
    if attempt.status == "sent":
        attempt.delivered_at = datetime.now(timezone.utc)
    _audit(db, context, action="ALERT_DELIVERY_ATTEMPTED", resource_type="alert_delivery", resource_id=attempt.id, result=attempt.status, metadata={"channel_type": channel.channel_type})
    db.commit()
    return api_response({"attempt_id": str(attempt.id), **result}, request)


@router.post("/alert-deliveries/drain")
def drain_alert_deliveries(
    request: Request,
    limit: int = Query(default=25, ge=1, le=100),
    context: RequestContext = Depends(require_permission("alert.manage")),
    db: Session = Depends(get_db),
):
    attempts = (
        db.query(ArceusAlertDeliveryAttempt)
        .filter(ArceusAlertDeliveryAttempt.tenant_id == context.tenant_id, ArceusAlertDeliveryAttempt.status == "queued")
        .order_by(ArceusAlertDeliveryAttempt.created_at.asc())
        .limit(limit)
        .all()
    )
    results = []
    for attempt in attempts:
        alert = db.query(ArceusAlert).filter(ArceusAlert.tenant_id == context.tenant_id, ArceusAlert.id == attempt.alert_id).first()
        channel = db.query(ArceusAlertDeliveryChannel).filter(ArceusAlertDeliveryChannel.tenant_id == context.tenant_id, ArceusAlertDeliveryChannel.id == attempt.channel_id).first()
        if alert is None or channel is None:
            result = {"status": "failed", "response": {}, "error": {"reason": "missing_alert_or_channel"}}
        else:
            result = deliver_alert_attempt(alert=alert, channel=channel)
        attempt.status = result["status"]
        attempt.response = result.get("response", {})
        attempt.error = result.get("error", {})
        if attempt.status == "sent":
            attempt.delivered_at = datetime.now(timezone.utc)
        results.append({"attempt_id": str(attempt.id), **result})
    _audit(db, context, action="ALERT_DELIVERY_DRAINED", resource_type="alert_delivery", resource_id=context.tenant_id, result="processed", metadata={"count": len(results)})
    db.commit()
    return api_response({"processed": len(results), "results": results}, request)


@router.post("/recovery-actions")
def propose_recovery_action(
    payload: RecoveryActionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("incident.manage")),
    db: Session = Depends(get_db),
):
    decision = recovery_policy_decision(payload)
    execution_result = {}
    if decision.policy_status == "allowed" and decision.execution_status == "executed":
        execution_result = execute_safe_recovery_action(action_type=payload.action_type, parameters=payload.parameters)
        decision.result = {**decision.result, "executor": execution_result}
        if not execution_result.get("executed"):
            decision.execution_status = "failed"

    row = ArceusRecoveryAction(
        tenant_id=context.tenant_id,
        action_key=payload.action_key,
        title=payload.title,
        trigger_alert_key=payload.trigger_alert_key,
        incident_id=payload.incident_id,
        risk_level=payload.risk_level,
        policy_status=decision.policy_status,
        execution_status=decision.execution_status,
        action_type=payload.action_type,
        parameters=payload.parameters,
        approval_required=decision.approval_required,
        approved_by=context.user_id if decision.policy_status == "allowed" and not decision.approval_required else None,
        evidence=payload.evidence,
        result=decision.result,
        executed_at=None if decision.execution_status != "executed" else datetime.now(timezone.utc),
    )
    db.add(row)
    db.flush()
    decision.recovery_action_id = row.id
    _audit(db, context, action="RECOVERY_ACTION_PROPOSED", resource_type="recovery_action", resource_id=row.id, result=row.execution_status, metadata={"policy_status": row.policy_status, "risk_level": row.risk_level})
    db.commit()
    return api_response(decision.model_dump(mode="json"), request)


@router.get("/recovery-actions")
def list_recovery_actions(
    request: Request,
    context: RequestContext = Depends(require_permission("incident.manage")),
    db: Session = Depends(get_db),
):
    rows = db.query(ArceusRecoveryAction).filter(ArceusRecoveryAction.tenant_id == context.tenant_id).order_by(ArceusRecoveryAction.created_at.desc()).limit(100).all()
    return collection_response(
        [
            {
                "recovery_action_id": str(row.id),
                "action_key": row.action_key,
                "title": row.title,
                "risk_level": row.risk_level,
                "policy_status": row.policy_status,
                "execution_status": row.execution_status,
                "action_type": row.action_type,
                "approval_required": row.approval_required,
                "result": row.result or {},
            }
            for row in rows
        ],
        request,
    )


@router.post("/recovery-actions/{recovery_action_id}/execute")
def execute_recovery_action(
    recovery_action_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("incident.manage")),
    db: Session = Depends(get_db),
):
    row = (
        db.query(ArceusRecoveryAction)
        .filter(ArceusRecoveryAction.tenant_id == context.tenant_id, ArceusRecoveryAction.id == recovery_action_id)
        .first()
    )
    if row is None:
        return api_response({"status": "failed", "error": {"reason": "recovery_action_not_found"}}, request)
    if row.policy_status != "allowed":
        return api_response({"status": "blocked", "error": {"reason": "policy_not_allowed", "policy_status": row.policy_status}}, request)
    result = execute_safe_recovery_action(action_type=row.action_type, parameters=row.parameters or {})
    row.execution_status = "executed" if result.get("executed") else "failed"
    row.result = {**(row.result or {}), "executor": result}
    row.executed_at = datetime.now(timezone.utc) if result.get("executed") else row.executed_at
    _audit(db, context, action="RECOVERY_ACTION_EXECUTED", resource_type="recovery_action", resource_id=row.id, result=row.execution_status, metadata={"action_type": row.action_type})
    db.commit()
    return api_response({"recovery_action_id": str(row.id), "execution_status": row.execution_status, "result": row.result}, request)


@router.get("/mission-control")
def mission_control_observability(
    request: Request,
    context: RequestContext = Depends(require_permission("telemetry.dashboard.view")),
    mission_id: UUID | None = None,
    db: Session = Depends(get_db),
):
    trace_query = db.query(ArceusTrace).filter(ArceusTrace.tenant_id == context.tenant_id)
    log_query = db.query(ArceusTelemetryLog).filter(ArceusTelemetryLog.tenant_id == context.tenant_id)
    alert_query = db.query(ArceusAlert).filter(ArceusAlert.tenant_id == context.tenant_id)
    incident_query = db.query(ArceusIncident).filter(ArceusIncident.tenant_id == context.tenant_id)
    recovery_query = db.query(ArceusRecoveryAction).filter(ArceusRecoveryAction.tenant_id == context.tenant_id)
    if mission_id:
        trace_query = trace_query.filter(ArceusTrace.mission_id == mission_id)
        log_query = log_query.filter(ArceusTelemetryLog.mission_id == mission_id)
        alert_query = alert_query.filter(ArceusAlert.mission_id == mission_id)
        incident_query = incident_query.filter(ArceusIncident.mission_id == mission_id)
    traces = trace_query.order_by(ArceusTrace.started_at.desc()).limit(20).all()
    logs = log_query.order_by(ArceusTelemetryLog.occurred_at.desc()).limit(30).all()
    alerts = alert_query.order_by(ArceusAlert.fired_at.desc()).limit(20).all()
    incidents = incident_query.order_by(ArceusIncident.opened_at.desc()).limit(20).all()
    exporters = db.query(ArceusTelemetryExporterConfig).filter(ArceusTelemetryExporterConfig.tenant_id == context.tenant_id).all()
    channels = db.query(ArceusAlertDeliveryChannel).filter(ArceusAlertDeliveryChannel.tenant_id == context.tenant_id).all()
    recovery_actions = recovery_query.order_by(ArceusRecoveryAction.created_at.desc()).limit(20).all()
    response = MissionControlObservabilityResponse(
        traces=[{"trace_id": row.trace_id, "service": row.service, "name": row.name, "status": row.status, "duration_ms": row.duration_ms} for row in traces],
        logs=[{"log_id": str(row.id), "trace_id": row.trace_id, "level": row.level, "service": row.service, "message": row.message, "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None} for row in logs],
        alerts=[{"alert_id": str(row.id), "severity": row.severity, "status": row.status, "title": row.title, "fired_at": row.fired_at.isoformat() if row.fired_at else None} for row in alerts],
        incidents=[{"incident_id": str(row.id), "severity": row.severity, "status": row.status, "title": row.title, "summary": row.summary} for row in incidents],
        exporters=[{"exporter_key": row.exporter_key, "exporter_type": row.exporter_type, "status": row.status, "active": row.active} for row in exporters],
        delivery_channels=[{"channel_key": row.channel_key, "channel_type": row.channel_type, "status": row.status, "active": row.active} for row in channels],
        recovery_actions=[{"action_key": row.action_key, "title": row.title, "policy_status": row.policy_status, "execution_status": row.execution_status, "risk_level": row.risk_level} for row in recovery_actions],
        aiops_recommendations=dashboard_recommendations(active_alerts=len([row for row in alerts if row.status == "firing"]), open_incidents=len([row for row in incidents if row.status != "resolved"]), degraded_providers=0, total_cost=0, failed_missions=0),
    )
    return api_response(response.model_dump(mode="json"), request)
