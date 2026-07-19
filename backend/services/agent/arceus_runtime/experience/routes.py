from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.mission_factory import create_surface_mission
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    DashboardResponse,
    IntentExecutionResponse,
    IntentRequest,
    IntentResponse,
    PersonalWorkspaceResponse,
    SearchRequest,
    SearchResponse,
    TimelineItemResponse,
    VoiceRequest,
    VoiceResponse,
)
from .service import build_personal_workspace, dashboard, detect_intent, execute_intent, smart_search, timeline, voice_response


router = APIRouter(tags=["unified-experience"])


@router.get("/api/v1/workspace")
def get_personal_workspace(
    request: Request,
    context: RequestContext = Depends(require_permission("experience.workspace.view")),
):
    response = PersonalWorkspaceResponse(**build_personal_workspace(str(context.user_id)))
    return api_response(response.model_dump(mode="json"), request)


@router.get("/api/v1/intents")
def preview_intent(
    request: Request,
    q: str = Query(min_length=1, max_length=2_000),
    mode: str = Query(default="chat"),
    context: RequestContext = Depends(require_permission("experience.intent.view")),
):
    response = IntentResponse(**detect_intent({"objective": q, "mode": mode}, user_id=str(context.user_id)))
    return api_response(response.model_dump(mode="json"), request)


@router.post("/api/v1/intents/execute")
def execute_user_intent(
    payload: IntentRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("experience.intent.execute")),
    db: Session = Depends(get_db),
):
    result = execute_intent(payload.model_dump(mode="json"), user_id=str(context.user_id))
    mission = create_surface_mission(
        db,
        context,
        surface="experience",
        title=f"{result['intent']['category'].title()}: {payload.objective[:180]}",
        objective=payload.objective,
        status="awaiting_plan_approval" if result["status"] == "requires_confirmation" else "plan_pending",
        priority=4 if result["status"] == "requires_confirmation" else 3,
        risk_level="high" if result["status"] == "requires_confirmation" else "medium",
        source={"intent": result["intent"], "mode": payload.mode, "entities": payload.entities},
        desired_outcomes=result["response"].get("next_actions") or [],
        constraints=payload.constraints,
    )
    result["mission_thread"] = {
        **result["mission_thread"],
        "linked_mission_id": str(mission.id),
        "project_id": str(mission.project_id),
        "durable": True,
    }
    result["intent"]["context"] = {**result["intent"]["context"], "current_mission": str(mission.id)}
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="INTENT_RECEIVED",
        resource_type="intent",
        resource_id=result["intent"]["intent_id"],
        result=result["status"],
        metadata={
            "category": result["intent"]["category"],
            "mode": payload.mode,
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    response = IntentExecutionResponse(**result)
    return api_response(response.model_dump(mode="json"), request)


@router.get("/api/v1/timeline")
def get_timeline(
    request: Request,
    context: RequestContext = Depends(require_permission("experience.timeline.view")),
):
    rows = [TimelineItemResponse(**item).model_dump(mode="json") for item in timeline()]
    return collection_response(rows, request)


@router.get("/api/v1/dashboard")
def get_dashboard(
    request: Request,
    role: str = Query(default="developer", max_length=80),
    context: RequestContext = Depends(require_permission("experience.dashboard.view")),
):
    response = DashboardResponse(**dashboard(role=role))
    return api_response(response.model_dump(mode="json"), request)


@router.post("/api/v1/voice")
def interpret_voice(
    payload: VoiceRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("experience.voice")),
    db: Session = Depends(get_db),
):
    result = voice_response(payload.model_dump(mode="json"), user_id=str(context.user_id))
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="VOICE_COMMAND",
        resource_type="intent",
        resource_id=result["intent"]["intent_id"],
        result="requires_confirmation" if result["requires_confirmation"] else "interpreted",
        metadata={"locale": payload.locale, "device": payload.device, "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    response = VoiceResponse(**result)
    return api_response(response.model_dump(mode="json"), request)


@router.post("/api/v1/search")
def search_everything(
    payload: SearchRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("experience.search")),
):
    response = SearchResponse(**smart_search(payload.model_dump(mode="json")))
    return api_response(response.model_dump(mode="json"), request)
