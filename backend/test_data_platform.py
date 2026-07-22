from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from services.agent.arceus_runtime.data_platform.api_schemas import (
    AnalyticsExperimentRequest,
    DataQualityRuleRequest,
    DataQualityRunRequest,
    DomainEventRequest,
    EventContractRequest,
    MetricDefinitionRequest,
    MetricSnapshotRequest,
)
from services.agent.arceus_runtime.data_platform.service import (
    create_experiment,
    data_platform_health,
    publish_domain_event,
    record_metric_snapshot,
    record_quality_run,
    register_event_contract,
    register_metric,
    register_quality_rule,
    topic_for,
)
from services.shared.arceus_core_models import (
    ArceusDataEventContract,
    ArceusDataOutboxRecord,
    ArceusDataQualityRule,
    ArceusDataQualityRun,
    ArceusDataset,
    ArceusDeadLetterDataEvent,
    ArceusMetricDefinition,
)


def test_domain_event_contract_validates_and_publishes_to_partitioned_topic() -> None:
    tenant_id = uuid4()
    db = _FakeDb({})
    contract = register_event_contract(
        db,
        tenant_id=tenant_id,
        payload=EventContractRequest(
            event_type="mission.mission.completed",
            version="1",
            owner_domain="missions",
            classification="confidential",
            retention_policy_id="mission_7y",
            schema_definition={"required": ["mission_id", "status"]},
        ),
    )
    db.mapping[ArceusDataEventContract] = [contract]

    record = publish_domain_event(
        db,
        tenant_id=tenant_id,
        payload=DomainEventRequest(
            aggregate_type="mission",
            aggregate_id="mission-1",
            event_type="mission.mission.completed",
            event_version="1",
            organization_id=uuid4(),
            subject={"type": "mission", "id": "mission-1"},
            payload={"mission_id": "mission-1", "status": "completed"},
            classification="confidential",
        ),
    )

    assert isinstance(record, ArceusDataOutboxRecord)
    assert record.topic == "prod.mission.mission.v1"
    assert record.status == "pending"
    assert record.partition_key


def test_event_publish_requires_registered_contract_and_required_fields() -> None:
    tenant_id = uuid4()
    db = _FakeDb({})

    with pytest.raises(ValueError, match="DATA_EVENT_CONTRACT_NOT_FOUND"):
        publish_domain_event(
            db,
            tenant_id=tenant_id,
            payload=DomainEventRequest(aggregate_type="mission", aggregate_id="1", event_type="mission.mission.created", payload={}),
        )

    contract = ArceusDataEventContract(
        tenant_id=tenant_id,
        event_type="mission.mission.created",
        version="1",
        schema_definition={"required": ["mission_id"]},
        owner_domain="missions",
        classification="confidential",
        retention_policy_id="mission_7y",
    )
    db.mapping[ArceusDataEventContract] = [contract]

    with pytest.raises(ValueError, match="DATA_EVENT_SCHEMA_VALIDATION_FAILED"):
        publish_domain_event(
            db,
            tenant_id=tenant_id,
            payload=DomainEventRequest(aggregate_type="mission", aggregate_id="1", event_type="mission.mission.created", payload={}),
        )


def test_secret_payloads_are_not_allowed_in_analytics_outbox() -> None:
    tenant_id = uuid4()
    contract = ArceusDataEventContract(
        tenant_id=tenant_id,
        event_type="model.inference.completed",
        version="1",
        schema_definition={"required": ["request_id"]},
        owner_domain="models",
        classification="internal",
        retention_policy_id="model_1y",
        status="active",
    )
    db = _FakeDb({ArceusDataEventContract: [contract]})

    with pytest.raises(ValueError, match="SECRET_ANALYTICS_PAYLOAD_NOT_ALLOWED"):
        publish_domain_event(
            db,
            tenant_id=tenant_id,
            payload=DomainEventRequest(
                aggregate_type="model_request",
                aggregate_id="req-1",
                event_type="model.inference.completed",
                payload={"request_id": "req-1", "api_key": "sk-nope"},
            ),
        )


def test_metric_snapshots_require_certified_metric_definition() -> None:
    tenant_id = uuid4()
    metric = register_metric(
        _FakeDb({}),
        tenant_id=tenant_id,
        payload=MetricDefinitionRequest(
            metric_key="mission_success_rate",
            version="1",
            name="Mission Success Rate",
            domain="missions",
            expression="success / total",
            certification_status="certified",
            owner="data",
        ),
    )
    db = _FakeDb({ArceusMetricDefinition: [metric]})

    snapshot = record_metric_snapshot(
        db,
        tenant_id=tenant_id,
        payload=MetricSnapshotRequest(
            metric_key="mission_success_rate",
            metric_version="1",
            value=Decimal("0.950000"),
            window_start=datetime(2026, 7, 1, tzinfo=timezone.utc),
            window_end=datetime(2026, 7, 2, tzinfo=timezone.utc),
        ),
    )

    assert snapshot.value == Decimal("0.950000")

    draft = ArceusMetricDefinition(tenant_id=tenant_id, metric_key="draft_metric", version="1", name="Draft", domain="x", expression="1", certification_status="draft", owner="data")
    with pytest.raises(ValueError, match="CERTIFIED_METRIC_NOT_FOUND"):
        record_metric_snapshot(
            _FakeDb({ArceusMetricDefinition: [draft]}),
            tenant_id=tenant_id,
            payload=MetricSnapshotRequest(metric_key="draft_metric", metric_version="1", value=Decimal("1"), window_start=datetime.now(timezone.utc), window_end=datetime.now(timezone.utc)),
        )


def test_quality_run_status_follows_rule_severity() -> None:
    tenant_id = uuid4()
    rule = register_quality_rule(
        _FakeDb({}),
        tenant_id=tenant_id,
        payload=DataQualityRuleRequest(dataset_key="gold.mission_facts", rule_key="mission_id_not_null", rule_type="completeness", severity="critical"),
    )
    db = _FakeDb({ArceusDataQualityRule: [rule]})

    run = record_quality_run(
        db,
        tenant_id=tenant_id,
        payload=DataQualityRunRequest(dataset_key="gold.mission_facts", rule_key="mission_id_not_null", row_count=100, failed_count=2),
    )

    assert isinstance(run, ArceusDataQualityRun)
    assert run.status == "failed"


def test_experiment_allocation_must_sum_to_one_when_specified() -> None:
    payload = AnalyticsExperimentRequest(
        experiment_key="mission_onboarding_copy",
        name="Mission onboarding copy",
        hypothesis="Clearer onboarding improves first mission completion.",
        owner="growth",
        variants=[{"key": "control"}, {"key": "variant"}],
        primary_metric_key="mission_success_rate",
        allocation={"control": 0.5, "variant": 0.4},
    )

    with pytest.raises(ValueError, match="EXPERIMENT_ALLOCATION_MUST_SUM_TO_ONE"):
        create_experiment(_FakeDb({}), tenant_id=uuid4(), payload=payload)


def test_data_platform_health_blocks_on_failed_pipeline_or_quality() -> None:
    tenant_id = uuid4()
    db = _CountingDb(
        {
            ArceusDataEventContract: 2,
            ArceusDataOutboxRecord: {"pending": 0, "failed": 1},
            ArceusDeadLetterDataEvent: 1,
            ArceusMetricDefinition: 4,
            ArceusDataset: 0,
            ArceusDataQualityRun: 1,
        }
    )

    health = data_platform_health(db, tenant_id=tenant_id)

    assert health["status"] == "blocked"
    assert "event_pipeline_failures" in health["blockers"]
    assert "data_quality_failures" in health["blockers"]


def test_topic_naming_is_domain_category_versioned() -> None:
    assert topic_for("billing.invoice.paid", "2") == "prod.billing.invoice.v2"


class _Query:
    def __init__(self, rows):
        self.rows = rows

    def filter(self, *args, **kwargs):
        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, *_args):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return list(self.rows)

    def count(self):
        return len(self.rows)


class _FakeDb:
    def __init__(self, mapping) -> None:
        self.mapping = mapping
        self.added = []

    def query(self, model):
        return _Query(self.mapping.get(model, []))

    def add(self, item) -> None:
        if getattr(item, "id", None) is None:
            item.id = uuid4()
        self.added.append(item)

    def flush(self) -> None:
        return None


class _CountingQuery:
    def __init__(self, model, counts):
        self.model = model
        self.counts = counts
        self.filters = []

    def filter(self, *args, **kwargs):
        self.filters.extend(str(arg) for arg in args)
        return self

    def count(self):
        value = self.counts.get(self.model, 0)
        if isinstance(value, dict):
            text = " ".join(self.filters)
            if "failed" in text:
                return int(value.get("failed", 0))
            if "pending" in text:
                return int(value.get("pending", 0))
            return sum(int(item) for item in value.values())
        return int(value)


class _CountingDb:
    def __init__(self, counts) -> None:
        self.counts = counts

    def query(self, model):
        return _CountingQuery(model, self.counts)
