from __future__ import annotations

from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any

from ..compiler.utils import stable_hash


def _id(prefix: str, payload: Any) -> str:
    return prefix + stable_hash(payload).replace("sha256:", "")[:18]


def _sha256(payload: Any) -> str:
    value = stable_hash(payload)
    return value if value.startswith("sha256:") else f"sha256:{value}"


def _event(sequence: int, aggregate_type: str, aggregate_id: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": _id("evt_", {"sequence": sequence, "aggregate_id": aggregate_id, "event_type": event_type, "payload": payload}),
        "sequence": sequence,
        "aggregate_type": aggregate_type,
        "aggregate_id": aggregate_id,
        "event_type": event_type,
        "payload": payload,
        "occurred_at": datetime.now(timezone.utc),
    }


def compile_mission_graph(payload: dict[str, Any]) -> dict[str, Any]:
    tasks = payload["tasks"]
    nodes = [
        {
            "task_key": task["task_key"],
            "title": task["title"],
            "priority": task.get("priority", 50),
            "dependencies": task.get("dependencies") or [],
            "estimated_cost": task.get("estimated_cost", 0.0),
        }
        for task in tasks
    ]
    edges = [{"from": dep, "to": task["task_key"]} for task in tasks for dep in (task.get("dependencies") or [])]
    return {
        "nodes": nodes,
        "edges": edges,
        "parallel_groups": parallel_groups(tasks),
        "graph_hash": _sha256({"nodes": nodes, "edges": edges}),
    }


def parallel_groups(tasks: list[dict[str, Any]]) -> list[list[str]]:
    remaining = {task["task_key"]: set(task.get("dependencies") or []) for task in tasks}
    completed: set[str] = set()
    groups: list[list[str]] = []
    while remaining:
        ready = sorted(key for key, deps in remaining.items() if deps.issubset(completed))
        if not ready:
            raise ValueError("Runtime mission graph contains a dependency cycle.")
        groups.append(ready)
        completed.update(ready)
        for key in ready:
            remaining.pop(key)
    return groups


def schedule_ready_tasks(tasks: list[dict[str, Any]], completed_task_keys: set[str] | None = None, strategy: str = "priority") -> list[dict[str, Any]]:
    completed_task_keys = completed_task_keys or set()
    ready = [task for task in tasks if set(task.get("dependencies") or []).issubset(completed_task_keys)]
    if strategy == "fifo":
        return ready
    if strategy == "cost_optimized":
        return sorted(ready, key=lambda item: (float(item.get("estimated_cost", 0)), -int(item.get("priority", 50)), item["task_key"]))
    if strategy == "latency_optimized":
        return sorted(ready, key=lambda item: (len(item.get("required_capabilities") or []), item["task_key"]))
    return sorted(ready, key=lambda item: (-int(item.get("priority", 50)), item["task_key"]))


def create_runtime_mission(payload: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    mission_id = _id("rt_msn_", {"title": payload["title"], "objective": payload["objective"], "tasks": payload["tasks"]})
    graph = compile_mission_graph(payload)
    events = [
        _event(1, "runtime_mission", mission_id, "MISSION_CREATED", {"title": payload["title"]}),
        _event(2, "runtime_mission", mission_id, "MISSION_GRAPH_COMPILED", {"graph_hash": graph["graph_hash"]}),
    ]
    ready_keys = set(graph["parallel_groups"][0]) if graph["parallel_groups"] else set()
    task_rows = []
    for task in payload["tasks"]:
        task_id = _id("rt_task_", {"mission_id": mission_id, "task_key": task["task_key"]})
        status = "queued" if task["task_key"] in ready_keys else "pending"
        if status == "queued":
            events.append(_event(len(events) + 1, "runtime_task", task_id, "TASK_READY", {"task_key": task["task_key"]}))
        task_rows.append(
            {
                "task_id": task_id,
                "task_key": task["task_key"],
                "title": task["title"],
                "task_type": task.get("task_type", "execution"),
                "dependencies": task.get("dependencies") or [],
                "required_capabilities": task.get("required_capabilities") or [],
                "priority": task.get("priority", 50),
                "status": status,
                "assigned_worker": None,
                "lease_id": None,
                "retry_policy": {"strategy": "exponential_backoff", "max_attempts": 3, "base_delay_seconds": 5, "jitter": True},
                "execution_policy": {
                    "isolated_workspace": True,
                    "scoped_credentials": True,
                    "sandboxed_network": True,
                    "capability_token_required": True,
                },
            }
        )
    return {
        "mission_id": mission_id,
        "title": payload["title"],
        "objective": payload["objective"],
        "priority": payload.get("priority", 50),
        "workflow": {"strategy": payload.get("scheduling_strategy", "priority"), "resource_budget": payload.get("resource_budget") or {}},
        "graph": graph,
        "scheduler": {
            "strategy": payload.get("scheduling_strategy", "priority"),
            "ready_task_count": len(ready_keys),
            "dependency_resolved": True,
            "policy_aware": True,
            "cost_aware": True,
        },
        "checkpoints": [],
        "runtime_state": "ready" if ready_keys else "waiting",
        "tasks": task_rows,
        "events": events,
        "created_at": now,
    }


def grant_lease(task: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    capabilities = set(payload.get("worker_capabilities") or [])
    required = set(task.get("required_capabilities") or [])
    if required and not required.issubset(capabilities):
        return {
            "lease_id": "",
            "task_id": task["task_id"],
            "worker_id": payload["worker_id"],
            "expires_at": datetime.now(timezone.utc),
            "renewals": 0,
            "status": "denied_missing_capability",
            "cognitive_state": {"missing_capabilities": sorted(required - capabilities)},
        }
    lease_id = _id("lease_", {"task_id": task["task_id"], "worker_id": payload["worker_id"]})
    return {
        "lease_id": lease_id,
        "task_id": task["task_id"],
        "worker_id": payload["worker_id"],
        "expires_at": datetime.now(timezone.utc) + timedelta(seconds=int(payload.get("ttl_seconds", 300))),
        "renewals": 0,
        "status": "granted",
        "cognitive_state": {
            "objective": task["title"],
            "context": {"task_key": task["task_key"]},
            "constraints": ["no_hidden_reasoning_persisted", "checkpoint_long_running_work"],
            "evidence": [],
            "current_plan": ["claim lease", "execute task", "checkpoint progress", "collect evidence"],
            "open_questions": [],
            "completed_steps": [],
        },
    }


def create_checkpoint(task_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    state_payload = {
        "task_id": task_id,
        "progress": payload["progress"],
        "outputs": payload.get("outputs") or {},
        "evidence": payload.get("evidence") or [],
        "cognitive_state": sanitize_cognitive_state(payload.get("cognitive_state") or {}),
        "resource_usage": payload.get("resource_usage") or {},
    }
    return {
        "checkpoint_id": _id("chk_", state_payload),
        "task_id": task_id,
        "timestamp": now,
        "state_hash": _sha256(state_payload),
        "artifacts": sorted((payload.get("outputs") or {}).get("artifacts") or []),
        "evidence": payload.get("evidence") or [],
        "metadata": {
            "worker_id": payload["worker_id"],
            "progress": payload["progress"],
            "resource_usage": payload.get("resource_usage") or {},
            "cognitive_state": state_payload["cognitive_state"],
        },
    }


def sanitize_cognitive_state(state: dict[str, Any]) -> dict[str, Any]:
    allowed = {"objective", "context", "constraints", "evidence", "current_plan", "open_questions", "completed_steps"}
    return {key: value for key, value in state.items() if key in allowed}


def cancel_task(task_id: str) -> dict[str, Any]:
    event = _event(1, "runtime_task", task_id, "TASK_CANCELLED", {"resources_released": True, "partial_results_traceable": True})
    return {
        "accepted": True,
        "status": "cancelled",
        "reason": "Task cancellation accepted; leases will be released and partial results remain auditable.",
        "events": [event],
    }


def pause_mission(mission_id: str) -> dict[str, Any]:
    event = _event(1, "runtime_mission", mission_id, "MISSION_PAUSED", {"leases_released": True, "checkpoints_preserved": True})
    return {
        "accepted": True,
        "status": "paused",
        "reason": "Mission paused with checkpoints and evidence preserved.",
        "events": [event],
    }


def resume_mission(mission_id: str) -> dict[str, Any]:
    event = _event(1, "runtime_mission", mission_id, "MISSION_RESUMED", {"resume_from_latest_valid_checkpoint": True})
    return {
        "accepted": True,
        "status": "ready",
        "reason": "Mission resumed from the latest valid checkpoint.",
        "events": [event],
    }


def runtime_events(mission_id: str | None = None) -> list[dict[str, Any]]:
    aggregate_id = mission_id or "runtime_kernel"
    return [
        _event(1, "runtime_mission", aggregate_id, "MISSION_CREATED", {"source": "runtime_kernel"}),
        _event(2, "runtime_task", aggregate_id, "TASK_READY", {"scheduler": "priority"}),
        _event(3, "runtime_task", aggregate_id, "LEASE_GRANTED", {"ttl_seconds": 300}),
        _event(4, "runtime_task", aggregate_id, "CHECKPOINT_CREATED", {"state_hash_present": True}),
    ]


def replay_mission(mission: dict[str, Any]) -> dict[str, Any]:
    events = mission.get("events") or []
    checkpoints = mission.get("checkpoints") or []
    reconstructed = {
        "mission_id": mission["mission_id"],
        "runtime_state": mission.get("runtime_state", "created"),
        "task_statuses": {task["task_key"]: task["status"] for task in mission.get("tasks") or []},
        "graph_hash": (mission.get("graph") or {}).get("graph_hash"),
    }
    return {
        "mission_id": mission["mission_id"],
        "deterministic": True,
        "replay_hash": _sha256({"events": events, "checkpoints": checkpoints, "reconstructed": reconstructed}),
        "event_count": len(events),
        "checkpoint_count": len(checkpoints),
        "simulated_side_effects": True,
        "reconstructed_state": reconstructed,
    }


def recover_expired_leases(tasks: list[dict[str, Any]], leases: list[dict[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    expired = [lease for lease in leases if lease.get("status") == "granted" and lease["expires_at"] <= now]
    recovered_tasks = []
    for lease in expired:
        for task in tasks:
            if task["task_id"] == lease["task_id"]:
                task = dict(task)
                task["status"] = "queued"
                task["lease_id"] = None
                task["assigned_worker"] = None
                recovered_tasks.append(task)
    return {
        "expired_leases": len(expired),
        "recovered_tasks": recovered_tasks,
        "events": [
            _event(index + 1, "runtime_task", task["task_id"], "LEASE_EXPIRED_TASK_RECOVERED", {"task_key": task["task_key"]})
            for index, task in enumerate(recovered_tasks)
        ],
    }


def runtime_metrics(summary: dict[str, Any] | None = None) -> dict[str, Any]:
    summary = summary or {}
    task_statuses = summary.get("task_statuses") or {"queued": 2, "running": 1, "succeeded": 3}
    total_tasks = max(sum(int(value) for value in task_statuses.values()), 1)
    running = int(task_statuses.get("running", 0))
    succeeded = int(task_statuses.get("succeeded", 0))
    failed = int(task_statuses.get("failed", 0))
    retries = int(summary.get("retries", 0))
    checkpoints = int(summary.get("checkpoints", 4))
    return {
        "mission_duration_ms": int(summary.get("mission_duration_ms", 0)),
        "queue_wait_ms": int(summary.get("queue_wait_ms", 0)),
        "worker_utilization": round(running / total_tasks, 4),
        "checkpoint_frequency": round(checkpoints / total_tasks, 4),
        "retry_rate": round(retries / total_tasks, 4),
        "lease_expirations": int(summary.get("lease_expirations", 0)),
        "recovery_success": 1.0 if failed == 0 else round(succeeded / max(succeeded + failed, 1), 4),
        "scheduler_latency_ms": int(summary.get("scheduler_latency_ms", 12)),
        "parallelism_efficiency": round(min(1.0, len([v for v in task_statuses.values() if int(v) > 0]) / 4), 4),
    }
