from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response
from .api_schemas import (
    PlanValidationRequest,
    PlanValidationResponse,
    PlanningDecisionResponse,
    PlanningIntelligenceRequest,
    ReplanRequest,
    ReplanResponse,
)
from .service import build_planning_decision, replan_from_evidence, validate_planning_response


router = APIRouter(prefix="/api/v1/planning-intelligence", tags=["planning-intelligence"])


@router.post("/plan")
def plan(
    payload: PlanningIntelligenceRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("planning.intelligence")),
):
    response = build_planning_decision(payload)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/simulate")
def simulate(
    payload: PlanningIntelligenceRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("planning.intelligence")),
):
    response = build_planning_decision(payload)
    return api_response(
        {
            "plan_id": response.plan_id,
            "recommended_strategy_key": response.recommended_strategy_key,
            "simulations": [{"strategy_key": item.strategy_key, "simulation": item.simulation, "decision_score": item.decision_score} for item in response.alternatives],
        },
        request,
    )


@router.post("/next-action")
def next_action(
    payload: PlanningIntelligenceRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("planning.intelligence")),
):
    response = build_planning_decision(payload)
    return api_response({"plan_id": response.plan_id, "next_best_action": response.next_best_action}, request)


@router.post("/replan")
def replan(
    payload: ReplanRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("planning.intelligence")),
):
    response = replan_from_evidence(payload)
    return api_response(ReplanResponse(**response.model_dump()).model_dump(mode="json"), request)


@router.post("/validate")
def validate_plan(
    payload: PlanValidationRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("planning.intelligence")),
):
    valid, errors, warnings = validate_planning_response(PlanningDecisionResponse(**payload.plan.model_dump()))
    return api_response(PlanValidationResponse(valid=valid, errors=errors, warnings=warnings).model_dump(mode="json"), request)

