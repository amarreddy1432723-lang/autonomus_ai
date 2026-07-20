from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class PlatformRegionResponse(BaseModel):
    region_key: str
    role: str
    status: str
    provider_count: int
    healthy_provider_count: int
    compliance_profiles: list[str]
    data_residency_zones: list[str]
    edge_runtime: dict[str, Any]
    warnings: list[str]


class PlatformTenantResponse(BaseModel):
    tenant_id: UUID
    name: str
    slug: str
    status: str
    plan_key: str
    deployment_model: str
    home_region: str
    residency_regions: list[str]
    compliance_profiles: list[str]
    isolation: dict[str, bool]
    failover_policy: dict[str, Any]
    federation_policy: dict[str, Any]


class FederationRequest(BaseModel):
    peer_deployment_id: str = Field(min_length=3, max_length=160)
    peer_region: str = Field(min_length=2, max_length=120)
    shared_scopes: list[str] = Field(default_factory=list)
    purpose: str = Field(min_length=3, max_length=500)
    dry_run: bool = True


class FederationResponse(BaseModel):
    accepted: bool
    status: str
    peer_deployment_id: str
    peer_region: str
    authorized_scopes: list[str]
    denied_scopes: list[str]
    required_approvals: list[str]
    reason: str
    event_type: str


class PlatformHealthResponse(BaseModel):
    status: str
    ready: bool
    blockers: list[str]
    warnings: list[str]
    control_plane: dict[str, Any]
    regional_planes: list[dict[str, Any]]
    data_residency: dict[str, Any]
    federation: dict[str, Any]
    checked_at: datetime


class PlatformCapacityResponse(BaseModel):
    status: str
    active_regions: int
    active_missions: int
    ready_tasks: int
    running_tasks: int
    pending_events: int
    capacity_risks: list[str]
    recommendations: list[str]
    safety_margin: float


class PlatformFailoverRequest(BaseModel):
    target_region: str = Field(min_length=2, max_length=120)
    reason: str = Field(min_length=3, max_length=2_000)
    dry_run: bool = True


class PlatformFailoverResponse(BaseModel):
    accepted: bool
    dry_run: bool
    status: str
    target_region: str
    reason: str
    required_approvals: list[str]
    residency_safe: bool
    event_type: str
    audit_recorded: bool
