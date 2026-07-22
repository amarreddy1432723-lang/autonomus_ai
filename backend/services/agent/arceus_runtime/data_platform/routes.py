from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusDataEventContract, ArceusDataOutboxRecord, ArceusDataset, ArceusMetricDefinition, ArceusMetricSnapshot
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from .api_schemas import (
    AnalyticsExperimentRequest,
    DataPlatformHealthResponse,
    DataQualityRuleRequest,
    DataQualityRunRequest,
    DataQualityRunResponse,
    DatasetRequest,
    DatasetResponse,
    DomainEventRequest,
    DomainEventResponse,
    EventContractRequest,
    EventContractResponse,
    LineageEdgeRequest,
    MetricDefinitionRequest,
    MetricResponse,
    MetricSnapshotRequest,
)
from .service import (
    add_lineage_edge,
    create_experiment,
    data_platform_health,
    ensure_initial_metrics,
    publish_domain_event,
    record_metric_snapshot,
    record_quality_run,
    register_dataset,
    register_event_contract,
    register_metric,
    register_quality_rule,
)


router = APIRouter(prefix="/api/v1/data-platform", tags=["arceus-data-platform"])


@router.post("/contracts")
def create_contract(payload: EventContractRequest, request: Request, context: RequestContext = Depends(require_permission("data.contract.manage")), db: Session = Depends(get_db)):
    item = register_event_contract(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response(_contract_response(item).model_dump(mode="json"), request)


@router.get("/contracts")
def list_contracts(request: Request, context: RequestContext = Depends(require_permission("data.catalog.view")), owner_domain: str | None = None, db: Session = Depends(get_db)):
    query = db.query(ArceusDataEventContract).filter(ArceusDataEventContract.tenant_id == context.tenant_id)
    if owner_domain:
        query = query.filter(ArceusDataEventContract.owner_domain == owner_domain)
    rows = query.order_by(ArceusDataEventContract.event_type.asc(), ArceusDataEventContract.version.asc()).limit(200).all()
    return collection_response([_contract_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/events")
def publish_event(payload: DomainEventRequest, request: Request, context: RequestContext = Depends(require_permission("data.event.publish")), db: Session = Depends(get_db)):
    try:
        item = publish_domain_event(db, tenant_id=context.tenant_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": str(exc), "message": "Domain event could not be accepted into the analytics outbox."}) from exc
    db.commit()
    db.refresh(item)
    return api_response(_event_response(item).model_dump(mode="json"), request)


@router.get("/events/outbox")
def list_outbox(request: Request, context: RequestContext = Depends(require_permission("data.pipeline.view")), status: str | None = Query(default=None, max_length=40), db: Session = Depends(get_db)):
    query = db.query(ArceusDataOutboxRecord).filter(ArceusDataOutboxRecord.tenant_id == context.tenant_id)
    if status:
        query = query.filter(ArceusDataOutboxRecord.status == status)
    rows = query.order_by(ArceusDataOutboxRecord.created_at.desc()).limit(200).all()
    return collection_response([_event_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/datasets")
def create_dataset(payload: DatasetRequest, request: Request, context: RequestContext = Depends(require_permission("data.catalog.manage")), db: Session = Depends(get_db)):
    item = register_dataset(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response(_dataset_response(item).model_dump(mode="json"), request)


@router.get("/datasets")
def list_datasets(request: Request, context: RequestContext = Depends(require_permission("data.catalog.view")), domain: str | None = None, db: Session = Depends(get_db)):
    query = db.query(ArceusDataset).filter(ArceusDataset.tenant_id == context.tenant_id)
    if domain:
        query = query.filter(ArceusDataset.domain == domain)
    rows = query.order_by(ArceusDataset.domain.asc(), ArceusDataset.dataset_key.asc()).limit(200).all()
    return collection_response([_dataset_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/metrics/definitions")
def create_metric(payload: MetricDefinitionRequest, request: Request, context: RequestContext = Depends(require_permission("data.metric.manage")), db: Session = Depends(get_db)):
    item = register_metric(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response(_metric_definition_response(item).model_dump(mode="json"), request)


@router.post("/metrics/bootstrap")
def bootstrap_metrics(request: Request, context: RequestContext = Depends(require_permission("data.metric.manage")), db: Session = Depends(get_db)):
    rows = ensure_initial_metrics(db, tenant_id=context.tenant_id)
    db.commit()
    return collection_response([_metric_definition_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/metrics/snapshots")
def create_metric_snapshot(payload: MetricSnapshotRequest, request: Request, context: RequestContext = Depends(require_permission("data.metric.write")), db: Session = Depends(get_db)):
    try:
        item = record_metric_snapshot(db, tenant_id=context.tenant_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": str(exc), "message": "Only certified metrics can receive governed snapshots."}) from exc
    db.commit()
    db.refresh(item)
    return api_response(_metric_snapshot_response(item).model_dump(mode="json"), request)


@router.get("/metrics")
def list_metrics(request: Request, context: RequestContext = Depends(require_permission("data.metric.view")), certified_only: bool = True, db: Session = Depends(get_db)):
    query = db.query(ArceusMetricDefinition).filter(ArceusMetricDefinition.tenant_id == context.tenant_id)
    if certified_only:
        query = query.filter(ArceusMetricDefinition.certification_status == "certified")
    rows = query.order_by(ArceusMetricDefinition.domain.asc(), ArceusMetricDefinition.metric_key.asc()).limit(200).all()
    return collection_response([_metric_definition_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/quality/rules")
def create_quality_rule(payload: DataQualityRuleRequest, request: Request, context: RequestContext = Depends(require_permission("data.quality.manage")), db: Session = Depends(get_db)):
    item = register_quality_rule(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response({"id": str(item.id), "dataset_key": item.dataset_key, "rule_key": item.rule_key, "severity": item.severity}, request)


@router.post("/quality/runs")
def create_quality_run(payload: DataQualityRunRequest, request: Request, context: RequestContext = Depends(require_permission("data.quality.write")), db: Session = Depends(get_db)):
    try:
        item = record_quality_run(db, tenant_id=context.tenant_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail={"code": str(exc), "message": "Data quality rule was not found."}) from exc
    db.commit()
    db.refresh(item)
    return api_response(DataQualityRunResponse(id=item.id, dataset_key=item.dataset_key, rule_key=item.rule_key, status=item.status, failed_count=item.failed_count, row_count=item.row_count).model_dump(mode="json"), request)


@router.post("/lineage")
def create_lineage(payload: LineageEdgeRequest, request: Request, context: RequestContext = Depends(require_permission("data.catalog.manage")), db: Session = Depends(get_db)):
    item = add_lineage_edge(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response({"id": str(item.id), "source": item.source_key, "target": item.target_key, "relationship": item.relationship}, request)


@router.post("/experiments")
def create_analytics_experiment(payload: AnalyticsExperimentRequest, request: Request, context: RequestContext = Depends(require_permission("data.experiment.manage")), db: Session = Depends(get_db)):
    try:
        item = create_experiment(db, tenant_id=context.tenant_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"code": str(exc), "message": "Experiment allocation is invalid."}) from exc
    db.commit()
    db.refresh(item)
    return api_response({"id": str(item.id), "experiment_key": item.experiment_key, "status": item.status, "primary_metric_key": item.primary_metric_key}, request)


@router.get("/health")
def get_data_platform_health(request: Request, context: RequestContext = Depends(require_permission("data.pipeline.view")), db: Session = Depends(get_db)):
    return api_response(DataPlatformHealthResponse(**data_platform_health(db, tenant_id=context.tenant_id)).model_dump(mode="json"), request)


def _contract_response(item: ArceusDataEventContract) -> EventContractResponse:
    return EventContractResponse(id=item.id, event_type=item.event_type, version=item.version, owner_domain=item.owner_domain, classification=item.classification, compatibility_mode=item.compatibility_mode, status=item.status)


def _event_response(item: ArceusDataOutboxRecord) -> DomainEventResponse:
    return DomainEventResponse(id=item.id, event_type=item.event_type, event_version=item.event_version, topic=item.topic, partition_key=item.partition_key, status=item.status, classification=item.classification, occurred_at=item.occurred_at)


def _dataset_response(item: ArceusDataset) -> DatasetResponse:
    return DatasetResponse(id=item.id, dataset_key=item.dataset_key, name=item.name, layer=item.layer, domain=item.domain, classification=item.classification, lifecycle_status=item.lifecycle_status, freshness_slo_minutes=item.freshness_slo_minutes, last_refreshed_at=item.last_refreshed_at)


def _metric_definition_response(item: ArceusMetricDefinition) -> MetricResponse:
    return MetricResponse(metric_key=item.metric_key, version=item.version, name=item.name, certification_status=item.certification_status)


def _metric_snapshot_response(item: ArceusMetricSnapshot) -> MetricResponse:
    return MetricResponse(metric_key=item.metric_key, version=item.metric_version, name=item.metric_key, certification_status="certified", value=item.value, dimensions=item.dimensions or {}, freshness_at=item.freshness_at)
