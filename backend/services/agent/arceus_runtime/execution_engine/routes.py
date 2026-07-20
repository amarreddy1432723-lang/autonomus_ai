from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response
from .api_schemas import (
    EffectReservationRequest,
    LeasePlanRequest,
    MissionTransitionRequest,
    SchedulerRequest,
    WorkflowCompileRequest,
)
from .service import compile_workflow, plan_lease, reserve_effect, schedule_ready_nodes, validate_mission_transition, validate_workflow


router = APIRouter(prefix="/api/v1/execution-engine", tags=["execution-engine"])


@router.post("/workflows/compile")
def compile_execution_workflow(
    payload: WorkflowCompileRequest,
    request: Request,
    _context: RequestContext = Depends(require_permission("runtime.execute")),
):
    response = compile_workflow(payload)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/workflows/validate")
def validate_execution_workflow(
    payload: WorkflowCompileRequest,
    request: Request,
    _context: RequestContext = Depends(require_permission("runtime.report")),
):
    response = validate_workflow(payload.nodes, payload.edges)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/schedule")
def schedule_execution_nodes(
    payload: SchedulerRequest,
    request: Request,
    _context: RequestContext = Depends(require_permission("runtime.schedule")),
):
    response = schedule_ready_nodes(payload)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/transitions/validate")
def validate_execution_transition(
    payload: MissionTransitionRequest,
    request: Request,
    _context: RequestContext = Depends(require_permission("runtime.report")),
):
    response = validate_mission_transition(payload)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/leases/plan")
def plan_execution_lease(
    payload: LeasePlanRequest,
    request: Request,
    _context: RequestContext = Depends(require_permission("runtime.lease")),
):
    response = plan_lease(payload)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/effects/reserve")
def reserve_execution_effect(
    payload: EffectReservationRequest,
    request: Request,
    _context: RequestContext = Depends(require_permission("runtime.execute")),
):
    response = reserve_effect(payload)
    return api_response(response.model_dump(mode="json"), request)
