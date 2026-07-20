from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusModelProfile, ArceusProviderProfile, ArceusRoutingDecision
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from .api_schemas import ModelFeedbackRequest, ModelFeedbackResponse, ModelGatewayRequest
from .service import (
    dry_run_inference,
    estimate_gateway_cost,
    execution_ledger_record,
    provider_health,
    route_models,
    routing_decision_record,
)


router = APIRouter(prefix="/api/v1/model-gateway", tags=["model-gateway"])


def _profiles(db: Session) -> tuple[list[ArceusModelProfile], list[ArceusProviderProfile]]:
    providers = db.query(ArceusProviderProfile).all()
    models = db.query(ArceusModelProfile).all()
    return models, providers


@router.get("/catalog")
def catalog(
    request: Request,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("model.gateway")),
):
    models, providers = _profiles(db)
    provider_map = {provider.provider_key: provider for provider in providers}
    rows = []
    for model in models:
        provider = provider_map.get(model.provider_key)
        rows.append(
            {
                "provider_key": model.provider_key,
                "provider_enabled": bool(provider.enabled) if provider else False,
                "provider_health": provider.health_status if provider else "missing",
                "model_key": model.model_key,
                "display_name": model.display_name,
                "status": model.status,
                "capabilities": model.capabilities or [],
                "context_window_tokens": model.context_window_tokens,
                "supports_streaming": model.supports_streaming,
                "supports_tool_calling": model.supports_tool_calling,
                "supports_structured_output": model.supports_structured_output,
                "data_retention_policy": model.data_retention_policy,
            }
        )
    return collection_response(rows, request)


@router.post("/route")
def route(
    payload: ModelGatewayRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("model.gateway")),
):
    models, providers = _profiles(db)
    routing = route_models(payload, models, providers)
    if payload.mission_id:
        existing = (
            db.query(ArceusRoutingDecision)
            .filter(
                ArceusRoutingDecision.tenant_id == context.tenant_id,
                ArceusRoutingDecision.request_id == payload.request_id,
            )
            .first()
        )
        if existing is None:
            db.add(routing_decision_record(payload, context.tenant_id, routing))
            db.commit()
    return api_response(routing.model_dump(mode="json"), request)


@router.post("/estimate")
def estimate(
    payload: ModelGatewayRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("model.gateway")),
):
    models, providers = _profiles(db)
    response = estimate_gateway_cost(payload, models, providers)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/infer")
def infer(
    payload: ModelGatewayRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("model.gateway")),
):
    models, providers = _profiles(db)
    routing = route_models(payload, models, providers)
    inference = dry_run_inference(payload, routing)
    if payload.mission_id:
        ledger = execution_ledger_record(payload, context.tenant_id, inference)
        db.add(ledger)
        db.commit()
        inference.execution_id = ledger.id
    return api_response(inference.model_dump(mode="json"), request)


@router.get("/health")
def health(
    request: Request,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("model.gateway")),
):
    models, providers = _profiles(db)
    return collection_response([item.model_dump(mode="json") for item in provider_health(providers, models)], request)


@router.post("/feedback")
def feedback(
    payload: ModelFeedbackRequest,
    request: Request,
    db: Session = Depends(get_db),
    context: RequestContext = Depends(require_permission("model.gateway")),
):
    model = db.query(ArceusModelProfile).filter(ArceusModelProfile.model_key == payload.model_key).first()
    if model is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Model profile not found.")
    quality_scores = dict(model.quality_scores or {})
    previous = quality_scores.get(payload.task_type)
    blended = round((float(previous if previous is not None else payload.quality_score) * 0.7) + (payload.quality_score * 0.3), 4)
    quality_scores[payload.task_type] = blended
    model.quality_scores = quality_scores
    db.commit()
    response = ModelFeedbackResponse(model_key=payload.model_key, task_type=payload.task_type, previous_quality_score=previous, new_quality_score=blended, event_type="MODEL_FEEDBACK_RECORDED")
    return api_response(response.model_dump(mode="json"), request)
