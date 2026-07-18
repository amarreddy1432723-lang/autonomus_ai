from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusProviderProfile
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..health.routes import classify_runtime_health
from .api_schemas import (
    OperationHealthResponse,
    OperationsActionRequest,
    OperationsActionResponse,
    QueueResponse,
    RegionResponse,
    SloResponse,
    WorkerPoolResponse,
)
from .service import calculate_slo_posture, classify_queue_health, classify_worker_pool, configured_regions, operation_guard, region_status


router = APIRouter(prefix="/api/v1/operations", tags=["enterprise-operations"])


def _runtime_summary(db: Session, tenant_id):
    return SqlAlchemyUnitOfWork(db).runtime_health.summary(tenant_id=tenant_id)


@router.get("/health")
def get_operations_health(
    request: Request,
    context: RequestContext = Depends(require_permission("operations.view")),
    db: Session = Depends(get_db),
):
    summary = _runtime_summary(db, context.tenant_id)
    status, blockers, warnings = classify_runtime_health(summary)
    response = OperationHealthResponse(
        status=status,
        ready=status != "blocked",
        blockers=blockers,
        warnings=warnings,
        control_plane={
            "tenant_id": str(context.tenant_id),
            "mission_statuses": summary.get("mission_statuses") or {},
            "approval_statuses": summary.get("approval_statuses") or {},
        },
        execution_plane={
            "task_statuses": summary.get("task_statuses") or {},
            "outbox_statuses": summary.get("outbox_statuses") or {},
            "active_worker_leases": summary.get("active_worker_leases", 0),
            "stale_processing_outbox": summary.get("stale_processing_outbox", 0),
        },
        checked_at=datetime.now(timezone.utc),
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/regions")
def list_regions(
    request: Request,
    context: RequestContext = Depends(require_permission("operations.view")),
    db: Session = Depends(get_db),
):
    providers = db.query(ArceusProviderProfile).filter(ArceusProviderProfile.enabled.is_(True)).all()
    rows = []
    for region in configured_regions():
        region_providers = [
            provider
            for provider in providers
            if region in (provider.supported_regions or []) or "global" in (provider.supported_regions or []) or region == "local"
        ]
        rows.append(RegionResponse(**region_status(region_key=region, providers=region_providers)).model_dump(mode="json"))
    return collection_response(rows, request)


@router.get("/workers")
def get_workers(
    request: Request,
    context: RequestContext = Depends(require_permission("operations.view")),
    db: Session = Depends(get_db),
):
    summary = _runtime_summary(db, context.tenant_id)
    status, recommendations = classify_worker_pool(summary)
    task_statuses = summary.get("task_statuses") or {}
    response = WorkerPoolResponse(
        active_worker_leases=int(summary.get("active_worker_leases", 0)),
        stale_processing_outbox=int(summary.get("stale_processing_outbox", 0)),
        ready_tasks=int(task_statuses.get("ready", 0)),
        running_tasks=int(task_statuses.get("running", 0)),
        blocked_tasks=int(task_statuses.get("blocked", 0)),
        failed_tasks=int(task_statuses.get("failed", 0)),
        utilization_status=status,
        recommendations=recommendations,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/queues")
def get_queues(
    request: Request,
    context: RequestContext = Depends(require_permission("operations.view")),
    db: Session = Depends(get_db),
):
    summary = _runtime_summary(db, context.tenant_id)
    outbox_statuses = summary.get("outbox_statuses") or {}
    health, recommendations = classify_queue_health(outbox_statuses, stale_processing_outbox=int(summary.get("stale_processing_outbox", 0)))
    response = QueueResponse(
        queue_key="outbox",
        pending=int(outbox_statuses.get("pending", 0)),
        processing=int(outbox_statuses.get("processing", 0)),
        failed=int(outbox_statuses.get("failed", 0)),
        dead_letter=int(outbox_statuses.get("dead_letter", 0)),
        health=health,
        recommendations=recommendations,
    )
    return collection_response([response.model_dump(mode="json")], request)


@router.get("/slos")
def get_slos(
    request: Request,
    context: RequestContext = Depends(require_permission("operations.view")),
    db: Session = Depends(get_db),
):
    summary = _runtime_summary(db, context.tenant_id)
    return collection_response([SloResponse(**item).model_dump(mode="json") for item in calculate_slo_posture(summary)], request)


def _record_operations_action(db: Session, context: RequestContext, *, action: str, payload: OperationsActionRequest, accepted: bool, status: str) -> None:
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action=action,
        resource_type="operations",
        resource_id=payload.target_region,
        result=status,
        metadata={
            "target_region": payload.target_region,
            "dry_run": payload.dry_run,
            "accepted": accepted,
            "reason": payload.reason,
            "correlation_id": str(context.correlation_id),
        },
    )


@router.post("/failover")
def request_failover(
    payload: OperationsActionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("operations.manage")),
    db: Session = Depends(get_db),
):
    accepted, reason, approvals = operation_guard(action="failover", dry_run=payload.dry_run)
    status = "accepted" if accepted else "needs_approval"
    _record_operations_action(db, context, action="OPERATIONS_FAILOVER_REQUESTED", payload=payload, accepted=accepted, status=status)
    db.commit()
    response = OperationsActionResponse(
        action="failover",
        accepted=accepted,
        dry_run=payload.dry_run,
        status=status,
        reason=reason,
        required_approvals=approvals,
        audit_recorded=True,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.post("/dr-test")
def request_dr_test(
    payload: OperationsActionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("operations.manage")),
    db: Session = Depends(get_db),
):
    accepted, reason, approvals = operation_guard(action="dr_test", dry_run=payload.dry_run)
    status = "accepted" if accepted else "needs_approval"
    _record_operations_action(db, context, action="OPERATIONS_DR_TEST_REQUESTED", payload=payload, accepted=accepted, status=status)
    db.commit()
    response = OperationsActionResponse(
        action="dr_test",
        accepted=accepted,
        dry_run=payload.dry_run,
        status=status,
        reason=reason,
        required_approvals=approvals,
        audit_recorded=True,
    )
    return api_response(response.model_dump(mode="json"), request)
