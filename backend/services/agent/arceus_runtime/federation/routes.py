from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusMemoryItem
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..compiler.utils import stable_hash
from .api_schemas import (
    FederationCreateRequest,
    FederationCreateResponse,
    FederationDelegateRequest,
    FederationDelegateResponse,
    FederationJoinRequest,
    FederationJoinResponse,
    FederationMemberResponse,
    FederationStatusResponse,
    KnowledgeShareRequest,
    KnowledgeShareResponse,
    ResourceNegotiationRequest,
    ResourceNegotiationResponse,
)
from .service import create_federation, evaluate_join_request, federation_status, build_delegation, knowledge_share_decision, negotiate_resources, organization_payload


router = APIRouter(prefix="/api/v1/federation", tags=["global-orchestration-mesh"])


def _persist(db: Session, context: RequestContext, *, title: str, content_type: str, content: dict, event_type: str, lifecycle_status: str = "verified") -> ArceusMemoryItem:
    content_hash = stable_hash({"content_type": content_type, "title": title, "content": content})
    existing = (
        db.query(ArceusMemoryItem)
        .filter(
            ArceusMemoryItem.tenant_id == context.tenant_id,
            ArceusMemoryItem.memory_scope == "organization",
            ArceusMemoryItem.content_hash == content_hash,
        )
        .first()
    )
    if existing:
        return existing
    row = ArceusMemoryItem(
        tenant_id=context.tenant_id,
        memory_scope="organization",
        title=title,
        content=json.dumps(content, sort_keys=True, default=str),
        content_type=content_type,
        source_type="federation_protocol",
        source_ids=[str(content.get("federation_id") or content.get("delegation_id") or content.get("share_id") or content.get("agreement_id") or title)],
        evidence_ids=[str(item) for item in content.get("evidence_ids", [])],
        lifecycle_status=lifecycle_status,
        trust_level="governed",
        confidence=0.82,
        sensitivity="organization",
        content_hash=content_hash,
    )
    db.add(row)
    db.flush()
    SqlAlchemyUnitOfWork(db).audit.record(
        tenant_id=context.tenant_id,
        actor_id=context.user_id,
        action=event_type,
        resource_type=content_type,
        resource_id=row.id,
        result=lifecycle_status,
        metadata={"content_hash": content_hash, "correlation_id": str(context.correlation_id)},
    )
    return row


def _federation_memories(db: Session, tenant_id: UUID, limit: int = 200) -> list[dict]:
    rows = (
        db.query(ArceusMemoryItem)
        .filter(ArceusMemoryItem.tenant_id == tenant_id, ArceusMemoryItem.content_type.like("federation%"))
        .order_by(ArceusMemoryItem.created_at.desc())
        .limit(limit)
        .all()
    )
    payloads = []
    for row in rows:
        try:
            content = json.loads(row.content)
        except (TypeError, json.JSONDecodeError):
            content = {}
        payloads.append({"id": str(row.id), "title": row.title, "content_type": row.content_type, "content": content, "created_at": row.created_at})
    return payloads


def _members_from_memory(memories: list[dict]) -> list[dict]:
    members: dict[str, dict] = {}
    for item in memories:
        content = item.get("content") or {}
        if item.get("content_type") == "federation":
            for member in content.get("members", []):
                members[member["organization_id"]] = member
        if item.get("content_type") == "federation_member" and content.get("organization"):
            org = content["organization"]
            members[org["organization_id"]] = org
    return list(members.values())


@router.post("/create", status_code=status.HTTP_201_CREATED)
def create_federation_endpoint(
    payload: FederationCreateRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("federation.create")),
    db: Session = Depends(get_db),
):
    result = create_federation(payload.model_dump(mode="json"))
    row = _persist(db, context, title=result["name"], content_type="federation", content=result, event_type="FEDERATION_CREATED")
    db.commit()
    result["federation_id"] = row.id
    return api_response(FederationCreateResponse(**result).model_dump(mode="json"), request)


@router.post("/join", status_code=status.HTTP_201_CREATED)
def join_federation(
    payload: FederationJoinRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("federation.join")),
    db: Session = Depends(get_db),
):
    result = evaluate_join_request(payload.model_dump(mode="json"))
    _persist(db, context, title=f"Federation member {result['organization_id']}", content_type="federation_member", content=result, event_type=result["events"][0], lifecycle_status="verified" if result["status"] == "joined" else "proposed")
    db.commit()
    return api_response(FederationJoinResponse(**{key: value for key, value in result.items() if key != "organization"}).model_dump(mode="json"), request)


@router.post("/delegate", status_code=status.HTTP_201_CREATED)
def delegate_mission(
    payload: FederationDelegateRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("federation.delegate")),
    db: Session = Depends(get_db),
):
    result = build_delegation(payload.model_dump(mode="json"))
    _persist(db, context, title=f"Delegation for {payload.global_mission[:120]}", content_type="federation_delegation", content=result, event_type=result["events"][0], lifecycle_status="verified" if result["status"] == "contract_ready" else "proposed")
    db.commit()
    return api_response(FederationDelegateResponse(**result).model_dump(mode="json"), request)


@router.get("/status")
def get_federation_status(
    request: Request,
    context: RequestContext = Depends(require_permission("federation.view")),
    db: Session = Depends(get_db),
):
    response = FederationStatusResponse(**federation_status(_federation_memories(db, context.tenant_id)))
    return api_response(response.model_dump(mode="json"), request)


@router.get("/members")
def list_federation_members(
    request: Request,
    capability: str | None = Query(default=None, max_length=120),
    context: RequestContext = Depends(require_permission("federation.view")),
    db: Session = Depends(get_db),
):
    members = _members_from_memory(_federation_memories(db, context.tenant_id))
    if capability:
        key = capability.lower().replace(" ", "_")
        members = [member for member in members if key in member.get("capabilities", []) or key in member.get("specializations", [])]
    return collection_response([FederationMemberResponse(**member).model_dump(mode="json") for member in members], request)


@router.post("/knowledge/share", status_code=status.HTTP_201_CREATED)
def share_knowledge(
    payload: KnowledgeShareRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("federation.knowledge.share")),
    db: Session = Depends(get_db),
):
    members = _members_from_memory(_federation_memories(db, context.tenant_id))
    result = knowledge_share_decision(payload.model_dump(mode="json"), members)
    _persist(db, context, title=payload.title, content_type="federation_knowledge_share", content={**payload.model_dump(mode="json"), **result}, event_type=result["events"][0], lifecycle_status="verified" if result["authorized_targets"] else "proposed")
    db.commit()
    return api_response(KnowledgeShareResponse(**result).model_dump(mode="json"), request)


@router.post("/resources/negotiate", status_code=status.HTTP_201_CREATED)
def negotiate_federated_resources(
    payload: ResourceNegotiationRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("federation.resources.negotiate")),
    db: Session = Depends(get_db),
):
    result = negotiate_resources(payload.model_dump(mode="json"))
    _persist(db, context, title=f"Resource agreement for {payload.requesting_organization_id}", content_type="federation_resource_agreement", content={**payload.model_dump(mode="json"), **result}, event_type=result["events"][0], lifecycle_status="verified" if result["status"] == "allocated" else "proposed")
    db.commit()
    return api_response(ResourceNegotiationResponse(**result).model_dump(mode="json"), request)
