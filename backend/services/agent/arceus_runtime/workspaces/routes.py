from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusArtifact,
    ArceusDecision,
    ArceusEvent,
    ArceusEvidence,
    ArceusMission,
    ArceusMissionOrganization,
    ArceusOrganizationMember,
    ArceusProject,
    ArceusProjectRepository,
)
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    AddWorkspaceRepositoryRequest,
    CreateWorkspaceRequest,
    WorkspaceActivityResponse,
    WorkspaceKnowledgeResponse,
    WorkspaceOrganizationResponse,
    WorkspaceRepositoryResponse,
    WorkspaceResponse,
)
from .service import ACTIVE_MISSION_STATUSES, organization_role_summary, repository_fingerprint, workspace_settings, workspace_slug


router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])


def _workspace_counts(db: Session, *, tenant_id: UUID, workspace_id: UUID) -> tuple[int, int, int]:
    repository_count = (
        db.query(func.count(ArceusProjectRepository.id))
        .filter(ArceusProjectRepository.tenant_id == tenant_id, ArceusProjectRepository.project_id == workspace_id, ArceusProjectRepository.status == "active")
        .scalar()
        or 0
    )
    mission_count = db.query(func.count(ArceusMission.id)).filter(ArceusMission.tenant_id == tenant_id, ArceusMission.project_id == workspace_id).scalar() or 0
    active_mission_count = (
        db.query(func.count(ArceusMission.id))
        .filter(ArceusMission.tenant_id == tenant_id, ArceusMission.project_id == workspace_id, ArceusMission.status.in_(ACTIVE_MISSION_STATUSES))
        .scalar()
        or 0
    )
    return int(repository_count), int(mission_count), int(active_mission_count)


def _workspace_response(db: Session, *, tenant_id: UUID, workspace: ArceusProject) -> WorkspaceResponse:
    repository_count, mission_count, active_mission_count = _workspace_counts(db, tenant_id=tenant_id, workspace_id=workspace.id)
    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        slug=workspace.slug,
        description=workspace.description,
        status=workspace.status,
        settings=workspace.settings or {},
        repository_count=repository_count,
        mission_count=mission_count,
        active_mission_count=active_mission_count,
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
        version_number=int(workspace.version_number or 1),
    )


def _repository_response(repository: ArceusProjectRepository) -> WorkspaceRepositoryResponse:
    return WorkspaceRepositoryResponse(
        id=repository.id,
        project_id=repository.project_id,
        provider=repository.provider,
        repository_url=repository.repository_url,
        default_branch=repository.default_branch,
        local_workspace_path=repository.local_workspace_path,
        status=repository.status,
        metadata_json=repository.metadata_json or {},
        created_at=repository.created_at,
        updated_at=repository.updated_at,
        version_number=int(repository.version_number or 1),
    )


@router.get("")
def list_workspaces(
    request: Request,
    context: RequestContext = Depends(require_permission("workspace.view")),
    status_filter: str | None = Query(default="active", alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    query = db.query(ArceusProject).filter(ArceusProject.tenant_id == context.tenant_id)
    if status_filter:
        query = query.filter(ArceusProject.status == status_filter)
    workspaces = query.order_by(ArceusProject.updated_at.desc(), ArceusProject.id.desc()).limit(limit).all()
    return collection_response([_workspace_response(db, tenant_id=context.tenant_id, workspace=workspace).model_dump(mode="json") for workspace in workspaces], request)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_workspace(
    payload: CreateWorkspaceRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("workspace.create")),
    db: Session = Depends(get_db),
):
    base_slug = workspace_slug(payload.name)
    slug = base_slug
    suffix = 2
    while db.query(ArceusProject.id).filter(ArceusProject.tenant_id == context.tenant_id, ArceusProject.slug == slug).first():
        slug = f"{base_slug}-{suffix}"
        suffix += 1
    workspace = ArceusProject(
        tenant_id=context.tenant_id,
        name=payload.name,
        slug=slug,
        description=payload.description,
        status="active",
        settings=workspace_settings(payload.settings),
        created_by=context.user_id,
    )
    db.add(workspace)
    db.flush()
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="WORKSPACE_CREATED",
        resource_type="workspace",
        resource_id=workspace.id,
        result="created",
        metadata={"slug": slug, "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    db.refresh(workspace)
    return api_response(_workspace_response(db, tenant_id=context.tenant_id, workspace=workspace).model_dump(mode="json"), request)


@router.get("/{workspace_id}/missions")
def list_workspace_missions(
    workspace_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("workspace.view")),
    mission_status: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    SqlAlchemyUnitOfWork(db).projects.get(tenant_id=context.tenant_id, project_id=workspace_id)
    query = db.query(ArceusMission).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.project_id == workspace_id)
    if mission_status:
        query = query.filter(ArceusMission.status == mission_status)
    missions = query.order_by(ArceusMission.updated_at.desc(), ArceusMission.id.desc()).limit(limit).all()
    return collection_response(
        [
            {
                "id": str(mission.id),
                "workspace_id": str(workspace_id),
                "title": mission.title,
                "objective": mission.objective,
                "status": mission.status,
                "risk_level": mission.risk_level,
                "priority": mission.priority,
                "updated_at": mission.updated_at.isoformat() if mission.updated_at else None,
            }
            for mission in missions
        ],
        request,
    )


@router.post("/{workspace_id}/repositories", status_code=status.HTTP_201_CREATED)
def add_workspace_repository(
    workspace_id: UUID,
    payload: AddWorkspaceRepositoryRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("workspace.repository.manage")),
    db: Session = Depends(get_db),
):
    SqlAlchemyUnitOfWork(db).projects.get(tenant_id=context.tenant_id, project_id=workspace_id)
    metadata = {
        **payload.metadata_json,
        "fingerprint": repository_fingerprint(
            provider=payload.provider,
            repository_url=payload.repository_url,
            local_workspace_path=payload.local_workspace_path,
            metadata=payload.metadata_json,
        ),
    }
    repository = ArceusProjectRepository(
        tenant_id=context.tenant_id,
        project_id=workspace_id,
        provider=payload.provider,
        external_repository_id=payload.external_repository_id,
        repository_url=payload.repository_url,
        default_branch=payload.default_branch,
        local_workspace_path=payload.local_workspace_path,
        status="active",
        metadata_json=metadata,
    )
    db.add(repository)
    db.flush()
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action="WORKSPACE_REPOSITORY_ADDED",
        resource_type="workspace_repository",
        resource_id=repository.id,
        result="created",
        metadata={"workspace_id": str(workspace_id), "provider": payload.provider, "correlation_id": str(context.correlation_id)},
    )
    db.commit()
    db.refresh(repository)
    return api_response(_repository_response(repository).model_dump(mode="json"), request)


@router.get("/{workspace_id}/activity")
def list_workspace_activity(
    workspace_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("workspace.view")),
    limit: int = Query(default=100, ge=1, le=250),
    db: Session = Depends(get_db),
):
    SqlAlchemyUnitOfWork(db).projects.get(tenant_id=context.tenant_id, project_id=workspace_id)
    mission_ids = [row.id for row in db.query(ArceusMission.id).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.project_id == workspace_id).all()]
    if not mission_ids:
        return collection_response([], request)
    events = (
        db.query(ArceusEvent)
        .filter(ArceusEvent.tenant_id == context.tenant_id, ArceusEvent.aggregate_type == "mission", ArceusEvent.aggregate_id.in_(mission_ids))
        .order_by(ArceusEvent.occurred_at.desc(), ArceusEvent.id.desc())
        .limit(limit)
        .all()
    )
    return collection_response(
        [
            WorkspaceActivityResponse(
                id=event.id,
                mission_id=event.aggregate_id,
                sequence=int(event.aggregate_version),
                event_type=event.event_type,
                payload=event.payload or {},
                occurred_at=event.occurred_at,
            ).model_dump(mode="json")
            for event in events
        ],
        request,
    )


@router.get("/{workspace_id}/organization")
def get_workspace_organization(
    workspace_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("workspace.view")),
    db: Session = Depends(get_db),
):
    SqlAlchemyUnitOfWork(db).projects.get(tenant_id=context.tenant_id, project_id=workspace_id)
    mission_ids = [row.id for row in db.query(ArceusMission.id).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.project_id == workspace_id).all()]
    organizations = []
    members = []
    if mission_ids:
        organizations = db.query(ArceusMissionOrganization).filter(ArceusMissionOrganization.tenant_id == context.tenant_id, ArceusMissionOrganization.mission_id.in_(mission_ids)).all()
        organization_ids = [organization.id for organization in organizations]
        if organization_ids:
            members = db.query(ArceusOrganizationMember).filter(ArceusOrganizationMember.tenant_id == context.tenant_id, ArceusOrganizationMember.organization_id.in_(organization_ids)).all()
    response = WorkspaceOrganizationResponse(
        workspace_id=workspace_id,
        mission_count=len(mission_ids),
        organization_count=len(organizations),
        active_specialists=sum(1 for member in members if member.status == "active"),
        roles=organization_role_summary(members),
    )
    return api_response(response.model_dump(mode="json"), request)


@router.get("/{workspace_id}/knowledge")
def get_workspace_knowledge(
    workspace_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("workspace.view")),
    db: Session = Depends(get_db),
):
    SqlAlchemyUnitOfWork(db).projects.get(tenant_id=context.tenant_id, project_id=workspace_id)
    mission_ids = [row.id for row in db.query(ArceusMission.id).filter(ArceusMission.tenant_id == context.tenant_id, ArceusMission.project_id == workspace_id).all()]
    if not mission_ids:
        response = WorkspaceKnowledgeResponse(
            workspace_id=workspace_id,
            mission_count=0,
            decision_count=0,
            evidence_count=0,
            artifact_count=0,
            current_decision_count=0,
            trusted_evidence_count=0,
        )
        return api_response(response.model_dump(mode="json"), request)
    decision_count = db.query(func.count(ArceusDecision.id)).filter(ArceusDecision.tenant_id == context.tenant_id, ArceusDecision.mission_id.in_(mission_ids)).scalar() or 0
    current_decision_count = (
        db.query(func.count(ArceusDecision.id))
        .filter(ArceusDecision.tenant_id == context.tenant_id, ArceusDecision.mission_id.in_(mission_ids), ArceusDecision.status != "superseded")
        .scalar()
        or 0
    )
    evidence_count = db.query(func.count(ArceusEvidence.id)).filter(ArceusEvidence.tenant_id == context.tenant_id, ArceusEvidence.mission_id.in_(mission_ids)).scalar() or 0
    trusted_evidence_count = (
        db.query(func.count(ArceusEvidence.id))
        .filter(ArceusEvidence.tenant_id == context.tenant_id, ArceusEvidence.mission_id.in_(mission_ids), ArceusEvidence.status.in_(("validated", "trusted", "verified")))
        .scalar()
        or 0
    )
    artifact_count = db.query(func.count(ArceusArtifact.id)).filter(ArceusArtifact.tenant_id == context.tenant_id, ArceusArtifact.mission_id.in_(mission_ids)).scalar() or 0
    response = WorkspaceKnowledgeResponse(
        workspace_id=workspace_id,
        mission_count=len(mission_ids),
        decision_count=int(decision_count),
        evidence_count=int(evidence_count),
        artifact_count=int(artifact_count),
        current_decision_count=int(current_decision_count),
        trusted_evidence_count=int(trusted_evidence_count),
    )
    return api_response(response.model_dump(mode="json"), request)
