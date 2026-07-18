from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import OrganizationDetailResponse, OrganizationMemberResponse, OrganizationResponse, SpecialistProfileResponse


router = APIRouter(tags=["organizations"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _specialist_profile_response(profile) -> SpecialistProfileResponse | None:
    if profile is None:
        return None
    return SpecialistProfileResponse(
        id=profile.id,
        specialist_key=profile.specialist_key,
        display_name=profile.display_name,
        specialist_type=profile.specialist_type,
        authority_profile=profile.authority_profile or {},
        default_model_policy=profile.default_model_policy or {},
        active=profile.active,
    )


def _organization_response(organization) -> OrganizationResponse:
    return OrganizationResponse(
        id=organization.id,
        mission_id=organization.mission_id,
        organization_name=organization.organization_name,
        status=organization.status,
        rationale=organization.rationale,
        budget_policy=organization.budget_policy or {},
        created_at=organization.created_at,
        updated_at=organization.updated_at,
        version_number=organization.version_number,
    )


def _member_response(member, profile=None) -> OrganizationMemberResponse:
    return OrganizationMemberResponse(
        id=member.id,
        organization_id=member.organization_id,
        specialist_profile_id=member.specialist_profile_id,
        participant_user_id=member.participant_user_id,
        role_key=member.role_key,
        responsibility=member.responsibility,
        authority=member.authority or {},
        can_implement=member.can_implement,
        can_review=member.can_review,
        can_approve=member.can_approve,
        status=member.status,
        specialist_profile=_specialist_profile_response(profile),
        created_at=member.created_at,
        updated_at=member.updated_at,
        version_number=member.version_number,
    )


@router.get("/api/v1/missions/{mission_id}/organization")
def get_mission_organization(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("organization.view")),
    include_members: bool = Query(default=True),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    organization = uow.organizations.get_for_mission(tenant_id=context.tenant_id, mission_id=mission_id)
    if not include_members:
        return api_response(_organization_response(organization).model_dump(mode="json"), request)

    members = []
    for member in uow.organizations.members(tenant_id=context.tenant_id, organization_id=organization.id, status="active", limit=100):
        profile = uow.organizations.specialist_profile(specialist_profile_id=member.specialist_profile_id)
        members.append(_member_response(member, profile))
    response = OrganizationDetailResponse(**_organization_response(organization).model_dump(), members=members)
    return api_response(response.model_dump(mode="json"), request)


@router.get("/api/v1/organizations/{organization_id}/members")
def list_organization_members(
    organization_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("organization.view")),
    member_status: str | None = Query(default=None, alias="status", max_length=60),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.organizations.get(tenant_id=context.tenant_id, organization_id=organization_id)
    members = []
    for member in uow.organizations.members(tenant_id=context.tenant_id, organization_id=organization_id, status=member_status, limit=limit):
        profile = uow.organizations.specialist_profile(specialist_profile_id=member.specialist_profile_id)
        members.append(_member_response(member, profile).model_dump(mode="json"))
    return collection_response(members, request)


@router.get("/api/v1/organization-members/{member_id}")
def get_organization_member(
    member_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("organization.view")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    member = uow.organizations.get_member(tenant_id=context.tenant_id, member_id=member_id)
    profile = uow.organizations.specialist_profile(specialist_profile_id=member.specialist_profile_id)
    return api_response(_member_response(member, profile).model_dump(mode="json"), request)
