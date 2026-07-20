from __future__ import annotations

from backend.services.agent.arceus_runtime.mission_runtime.api_schemas import RuntimeTaskSpec
from backend.services.agent.arceus_runtime.mission_runtime.service import validate_task_dag, weighted_progress


def test_validate_task_dag_reports_topology_and_critical_path() -> None:
    result = validate_task_dag(
        [
            RuntimeTaskSpec(task_key="foundation", title="Foundation", estimated_seconds=60),
            RuntimeTaskSpec(task_key="api", title="API", dependencies=["foundation"], estimated_seconds=120),
            RuntimeTaskSpec(task_key="ui", title="UI", dependencies=["foundation"], estimated_seconds=90),
            RuntimeTaskSpec(task_key="qa", title="QA", dependencies=["api", "ui"], estimated_seconds=30),
        ]
    )

    assert result.valid is True
    assert result.errors == []
    assert result.topological_order[0] == "foundation"
    assert result.topological_order[-1] == "qa"
    assert result.critical_path == ["foundation", "api", "qa"]
    assert result.critical_path_seconds == 210
    assert result.ready_task_keys == ["foundation"]


def test_validate_task_dag_rejects_cycle_and_missing_dependencies() -> None:
    result = validate_task_dag(
        [
            RuntimeTaskSpec(task_key="a", title="A", dependencies=["b"]),
            RuntimeTaskSpec(task_key="b", title="B", dependencies=["a"]),
            RuntimeTaskSpec(task_key="c", title="C", dependencies=["missing"]),
        ]
    )

    assert result.valid is False
    assert any("Cycle detected" in error for error in result.errors)
    assert any("missing task missing" in error for error in result.errors)
    assert result.topological_order == []


def test_weighted_progress_uses_estimates_not_raw_task_count() -> None:
    tasks = [
        RuntimeTaskSpec(task_key="large", title="Large", status="completed", estimated_seconds=900),
        RuntimeTaskSpec(task_key="small", title="Small", status="pending", estimated_seconds=100),
    ]

    assert weighted_progress(tasks) == 90.0


def test_weighted_progress_counts_running_as_partial_progress() -> None:
    tasks = [
        RuntimeTaskSpec(task_key="running", title="Running", status="running", estimated_seconds=100),
        RuntimeTaskSpec(task_key="pending", title="Pending", status="pending", estimated_seconds=100),
    ]

    assert weighted_progress(tasks) == 25.0
