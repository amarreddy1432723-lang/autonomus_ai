from __future__ import annotations

import os
from typing import Any


SLO_TARGETS = {
    "api_availability": 99.95,
    "mission_runtime": 99.99,
    "model_gateway": 99.9,
    "tool_gateway": 99.95,
    "queue_delivery": 99.99,
    "mission_state_durability": 100.0,
}


def configured_regions() -> list[str]:
    raw = os.getenv("ARCEUS_REGIONS") or os.getenv("RAILWAY_REGION") or "local"
    regions = [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]
    return regions or ["local"]


def classify_queue_health(outbox_statuses: dict[str, int], *, stale_processing_outbox: int = 0) -> tuple[str, list[str]]:
    recommendations: list[str] = []
    dead_letter = int(outbox_statuses.get("dead_letter", 0))
    failed = int(outbox_statuses.get("failed", 0))
    pending = int(outbox_statuses.get("pending", 0))
    processing = int(outbox_statuses.get("processing", 0))
    if dead_letter > 0:
        recommendations.append("inspect_dead_letter_queue")
        return "blocked", recommendations
    if stale_processing_outbox > 0:
        recommendations.append("recover_stale_processing_messages")
        return "blocked", recommendations
    if failed > 0:
        recommendations.append("allow_retry_backoff_or_requeue")
        return "degraded", recommendations
    if pending > 1000:
        recommendations.append("enable_overflow_worker_cluster")
        return "degraded", recommendations
    if pending > 100:
        recommendations.append("scale_worker_pool")
        return "warning", recommendations
    if processing == 0 and pending > 0:
        recommendations.append("check_worker_availability")
        return "warning", recommendations
    return "healthy", recommendations


def classify_worker_pool(summary: dict[str, Any]) -> tuple[str, list[str]]:
    recommendations: list[str] = []
    task_statuses = summary.get("task_statuses") or {}
    active_leases = int(summary.get("active_worker_leases", 0))
    ready_tasks = int(task_statuses.get("ready", 0))
    running_tasks = int(task_statuses.get("running", 0))
    blocked_tasks = int(task_statuses.get("blocked", 0))
    failed_tasks = int(task_statuses.get("failed", 0))
    if failed_tasks:
        recommendations.append("triage_failed_tasks")
    if blocked_tasks:
        recommendations.append("resolve_blocked_tasks")
    if ready_tasks > 0 and active_leases == 0:
        recommendations.append("start_or_scale_workers")
        return "starved", recommendations
    if ready_tasks > 100:
        recommendations.append("scale_worker_pool")
        return "saturated", recommendations
    if running_tasks > 0 or active_leases > 0:
        return "active", recommendations
    return "idle", recommendations


def calculate_slo_posture(summary: dict[str, Any]) -> list[dict[str, Any]]:
    outbox_statuses = summary.get("outbox_statuses") or {}
    task_statuses = summary.get("task_statuses") or {}
    blockers: list[str] = []
    warnings: list[str] = []
    if int(outbox_statuses.get("dead_letter", 0)) > 0:
        blockers.append("dead_letter_queue")
    if int(summary.get("stale_processing_outbox", 0)) > 0:
        blockers.append("stale_processing_queue")
    if int(task_statuses.get("failed", 0)) > 0:
        warnings.append("failed_tasks")
    if int(task_statuses.get("blocked", 0)) > 0:
        warnings.append("blocked_tasks")

    observed = {
        "api_availability": 99.95 if not blockers else 99.0,
        "mission_runtime": 99.99 if not blockers else 98.5,
        "model_gateway": 99.9,
        "tool_gateway": 99.95 if not warnings else 99.5,
        "queue_delivery": 99.99 if not blockers else 97.0,
        "mission_state_durability": 100.0,
    }
    results = []
    for key, target in SLO_TARGETS.items():
        value = observed[key]
        status = "met" if value >= target else "breached"
        results.append(
            {
                "slo_key": key,
                "target": target,
                "observed": value,
                "status": status,
                "error_budget_remaining": round(max(value - target, 0.0), 4),
                "burn_reasons": blockers + warnings if status == "breached" else [],
            }
        )
    return results


def region_status(*, region_key: str, providers: list[Any]) -> dict[str, Any]:
    healthy = [provider for provider in providers if getattr(provider, "health_status", "healthy") == "healthy"]
    warnings = []
    if providers and not healthy:
        warnings.append("all_region_providers_unhealthy")
    if not providers:
        warnings.append("no_region_providers_configured")
    return {
        "region_key": region_key,
        "status": "healthy" if not warnings else "degraded",
        "role": "primary" if region_key == configured_regions()[0] else "secondary",
        "data_residency_allowed": True,
        "provider_count": len(providers),
        "healthy_provider_count": len(healthy),
        "warnings": warnings,
    }


def operation_guard(*, action: str, dry_run: bool) -> tuple[bool, str, list[str]]:
    approvals = ["sre_lead", "security_reviewer"]
    if dry_run:
        return True, f"{action} dry run accepted; no infrastructure changes performed.", approvals
    return False, f"{action} requires external infrastructure automation and approval workflow before execution.", approvals
