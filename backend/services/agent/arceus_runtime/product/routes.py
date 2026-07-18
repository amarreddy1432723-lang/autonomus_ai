from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
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
