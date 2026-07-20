from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    RepositoryDependencyResponse,
    RepositoryIndexRequest,
    RepositoryIndexResponse,
    RepositoryQueryRequest,
    RepositorySearchResponse,
)
from .service import dependency_graph, get_index, index_repository_path, search_index


router = APIRouter(prefix="/api/v1/repository", tags=["repository-intelligence"])


@router.post("/index")
def index_repository(
    payload: RepositoryIndexRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("repository.index")),
    db: Session = Depends(get_db),
):
    try:
        result = index_repository_path(
            payload.root_path,
            repository_id=payload.repository_id,
            max_files=payload.max_files,
            max_file_bytes=payload.max_file_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error_class": "repository_invalid", "message": str(exc)}) from exc

    profile = result["profile"]
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="REPOSITORY_INTELLIGENCE_INDEXED",
        resource_type="repository",
        resource_id=profile["id"],
        result="completed",
        metadata={
            "root": profile["root"],
            "graph_hash": profile["graph_hash"],
            "indexed_file_count": profile["indexed_file_count"],
            "symbol_count": len(result["symbols"]),
            "relationship_count": len(result["relationships"]),
            "correlation_id": str(context.correlation_id),
        },
    )
    db.commit()
    return api_response(RepositoryIndexResponse(**result).model_dump(mode="json"), request)


@router.get("/profile")
def repository_profile(
    request: Request,
    repository_id: str = Query(min_length=1, max_length=160),
    context: RequestContext = Depends(require_permission("repository.view")),
):
    result = get_index(repository_id)
    if not result:
        raise HTTPException(status_code=404, detail={"error_class": "repository_index_missing", "message": "Repository index not found. Run POST /api/v1/repository/index first."})
    return api_response(result["profile"], request)


@router.get("/symbols")
def repository_symbols(
    request: Request,
    repository_id: str = Query(min_length=1, max_length=160),
    q: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=500),
    context: RequestContext = Depends(require_permission("repository.view")),
):
    result = get_index(repository_id)
    if not result:
        raise HTTPException(status_code=404, detail={"error_class": "repository_index_missing", "message": "Repository index not found."})
    symbols = result["symbols"]
    if q:
        needle = q.lower()
        symbols = [item for item in symbols if needle in item["name"].lower() or needle in item["file"].lower()]
    return api_response(symbols[:limit], request)


@router.get("/dependencies")
def repository_dependencies(
    request: Request,
    repository_id: str = Query(min_length=1, max_length=160),
    context: RequestContext = Depends(require_permission("repository.view")),
):
    return api_response(RepositoryDependencyResponse(**dependency_graph(repository_id)).model_dump(mode="json"), request)


@router.get("/tests")
def repository_tests(
    request: Request,
    repository_id: str = Query(min_length=1, max_length=160),
    context: RequestContext = Depends(require_permission("repository.view")),
):
    result = get_index(repository_id)
    if not result:
        raise HTTPException(status_code=404, detail={"error_class": "repository_index_missing", "message": "Repository index not found."})
    return api_response(result["tests"], request)


@router.get("/architecture")
def repository_architecture(
    request: Request,
    repository_id: str = Query(min_length=1, max_length=160),
    context: RequestContext = Depends(require_permission("repository.view")),
):
    result = get_index(repository_id)
    if not result:
        raise HTTPException(status_code=404, detail={"error_class": "repository_index_missing", "message": "Repository index not found."})
    return api_response(result["architecture"], request)


@router.get("/search")
def repository_search(
    request: Request,
    repository_id: str = Query(min_length=1, max_length=160),
    q: str = Query(min_length=1, max_length=500),
    limit: int = Query(default=20, ge=1, le=100),
    context: RequestContext = Depends(require_permission("repository.search")),
):
    return api_response(RepositorySearchResponse(**search_index(repository_id, q, limit=limit)).model_dump(mode="json"), request)
