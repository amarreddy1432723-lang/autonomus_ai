from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


DataClassification = Literal["public", "internal", "confidential", "restricted", "regulated", "secret"]


class DataPlatformSchema(BaseModel):
    model_config = ConfigDict(protected_namespaces=())


class EventContractRequest(DataPlatformSchema):
    event_type: str = Field(min_length=3, max_length=200)
    version: str = Field(default="1", min_length=1, max_length=40)
    schema_format: Literal["json_schema", "avro", "protobuf"] = "json_schema"
    schema_definition: dict[str, Any] = Field(default_factory=dict)
    compatibility_mode: Literal["backward", "forward", "full", "none"] = "backward"
    owner_domain: str = Field(min_length=1, max_length=120)
    classification: DataClassification = "internal"
    retention_policy_id: str = Field(min_length=1, max_length=120)
    example_event: dict[str, Any] = Field(default_factory=dict)
    documentation: str | None = None


class EventContractResponse(DataPlatformSchema):
    id: UUID
    event_type: str
    version: str
    owner_domain: str
    classification: str
    compatibility_mode: str
    status: str


class DomainEventRequest(DataPlatformSchema):
    aggregate_type: str = Field(min_length=1, max_length=120)
    aggregate_id: str = Field(min_length=1, max_length=160)
    event_type: str = Field(min_length=3, max_length=200)
    event_version: str = Field(default="1", min_length=1, max_length=40)
    organization_id: UUID | None = None
    workspace_id: UUID | None = None
    actor_id: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    trace_id: str | None = None
    subject: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    classification: DataClassification = "internal"
    occurred_at: datetime | None = None


class DomainEventResponse(DataPlatformSchema):
    id: UUID
    event_type: str
    event_version: str
    topic: str
    partition_key: str
    status: str
    classification: str
    occurred_at: datetime | None = None


class DatasetRequest(DataPlatformSchema):
    dataset_key: str = Field(min_length=3, max_length=200)
    name: str = Field(min_length=1)
    layer: Literal["bronze", "silver", "gold", "semantic", "feature"]
    domain: str = Field(min_length=1, max_length=120)
    owner_service: str = Field(min_length=1, max_length=120)
    classification: DataClassification = "internal"
    freshness_slo_minutes: int = Field(default=1440, ge=1)
    retention_policy_id: str = Field(min_length=1, max_length=120)
    access_policy: dict[str, Any] = Field(default_factory=dict)
    documentation: str | None = None


class DatasetResponse(DataPlatformSchema):
    id: UUID
    dataset_key: str
    name: str
    layer: str
    domain: str
    classification: str
    lifecycle_status: str
    freshness_slo_minutes: int
    last_refreshed_at: datetime | None


class MetricDefinitionRequest(DataPlatformSchema):
    metric_key: str = Field(min_length=3, max_length=200)
    version: str = Field(default="1", min_length=1, max_length=40)
    name: str = Field(min_length=1)
    domain: str = Field(min_length=1, max_length=120)
    expression: str = Field(min_length=1)
    unit: str = Field(default="count", max_length=60)
    dimensions: list[str] = Field(default_factory=list)
    source_dataset_keys: list[str] = Field(default_factory=list)
    certification_status: Literal["draft", "review", "certified", "deprecated"] = "draft"
    owner: str = Field(min_length=1, max_length=160)
    documentation: str | None = None


class MetricSnapshotRequest(DataPlatformSchema):
    metric_key: str
    metric_version: str = "1"
    value: Decimal
    dimensions: dict[str, Any] = Field(default_factory=dict)
    window_start: datetime
    window_end: datetime
    lineage: dict[str, Any] = Field(default_factory=dict)


class MetricResponse(DataPlatformSchema):
    metric_key: str
    version: str
    name: str
    certification_status: str
    value: Decimal | None = None
    dimensions: dict[str, Any] = Field(default_factory=dict)
    freshness_at: datetime | None = None


class DataQualityRuleRequest(DataPlatformSchema):
    dataset_key: str
    rule_key: str
    rule_type: Literal["completeness", "accuracy", "validity", "uniqueness", "consistency", "freshness", "referential_integrity"]
    severity: Literal["info", "warning", "critical"] = "warning"
    expectation: dict[str, Any] = Field(default_factory=dict)


class DataQualityRunRequest(DataPlatformSchema):
    dataset_key: str
    rule_key: str
    observed_value: dict[str, Any] = Field(default_factory=dict)
    expected_value: dict[str, Any] = Field(default_factory=dict)
    row_count: int = Field(default=0, ge=0)
    failed_count: int = Field(default=0, ge=0)


class DataQualityRunResponse(DataPlatformSchema):
    id: UUID
    dataset_key: str
    rule_key: str
    status: str
    failed_count: int
    row_count: int


class LineageEdgeRequest(DataPlatformSchema):
    source_type: str
    source_key: str
    target_type: str
    target_key: str
    transform_key: str | None = None
    relationship: str = "derived_from"
    metadata: dict[str, Any] = Field(default_factory=dict)


class AnalyticsExperimentRequest(DataPlatformSchema):
    experiment_key: str = Field(min_length=3, max_length=200)
    name: str
    hypothesis: str
    owner: str
    variants: list[dict[str, Any]]
    primary_metric_key: str
    guardrail_metric_keys: list[str] = Field(default_factory=list)
    allocation: dict[str, float] = Field(default_factory=dict)


class DataPlatformHealthResponse(DataPlatformSchema):
    contracts: int
    pending_outbox: int
    failed_outbox: int
    dead_letters: int
    certified_metrics: int
    stale_datasets: int
    failed_quality_runs: int
    status: str
    blockers: list[str]
