from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from services.agent.task_runtime.dispatcher import append_runtime_event, utc_now  # noqa: E402
from services.agent.task_runtime.observability import build_mission_observability  # noqa: E402
from services.agent.task_runtime.scheduler import schedule_ready_tasks  # noqa: E402
from services.shared.arceus_core_models import (  # noqa: E402
    ArceusMission,
    ArceusMissionTaskAssignment,
    ArceusProject,
    ArceusProjectRepository,
    ArceusTask,
    ArceusTaskDependency,
    ArceusTenant,
    ArceusUser,
)
from services.shared.database import Base, SessionLocal, engine  # noqa: E402


def _ok(name: str, ok: bool, detail: str) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail}


def _create_task(db, *, tenant_id, mission_id, key: str, status: str, task_type: str, input_contract: dict) -> ArceusTask:
    task = ArceusTask(
        tenant_id=tenant_id,
        mission_id=mission_id,
        task_key=key,
        title=key.replace("_", " ").title(),
        task_type=task_type,
        status=status,
        input_contract=input_contract,
        output_contract={},
        acceptance_criteria=[],
    )
    db.add(task)
    db.flush()
    return task


def main() -> int:
    Base.metadata.create_all(bind=engine)
    run_id = uuid.uuid4().hex[:12]
    checks: list[dict] = []
    with SessionLocal() as db:
        tenant = ArceusTenant(name=f"Mission Observability {run_id}", slug=f"mission-observability-{run_id}", status="active", plan_key="pro")
        user = ArceusUser(external_identity_id=f"mission-observability-{run_id}", email=f"mission-observability-{run_id}@example.test", display_name="Mission Observability")
        db.add_all([tenant, user])
        db.flush()

        project = ArceusProject(tenant_id=tenant.id, name="Mission Observability Proof", slug=f"mission-observability-{run_id}", created_by=user.id)
        db.add(project)
        db.flush()
        repository = ArceusProjectRepository(
            tenant_id=tenant.id,
            project_id=project.id,
            provider="local",
            repository_url=f"file:///mission-observability/{run_id}",
            default_branch="main",
            status="active",
        )
        db.add(repository)
        db.flush()
        mission = ArceusMission(
            tenant_id=tenant.id,
            project_id=project.id,
            created_by=user.id,
            title="Mission observability proof",
            objective="Expose timeline, workers, DAG, locks, recovery, and operational metrics.",
            status="running",
            metadata_json={"scheduler_limits": {"total": 3, "read_only": 1, "write_sensitive": 1}},
        )
        db.add(mission)
        db.flush()

        analysis = _create_task(
            db,
            tenant_id=tenant.id,
            mission_id=mission.id,
            key="analyze_repository",
            status="ready",
            task_type="analysis",
            input_contract={"repository_id": str(repository.id)},
        )
        implementation = _create_task(
            db,
            tenant_id=tenant.id,
            mission_id=mission.id,
            key="write_release_notes",
            status="ready",
            task_type="implementation",
            input_contract={"repository_id": str(repository.id), "write_paths": ["docs/release-notes.md"], "required_capabilities": {"filesystem_write": True}},
        )
        verification = _create_task(
            db,
            tenant_id=tenant.id,
            mission_id=mission.id,
            key="verify_release_notes",
            status="blocked",
            task_type="verification",
            input_contract={"repository_id": str(repository.id)},
            )
        db.add(ArceusTaskDependency(tenant_id=tenant.id, task_id=verification.id, depends_on_task_id=implementation.id, dependency_type="blocks"))
        db.commit()

        first_schedule = schedule_ready_tasks(db, tenant_id=tenant.id, mission_id=mission.id, correlation_id=uuid.uuid4(), max_assignments=3)
        db.commit()
        write_assignment = (
            db.query(ArceusMissionTaskAssignment)
            .filter(ArceusMissionTaskAssignment.tenant_id == tenant.id, ArceusMissionTaskAssignment.task_id == implementation.id)
            .first()
        )
        if write_assignment:
            now = utc_now()
            metadata = dict(write_assignment.metadata_json or {})
            recovery_record = {
                "report_id": f"recovery-{run_id}",
                "status": "manual_review_required",
                "local_stage": "after_patch_write",
                "repository_state": "partial_changes_present",
                "recommended_action": "manual_review_required",
                "artifacts": {"change_set": "observability-proof"},
                "recorded_at": now.isoformat(),
            }
            metadata["recovery_reports"] = {recovery_record["report_id"]: recovery_record}
            metadata["latest_recovery_report"] = recovery_record
            write_assignment.metadata_json = metadata
            append_runtime_event(
                db,
                tenant_id=tenant.id,
                mission_id=mission.id,
                event_type="assignment.recovery.reported",
                actor_type="worker",
                actor_id="observability-proof",
                payload={
                    "assignment_id": str(write_assignment.id),
                    "task_id": str(write_assignment.task_id),
                    "report_id": recovery_record["report_id"],
                    "status": recovery_record["status"],
                },
                correlation_id=uuid.uuid4(),
                idempotency_key=f"mission-observability-recovery:{write_assignment.id}:{run_id}",
            )
        db.commit()

        snapshot = build_mission_observability(db, tenant_id=tenant.id, mission_id=mission.id)
        metrics = snapshot["metrics"]
        dag_nodes = snapshot["dag"]["nodes"]
        checks.append(_ok("Mission metadata exposed", snapshot["mission"]["title"] == mission.title and snapshot["mission"]["status"] == "running", json.dumps(snapshot["mission"], sort_keys=True)))
        checks.append(_ok("Timeline events exposed", any(event["event_type"] == "assignment.recovery.reported" for event in snapshot["timeline"]), f"events={len(snapshot['timeline'])}"))
        checks.append(_ok("Workers visible", len(snapshot["workers"]) >= 1, f"workers={len(snapshot['workers'])}"))
        checks.append(_ok("DAG nodes visible", len(dag_nodes) == 3, f"nodes={[node['task_key'] for node in dag_nodes]}"))
        checks.append(_ok("DAG dependency visible", any(edge["from_task_key"] == "write_release_notes" and edge["to_task_key"] == "verify_release_notes" for edge in snapshot["dag"]["edges"]), json.dumps(snapshot["dag"]["edges"], sort_keys=True)))
        checks.append(_ok("Repository lock visible", any(reservation["path_pattern"] == "docs/release-notes.md" and reservation["status"] == "active" for reservation in snapshot["reservations"]), json.dumps(snapshot["reservations"], sort_keys=True)))
        checks.append(_ok("Recovery center visible", len(snapshot["recovery"]) == 1 and snapshot["recovery"][0]["status"] == "manual_review_required", json.dumps(snapshot["recovery"], sort_keys=True)))
        checks.append(_ok("Operational metrics visible", metrics["task_count"] == 3 and metrics["active_assignments"] >= 1 and metrics["manual_review_required"] == 1, json.dumps(metrics, sort_keys=True)))
        checks.append(_ok("Scheduler contributed assignments", len(first_schedule.assignments) >= 1, f"scheduled={len(first_schedule.assignments)}"))

    result = {"ok": all(check["ok"] for check in checks), "checks": checks}
    print(json.dumps(result))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
