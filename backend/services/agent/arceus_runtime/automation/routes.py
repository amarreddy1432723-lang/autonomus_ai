from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    AutomationDashboardResponse,
    AutomationExecuteRequest,
    AutomationExecuteResponse,
    AutomationMissionResponse,
    AutomationOrganizationResponse,
    AutomationTemplateRequest,
    AutomationTemplateResponse,
    AutomationTriggerRequest,
    AutomationTriggerResponse,
)
from .service import active_automation_missions, automation_dashboard, create_trigger, execute_automation, list_organizations, register_template, template_catalog


router = APIRouter(prefix="/api/v1/automation", tags=["enterprise-automation"])


@router.post("/triggers")
def create_automation_trigger(
    payload: AutomationTriggerRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("automation.trigger.create")),
    db: Session = Depends(get_db),
):
    result = create_trigger(payload.model_dump(mode="json"))
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="AUTOMATION_TRIGGERED",
        resource_type="automation_trigger",
        resource_id=result["trigger_id"],
        result=result["status"],
        metadata={
            "domain": payload.domain,
            "risk_level": result["risk_level"],
            "mission_id": result["generated_mission"]["mission_id"],
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    response = AutomationTriggerResponse(**result)
    return api_response(response.model_dump(mode="json"), request)


@router.get("/missions")
def list_automation_missions(
    request: Request,
    context: RequestContext = Depends(require_permission("automation.view")),
):
    rows = [AutomationMissionResponse(**item).model_dump(mode="json") for item in active_automation_missions()]
    return collection_response(rows, request)


@router.post("/templates")
def create_automation_template(
    payload: AutomationTemplateRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("automation.template.create")),
    db: Session = Depends(get_db),
):
    result = register_template(payload.model_dump(mode="json"))
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="AUTOMATION_TEMPLATE_REGISTERED",
        resource_type="automation_template",
        resource_id=result["template_key"],
        result="registered",
        metadata={"domain": payload.domain, "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    response = AutomationTemplateResponse(**result)
    return api_response(response.model_dump(mode="json"), request)


@router.get("/organizations")
def list_automation_organizations(
    request: Request,
    context: RequestContext = Depends(require_permission("automation.view")),
):
    rows = [AutomationOrganizationResponse(**item).model_dump(mode="json") for item in list_organizations()]
    return collection_response(rows, request)


@router.post("/execute")
def execute_automation_workflow(
    payload: AutomationExecuteRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("automation.execute")),
    db: Session = Depends(get_db),
):
    result = execute_automation(payload.model_dump(mode="json"))
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="WORKFLOW_STARTED" if result["accepted"] else "POLICY_BLOCKED",
        resource_type="automation_execution",
        resource_id=result["execution_id"],
        result=result["status"],
        metadata={"domain": payload.domain, "risk_level": payload.risk_level, "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    response = AutomationExecuteResponse(**result)
    return api_response(response.model_dump(mode="json"), request)


@router.get("/dashboard")
def get_automation_dashboard(
    request: Request,
    context: RequestContext = Depends(require_permission("automation.view")),
):
    response = AutomationDashboardResponse(**automation_dashboard())
    return api_response(response.model_dump(mode="json"), request)


@router.get("/templates")
def list_automation_templates(
    request: Request,
    context: RequestContext = Depends(require_permission("automation.view")),
):
    rows = [AutomationTemplateResponse(**item).model_dump(mode="json") for item in template_catalog()]
    return collection_response(rows, request)
