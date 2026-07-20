from __future__ import annotations

from collections import defaultdict, deque
from datetime import timedelta
from typing import Any

from ..compiler.utils import stable_hash
from .api_schemas import (
    DependencyEvaluation,
    EffectReservationRequest,
    EffectReservationResponse,
    ExecutableWorkflowResponse,
    LeasePlanRequest,
    LeasePlanResponse,
    MissionTransitionRequest,
    MissionTransitionResponse,
    NodeRuntimeStatus,
    NodeState,
    ScheduledNodeResponse,
    SchedulerRequest,
    SchedulerResponse,
    WorkflowCompileRequest,
    WorkflowEdgeSpec,
    WorkflowNodeSpec,
    WorkflowValidationResponse,
)


MISSION_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"planning", "cancelled"},
    "planning": {"awaiting_approval", "failed", "cancelled"},
    "awaiting_approval": {"approved", "planning", "cancelled"},
    "approved": {"queued", "planning", "cancelled"},
    "queued": {"running", "paused", "cancelled"},
    "running": {"paused", "blocked", "replanning", "cancelling", "verifying", "failed"},
    "paused": {"running", "cancelling", "cancelled"},
    "blocked": {"running", "replanning", "failed", "cancelling"},
    "replanning": {"running", "awaiting_approval", "failed", "cancelled"},
    "recovering": {"running", "blocked", "failed", "cancelled"},
    "cancelling": {"cancelled"},
    "verifying": {"completed", "partially_completed", "failed", "running"},
    "completed": set(),
    "partially_completed": set(),
    "failed": set(),
    "cancelled": set(),
}

TERMINAL_NODE_STATUSES = {"succeeded", "failed", "skipped", "cancelled", "timed_out"}
SUCCESS_STATUSES = {"succeeded", "skipped"}


def validate_mission_transition(payload: MissionTransitionRequest) -> MissionTransitionResponse:
    current = payload.current_status
    requested = payload.requested_status
    allowed = requested in MISSION_TRANSITIONS[str(current)]
    return MissionTransitionResponse(
        allowed=allowed,
        current_status=current,
        requested_status=requested,
        event_type=f"MISSION_{str(requested).upper()}" if allowed else None,
        reason="Transition accepted by mission state machine." if allowed else f"Cannot transition mission from {current} to {requested}.",
    )


def validate_workflow(nodes: list[WorkflowNodeSpec], edges: list[WorkflowEdgeSpec]) -> WorkflowValidationResponse:
    errors: list[str] = []
    warnings: list[str] = []
    node_by_id: dict[str, WorkflowNodeSpec] = {}
    duplicate_ids: set[str] = set()
    for node in nodes:
        if node.node_id in node_by_id:
            duplicate_ids.add(node.node_id)
        node_by_id[node.node_id] = node
    for node_id in sorted(duplicate_ids):
        errors.append(f"Duplicate node id: {node_id}")

    children: dict[str, list[str]] = defaultdict(list)
    parents: dict[str, list[str]] = {node.node_id: [] for node in nodes}
    seen_edges: set[tuple[str, str]] = set()
    for edge in edges:
        if edge.from_node_id not in node_by_id:
            errors.append(f"Edge {edge.edge_id} references missing source node {edge.from_node_id}.")
            continue
        if edge.to_node_id not in node_by_id:
            errors.append(f"Edge {edge.edge_id} references missing target node {edge.to_node_id}.")
            continue
        pair = (edge.from_node_id, edge.to_node_id)
        if pair in seen_edges:
            warnings.append(f"Duplicate edge pair ignored by scheduler: {edge.from_node_id}->{edge.to_node_id}.")
        seen_edges.add(pair)
        children[edge.from_node_id].append(edge.to_node_id)
        parents[edge.to_node_id].append(edge.from_node_id)

    for node in nodes:
        for dependency in node.dependencies:
            if dependency == node.node_id:
                errors.append(f"Node {node.node_id} cannot depend on itself.")
            elif dependency not in node_by_id:
                errors.append(f"Node {node.node_id} depends on missing node {dependency}.")
            else:
                children[dependency].append(node.node_id)
                parents[node.node_id].append(dependency)
        if node.compensation_node_id and node.compensation_node_id not in node_by_id:
            errors.append(f"Node {node.node_id} has missing compensation node {node.compensation_node_id}.")
        if node.execution_policy.side_effect_level in {"irreversible", "compensatable"} and not _has_approval_predecessor(node.node_id, node_by_id, parents):
            errors.append(f"Node {node.node_id} performs {node.execution_policy.side_effect_level} side effects without an approval predecessor.")
        if node.execution_policy.side_effect_level == "irreversible" and node.compensation_node_id:
            warnings.append(f"Node {node.node_id} is irreversible; compensation node can only record mitigation, not true rollback.")

    indegree = {node.node_id: len(set(parents[node.node_id])) for node in nodes}
    queue = deque(sorted(node_id for node_id, value in indegree.items() if value == 0))
    order: list[str] = []
    while queue:
        node_id = queue.popleft()
        order.append(node_id)
        for child in sorted(set(children.get(node_id, []))):
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if len(order) != len(nodes):
        cyclic = sorted(node_id for node_id, value in indegree.items() if value > 0)
        errors.append("WORKFLOW_CYCLE_DETECTED: " + ", ".join(cyclic))

    entry = sorted(node_id for node_id, incoming in parents.items() if not incoming)
    terminal = sorted(node.node_id for node in nodes if not children.get(node.node_id))
    reachable = _reachable(entry, children)
    for node in nodes:
        if node.node_id not in reachable:
            errors.append(f"Node {node.node_id} is unreachable from workflow entry.")
    reverse_children: dict[str, list[str]] = defaultdict(list)
    for parent, child_ids in children.items():
        for child in child_ids:
            reverse_children[child].append(parent)
    terminal_reachable = _reachable(terminal, reverse_children)
    for node in nodes:
        if node.node_id not in terminal_reachable:
            errors.append(f"Node {node.node_id} cannot reach a terminal node.")

    critical_path, critical_weight = _critical_path(node_by_id, order, parents) if not errors else ([], 0.0)
    return WorkflowValidationResponse(
        valid=not errors,
        errors=errors,
        warnings=warnings,
        topological_order=order if not errors else [],
        entry_node_ids=entry if not errors else [],
        terminal_node_ids=terminal if not errors else [],
        edge_count=len(edges),
        critical_path=critical_path,
        critical_path_weight=round(critical_weight, 4),
    )


def compile_workflow(payload: WorkflowCompileRequest) -> ExecutableWorkflowResponse:
    edges = list(payload.edges)
    existing_pairs = {(edge.from_node_id, edge.to_node_id) for edge in edges}
    for node in payload.nodes:
        for dependency in node.dependencies:
            pair = (dependency, node.node_id)
            if pair not in existing_pairs:
                edges.append(WorkflowEdgeSpec(from_node_id=dependency, to_node_id=node.node_id, edge_type="success"))
                existing_pairs.add(pair)
    validation = validate_workflow(payload.nodes, edges)
    graph_hash = stable_hash(
        {
            "mission_id": str(payload.mission_id),
            "plan_id": str(payload.plan_id),
            "plan_version": payload.plan_version,
            "nodes": [node.model_dump(mode="json") for node in payload.nodes],
            "edges": [edge.model_dump(mode="json") for edge in edges],
            "compiler": payload.compiler_version,
        }
    )
    return ExecutableWorkflowResponse(
        workflow_id=stable_uuid(graph_hash),
        mission_id=payload.mission_id,
        plan_id=payload.plan_id,
        plan_version=payload.plan_version,
        workflow_version=1,
        nodes=payload.nodes,
        edges=edges,
        entry_node_ids=validation.entry_node_ids,
        terminal_node_ids=validation.terminal_node_ids,
        maximum_concurrency=payload.maximum_concurrency,
        compiler_version=payload.compiler_version,
        graph_hash=graph_hash,
        validation=validation,
    )


def schedule_ready_nodes(payload: SchedulerRequest) -> SchedulerResponse:
    if payload.mission_status != "running":
        return SchedulerResponse(ready_nodes=[], blocked=[], events=["MISSION_NOT_RUNNING"], dispatch_count=0)
    state_by_id = {state.node_id: state for state in payload.node_states}
    node_by_id = {node.node_id: node for node in payload.workflow.nodes}
    children, parents = _graph(payload.workflow.nodes, payload.workflow.edges)
    evaluations: list[DependencyEvaluation] = []
    scheduled: list[ScheduledNodeResponse] = []
    used_resources = set(payload.locked_resources)
    for node_id in payload.workflow.validation.topological_order or [node.node_id for node in payload.workflow.nodes]:
        node = node_by_id[node_id]
        state = state_by_id.get(node_id, NodeState(node_id=node_id))
        if state.status in TERMINAL_NODE_STATUSES or state.active_lease_id or state.status in {"leased", "dispatched", "running"}:
            continue
        evaluation = evaluate_dependencies(node_id=node_id, parents=parents, state_by_id=state_by_id)
        if not evaluation.satisfied:
            evaluations.append(evaluation)
            continue
        resource_keys = [f"{item.resource_type}:{item.resource_key}" for item in node.resource_requirements]
        if any(key in used_resources for key in resource_keys):
            evaluations.append(
                DependencyEvaluation(
                    node_id=node_id,
                    satisfied=False,
                    unresolved_conditions=["resource_lock_unavailable"],
                )
            )
            continue
        if payload.budget_remaining_percent <= 0:
            evaluations.append(DependencyEvaluation(node_id=node_id, satisfied=False, unresolved_conditions=["budget_exhausted"]))
            continue
        for key in resource_keys:
            used_resources.add(key)
        scheduled.append(
            ScheduledNodeResponse(
                node_id=node_id,
                name=node.name,
                queue=_queue_for_node(node),
                priority_score=_priority_score(node=node, state=state, dependency_unlock_value=len(children.get(node_id, [])), budget_remaining_percent=payload.budget_remaining_percent),
                idempotency_key=stable_hash(
                    {
                        "mission_id": str(payload.workflow.mission_id),
                        "workflow_version": payload.workflow.workflow_version,
                        "node_id": node_id,
                        "logical_attempt": max(1, state.attempt_number + 1),
                    }
                ),
                required_capabilities=node.required_capabilities,
                required_permissions=node.required_permissions,
                resource_keys=resource_keys,
            )
        )
        if len(scheduled) >= min(payload.maximum_dispatch, payload.workflow.maximum_concurrency):
            break
    scheduled.sort(key=lambda item: item.priority_score, reverse=True)
    return SchedulerResponse(
        ready_nodes=scheduled,
        blocked=evaluations,
        events=["READY_NODES_SCHEDULED" if scheduled else "NO_READY_NODES"],
        dispatch_count=len(scheduled),
    )


def evaluate_dependencies(*, node_id: str, parents: dict[str, list[str]], state_by_id: dict[str, NodeState]) -> DependencyEvaluation:
    missing: list[str] = []
    failed: list[str] = []
    for dependency in sorted(set(parents.get(node_id, []))):
        state = state_by_id.get(dependency)
        if state is None or state.status not in SUCCESS_STATUSES:
            if state and state.status in {"failed", "timed_out", "cancelled"}:
                failed.append(dependency)
            else:
                missing.append(dependency)
    return DependencyEvaluation(node_id=node_id, satisfied=not missing and not failed, missing_dependencies=missing, failed_dependencies=failed)


def plan_lease(payload: LeasePlanRequest) -> LeasePlanResponse:
    lease_material = {
        "mission_id": str(payload.mission_id),
        "workflow_version": payload.workflow_version,
        "node_id": payload.node_id,
        "worker_id": payload.worker_id,
        "logical_attempt": payload.logical_attempt,
    }
    idempotency_key = stable_hash(lease_material)
    fencing_token = int(stable_hash({**lease_material, "fence": True})[:12], 16)
    return LeasePlanResponse(
        lease_id=f"lease_{idempotency_key[:24]}",
        idempotency_key=idempotency_key,
        fencing_token=fencing_token,
        acquired_at=payload.now,
        expires_at=payload.now + timedelta(seconds=payload.ttl_seconds),
        status="planned",
        safety_rules=[
            "verify_active_lease_before_side_effect",
            "check_fencing_token_before_completion",
            "write_receipt_before_terminal_success",
            "abort_if_lease_expired",
        ],
    )


def reserve_effect(payload: EffectReservationRequest) -> EffectReservationResponse:
    for effect in payload.existing_effects:
        if effect.get("idempotency_key") == payload.idempotency_key:
            return EffectReservationResponse(
                reserved=False,
                status="duplicate",
                idempotency_key=payload.idempotency_key,
                effect_id=str(effect.get("id") or stable_hash(effect)),
                reason="Effect already exists for this idempotency key.",
            )
        if effect.get("target_resource") == payload.target_resource and effect.get("effect_type") == payload.effect_type and effect.get("status") in {"reserved", "applied", "unknown"}:
            return EffectReservationResponse(
                reserved=False,
                status="conflict",
                idempotency_key=payload.idempotency_key,
                effect_id=str(effect.get("id") or stable_hash(effect)),
                reason="Another active effect already targets this resource.",
            )
    effect_id = "effect_" + stable_hash(payload.model_dump(mode="json"))[:24]
    return EffectReservationResponse(reserved=True, status="reserved", idempotency_key=payload.idempotency_key, effect_id=effect_id, reason="Effect reserved for exactly-once side-effect protection.")


def mission_progress(workflow: ExecutableWorkflowResponse, node_states: list[NodeState]) -> float:
    state_by_id = {state.node_id: state for state in node_states}
    total = 0.0
    completed = 0.0
    for node in workflow.nodes:
        if node.optional:
            continue
        total += node.weight
        state = state_by_id.get(node.node_id)
        if state and state.status in SUCCESS_STATUSES:
            completed += node.weight
        elif state and state.status in {"running", "verifying"}:
            completed += node.weight * 0.5
        elif state and state.status in {"ready", "leased", "dispatched"}:
            completed += node.weight * 0.15
    return round((completed / total) * 100, 2) if total else 0.0


def stable_uuid(material: Any):
    from uuid import UUID

    digest = stable_hash(material)
    return UUID(f"{digest[:8]}-{digest[8:12]}-{digest[12:16]}-{digest[16:20]}-{digest[20:32]}")


def _graph(nodes: list[WorkflowNodeSpec], edges: list[WorkflowEdgeSpec]) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    children: dict[str, list[str]] = defaultdict(list)
    parents: dict[str, list[str]] = {node.node_id: [] for node in nodes}
    for node in nodes:
        for dependency in node.dependencies:
            children[dependency].append(node.node_id)
            parents[node.node_id].append(dependency)
    for edge in edges:
        children[edge.from_node_id].append(edge.to_node_id)
        parents.setdefault(edge.to_node_id, []).append(edge.from_node_id)
    return children, parents


def _reachable(start: list[str], children: dict[str, list[str]]) -> set[str]:
    seen: set[str] = set()
    queue = deque(start)
    while queue:
        node_id = queue.popleft()
        if node_id in seen:
            continue
        seen.add(node_id)
        queue.extend(children.get(node_id, []))
    return seen


def _critical_path(node_by_id: dict[str, WorkflowNodeSpec], order: list[str], parents: dict[str, list[str]]) -> tuple[list[str], float]:
    if not order:
        return [], 0.0
    best: dict[str, float] = {}
    predecessor: dict[str, str | None] = {}
    for node_id in order:
        node = node_by_id[node_id]
        dependencies = sorted(set(parents.get(node_id, [])))
        if not dependencies:
            best[node_id] = node.weight
            predecessor[node_id] = None
            continue
        parent = max(dependencies, key=lambda item: best.get(item, 0.0))
        best[node_id] = best.get(parent, 0.0) + node.weight
        predecessor[node_id] = parent
    end = max(best, key=best.get)
    path: list[str] = []
    cursor: str | None = end
    while cursor is not None:
        path.append(cursor)
        cursor = predecessor.get(cursor)
    path.reverse()
    return path, best[end]


def _has_approval_predecessor(node_id: str, node_by_id: dict[str, WorkflowNodeSpec], parents: dict[str, list[str]]) -> bool:
    queue = deque(parents.get(node_id, []))
    seen: set[str] = set()
    while queue:
        current = queue.popleft()
        if current in seen:
            continue
        seen.add(current)
        node = node_by_id.get(current)
        if node and node.node_type == "approval_gate":
            return True
        queue.extend(parents.get(current, []))
    return False


def _queue_for_node(node: WorkflowNodeSpec) -> str:
    if node.node_type == "verification":
        return "verification"
    if node.node_type == "tool_action":
        tool = str(node.metadata.get("tool") or "general")
        return f"tool.{tool}"
    if node.node_type == "approval_gate":
        return "mission.control"
    if node.node_type == "compensation":
        return "compensation"
    if "security" in node.required_capabilities:
        return "agent.security"
    if "review" in node.required_capabilities:
        return "agent.review"
    if "coding" in node.required_capabilities or "implementation" in node.required_capabilities:
        return "agent.code"
    return "agent.general"


def _priority_score(*, node: WorkflowNodeSpec, state: NodeState, dependency_unlock_value: int, budget_remaining_percent: float) -> float:
    age_bonus = min(15.0, max(0, state.attempt_number) * 1.5)
    cost_pressure = max(0.0, 100 - budget_remaining_percent) * 0.1
    retry_penalty = state.attempt_number * 2.0
    return round(node.priority + dependency_unlock_value * 3 + age_bonus - cost_pressure - retry_penalty, 4)
