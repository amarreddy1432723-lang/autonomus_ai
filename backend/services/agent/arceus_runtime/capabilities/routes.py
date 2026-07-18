from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import CapabilityResponse, MissionRequiredCapabilityResponse, SpecialistCapabilityResponse


router = APIRouter(tags=["capabilities"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _capability_response(capability) -> CapabilityResponse | None:
    if capability is None:
        return None
    return CapabilityResponse(
        id=capability.id,
        capability_key=capability.capability_key,
        domain=capability.domain,
        name=capability.name,
        description=capability.description,
        verification_methods=capability.verification_methods or [],
        active=capability.active,
        created_at=capability.created_at,
        updated_at=capability.updated_at,
        version_number=capability.version_number,
    )


@router.get("/api/v1/capabilities")
def list_capabilities(
    request: Request,
    context: RequestContext = Depends(require_permission("capability.view")),
    domain: str | None = Query(default=None, max_length=120),
    active: bool | None = Query(default=True),
    limit: int = Query(default=100, ge=1, le=250),
    db: Session = Depends(get_db),
):
    capabilities = _uow(db).capabilities.list(domain=domain, active=active, limit=limit)
    return collection_response([_capability_response(item).model_dump(mode="json") for item in capabilities if item is not None], request)


@router.get("/api/v1/capabilities/{capability_id}")
def get_capability(
    capability_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("capability.view")),
    db: Session = Depends(get_db),
):
    capability = _uow(db).capabilities.get(capability_id=capability_id)
    response = _capability_response(capability)
    return api_response(response.model_dump(mode="json") if response else None, request)


@router.get("/api/v1/missions/{mission_id}/capabilities/required")
def list_required_mission_capabilities(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("capability.view")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    rows = []
    for requirement, capability in uow.capabilities.required_for_mission(tenant_id=context.tenant_id, mission_id=mission_id):
        rows.append(
            MissionRequiredCapabilityResponse(
                id=requirement.id,
                mission_id=requirement.mission_id,
                capability_id=requirement.capability_id,
                reason=requirement.reason,
                required_level=requirement.required_level,
                capability=_capability_response(capability),
                created_at=requirement.created_at,
                updated_at=requirement.updated_at,
                version_number=requirement.version_number,
            ).model_dump(mode="json")
        )
    return collection_response(rows, request)


@router.get("/api/v1/specialist-profiles/{specialist_profile_id}/capabilities")
def list_specialist_capabilities(
    specialist_profile_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("capability.view")),
    db: Session = Depends(get_db),
):
    rows = []
    for specialist_capability, capability in _uow(db).capabilities.specialist_capabilities(specialist_profile_id=specialist_profile_id):
        rows.append(
            SpecialistCapabilityResponse(
                id=specialist_capability.id,
                specialist_profile_id=specialist_capability.specialist_profile_id,
                capability_id=specialist_capability.capability_id,
                proficiency=specialist_capability.proficiency,
                evidence=specialist_capability.evidence or {},
                capability=_capability_response(capability),
                created_at=specialist_capability.created_at,
                updated_at=specialist_capability.updated_at,
                version_number=specialist_capability.version_number,
            ).model_dump(mode="json")
        )
    return collection_response(rows, request)
