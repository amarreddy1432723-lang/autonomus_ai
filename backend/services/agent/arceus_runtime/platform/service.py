from __future__ import annotations

import os
from typing import Any

from services.shared.arceus_core_models import ArceusProviderProfile, ArceusTenant

from ..operations.service import configured_regions, region_status


DEFAULT_COMPLIANCE_BY_REGION = {
    "local": ["development"],
    "india": ["soc2", "iso27001"],
    "asia": ["soc2", "iso27001"],
    "us": ["soc2", "hipaa", "pci_dss"],
    "europe": ["gdpr", "soc2", "iso27001"],
    "government": ["government_baseline"],
}

SENSITIVE_FEDERATION_SCOPES = {"secrets", "private_repository", "billing", "identity", "customer_pii"}


def configured_platform_regions() -> list[str]:
    return configured_regions()


def _region_family(region_key: str) -> str:
    lowered = region_key.lower()
    if lowered in DEFAULT_COMPLIANCE_BY_REGION:
        return lowered
    if lowered.startswith(("in-", "ap-south", "india")):
        return "india"
    if lowered.startswith(("eu-", "europe")):
        return "europe"
    if lowered.startswith(("us-", "america")):
        return "us"
    if lowered.startswith(("gov", "government")):
        return "government"
    if lowered == "local":
        return "local"
    return "asia" if lowered.startswith(("ap-", "asia")) else "local"


def _as_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.replace(";", ",").split(",") if item.strip()]
    return fallback


def region_control_plane_status(*, region_key: str, providers: list[ArceusProviderProfile]) -> dict[str, Any]:
    base = region_status(region_key=region_key, providers=providers)
    family = _region_family(region_key)
    return {
        **base,
        "compliance_profiles": DEFAULT_COMPLIANCE_BY_REGION.get(family, ["soc2"]),
        "data_residency_zones": [region_key] if region_key != "local" else ["local"],
        "edge_runtime": {
            "enabled": os.getenv("ARCEUS_EDGE_RUNTIME_ENABLED", "false").lower() == "true",
            "low_latency_inference": True,
            "local_policy_checks": True,
            "heavy_mission_escalation": "regional_cluster",
        },
    }


def tenant_platform_profile(tenant: ArceusTenant) -> dict[str, Any]:
    settings = tenant.settings or {}
    regions = configured_platform_regions()
    home_region = str(settings.get("home_region") or settings.get("region") or regions[0])
    residency_regions = _as_list(settings.get("residency_regions"), [home_region])
    compliance_profiles = _as_list(settings.get("compliance_profiles"), DEFAULT_COMPLIANCE_BY_REGION.get(_region_family(home_region), ["soc2"]))
    failover_allowed = _as_list(settings.get("failover_regions"), [item for item in regions if item in residency_regions] or [home_region])
    federation = settings.get("federation") if isinstance(settings.get("federation"), dict) else {}
    return {
        "tenant_id": tenant.id,
        "name": tenant.name,
        "slug": tenant.slug,
        "status": tenant.status,
        "plan_key": tenant.plan_key,
        "deployment_model": settings.get("deployment_model", "multi_tenant_saas"),
        "home_region": home_region,
        "residency_regions": residency_regions,
        "compliance_profiles": compliance_profiles,
        "isolation": {
            "identity": True,
            "missions": True,
            "memory": True,
            "knowledge_graph": True,
            "secrets": True,
            "billing": True,
            "audit_logs": True,
        },
        "failover_policy": {
            "mode": settings.get("failover_mode", "manual_approval"),
            "allowed_regions": failover_allowed,
            "rto_seconds": int(settings.get("rto_seconds", 60)),
            "rpo_seconds": int(settings.get("rpo_seconds", 300)),
        },
        "federation_policy": {
            "enabled": bool(federation.get("enabled", False)),
            "allowed_scopes": _as_list(federation.get("allowed_scopes"), ["capability_catalog", "verified_lessons"]),
            "requires_explicit_approval": bool(federation.get("requires_explicit_approval", True)),
            "implicit_trust": False,
        },
    }


def residency_allows_region(tenant_profile: dict[str, Any], region_key: str) -> bool:
    regions = tenant_profile.get("residency_regions") or []
    return "global" in regions or region_key in regions


def evaluate_federation_request(tenant_profile: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    requested = [str(scope) for scope in payload.get("shared_scopes", [])]
    policy = tenant_profile.get("federation_policy") or {}
    allowed = set(policy.get("allowed_scopes") or [])
    enabled = bool(policy.get("enabled"))
    authorized = [scope for scope in requested if scope in allowed and scope not in SENSITIVE_FEDERATION_SCOPES]
    denied = [scope for scope in requested if scope not in authorized]
    if not enabled:
        return {
            "accepted": False,
            "status": "disabled",
            "authorized_scopes": [],
            "denied_scopes": requested,
            "required_approvals": ["tenant_owner", "security_reviewer"],
            "reason": "Federation is disabled for this tenant.",
            "event_type": "FEDERATION_DENIED",
        }
    if denied:
        return {
            "accepted": False,
            "status": "needs_policy_update",
            "authorized_scopes": authorized,
            "denied_scopes": denied,
            "required_approvals": ["tenant_owner", "security_reviewer"],
            "reason": "Federation request includes scopes not authorized by tenant policy.",
            "event_type": "FEDERATION_DENIED",
        }
    return {
        "accepted": bool(payload.get("dry_run", True)),
        "status": "dry_run_accepted" if payload.get("dry_run", True) else "needs_approval",
        "authorized_scopes": authorized,
        "denied_scopes": [],
        "required_approvals": ["tenant_owner", "security_reviewer"],
        "reason": "Federation is policy-safe; live federation still requires approval and key exchange.",
        "event_type": "FEDERATION_ESTABLISHED" if payload.get("dry_run", True) else "FEDERATION_REQUESTED",
    }


def calculate_capacity_posture(summary: dict[str, Any], *, region_count: int) -> dict[str, Any]:
    task_statuses = summary.get("task_statuses") or {}
    mission_statuses = summary.get("mission_statuses") or {}
    outbox_statuses = summary.get("outbox_statuses") or {}
    active_missions = int(mission_statuses.get("running", 0)) + int(mission_statuses.get("approved", 0))
    ready_tasks = int(task_statuses.get("ready", 0))
    running_tasks = int(task_statuses.get("running", 0))
    pending_events = int(outbox_statuses.get("pending", 0)) + int(outbox_statuses.get("processing", 0))
    risks: list[str] = []
    recommendations: list[str] = []
    if region_count < 2:
        risks.append("single_region_deployment")
        recommendations.append("configure_secondary_region_before_public_enterprise_launch")
    if ready_tasks > 100:
        risks.append("worker_queue_saturation")
        recommendations.append("scale_regional_worker_pool")
    if pending_events > 1000:
        risks.append("event_mesh_backlog")
        recommendations.append("increase_outbox_relay_capacity")
    if int(summary.get("stale_processing_outbox", 0)) > 0:
        risks.append("stale_event_processing")
        recommendations.append("run_recovery_worker")
    status = "healthy" if not risks else "warning"
    if any(risk in risks for risk in ["event_mesh_backlog", "stale_event_processing"]):
        status = "degraded"
    safety_margin = max(0.1, min(1.0, 1.0 - (ready_tasks / 1000.0) - (pending_events / 5000.0)))
    return {
        "status": status,
        "active_regions": region_count,
        "active_missions": active_missions,
        "ready_tasks": ready_tasks,
        "running_tasks": running_tasks,
        "pending_events": pending_events,
        "capacity_risks": risks,
        "recommendations": recommendations,
        "safety_margin": round(safety_margin, 3),
    }
