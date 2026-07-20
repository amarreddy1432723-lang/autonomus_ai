from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusModelProfile, ArceusProviderProfile
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    ComputeCacheResponse,
    ComputeCostResponse,
    ComputeInferRequest,
    ComputeInferResponse,
    ComputePlanRequest,
    ComputePlanResponse,
    ComputeResourceResponse,
    ComputeScheduleResponse,
)
from .service import build_compute_plan, build_compute_resources, cache_policy, cost_summary


router = APIRouter(prefix="/api/v1/compute", tags=["ai-compute-fabric"])


def _models_and_providers(db: Session) -> tuple[list[ArceusModelProfile], list[ArceusProviderProfile]]:
    providers = db.query(ArceusProviderProfile).filter(ArceusProviderProfile.enabled.is_(True)).all()
    models = db.query(ArceusModelProfile).filter(ArceusModelProfile.status.in_(["available", "degraded"])).all()
    return models, providers


def _resources(db: Session) -> list[dict]:
    models, providers = _models_and_providers(db)
    return build_compute_resources(models, providers)


@router.get("/resources")
def list_compute_resources(
    request: Request,
    context: RequestContext = Depends(require_permission("compute.view")),
    db: Session = Depends(get_db),
):
    rows = [ComputeResourceResponse(**item).model_dump(mode="json") for item in _resources(db)]
    return collection_response(rows, request)


@router.post("/plan")
def create_compute_plan(
    payload: ComputePlanRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("compute.plan")),
    db: Session = Depends(get_db),
):
    plan = build_compute_plan(payload.model_dump(mode="json"), _resources(db))
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="COMPUTE_PLAN_CREATED",
        resource_type="compute_plan",
        resource_id=plan["plan_id"],
        result="selected" if plan["selected_resource"] else "no_candidate",
        metadata={"events": plan["events"], "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    return api_response(ComputePlanResponse(**plan).model_dump(mode="json"), request)


@router.post("/schedule")
def schedule_compute(
    payload: ComputePlanRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("compute.schedule")),
    db: Session = Depends(get_db),
):
    plan = build_compute_plan(payload.model_dump(mode="json"), _resources(db))
    accepted = plan["selected_resource"] is not None
    required_events = ["COMPUTE_PLAN_CREATED", "MODEL_SELECTED", "INFERENCE_STARTED"] if accepted else ["COMPUTE_PLAN_CREATED"]
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="MODEL_SELECTED" if accepted else "COMPUTE_PLAN_BLOCKED",
        resource_type="compute_plan",
        resource_id=plan["plan_id"],
        result="accepted" if accepted else "blocked",
        metadata={"required_events": required_events, "selected_resource": plan["selected_resource"], "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    response = ComputeScheduleResponse(accepted=accepted, plan=ComputePlanResponse(**plan), required_events=required_events, audit_recorded=True)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/infer")
def infer_with_compute_fabric(
    payload: ComputeInferRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("compute.infer")),
    db: Session = Depends(get_db),
):
    plan = build_compute_plan(payload.model_dump(mode="json"), _resources(db))
    accepted = plan["selected_resource"] is not None
    governance = {
        "dry_run_only": payload.dry_run,
        "execution_boundary": "gateway_provider_execution" if not payload.dry_run else "planning_only",
        "requires_existing_gateway_for_live_inference": True,
        "policy_enforced": True,
    }
    provider_execution = {
        "status": "not_started" if payload.dry_run else "ready_for_gateway_dispatch",
        "selected_resource": plan["selected_resource"],
        "prompt_hash": payload.prompt_hash,
    }
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="INFERENCE_STARTED" if accepted and not payload.dry_run else "COMPUTE_PLAN_CREATED",
        resource_type="compute_inference",
        resource_id=plan["plan_id"],
        result="dry_run" if payload.dry_run else ("accepted" if accepted else "blocked"),
        metadata={"governance": governance, "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    response = ComputeInferResponse(
        accepted=accepted,
        dry_run=payload.dry_run,
        execution_plan=ComputePlanResponse(**plan),
        provider_execution=provider_execution,
        governance=governance,
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/cost")
def get_compute_cost(
    request: Request,
    context: RequestContext = Depends(require_permission("compute.view")),
    db: Session = Depends(get_db),
):
    response = ComputeCostResponse(**cost_summary(_resources(db)))
    return api_response(response.model_dump(mode="json"), request)


@router.get("/cache")
def get_compute_cache_policy(
    request: Request,
    context: RequestContext = Depends(require_permission("compute.view")),
):
    policy = cache_policy({"objective": "default", "required_capabilities": [], "maximum_context_tokens": 8192, "cache_policy": "prefer_cache"})
    response = ComputeCacheResponse(
        enabled=True,
        cache_policy=policy["policy"],
        cacheable_items=policy["cacheable_items"],
        invalidation_rules=policy["invalidation"],
        estimated_lookup_ms=policy["lookup_ms"],
    )
    return api_response(response.model_dump(mode="json"), request)
