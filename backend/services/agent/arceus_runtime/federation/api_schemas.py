from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class FederationOrganizationInput(BaseModel):
    organization_id: str = Field(min_length=2, max_length=160)
    name: str = Field(min_length=2, max_length=240)
    capabilities: list[str] = Field(default_factory=list, max_length=100)
    specializations: list[str] = Field(default_factory=list, max_length=100)
    certifications: list[str] = Field(default_factory=list, max_length=50)
    supported_domains: list[str] = Field(default_factory=list, max_length=50)
    resource_capacity: dict[str, float] = Field(default_factory=dict)
    trust_level: str = Field(default="verified", max_length=80)
    federation_status: str = Field(default="active", max_length=80)


class FederationCreateRequest(BaseModel):
    name: str = Field(min_length=3, max_length=240)
    objectives: list[str] = Field(min_length=1, max_length=50)
    governance: dict[str, Any] = Field(default_factory=dict)
    policies: list[str] = Field(default_factory=list, max_length=100)
    trust_model: str = Field(default="verified_members_only", max_length=120)
    members: list[FederationOrganizationInput] = Field(default_factory=list, max_length=50)


class FederationCreateResponse(BaseModel):
    federation_id: UUID | str
    name: str
    status: str
    objectives: list[str]
    governance: dict[str, Any]
    members: list[dict[str, Any]]
    capability_index: dict[str, list[str]]
    events: list[str]
    created_at: datetime


class FederationJoinRequest(BaseModel):
    federation_id: UUID | None = None
    organization: FederationOrganizationInput
    requested_scopes: list[str] = Field(default_factory=list, max_length=50)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)


class FederationJoinResponse(BaseModel):
    federation_id: UUID | None
    organization_id: str
    status: str
    authorized_scopes: list[str]
    denied_scopes: list[str]
    required_approvals: list[str]
    trust_level: str
    events: list[str]


class FederationDelegateRequest(BaseModel):
    federation_id: UUID | None = None
    mission_id: UUID | None = None
    global_mission: str = Field(min_length=5, max_length=4000)
    required_capabilities: list[str] = Field(min_length=1, max_length=100)
    candidate_organizations: list[FederationOrganizationInput] = Field(default_factory=list, max_length=50)
    deliverables: list[str] = Field(default_factory=list, max_length=100)
    deadline: str | None = Field(default=None, max_length=120)
    evidence_requirements: list[str] = Field(default_factory=list, max_length=100)
    sla: dict[str, Any] = Field(default_factory=dict)
    governance_policies: list[str] = Field(default_factory=list, max_length=100)
    review_requirements: list[str] = Field(default_factory=list, max_length=100)


class FederationDelegateResponse(BaseModel):
    delegation_id: UUID | str
    selected_organization: dict[str, Any] | None
    capability_matches: list[dict[str, Any]]
    contract: dict[str, Any]
    status: str
    synchronization_points: list[dict[str, Any]]
    events: list[str]


class FederationStatusResponse(BaseModel):
    status: str
    federation_count: int
    member_count: int
    delegation_count: int
    open_disputes: int
    shared_knowledge_count: int
    resource_agreements: int
    health: dict[str, Any]
    refreshed_at: datetime


class FederationMemberResponse(BaseModel):
    organization_id: str
    name: str
    capabilities: list[str]
    specializations: list[str]
    certifications: list[str]
    supported_domains: list[str]
    resource_capacity: dict[str, float]
    trust_level: str
    federation_status: str
    score: float | None = None


class KnowledgeShareRequest(BaseModel):
    federation_id: UUID | None = None
    source_organization_id: str = Field(min_length=2, max_length=160)
    target_organization_ids: list[str] = Field(default_factory=list, max_length=50)
    knowledge_type: str = Field(min_length=2, max_length=120)
    title: str = Field(min_length=2, max_length=240)
    content: dict[str, Any] = Field(default_factory=dict)
    trust_level_required: str = Field(default="verified", max_length=80)
    evidence_ids: list[str] = Field(default_factory=list, max_length=100)
    sensitivity: str = Field(default="organization", max_length=80)


class KnowledgeShareResponse(BaseModel):
    share_id: UUID | str
    status: str
    authorized_targets: list[str]
    denied_targets: list[str]
    policy_filters: list[str]
    events: list[str]


class ResourceNegotiationRequest(BaseModel):
    federation_id: UUID | None = None
    requesting_organization_id: str = Field(min_length=2, max_length=160)
    required_resources: dict[str, float] = Field(default_factory=dict)
    candidate_organizations: list[FederationOrganizationInput] = Field(default_factory=list, max_length=50)
    priority: str = Field(default="normal", max_length=80)
    max_cost: float | None = Field(default=None, ge=0)
    sla: dict[str, Any] = Field(default_factory=dict)
    regulatory_constraints: list[str] = Field(default_factory=list, max_length=50)


class ResourceNegotiationResponse(BaseModel):
    agreement_id: UUID | str
    status: str
    selected_provider: dict[str, Any] | None
    allocation: dict[str, float]
    estimated_cost: float
    sla: dict[str, Any]
    unresolved_resources: dict[str, float]
    required_approvals: list[str]
    events: list[str]
