from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusAnalyticsExperiment,
    ArceusDataEventContract,
    ArceusDataLineageEdge,
    ArceusDataOutboxRecord,
    ArceusDataQualityRule,
    ArceusDataQualityRun,
    ArceusDataset,
    ArceusDeadLetterDataEvent,
    ArceusMetricDefinition,
    ArceusMetricSnapshot,
)

from .api_schemas import (
    AnalyticsExperimentRequest,
    DataQualityRuleRequest,
    DataQualityRunRequest,
    DatasetRequest,
    DomainEventRequest,
    EventContractRequest,
    LineageEdgeRequest,
    MetricDefinitionRequest,
    MetricSnapshotRequest,
)


SECRET_KEYS = {"secret", "password", "token", "api_key", "private_key", "credential"}
INITIAL_CERTIFIED_METRICS = [
    {"metric_key": "missions_created", "name": "Missions Created", "domain": "missions", "expression": "count(mission.mission.created)", "unit": "count"},
    {"metric_key": "missions_completed", "name": "Missions Completed", "domain": "missions", "expression": "count(mission.mission.completed)", "unit": "count"},
    {"metric_key": "mission_success_rate", "name": "Mission Success Rate", "domain": "missions", "expression": "missions_completed / nullif(missions_finished, 0)", "unit": "ratio"},
    {"metric_key": "model_inference_success_rate", "name": "Model Inference Success Rate", "domain": "models", "expression": "model_inference_completed / nullif(model_inference_finished, 0)", "unit": "ratio"},
    {"metric_key": "tool_invocation_success_rate", "name": "Tool Invocation Success Rate", "domain": "tools", "expression": "tool_invocation_completed / nullif(tool_invocation_finished, 0)", "unit": "ratio"},
    {"metric_key": "verification_pass_rate", "name": "Verification Pass Rate", "domain": "verification", "expression": "verification_passed / nullif(verification_completed, 0)", "unit": "ratio"},
]


def register_event_contract(db: Session, *, tenant_id: UUID, payload: EventContractRequest) -> ArceusDataEventContract:
    existing = db.query(ArceusDataEventContract).filter(ArceusDataEventContract.tenant_id == tenant_id, ArceusDataEventContract.event_type == payload.event_type, ArceusDataEventContract.version == payload.version).first()
    if existing is None:
        existing = ArceusDataEventContract(tenant_id=tenant_id)
        db.add(existing)
    for key, value in payload.model_dump().items():
        setattr(existing, key, value)
    existing.status = "active"
    db.flush()
    return existing


def publish_domain_event(db: Session, *, tenant_id: UUID, payload: DomainEventRequest) -> ArceusDataOutboxRecord:
    contract = db.query(ArceusDataEventContract).filter(ArceusDataEventContract.tenant_id == tenant_id, ArceusDataEventContract.event_type == payload.event_type, ArceusDataEventContract.version == payload.event_version, ArceusDataEventContract.status == "active").first()
    if contract is None:
        raise ValueError("DATA_EVENT_CONTRACT_NOT_FOUND")
    if _contains_secret(payload.payload) or payload.classification == "secret":
        raise ValueError("SECRET_ANALYTICS_PAYLOAD_NOT_ALLOWED")
    missing = required_fields(contract.schema_definition) - set(payload.payload)
    if missing:
        raise ValueError("DATA_EVENT_SCHEMA_VALIDATION_FAILED:" + ",".join(sorted(missing)))
    topic = topic_for(payload.event_type, payload.event_version)
    partition_key = str(payload.organization_id or payload.subject.get("id") or payload.aggregate_id)
    record = ArceusDataOutboxRecord(
        tenant_id=tenant_id,
        aggregate_type=payload.aggregate_type,
        aggregate_id=payload.aggregate_id,
        event_type=payload.event_type,
        event_version=payload.event_version,
        organization_id=payload.organization_id,
        workspace_id=payload.workspace_id,
        actor_id=payload.actor_id,
        correlation_id=payload.correlation_id,
        causation_id=payload.causation_id,
        trace_id=payload.trace_id,
        subject=payload.subject,
        payload=payload.payload,
        metadata_json=payload.metadata,
        classification=payload.classification,
        topic=topic,
        partition_key=partition_key,
        status="pending",
        attempt_count=0,
        occurred_at=payload.occurred_at or datetime.now(timezone.utc),
    )
    db.add(record)
    db.flush()
    return record


def register_dataset(db: Session, *, tenant_id: UUID, payload: DatasetRequest) -> ArceusDataset:
    item = db.query(ArceusDataset).filter(ArceusDataset.tenant_id == tenant_id, ArceusDataset.dataset_key == payload.dataset_key).first()
    if item is None:
        item = ArceusDataset(tenant_id=tenant_id)
        db.add(item)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    item.lifecycle_status = "active" if payload.layer in {"bronze", "silver"} else item.lifecycle_status or "draft"
    db.flush()
    return item


def register_metric(db: Session, *, tenant_id: UUID, payload: MetricDefinitionRequest) -> ArceusMetricDefinition:
    item = db.query(ArceusMetricDefinition).filter(ArceusMetricDefinition.tenant_id == tenant_id, ArceusMetricDefinition.metric_key == payload.metric_key, ArceusMetricDefinition.version == payload.version).first()
    if item is None:
        item = ArceusMetricDefinition(tenant_id=tenant_id)
        db.add(item)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    db.flush()
    return item


def record_metric_snapshot(db: Session, *, tenant_id: UUID, payload: MetricSnapshotRequest) -> ArceusMetricSnapshot:
    metric = db.query(ArceusMetricDefinition).filter(ArceusMetricDefinition.tenant_id == tenant_id, ArceusMetricDefinition.metric_key == payload.metric_key, ArceusMetricDefinition.version == payload.metric_version).first()
    if metric is None or metric.certification_status != "certified":
        raise ValueError("CERTIFIED_METRIC_NOT_FOUND")
    item = ArceusMetricSnapshot(tenant_id=tenant_id, **payload.model_dump())
    db.add(item)
    db.flush()
    return item


def register_quality_rule(db: Session, *, tenant_id: UUID, payload: DataQualityRuleRequest) -> ArceusDataQualityRule:
    item = db.query(ArceusDataQualityRule).filter(ArceusDataQualityRule.tenant_id == tenant_id, ArceusDataQualityRule.dataset_key == payload.dataset_key, ArceusDataQualityRule.rule_key == payload.rule_key).first()
    if item is None:
        item = ArceusDataQualityRule(tenant_id=tenant_id)
        db.add(item)
    for key, value in payload.model_dump().items():
        setattr(item, key, value)
    item.status = "active"
    db.flush()
    return item


def record_quality_run(db: Session, *, tenant_id: UUID, payload: DataQualityRunRequest) -> ArceusDataQualityRun:
    rule = db.query(ArceusDataQualityRule).filter(ArceusDataQualityRule.tenant_id == tenant_id, ArceusDataQualityRule.dataset_key == payload.dataset_key, ArceusDataQualityRule.rule_key == payload.rule_key, ArceusDataQualityRule.status == "active").first()
    if rule is None:
        raise ValueError("DATA_QUALITY_RULE_NOT_FOUND")
    status = "passed" if payload.failed_count == 0 else "failed" if rule.severity == "critical" else "warning"
    item = ArceusDataQualityRun(tenant_id=tenant_id, status=status, **payload.model_dump())
    db.add(item)
    db.flush()
    return item


def add_lineage_edge(db: Session, *, tenant_id: UUID, payload: LineageEdgeRequest) -> ArceusDataLineageEdge:
    item = ArceusDataLineageEdge(tenant_id=tenant_id, metadata_json=payload.metadata, **payload.model_dump(exclude={"metadata"}))
    db.add(item)
    db.flush()
    return item


def create_experiment(db: Session, *, tenant_id: UUID, payload: AnalyticsExperimentRequest) -> ArceusAnalyticsExperiment:
    if round(sum(payload.allocation.values()), 6) not in {0, 1}:
        raise ValueError("EXPERIMENT_ALLOCATION_MUST_SUM_TO_ONE")
    item = ArceusAnalyticsExperiment(tenant_id=tenant_id, status="draft", **payload.model_dump())
    db.add(item)
    db.flush()
    return item


def ensure_initial_metrics(db: Session, *, tenant_id: UUID) -> list[ArceusMetricDefinition]:
    rows = []
    for definition in INITIAL_CERTIFIED_METRICS:
        rows.append(
            register_metric(
                db,
                tenant_id=tenant_id,
                payload=MetricDefinitionRequest(
                    version="1",
                    certification_status="certified",
                    owner="arceus-data-platform",
                    source_dataset_keys=["gold.mission_facts"],
                    dimensions=["organization_id", "workspace_id"],
                    **definition,
                ),
            )
        )
    return rows


def data_platform_health(db: Session, *, tenant_id: UUID) -> dict[str, object]:
    contracts = db.query(ArceusDataEventContract).filter(ArceusDataEventContract.tenant_id == tenant_id, ArceusDataEventContract.status == "active").count()
    pending = db.query(ArceusDataOutboxRecord).filter(ArceusDataOutboxRecord.tenant_id == tenant_id, ArceusDataOutboxRecord.status == "pending").count()
    failed = db.query(ArceusDataOutboxRecord).filter(ArceusDataOutboxRecord.tenant_id == tenant_id, ArceusDataOutboxRecord.status == "failed").count()
    dead = db.query(ArceusDeadLetterDataEvent).filter(ArceusDeadLetterDataEvent.tenant_id == tenant_id, ArceusDeadLetterDataEvent.replay_status == "pending").count()
    certified = db.query(ArceusMetricDefinition).filter(ArceusMetricDefinition.tenant_id == tenant_id, ArceusMetricDefinition.certification_status == "certified").count()
    stale = db.query(ArceusDataset).filter(ArceusDataset.tenant_id == tenant_id, ArceusDataset.lifecycle_status.in_(["certified", "active"]), ArceusDataset.last_refreshed_at.is_(None)).count()
    failed_quality = db.query(ArceusDataQualityRun).filter(ArceusDataQualityRun.tenant_id == tenant_id, ArceusDataQualityRun.status == "failed").count()
    blockers = []
    if failed or dead:
        blockers.append("event_pipeline_failures")
    if failed_quality:
        blockers.append("data_quality_failures")
    status = "blocked" if blockers else "degraded" if stale or pending > 1000 else "healthy"
    return {"contracts": contracts, "pending_outbox": pending, "failed_outbox": failed, "dead_letters": dead, "certified_metrics": certified, "stale_datasets": stale, "failed_quality_runs": failed_quality, "status": status, "blockers": blockers}


def required_fields(schema: dict[str, object]) -> set[str]:
    required = schema.get("required") if isinstance(schema, dict) else None
    return {str(item) for item in required or []}


def topic_for(event_type: str, version: str) -> str:
    parts = event_type.split(".")
    domain = parts[0] if parts else "platform"
    category = parts[1] if len(parts) > 1 else "events"
    return f"prod.{slug(domain)}.{slug(category)}.v{slug(version)}"


def _contains_secret(value: object) -> bool:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in SECRET_KEYS:
                return True
            if _contains_secret(child):
                return True
    if isinstance(value, list):
        return any(_contains_secret(item) for item in value)
    return False


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "events"


def stable_fingerprint(payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
