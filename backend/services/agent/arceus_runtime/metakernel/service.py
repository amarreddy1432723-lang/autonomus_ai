from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID


CANONICAL_LIFECYCLE = ["created", "validated", "active", "modified", "verified", "archived", "deleted"]

ENTITY_REGISTRY: dict[str, dict[str, Any]] = {
    "tenant": {
        "table": "arceus_tenants",
        "owner_field": None,
        "tenant_scoped": False,
        "versioned": True,
        "required_links": [],
        "invariants": ["tenant_is_root_scope", "logical_deletion_only"],
    },
    "organization": {
        "table": "arceus_mission_organizations",
        "owner_field": "mission_id",
        "tenant_scoped": True,
        "versioned": True,
        "required_links": ["tenant", "mission"],
        "invariants": ["organization_belongs_to_tenant", "organization_has_purpose"],
    },
    "workspace": {
        "table": "arceus_projects",
        "owner_field": "created_by",
        "tenant_scoped": True,
        "versioned": True,
        "required_links": ["tenant", "identity"],
        "invariants": ["workspace_belongs_to_tenant"],
    },
    "mission": {
        "table": "arceus_missions",
        "owner_field": "created_by",
        "tenant_scoped": True,
        "versioned": True,
        "required_links": ["tenant", "workspace", "identity"],
        "invariants": ["mission_has_objective", "mission_has_owner", "mission_policy_validated_before_execution"],
    },
    "workflow": {
        "table": "arceus_workflow_definitions",
        "owner_field": "mission_id",
        "tenant_scoped": True,
        "versioned": True,
        "required_links": ["tenant", "mission"],
        "invariants": ["workflow_has_mission", "workflow_graph_is_versioned"],
    },
    "task": {
        "table": "arceus_tasks",
        "owner_field": "mission_id",
        "tenant_scoped": True,
        "versioned": True,
        "required_links": ["tenant", "mission"],
        "invariants": ["task_has_mission", "task_completion_requires_verification"],
    },
    "specialist": {
        "table": "arceus_specialist_profiles",
        "owner_field": None,
        "tenant_scoped": False,
        "versioned": True,
        "required_links": ["capability", "policy"],
        "invariants": ["specialist_follows_contract", "specialist_authority_is_policy_controlled"],
    },
    "knowledge": {
        "table": "arceus_memory_items",
        "owner_field": "scope_reference_id",
        "tenant_scoped": True,
        "versioned": True,
        "required_links": ["tenant", "evidence"],
        "invariants": ["knowledge_has_provenance", "promotion_requires_approval"],
    },
    "decision": {
        "table": "arceus_decisions",
        "owner_field": "mission_id",
        "tenant_scoped": True,
        "versioned": True,
        "required_links": ["tenant", "mission", "evidence"],
        "invariants": ["decision_references_evidence", "decision_records_alternatives"],
    },
    "evidence": {
        "table": "arceus_evidence",
        "owner_field": "mission_id",
        "tenant_scoped": True,
        "versioned": True,
        "required_links": ["tenant", "mission"],
        "invariants": ["evidence_is_immutable", "evidence_has_hash"],
    },
    "policy": {
        "table": "arceus_policies",
        "owner_field": None,
        "tenant_scoped": True,
        "versioned": True,
        "required_links": ["tenant"],
        "invariants": ["policy_evaluation_is_audited"],
    },
    "resource": {
        "table": "arceus_budgets",
        "owner_field": "scope_id",
        "tenant_scoped": True,
        "versioned": True,
        "required_links": ["tenant", "policy"],
        "invariants": ["resource_use_is_budgeted"],
    },
    "event": {
        "table": "arceus_events",
        "owner_field": "aggregate_id",
        "tenant_scoped": True,
        "versioned": True,
        "required_links": ["tenant", "identity"],
        "invariants": ["events_are_immutable", "aggregate_version_monotonic"],
    },
    "artifact": {
        "table": "arceus_artifacts",
        "owner_field": "mission_id",
        "tenant_scoped": True,
        "versioned": True,
        "required_links": ["tenant", "mission", "evidence"],
        "invariants": ["artifact_links_to_originating_mission"],
    },
    "capability": {
        "table": "arceus_capabilities",
        "owner_field": None,
        "tenant_scoped": False,
        "versioned": True,
        "required_links": ["policy"],
        "invariants": ["capability_has_verification_method"],
    },
    "identity": {
        "table": "arceus_users",
        "owner_field": None,
        "tenant_scoped": False,
        "versioned": True,
        "required_links": ["tenant_membership"],
        "invariants": ["identity_is_policy_subject"],
    },
}

CONTRACT_REGISTRY: dict[str, dict[str, Any]] = {
    "scheduler": {
        "purpose": "Schedule and recover governed organizational work.",
        "operations": ["schedule", "pause", "resume", "cancel", "checkpoint", "recover", "verify"],
        "required_events": ["SCHEDULED", "CHECKPOINT_CREATED", "RECOVERED", "VERIFIED"],
        "invariants": ["task_has_mission", "runtime_action_replayable"],
    },
    "specialist": {
        "purpose": "Provide interchangeable human, AI, and system specialist behavior.",
        "operations": ["plan", "execute", "review", "explain", "verify", "learn"],
        "required_events": ["SPECIALIST_ASSIGNED", "ACTION_EXPLAINED", "VERIFICATION_RECORDED"],
        "invariants": ["specialist_follows_contract", "implementer_cannot_be_only_reviewer"],
    },
    "knowledge": {
        "purpose": "Retrieve, verify, promote, and archive governed organizational knowledge.",
        "operations": ["search", "retrieve", "promote", "verify", "archive"],
        "required_events": ["CONTEXT_ASSEMBLED", "KNOWLEDGE_VERIFIED", "KNOWLEDGE_PROMOTED"],
        "invariants": ["knowledge_has_provenance", "promotion_requires_approval"],
    },
    "policy": {
        "purpose": "Evaluate and audit every authority-sensitive action.",
        "operations": ["evaluate", "approve", "deny", "recommend", "audit"],
        "required_events": ["POLICY_ENFORCED", "APPROVAL_REQUESTED", "APPROVAL_RECORDED"],
        "invariants": ["policy_evaluation_is_audited", "no_automation_bypasses_governance"],
    },
    "runtime": {
        "purpose": "Execute durable work using leases, checkpoints, heartbeats, and completion evidence.",
        "operations": ["initialize", "lease", "execute", "checkpoint", "heartbeat", "complete", "shutdown"],
        "required_events": ["LEASE_GRANTED", "HEARTBEAT_RECORDED", "TASK_COMPLETED"],
        "invariants": ["runtime_action_replayable", "completion_requires_verification"],
    },
    "storage": {
        "purpose": "Persist versioned state across SQL, graph, vector, and object stores.",
        "operations": ["read", "write", "query", "version", "archive", "replicate"],
        "required_events": ["ENTITY_CREATED", "ENTITY_VERSIONED", "ENTITY_ARCHIVED"],
        "invariants": ["entity_version_monotonic", "logical_deletion_only"],
    },
}

INVARIANTS: list[dict[str, Any]] = [
    {"invariant_key": "execution_belongs_to_mission", "statement": "Every execution belongs to a mission.", "severity": "critical", "enforced_by": ["runtime", "scheduler", "policy"]},
    {"invariant_key": "mission_belongs_to_organization", "statement": "Every mission belongs to an organization before execution.", "severity": "critical", "enforced_by": ["organization", "mission", "policy"]},
    {"invariant_key": "organization_belongs_to_tenant", "statement": "Every organization belongs to a tenant.", "severity": "critical", "enforced_by": ["identity", "storage"]},
    {"invariant_key": "action_generates_audit", "statement": "Every material action generates an audit event.", "severity": "high", "enforced_by": ["api", "audit"]},
    {"invariant_key": "decision_references_evidence", "statement": "Every decision references evidence or remains review-required.", "severity": "high", "enforced_by": ["decision", "evidence", "policy"]},
    {"invariant_key": "promotion_requires_verification", "statement": "Every promotion references verification and approval.", "severity": "critical", "enforced_by": ["knowledge", "learning", "approval"]},
    {"invariant_key": "entity_version_monotonic", "statement": "Every entity version increases monotonically.", "severity": "high", "enforced_by": ["storage", "event"]},
    {"invariant_key": "runtime_action_replayable", "statement": "Every runtime action is replayable from events and checkpoints.", "severity": "high", "enforced_by": ["runtime", "event"]},
    {"invariant_key": "specialist_follows_contract", "statement": "Every AI specialist follows constitutional governance.", "severity": "high", "enforced_by": ["specialist", "policy"]},
    {"invariant_key": "no_subsystem_bypasses_metakernel", "statement": "No subsystem bypasses identity, authorization, validation, event, and audit.", "severity": "critical", "enforced_by": ["api", "policy", "audit"]},
]

CONSTITUTIONAL_PATH = ["identity", "authorization", "validation", "execution", "verification", "event", "audit"]


def canonical_entities() -> list[dict[str, Any]]:
    return [
        {
            "entity_type": key,
            "lifecycle": CANONICAL_LIFECYCLE,
            **value,
        }
        for key, value in sorted(ENTITY_REGISTRY.items())
    ]


def canonical_contracts() -> list[dict[str, Any]]:
    return [{"contract_key": key, **value} for key, value in sorted(CONTRACT_REGISTRY.items())]


def kernel_invariants() -> list[dict[str, Any]]:
    return INVARIANTS


def validate_kernel_payload(*, entity_type: str, payload: dict[str, Any], intended_action: str) -> dict[str, Any]:
    normalized_type = entity_type.strip().lower()
    entity = ENTITY_REGISTRY.get(normalized_type)
    violations: list[dict[str, Any]] = []
    required_events = ["CONTRACT_VALIDATED"]
    if not entity:
        violations.append({"invariant": "canonical_entity_required", "severity": "critical", "message": "Entity type is not in the Meta-Kernel canonical model."})
        return _validation_result(violations, required_events)

    required_events.extend(["POLICY_ENFORCED", "EVENT_COMMITTED"])
    for link in entity["required_links"]:
        if link == "tenant":
            continue
        field_name = f"{link}_id"
        if field_name not in payload and link not in payload:
            violations.append({"invariant": f"{normalized_type}_requires_{link}", "severity": "high", "message": f"{normalized_type} requires explicit {link} linkage."})

    if entity["versioned"] and int(payload.get("version", payload.get("version_number", 1)) or 0) < 1:
        violations.append({"invariant": "entity_version_monotonic", "severity": "high", "message": "Version must start at 1 or greater."})

    status = str(payload.get("status", "created")).lower()
    if status not in CANONICAL_LIFECYCLE and status not in {"draft", "pending", "ready", "running", "completed", "failed", "approved", "proposed", "verified"}:
        violations.append({"invariant": "canonical_lifecycle_required", "severity": "medium", "message": f"Status '{status}' is not a canonical lifecycle or runtime state."})

    action = intended_action.strip().lower()
    if action in {"execute", "run", "complete"} and normalized_type in {"task", "mission", "workflow"}:
        if normalized_type != "mission" and "mission_id" not in payload:
            violations.append({"invariant": "execution_belongs_to_mission", "severity": "critical", "message": "Execution action requires mission_id."})
        if action == "complete" and not payload.get("verification") and not payload.get("evidence_ids"):
            violations.append({"invariant": "completion_requires_verification", "severity": "critical", "message": "Completion requires verification or evidence_ids."})

    if normalized_type == "decision" and not payload.get("evidence_ids"):
        violations.append({"invariant": "decision_references_evidence", "severity": "high", "message": "Decision must reference evidence or stay review-required."})

    if action in {"promote", "learn"} and not payload.get("verification_id") and not payload.get("evidence_ids"):
        violations.append({"invariant": "promotion_requires_verification", "severity": "critical", "message": "Promotion/learning requires verification evidence."})

    return _validation_result(violations, required_events)


def _validation_result(violations: list[dict[str, Any]], required_events: list[str]) -> dict[str, Any]:
    critical = any(item.get("severity") == "critical" for item in violations)
    return {
        "valid": not critical and not violations,
        "status": "valid" if not violations else "blocked" if critical else "review_required",
        "violations": violations,
        "required_events": sorted(set(required_events)),
        "required_audit": True,
        "constitutional_path": CONSTITUTIONAL_PATH,
    }


def replay_events(*, aggregate_type: str, aggregate_id: UUID, events: list[Any], from_version: int, to_version: int | None) -> dict[str, Any]:
    filtered = [
        event
        for event in events
        if int(event.aggregate_version) >= from_version and (to_version is None or int(event.aggregate_version) <= to_version)
    ]
    state: dict[str, Any] = {
        "aggregate_type": aggregate_type,
        "aggregate_id": str(aggregate_id),
        "status": "created" if filtered else "unknown",
        "version": from_version - 1,
        "facts": {},
        "timeline": [],
    }
    violations: list[dict[str, Any]] = []
    previous_version = from_version - 1
    for event in sorted(filtered, key=lambda item: int(item.aggregate_version)):
        version = int(event.aggregate_version)
        if version != previous_version + 1:
            violations.append(
                {
                    "invariant": "aggregate_version_monotonic",
                    "severity": "high",
                    "message": f"Expected version {previous_version + 1}, received {version}.",
                }
            )
        previous_version = version
        payload = event.payload or {}
        state["version"] = version
        state["status"] = payload.get("status") or _status_from_event_type(event.event_type, state["status"])
        state["facts"].update(payload.get("facts") or {})
        state["timeline"].append(
            {
                "version": version,
                "event_type": event.event_type,
                "actor_type": event.actor_type,
                "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
            }
        )
    return {
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "replayable": not any(item["severity"] == "critical" for item in violations),
        "version_range": {"from": from_version, "to": to_version or (filtered[-1].aggregate_version if filtered else None)},
        "event_count": len(filtered),
        "state": state,
        "violations": violations,
    }


def _status_from_event_type(event_type: str, current: str) -> str:
    lowered = event_type.lower()
    if "created" in lowered:
        return "created"
    if "validated" in lowered:
        return "validated"
    if "started" in lowered or "active" in lowered or "running" in lowered:
        return "active"
    if "verified" in lowered or "completed" in lowered:
        return "verified"
    if "archived" in lowered:
        return "archived"
    if "deleted" in lowered:
        return "deleted"
    return current


def event_stream_health(events: list[Any]) -> dict[str, Any]:
    grouped: dict[tuple[str, UUID], list[int]] = defaultdict(list)
    for event in events:
        grouped[(event.aggregate_type, event.aggregate_id)].append(int(event.aggregate_version))
    gaps = []
    for (aggregate_type, aggregate_id), versions in grouped.items():
        ordered = sorted(versions)
        expected = list(range(ordered[0], ordered[-1] + 1)) if ordered else []
        missing = sorted(set(expected) - set(ordered))
        if missing:
            gaps.append({"aggregate_type": aggregate_type, "aggregate_id": str(aggregate_id), "missing_versions": missing})
    return {"stream_count": len(grouped), "event_count": len(events), "version_gaps": gaps, "deterministic_replay_ready": not gaps}
