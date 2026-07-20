from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

from services.agent.arceus_runtime.metakernel.service import (
    canonical_contracts,
    canonical_entities,
    event_stream_health,
    kernel_invariants,
    replay_events,
    validate_kernel_payload,
)


AGGREGATE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _event(version: int, event_type: str, payload: dict | None = None):
    return SimpleNamespace(
        aggregate_type="runtime_mission",
        aggregate_id=AGGREGATE_ID,
        aggregate_version=version,
        event_type=event_type,
        actor_type="system",
        actor_id="tester",
        payload=payload or {},
        metadata_json={},
        occurred_at=datetime.now(timezone.utc),
    )


def test_canonical_entity_model_covers_core_aios_objects():
    entities = {item["entity_type"]: item for item in canonical_entities()}

    for key in ["tenant", "organization", "workspace", "mission", "workflow", "task", "specialist", "knowledge", "decision", "evidence", "policy", "resource", "event", "artifact", "capability", "identity"]:
        assert key in entities
        assert entities[key]["versioned"] is True
        assert "created" in entities[key]["lifecycle"]


def test_contract_registry_exposes_interchangeable_interfaces():
    contracts = {item["contract_key"]: item for item in canonical_contracts()}

    assert contracts["scheduler"]["operations"] == ["schedule", "pause", "resume", "cancel", "checkpoint", "recover", "verify"]
    assert "plan" in contracts["specialist"]["operations"]
    assert "evaluate" in contracts["policy"]["operations"]
    assert "replicate" in contracts["storage"]["operations"]


def test_validation_blocks_execution_without_mission_and_completion_without_evidence():
    task_without_mission = validate_kernel_payload(entity_type="task", payload={"version": 1}, intended_action="execute")
    complete_without_evidence = validate_kernel_payload(entity_type="task", payload={"mission_id": str(AGGREGATE_ID), "version": 1}, intended_action="complete")

    assert task_without_mission["status"] == "blocked"
    assert any(item["invariant"] == "execution_belongs_to_mission" for item in task_without_mission["violations"])
    assert complete_without_evidence["status"] == "blocked"
    assert any(item["invariant"] == "completion_requires_verification" for item in complete_without_evidence["violations"])


def test_decisions_need_evidence_or_review_required():
    decision = validate_kernel_payload(
        entity_type="decision",
        payload={"mission_id": str(AGGREGATE_ID), "version": 1, "alternatives": ["A", "B"]},
        intended_action="record",
    )

    assert decision["status"] == "review_required"
    assert any(item["invariant"] == "decision_references_evidence" for item in decision["violations"])
    assert "POLICY_ENFORCED" in decision["required_events"]


def test_replay_derives_state_and_detects_version_gaps():
    events = [_event(1, "ENTITY_CREATED", {"facts": {"title": "Mission"}}), _event(3, "VERIFICATION_COMPLETED", {"status": "verified"})]
    replay = replay_events(aggregate_type="runtime_mission", aggregate_id=AGGREGATE_ID, events=events, from_version=1, to_version=None)
    health = event_stream_health(events)

    assert replay["state"]["status"] == "verified"
    assert replay["event_count"] == 2
    assert replay["violations"][0]["invariant"] == "aggregate_version_monotonic"
    assert health["deterministic_replay_ready"] is False
    assert health["version_gaps"][0]["missing_versions"] == [2]


def test_invariants_include_no_bypass_rule():
    invariants = {item["invariant_key"]: item for item in kernel_invariants()}

    assert "no_subsystem_bypasses_metakernel" in invariants
    assert invariants["no_subsystem_bypasses_metakernel"]["severity"] == "critical"
