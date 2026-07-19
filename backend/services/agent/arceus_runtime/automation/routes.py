from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusMission
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.mission_factory import create_surface_mission
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
from .service import active_automation_missions, automation_dashboard, create_trigger, execute_automation, get_template, list_organizations, register_template, template_catalog


router = APIRouter(prefix="/api/v1/automation", tags=["enterprise-automation"])


@router.post("/triggers")
def create_automation_trigger(
    payload: AutomationTriggerRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("automation.trigger.create")),
    db: Session = Depends(get_db),
):
    result = create_trigger(payload.model_dump(mode="json"))
    mission_status = "ready" if result["accepted"] else "awaiting_plan_approval"
    mission = create_surface_mission(
        db,
        context,
        surface="automation",
        title=result["generated_mission"]["title"],
        objective=result["generated_mission"]["title"],
        status=mission_status,
        priority=4 if result["risk_level"] in {"high", "critical"} else 3,
        risk_level=result["risk_level"],
        source={"trigger": payload.model_dump(mode="json"), "trigger_id": result["trigger_id"], "workflow_id": result["generated_mission"]["workflow_id"]},
        desired_outcomes=[f"Execute {payload.mission_template} automation with evidence.", "Record policy decision and review state."],
        constraints=["Respect automation policy decision.", "Require human review when policy blocks execution."],
    )
    result["generated_mission"] = {
        **result["generated_mission"],
        "mission_id": str(mission.id),
        "project_id": str(mission.project_id),
        "status": mission.status,
        "durable": True,
    }
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
    db: Session = Depends(get_db),
):
    stored = db.query(ArceusMission).filter(ArceusMission.tenant_id == context.tenant_id).all()
    automation_rows = []
    for mission in stored:
        metadata = mission.metadata_json or {}
        if metadata.get("created_from") != "automation":
            continue
        source = metadata.get("source") or {}
        trigger = source.get("trigger") or {}
        template_key = trigger.get("mission_template") or trigger.get("template_key") or "release"
        workflow_steps = [str(item) for item in get_template(template_key, trigger.get("domain") or "engineering").get("tasks", [])]
        automation_rows.append(
            {
                "mission_id": str(mission.id),
                "title": mission.title,
                "domain": trigger.get("domain") or "engineering",
                "status": mission.status,
                "autonomy_level": trigger.get("autonomy_level") or "L2",
                "risk_level": mission.risk_level,
                "owner_organization": f"{trigger.get('domain') or 'engineering'}_organization",
                "generated_from": trigger.get("source") or "automation",
                "workflow_steps": workflow_steps,
            }
        )
    rows = [AutomationMissionResponse(**item).model_dump(mode="json") for item in (automation_rows or active_automation_missions())]
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
    mission_status = "ready" if result["accepted"] else "awaiting_plan_approval"
    mission = create_surface_mission(
        db,
        context,
        surface="automation",
        title=f"Automation: {payload.template_key.replace('_', ' ').title()}",
        objective=payload.objective,
        status=mission_status,
        priority=4 if payload.risk_level in {"high", "critical"} else 3,
        risk_level=payload.risk_level,
        source={"execution": payload.model_dump(mode="json"), "execution_id": result["execution_id"], "workflow_id": result["workflow"]["workflow_id"]},
        desired_outcomes=result["workflow"].get("objectives") or [],
        constraints=["Respect connector scopes.", "Collect verification evidence.", "Do not bypass required approvals."],
    )
    result["workflow"] = {**result["workflow"], "durable_mission": {"mission_id": str(mission.id), "project_id": str(mission.project_id), "status": mission.status}}
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
