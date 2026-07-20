from __future__ import annotations

from uuid import uuid4

from backend.services.agent.arceus_runtime.execution_engine.api_schemas import (
    EffectReservationRequest,
    LeasePlanRequest,
    MissionTransitionRequest,
    NodeExecutionPolicy,
    NodeState,
    ResourceRequirement,
    SchedulerRequest,
    WorkflowCompileRequest,
    WorkflowEdgeSpec,
    WorkflowNodeSpec,
)
from backend.services.agent.arceus_runtime.execution_engine.service import (
    compile_workflow,
    mission_progress,
    plan_lease,
    reserve_effect,
    schedule_ready_nodes,
    validate_mission_transition,
    validate_workflow,
)


def _node(node_id: str, deps: list[str] | None = None, *, node_type: str = "agent_task", priority: int = 50, side_effect: str = "none") -> WorkflowNodeSpec:
    return WorkflowNodeSpec(
        node_id=node_id,
        node_type=node_type,  # type: ignore[arg-type]
        name=node_id.replace("_", " ").title(),
        dependencies=deps or [],
        priority=priority,
        required_capabilities=["coding"] if node_type == "agent_task" else [],
        execution_policy=NodeExecutionPolicy(side_effect_level=side_effect),  # type: ignore[arg-type]
    )


def test_workflow_compile_adds_dependency_edges_and_topological_order() -> None:
    request = WorkflowCompileRequest(nodes=[_node("inspect"), _node("implement", ["inspect"]), _node("verify", ["implement"], node_type="verification")])

    workflow = compile_workflow(request)

    assert workflow.validation.valid is True
    assert workflow.validation.topological_order == ["inspect", "implement", "verify"]
    assert ("inspect", "implement") in {(edge.from_node_id, edge.to_node_id) for edge in workflow.edges}
    assert workflow.entry_node_ids == ["inspect"]
    assert workflow.terminal_node_ids == ["verify"]


def test_dag_validation_rejects_cycles() -> None:
    nodes = [_node("a", ["c"]), _node("b", ["a"]), _node("c", ["b"])]

    result = validate_workflow(nodes, [])

    assert result.valid is False
    assert any("WORKFLOW_CYCLE_DETECTED" in item for item in result.errors)


def test_unsafe_side_effect_requires_approval_predecessor() -> None:
    deploy = _node("deploy", side_effect="irreversible")

    result = validate_workflow([deploy], [])

    assert result.valid is False
    assert "without an approval predecessor" in result.errors[0]


def test_scheduler_only_dispatches_dependency_satisfied_nodes() -> None:
    workflow = compile_workflow(WorkflowCompileRequest(nodes=[_node("inspect", priority=40), _node("implement", ["inspect"], priority=80), _node("verify", ["implement"], node_type="verification")]))
    states = [NodeState(node_id="inspect", status="succeeded")]

    result = schedule_ready_nodes(SchedulerRequest(workflow=workflow, node_states=states, maximum_dispatch=5))

    assert [node.node_id for node in result.ready_nodes] == ["implement"]
    assert any(item.node_id == "verify" and item.missing_dependencies == ["implement"] for item in result.blocked)


def test_scheduler_respects_resource_locks() -> None:
    node = _node("edit_file")
    node.resource_requirements = [ResourceRequirement(resource_type="file", resource_key="src/app.ts", lock_mode="exclusive")]
    workflow = compile_workflow(WorkflowCompileRequest(nodes=[node]))

    result = schedule_ready_nodes(SchedulerRequest(workflow=workflow, locked_resources=["file:src/app.ts"]))

    assert result.ready_nodes == []
    assert result.blocked[0].unresolved_conditions == ["resource_lock_unavailable"]


def test_mission_transition_blocks_terminal_restart() -> None:
    accepted = validate_mission_transition(MissionTransitionRequest(current_status="approved", requested_status="queued"))
    rejected = validate_mission_transition(MissionTransitionRequest(current_status="completed", requested_status="running"))

    assert accepted.allowed is True
    assert accepted.event_type == "MISSION_QUEUED"
    assert rejected.allowed is False


def test_lease_plan_is_stable_and_contains_fencing_token() -> None:
    mission_id = uuid4()
    request = LeasePlanRequest(mission_id=mission_id, node_id="implement", worker_id="worker-a", logical_attempt=2)

    first = plan_lease(request)
    second = plan_lease(request)

    assert first.idempotency_key == second.idempotency_key
    assert first.fencing_token == second.fencing_token
    assert "abort_if_lease_expired" in first.safety_rules


def test_effect_reservation_deduplicates_by_idempotency_key() -> None:
    request = EffectReservationRequest(
        mission_id=uuid4(),
        node_id="deploy",
        execution_id="exec-1",
        effect_type="deployment",
        target_resource="production",
        idempotency_key="same-key",
        existing_effects=[{"id": "effect-existing", "idempotency_key": "same-key", "status": "applied"}],
    )

    response = reserve_effect(request)

    assert response.reserved is False
    assert response.status == "duplicate"
    assert response.effect_id == "effect-existing"


def test_weighted_progress_counts_running_as_partial() -> None:
    workflow = compile_workflow(WorkflowCompileRequest(nodes=[_node("a"), _node("b", ["a"]), _node("c", ["b"])]))

    progress = mission_progress(workflow, [NodeState(node_id="a", status="succeeded"), NodeState(node_id="b", status="running")])

    assert progress == 50.0
