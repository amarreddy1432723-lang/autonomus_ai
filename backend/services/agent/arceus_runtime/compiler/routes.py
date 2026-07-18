from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import CompilerRunDetailResponse, CompilerRunSummaryResponse


router = APIRouter(tags=["compiler"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _compiler_run_summary(compiler_run) -> CompilerRunSummaryResponse:
    return CompilerRunSummaryResponse(
        id=compiler_run.id,
        mission_id=compiler_run.mission_id,
        source_mission_version=int(compiler_run.source_mission_version),
        status=compiler_run.status,
        current_stage=compiler_run.current_stage,
        warning_codes=compiler_run.warning_codes or [],
        error_code=compiler_run.error_code,
        error_message=compiler_run.error_message,
        started_at=compiler_run.started_at,
        completed_at=compiler_run.completed_at,
        created_at=compiler_run.created_at,
        updated_at=compiler_run.updated_at,
        version_number=int(compiler_run.version_number),
    )


@router.get("/api/v1/missions/{mission_id}/compiler-runs")
def list_mission_compiler_runs(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("compiler.view")),
    status: str | None = Query(default=None, max_length=60),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    compiler_runs = uow.compiler_runs.list_for_mission(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        status=status,
        limit=limit,
    )
    return collection_response([_compiler_run_summary(item).model_dump(mode="json") for item in compiler_runs], request)


@router.get("/api/v1/compiler-runs/{compiler_run_id}")
def get_compiler_run(
    compiler_run_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("compiler.view")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    compiler_run = uow.compiler_runs.get(tenant_id=context.tenant_id, compiler_run_id=compiler_run_id)
    response = CompilerRunDetailResponse(
        **_compiler_run_summary(compiler_run).model_dump(),
        stage_results=compiler_run.stage_results or {},
        source_manifest_id=compiler_run.source_manifest_id,
        compiled_mission_version_id=compiler_run.compiled_mission_version_id,
        model_execution_ids=[str(item) for item in (compiler_run.model_execution_ids or [])],
    )
    return api_response(response.model_dump(mode="json"), request)

