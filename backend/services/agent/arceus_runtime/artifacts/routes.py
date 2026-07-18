from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import ArtifactContentResponse, ArtifactSummaryResponse, ArtifactVersionResponse


router = APIRouter(tags=["artifacts"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _artifact_summary(artifact) -> ArtifactSummaryResponse:
    return ArtifactSummaryResponse(
        id=artifact.id,
        mission_id=artifact.mission_id,
        task_id=artifact.task_id,
        artifact_key=artifact.artifact_key,
        artifact_type=artifact.artifact_type,
        title=artifact.title,
        current_version_id=artifact.current_version_id,
        trust_status=artifact.trust_status,
        metadata_json=artifact.metadata_json or {},
        created_at=artifact.created_at,
        updated_at=artifact.updated_at,
        version_number=artifact.version_number,
    )


def _artifact_version(version) -> ArtifactVersionResponse:
    return ArtifactVersionResponse(
        id=version.id,
        artifact_id=version.artifact_id,
        version=version.version,
        content_hash=version.content_hash,
        produced_by_member_id=version.produced_by_member_id,
        provenance=version.provenance or {},
        created_at=version.created_at,
        version_number=version.version_number,
    )


@router.get("/api/v1/missions/{mission_id}/artifacts")
def list_mission_artifacts(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("artifact.view")),
    artifact_type: str | None = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    artifacts = uow.artifacts.list_for_mission(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        artifact_type=artifact_type,
        limit=limit,
    )
    return collection_response([_artifact_summary(item).model_dump(mode="json") for item in artifacts], request)


@router.get("/api/v1/artifacts/{artifact_id}")
def get_artifact(
    artifact_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("artifact.view")),
    db: Session = Depends(get_db),
):
    artifact = _uow(db).artifacts.get(tenant_id=context.tenant_id, artifact_id=artifact_id)
    return api_response(_artifact_summary(artifact).model_dump(mode="json"), request)


@router.get("/api/v1/artifacts/{artifact_id}/versions")
def list_artifact_versions(
    artifact_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("artifact.view")),
    db: Session = Depends(get_db),
):
    versions = _uow(db).artifacts.versions(tenant_id=context.tenant_id, artifact_id=artifact_id)
    return collection_response([_artifact_version(item).model_dump(mode="json") for item in versions], request)


@router.get("/api/v1/artifact-versions/{version_id}/content")
def get_artifact_version_content(
    version_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("artifact.view")),
    db: Session = Depends(get_db),
):
    version = _uow(db).artifacts.get_version(tenant_id=context.tenant_id, version_id=version_id)
    response = ArtifactContentResponse(
        id=version.id,
        artifact_id=version.artifact_id,
        version=version.version,
        content_hash=version.content_hash,
        produced_by_member_id=version.produced_by_member_id,
        provenance=version.provenance or {},
        created_at=version.created_at,
        version_number=version.version_number,
        content=version.content or {},
    )
    return api_response(response.model_dump(mode="json"), request)
