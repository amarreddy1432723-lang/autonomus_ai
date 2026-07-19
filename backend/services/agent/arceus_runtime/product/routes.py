from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.mission_factory import create_surface_mission
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    ExperimentRequest,
    ExperimentResponse,
    ProductDashboardResponse,
    ProductMetricsResponse,
    ProductOpportunityResponse,
    ProductRequirementRequest,
    ProductRequirementResponse,
    ReleaseResponse,
    RoadmapItemResponse,
    PersonaResponse,
)
from .service import build_roadmap, create_experiment, default_personas, discover_opportunities, generate_requirement, planned_releases, product_dashboard, product_metrics


router = APIRouter(prefix="/api/v1/product", tags=["product-intelligence"])


@router.get("/opportunities")
def list_opportunities(
    request: Request,
    framework: str = Query(default="rice", pattern="^(rice|ice|moscow|wsjf|value_effort)$"),
    context: RequestContext = Depends(require_permission("product.view")),
):
    rows = [ProductOpportunityResponse(**item).model_dump(mode="json") for item in discover_opportunities(framework=framework)]
    return collection_response(rows, request)


@router.get("/roadmap")
def get_roadmap(
    request: Request,
    context: RequestContext = Depends(require_permission("product.view")),
):
    rows = [RoadmapItemResponse(**item).model_dump(mode="json") for item in build_roadmap()]
    return collection_response(rows, request)


@router.post("/requirements")
def create_requirement(
    payload: ProductRequirementRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("product.requirement.create")),
    db: Session = Depends(get_db),
):
    result = generate_requirement(payload.model_dump(mode="json"))
    mission = create_surface_mission(
        db,
        context,
        surface="product",
        title=f"Implement PRD: {payload.title}",
        objective=result["mission_seed"]["objective"],
        status="plan_pending",
        priority=4 if result["priority"]["priority_score"] >= 75 else 3,
        risk_level="medium",
        source={"requirement": payload.model_dump(mode="json"), "requirement_id": result["requirement_id"], "priority": result["priority"]},
        desired_outcomes=result["objectives"],
        constraints=result["risks"],
    )
    result["mission_seed"] = {
        **result["mission_seed"],
        "durable_mission_id": str(mission.id),
        "project_id": str(mission.project_id),
        "status": mission.status,
    }
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="PRD_GENERATED",
        resource_type="product_requirement",
        resource_id=result["requirement_id"],
        result="completed",
        metadata={
            "title": payload.title,
            "priority_score": result["priority"]["priority_score"],
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    response = ProductRequirementResponse(**result)
    return api_response(response.model_dump(mode="json"), request)


@router.get("/personas")
def list_personas(
    request: Request,
    context: RequestContext = Depends(require_permission("product.view")),
):
    rows = [PersonaResponse(**item).model_dump(mode="json") for item in default_personas()]
    return collection_response(rows, request)


@router.post("/experiments")
def create_product_experiment(
    payload: ExperimentRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("product.experiment.create")),
    db: Session = Depends(get_db),
):
    result = create_experiment(payload.model_dump(mode="json"))
    mission = create_surface_mission(
        db,
        context,
        surface="product",
        title=f"Experiment: {payload.hypothesis[:120]}",
        objective=f"Run product experiment: {payload.hypothesis}",
        status="awaiting_plan_approval" if result["status"] == "approval_required" else "ready",
        priority=3,
        risk_level="medium" if result["status"] == "ready" else "high",
        source={"experiment": payload.model_dump(mode="json"), "experiment_id": result["experiment_id"]},
        desired_outcomes=[f"Measure {metric}" for metric in payload.metrics],
        constraints=["Respect rollout limits.", "Collect statistically useful evidence.", "Stop if guardrail metrics regress."],
    )
    result["governance"] = {
        **result["governance"],
        "durable_mission_id": str(mission.id),
        "project_id": str(mission.project_id),
        "mission_status": mission.status,
    }
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="EXPERIMENT_STARTED" if result["status"] == "ready" else "EXPERIMENT_APPROVAL_REQUIRED",
        resource_type="product_experiment",
        resource_id=result["experiment_id"],
        result=result["status"],
        metadata={"owner": payload.owner, "rollout": payload.rollout, "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    response = ExperimentResponse(**result)
    return api_response(response.model_dump(mode="json"), request)


@router.get("/releases")
def list_releases(
    request: Request,
    context: RequestContext = Depends(require_permission("product.view")),
):
    rows = [ReleaseResponse(**item).model_dump(mode="json") for item in planned_releases()]
    return collection_response(rows, request)


@router.get("/metrics")
def get_product_metrics(
    request: Request,
    context: RequestContext = Depends(require_permission("product.view")),
):
    response = ProductMetricsResponse(**product_metrics())
    return api_response(response.model_dump(mode="json"), request)


@router.get("/dashboard")
def get_product_dashboard(
    request: Request,
    context: RequestContext = Depends(require_permission("product.view")),
):
    response = ProductDashboardResponse(**product_dashboard())
    return api_response(response.model_dump(mode="json"), request)
