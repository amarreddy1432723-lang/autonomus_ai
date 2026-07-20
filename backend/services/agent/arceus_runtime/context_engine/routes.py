from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import ContextBuildRequest, ContextBuildResponse, ContextCacheEntry, ContextExpandRequest, ContextRankRequest, ContextRankResponse
from .service import analyze_intent, build_context_package, cache_entries, clear_cache, expand_context, rank_candidates


router = APIRouter(prefix="/api/v1/context", tags=["context-engine"])


@router.post("/build")
def build_context(
    payload: ContextBuildRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("context.build")),
    db: Session = Depends(get_db),
):
    package, intent, cache_hit = build_context_package(payload)
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="CONTEXT_PACKAGE_BUILT",
        resource_type="context_package",
        resource_id=package.package_id,
        result="cache_hit" if cache_hit else "completed",
        metadata={
            "mission_id": payload.mission_id,
            "repository_id": package.metadata.get("repository_id"),
            "estimated_tokens": package.estimated_tokens,
            "selected_count": len(package.items),
            "confidence": package.confidence,
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    return api_response(ContextBuildResponse(intent=intent, package=package, cache_hit=cache_hit).model_dump(mode="json"), request)


@router.post("/expand")
def expand_context_package(
    payload: ContextExpandRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("context.build")),
):
    package = expand_context(payload.package_id, payload.query, payload.additional_tokens)
    if package is None:
        raise HTTPException(status_code=404, detail={"error_class": "context_package_missing", "message": "Context package not found in cache."})
    return api_response(package.model_dump(mode="json"), request)


@router.post("/rank")
def rank_context_candidates(
    payload: ContextRankRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("context.view")),
):
    intent = analyze_intent(payload.prompt)
    return api_response(ContextRankResponse(intent=intent, ranked=rank_candidates(payload.candidates, intent)).model_dump(mode="json"), request)


@router.get("/cache")
def get_context_cache(
    request: Request,
    context: RequestContext = Depends(require_permission("context.view")),
):
    return api_response([ContextCacheEntry(**item).model_dump(mode="json") for item in cache_entries()], request)


@router.delete("/cache")
def delete_context_cache(
    request: Request,
    package_id: str | None = Query(default=None, max_length=160),
    context: RequestContext = Depends(require_permission("context.build")),
):
    return api_response({"cleared": clear_cache(package_id)}, request)
