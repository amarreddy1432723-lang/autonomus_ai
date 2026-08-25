from __future__ import annotations

import json
import difflib
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusArtifact, ArceusArtifactVersion, ArceusEvidence, ArceusEvent, ArceusOutboxMessage, ArceusTask
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from .api_schemas import (
    ChangeSetExecutionRequest,
    ChangeSetExecutionResponse,
    ChangeSetExecutionResult,
    ChangeSetReviewActionRequest,
    ChangeSetReviewActionResponse,
    EvidenceResponse,
    TaskChangeSetRequest,
    ToolEvidenceRequest,
    VerificationRunResponse,
)


router = APIRouter(tags=["evidence"])


def _uow(db: Session) -> SqlAlchemyUnitOfWork:
    return SqlAlchemyUnitOfWork(db)


def _evidence_response(evidence) -> EvidenceResponse:
    return EvidenceResponse(
        id=evidence.id,
        mission_id=evidence.mission_id,
        workflow_id=evidence.workflow_id,
        task_id=evidence.task_id,
        artifact_id=evidence.artifact_id,
        evidence_type=evidence.evidence_type,
        status=evidence.status,
        summary=evidence.summary,
        payload=evidence.payload or {},
        verification_method=evidence.verification_method,
        content_hash=evidence.content_hash,
        trust_level=evidence.trust_level,
        immutable=evidence.immutable,
        collected_by_member_id=evidence.collected_by_member_id,
        created_at=evidence.created_at,
        updated_at=evidence.updated_at,
        version_number=evidence.version_number,
    )


def _verification_run_response(run) -> VerificationRunResponse:
    return VerificationRunResponse(
        id=run.id,
        mission_id=run.mission_id,
        task_id=run.task_id,
        verification_type=run.verification_type,
        status=run.status,
        started_at=run.started_at,
        finished_at=run.finished_at,
        command=run.command,
        result=run.result or {},
        evidence_id=run.evidence_id,
        created_at=run.created_at,
        updated_at=run.updated_at,
        version_number=run.version_number,
    )


def _stable_hash(payload: dict) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")).hexdigest()


def _text_hash(value: str | None) -> str | None:
    if value is None:
        return None
    return sha256(value.encode("utf-8")).hexdigest()


def _normal_path(value: str | None) -> str:
    return str(value or "").replace("\\", "/").strip().lstrip("/")


def _diff_impact(diff: str) -> dict[str, int]:
    return {
        "additions": sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")),
        "deletions": sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")),
    }


def _unified_diff(*, old_path: str, new_path: str, old_text: str | None, new_text: str | None) -> str:
    old_lines = (old_text or "").splitlines(keepends=True)
    new_lines = (new_text or "").splitlines(keepends=True)
    return "".join(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=old_path or new_path,
            tofile=new_path,
            lineterm="",
        )
    )


def _operation_risk(operation: str, existing_risk: str, review_required: bool) -> tuple[str, bool]:
    if operation in {"delete", "rename"}:
        return ("high" if existing_risk in {"", "low", "medium"} else existing_risk, True)
    return (existing_risk or "low", review_required)


def _default_apply_payload(change: dict) -> dict:
    operation = change.get("operation")
    path = change.get("path")
    if operation == "folder":
        return {"operation": "create_folder", "path": path}
    if operation == "create":
        return {"operation": "write_file", "path": path, "content": change.get("modified_content"), "expected_original_sha256": None}
    if operation == "modify":
        return {"operation": "write_file", "path": path, "content": change.get("modified_content"), "expected_original_sha256": change.get("original_sha256")}
    if operation == "delete":
        return {"operation": "delete_file", "path": path, "expected_original_sha256": change.get("original_sha256")}
    if operation == "rename":
        return {"operation": "rename_path", "old_path": change.get("old_path"), "path": path, "expected_original_sha256": change.get("original_sha256")}
    return {"operation": operation, "path": path}


def _default_rollback_payload(change: dict) -> dict:
    operation = change.get("operation")
    path = change.get("path")
    if operation == "folder":
        return {"operation": "delete_folder_if_empty", "path": path}
    if operation == "create":
        return {"operation": "delete_file", "path": path, "expected_current_sha256": change.get("modified_sha256")}
    if operation == "modify":
        return {"operation": "write_file", "path": path, "content": change.get("original_content"), "expected_current_sha256": change.get("modified_sha256")}
    if operation == "delete":
        return {"operation": "write_file", "path": path, "content": change.get("original_content"), "expected_current_sha256": None}
    if operation == "rename":
        return {"operation": "rename_path", "old_path": path, "path": change.get("old_path"), "expected_current_sha256": change.get("modified_sha256")}
    return {"operation": f"rollback_{operation}", "path": path}


def _normalize_change_set_content(payload: TaskChangeSetRequest, *, mission_id: UUID, task_id: UUID) -> dict:
    content = payload.model_dump(mode="json")
    normalized_changes: list[dict] = []
    for raw_change in content.get("changes") or []:
        change = dict(raw_change or {})
        metadata = dict(change.get("metadata") or {})
        operation = str(change.get("operation") or "")
        path = _normal_path(change.get("path"))
        old_path = _normal_path(change.get("old_path")) or None
        original_content = change.get("original_content")
        modified_content = change.get("modified_content")
        if original_content is None:
            original_content = metadata.get("original_content")
        if modified_content is None:
            modified_content = metadata.get("modified_content") or metadata.get("content")

        diff = change.get("diff") or metadata.get("diff") or ""
        if not diff and operation != "folder" and (original_content is not None or modified_content is not None):
            diff = _unified_diff(old_path=old_path or path, new_path=path, old_text=original_content, new_text=modified_content)

        impact = _diff_impact(diff)
        original_sha = change.get("original_sha256") or metadata.get("original_sha256") or _text_hash(original_content)
        modified_sha = change.get("modified_sha256") or metadata.get("modified_sha256") or _text_hash(modified_content)
        risk, review_required = _operation_risk(operation, str(change.get("risk") or "medium"), bool(change.get("review_required")))

        change.update(
            {
                "path": path,
                "old_path": old_path,
                "diff": diff,
                "original_content": original_content,
                "modified_content": modified_content,
                "original_sha256": original_sha,
                "modified_sha256": modified_sha,
                "additions": int(change.get("additions") or impact["additions"]),
                "deletions": int(change.get("deletions") or impact["deletions"]),
                "risk": risk,
                "review_required": review_required,
            }
        )
        apply_payload = change.get("apply_payload") or metadata.get("apply_payload") or _default_apply_payload(change)
        rollback_payload = change.get("rollback_payload") or metadata.get("rollback_payload") or _default_rollback_payload(change)
        change.update(
            {
                "apply_payload": apply_payload,
                "rollback_payload": rollback_payload,
                "metadata": {
                    **metadata,
                    "diff_present": bool(diff),
                    "apply_payload_present": bool(apply_payload),
                    "rollback_payload_present": bool(rollback_payload),
                },
            }
        )
        normalized_changes.append(change)

    content["changes"] = normalized_changes
    content["mission_id"] = str(mission_id)
    content["task_id"] = str(task_id)
    content["impact"] = {
        "files_changed": len(normalized_changes),
        "additions": sum(int(item.get("additions") or 0) for item in normalized_changes),
        "deletions": sum(int(item.get("deletions") or 0) for item in normalized_changes),
        "review_required": sum(1 for item in normalized_changes if item.get("review_required")),
        "diffs_present": sum(1 for item in normalized_changes if item.get("diff")),
        "apply_payloads_present": sum(1 for item in normalized_changes if item.get("apply_payload")),
        "rollback_payloads_present": sum(1 for item in normalized_changes if item.get("rollback_payload")),
    }
    return content


def _next_event_sequence(db: Session, *, tenant_id: UUID, mission_id: UUID) -> int:
    from sqlalchemy import func

    current = (
        db.query(func.max(ArceusEvent.aggregate_version))
        .filter(ArceusEvent.tenant_id == tenant_id, ArceusEvent.aggregate_type == "mission", ArceusEvent.aggregate_id == mission_id)
        .scalar()
        or 0
    )
    return int(current) + 1


def _append_evidence_event(db: Session, *, context: RequestContext, mission_id: UUID, task_id: UUID, evidence_ids: list[str]) -> None:
    event = ArceusEvent(
        tenant_id=context.tenant_id,
        aggregate_type="mission",
        aggregate_id=mission_id,
        aggregate_version=_next_event_sequence(db, tenant_id=context.tenant_id, mission_id=mission_id),
        event_type="task.evidence.collected",
        actor_type="desktop",
        actor_id=str(context.user_id),
        payload={"mission_id": str(mission_id), "task_id": str(task_id), "evidence_ids": evidence_ids, "count": len(evidence_ids)},
        metadata_json={"correlation_id": str(context.correlation_id), "idempotency_key": f"task.evidence:{task_id}:{_stable_hash({'evidence_ids': evidence_ids})[:16]}"},
    )
    db.add(event)
    db.flush()
    db.add(
        ArceusOutboxMessage(
            tenant_id=context.tenant_id,
            event_id=event.id,
            topic="arceus.task.evidence.collected",
            payload={"event_id": str(event.id), "mission_id": str(mission_id), "task_id": str(task_id), "evidence_ids": evidence_ids},
        )
    )


def _append_task_event(db: Session, *, context: RequestContext, mission_id: UUID, task_id: UUID, event_type: str, payload: dict) -> None:
    event = ArceusEvent(
        tenant_id=context.tenant_id,
        aggregate_type="mission",
        aggregate_id=mission_id,
        aggregate_version=_next_event_sequence(db, tenant_id=context.tenant_id, mission_id=mission_id),
        event_type=event_type,
        actor_type="desktop",
        actor_id=str(context.user_id),
        payload={"mission_id": str(mission_id), "task_id": str(task_id), **payload},
        metadata_json={"correlation_id": str(context.correlation_id), "idempotency_key": f"{event_type}:{task_id}:{_stable_hash(payload)[:16]}"},
    )
    db.add(event)
    db.flush()
    db.add(
        ArceusOutboxMessage(
            tenant_id=context.tenant_id,
            event_id=event.id,
            topic=f"arceus.{event_type}",
            payload={"event_id": str(event.id), "mission_id": str(mission_id), "task_id": str(task_id), **payload},
        )
    )


def _review_state_for_action(action: str) -> str:
    return {
        "approve": "validated",
        "reject": "rejected",
        "apply": "applied",
        "rollback": "rolled_back",
    }[action]


def _load_change_set_artifact(db: Session, *, context: RequestContext, task: ArceusTask, payload: ChangeSetReviewActionRequest):
    metadata = dict(task.output_contract or {})
    latest = dict(metadata.get("latest_change_set") or {})
    artifact_id = payload.artifact_id or latest.get("artifact_id")
    if not artifact_id:
        raise HTTPException(status_code=409, detail={"error": {"code": "CHANGE_SET_NOT_FOUND", "message": "No recorded change set is available for this task.", "retryable": False}})
    artifact = db.query(ArceusArtifact).filter(ArceusArtifact.tenant_id == context.tenant_id, ArceusArtifact.id == artifact_id, ArceusArtifact.task_id == task.id).first()
    if artifact is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "CHANGE_SET_NOT_FOUND", "message": "Change set artifact not found.", "retryable": False}})
    version_id = payload.artifact_version_id or artifact.current_version_id
    version = db.query(ArceusArtifactVersion).filter(ArceusArtifactVersion.tenant_id == context.tenant_id, ArceusArtifactVersion.artifact_id == artifact.id, ArceusArtifactVersion.id == version_id).first()
    if version is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "CHANGE_SET_VERSION_NOT_FOUND", "message": "Change set artifact version not found.", "retryable": False}})
    return artifact, version


def _change_set_error(status_code: int, code: str, message: str, **details):
    raise HTTPException(status_code=status_code, detail={"error": {"code": code, "message": message, "retryable": False, "details": details}})


def _file_content_hash(path: Path) -> str:
    return _text_hash(path.read_text(encoding="utf-8", errors="replace")) or ""


def _resolve_workspace_root(payload: ChangeSetExecutionRequest, *, task: ArceusTask, content: dict) -> Path:
    metadata = dict(payload.metadata or {})
    content_metadata = dict(content.get("metadata") or {})
    task_input = dict(task.input_contract or {})
    task_output = dict(task.output_contract or {})
    candidates = [
        payload.workspace_root,
        metadata.get("workspace_root"),
        metadata.get("repository_root"),
        content_metadata.get("workspace_root"),
        content_metadata.get("repository_root"),
        task_input.get("workspace_root"),
        task_input.get("repository_root"),
        task_input.get("local_path"),
        task_output.get("workspace_root"),
        task_output.get("repository_root"),
        task_output.get("local_path"),
    ]
    for candidate in candidates:
        if candidate:
            root = Path(str(candidate)).expanduser().resolve()
            if not root.exists() or not root.is_dir():
                _change_set_error(409, "WORKSPACE_ROOT_UNAVAILABLE", "The trusted workspace root is not available on this machine.", workspace_root=str(root))
            return root
    _change_set_error(409, "WORKSPACE_ROOT_REQUIRED", "A trusted workspace_root is required before filesystem apply or rollback can run.")


def _resolve_payload_path(root: Path, relative_path: str | None, *, field_name: str = "path") -> Path:
    normalized = _normal_path(relative_path)
    if not normalized:
        _change_set_error(409, "CHANGE_SET_PATH_REQUIRED", f"{field_name} is required for filesystem execution.")
    candidate = (root / normalized).resolve()
    if candidate != root and root not in candidate.parents:
        _change_set_error(409, "CHANGE_SET_PATH_ESCAPE", "Change-set payload path escapes the trusted workspace.", path=normalized)
    return candidate


def _assert_hash(path: Path, *, expected: str | None, code: str = "CHANGE_SET_HASH_MISMATCH") -> None:
    if not expected:
        return
    if not path.is_file():
        _change_set_error(409, code, "Expected file is not present for hash verification.", path=str(path), expected_sha256=expected)
    actual = _file_content_hash(path)
    if actual != expected:
        _change_set_error(409, code, "File hash changed since this change set was prepared.", path=str(path), expected_sha256=expected, actual_sha256=actual)


def _selected_change_set(changes: list[dict], file_paths: list[str]) -> list[dict]:
    requested = {_normal_path(item) for item in file_paths if str(item).strip()}
    if not requested:
        return [dict(item or {}) for item in changes]
    selected: list[dict] = []
    for item in changes:
        change = dict(item or {})
        paths = {_normal_path(change.get("path")), _normal_path(change.get("old_path"))}
        if paths & requested:
            selected.append(change)
    if not selected:
        _change_set_error(409, "CHANGE_SET_FILE_NOT_FOUND", "None of the requested files exist in the recorded change set.")
    return selected


def _preflight_change_set_payloads(root: Path, changes: list[dict], *, action: str) -> list[dict]:
    prepared: list[dict] = []
    payload_key = "apply_payload" if action == "apply" else "rollback_payload"
    for change in changes:
        payload = dict(change.get(payload_key) or {})
        operation = str(payload.get("operation") or "")
        if operation not in {"write_file", "delete_file", "rename_path", "create_folder", "delete_folder_if_empty"}:
            _change_set_error(409, "CHANGE_SET_OPERATION_UNSUPPORTED", "Change-set payload operation is not supported by the filesystem executor.", operation=operation)

        path = _resolve_payload_path(root, payload.get("path"))
        old_path = _resolve_payload_path(root, payload.get("old_path"), field_name="old_path") if operation == "rename_path" else None
        expected_original = payload.get("expected_original_sha256")
        expected_current = payload.get("expected_current_sha256")

        if operation == "write_file":
            if "content" not in payload or payload.get("content") is None:
                _change_set_error(409, "CHANGE_SET_CONTENT_REQUIRED", "write_file payload requires content.", path=str(payload.get("path") or ""))
            if expected_original or expected_current:
                _assert_hash(path, expected=str(expected_original or expected_current))
            elif action == "apply" and change.get("operation") == "create" and path.exists():
                _change_set_error(409, "CHANGE_SET_FILE_EXISTS", "Create payload cannot overwrite an existing file without a matching hash.", path=str(payload.get("path") or ""))
        elif operation == "delete_file":
            if not path.exists():
                _change_set_error(409, "CHANGE_SET_FILE_MISSING", "delete_file payload target does not exist.", path=str(payload.get("path") or ""))
            if not path.is_file():
                _change_set_error(409, "CHANGE_SET_NOT_A_FILE", "delete_file payload target is not a file.", path=str(payload.get("path") or ""))
            _assert_hash(path, expected=str(expected_original or expected_current or "") or None)
        elif operation == "rename_path":
            assert old_path is not None
            if not old_path.exists():
                _change_set_error(409, "CHANGE_SET_SOURCE_MISSING", "rename_path payload source does not exist.", old_path=str(payload.get("old_path") or ""))
            if path.exists():
                _change_set_error(409, "CHANGE_SET_DESTINATION_EXISTS", "rename_path payload destination already exists.", path=str(payload.get("path") or ""))
            if old_path.is_file():
                _assert_hash(old_path, expected=str(expected_original or expected_current or "") or None)
        elif operation == "create_folder":
            if path.exists() and not path.is_dir():
                _change_set_error(409, "CHANGE_SET_NOT_A_FOLDER", "create_folder target exists and is not a folder.", path=str(payload.get("path") or ""))
        elif operation == "delete_folder_if_empty":
            if path.exists() and (not path.is_dir() or any(path.iterdir())):
                _change_set_error(409, "CHANGE_SET_FOLDER_NOT_EMPTY", "Rollback can only remove folders that are still empty.", path=str(payload.get("path") or ""))

        prepared.append({"change": change, "payload": payload, "operation": operation, "path": path, "old_path": old_path})
    return prepared


def _execute_change_set_payloads(root: Path, changes: list[dict], *, action: str, dry_run: bool = False) -> list[dict]:
    prepared = _preflight_change_set_payloads(root, changes, action=action)
    results: list[dict] = []
    for item in prepared:
        payload = item["payload"]
        operation = item["operation"]
        path: Path = item["path"]
        old_path: Path | None = item["old_path"]
        status = "would_execute" if dry_run else ("rolled_back" if action == "rollback" else "applied")
        if not dry_run:
            if operation == "write_file":
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(str(payload.get("content") or ""), encoding="utf-8")
            elif operation == "delete_file":
                path.unlink()
            elif operation == "rename_path":
                assert old_path is not None
                path.parent.mkdir(parents=True, exist_ok=True)
                old_path.rename(path)
            elif operation == "create_folder":
                path.mkdir(parents=True, exist_ok=True)
            elif operation == "delete_folder_if_empty" and path.exists():
                path.rmdir()

        result_path = _normal_path(payload.get("path"))
        sha = _file_content_hash(path) if path.is_file() else None
        byte_count = path.stat().st_size if path.is_file() else None
        results.append(
            {
                "path": result_path,
                "operation": operation,
                "status": status,
                "sha256": sha,
                "bytes": byte_count,
                "metadata": {"old_path": _normal_path(payload.get("old_path")) or None, "dry_run": dry_run},
            }
        )
    return results


@router.get("/api/v1/missions/{mission_id}/evidence")
def list_mission_evidence(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("evidence.view")),
    evidence_type: str | None = Query(default=None, max_length=100),
    evidence_status: str | None = Query(default=None, alias="status", max_length=60),
    task_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    evidence = uow.evidence.list_for_mission(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        evidence_type=evidence_type,
        status=evidence_status,
        limit=limit,
    )
    if task_id:
        evidence = [item for item in evidence if item.task_id == task_id]
    return collection_response([_evidence_response(item).model_dump(mode="json") for item in evidence], request)


@router.post("/api/v1/missions/{mission_id}/tasks/{task_id}/tool-evidence")
def record_task_tool_evidence(
    mission_id: UUID,
    task_id: UUID,
    payload: ToolEvidenceRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("evidence.collect")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    task = db.query(ArceusTask).filter(ArceusTask.tenant_id == context.tenant_id, ArceusTask.mission_id == mission_id, ArceusTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "TASK_NOT_FOUND", "message": "Task not found.", "retryable": False}})

    evidence_rows: list[ArceusEvidence] = []
    for record in payload.records:
        record_payload = record.model_dump(mode="json")
        evidence_payload = {
            "source": payload.source,
            "tool": record.tool,
            "input_summary": record.input_summary,
            "output_summary": record.output_summary,
            "duration_ms": record.duration_ms,
            "status": record.status,
            "error_class": record.error_class,
            "audit_id": record.audit_id,
            "timestamp": record.timestamp,
            "payload": record.payload,
        }
        content_hash = _stable_hash({"mission_id": str(mission_id), "task_id": str(task_id), "record": record_payload})
        evidence = ArceusEvidence(
            tenant_id=context.tenant_id,
            mission_id=mission_id,
            task_id=task_id,
            evidence_type="tool_invocation",
            status="failed" if record.status == "failed" else "validated",
            summary=payload.summary or f"{record.tool} {record.status}",
            payload=evidence_payload,
            verification_method=payload.source,
            content_hash=content_hash,
            trust_level="tool_verified" if record.status != "failed" else "unverified",
            immutable=True,
        )
        db.add(evidence)
        evidence_rows.append(evidence)
    db.flush()
    evidence_ids = [str(item.id) for item in evidence_rows]
    metadata = dict(task.output_contract or {})
    metadata["evidence_ids"] = sorted(set([*(metadata.get("evidence_ids") or []), *evidence_ids]))
    metadata["latest_evidence_count"] = len(metadata["evidence_ids"])
    task.output_contract = metadata
    task.version_number = int(task.version_number or 1) + 1
    _append_evidence_event(db, context=context, mission_id=mission_id, task_id=task_id, evidence_ids=evidence_ids)
    db.commit()
    return api_response(
        {
            "mission_id": str(mission_id),
            "task_id": str(task_id),
            "evidence_count": len(evidence_rows),
            "evidence": [_evidence_response(item).model_dump(mode="json") for item in evidence_rows],
        },
        request,
    )


@router.post("/api/v1/missions/{mission_id}/tasks/{task_id}/change-set")
def record_task_change_set(
    mission_id: UUID,
    task_id: UUID,
    payload: TaskChangeSetRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("evidence.collect")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    task = db.query(ArceusTask).filter(ArceusTask.tenant_id == context.tenant_id, ArceusTask.mission_id == mission_id, ArceusTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "TASK_NOT_FOUND", "message": "Task not found.", "retryable": False}})

    content = _normalize_change_set_content(payload, mission_id=mission_id, task_id=task_id)
    content_hash = _stable_hash(content)
    artifact_key = f"task-{task_id}-change-set-{content_hash[:12]}"
    trust_status = "verified" if payload.review_state in {"applied", "rolled_back"} else "unverified"
    impact = dict(content.get("impact") or {})
    artifact = ArceusArtifact(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        task_id=task_id,
        artifact_key=artifact_key,
        artifact_type="change_set",
        title=payload.title,
        trust_status=trust_status,
        metadata_json={
            "source": payload.source,
            "review_state": payload.review_state,
            "change_count": len(payload.changes),
            "impact": impact,
            "diffs_present": impact.get("diffs_present", 0),
            "apply_payloads_present": impact.get("apply_payloads_present", 0),
            "rollback_payloads_present": impact.get("rollback_payloads_present", 0),
            "content_hash": content_hash,
        },
    )
    db.add(artifact)
    db.flush()
    version = ArceusArtifactVersion(
        tenant_id=context.tenant_id,
        artifact_id=artifact.id,
        version=1,
        content=content,
        content_hash=content_hash,
        provenance={"source": payload.source, "mission_id": str(mission_id), "task_id": str(task_id), "review_state": payload.review_state},
    )
    db.add(version)
    db.flush()
    artifact.current_version_id = version.id

    metadata = dict(task.output_contract or {})
    metadata["change_set_artifact_ids"] = sorted(set([*(metadata.get("change_set_artifact_ids") or []), str(artifact.id)]))
    metadata["latest_change_set"] = {
        "artifact_id": str(artifact.id),
        "version_id": str(version.id),
        "review_state": payload.review_state,
        "change_count": len(payload.changes),
        "impact": impact,
        "diffs_present": impact.get("diffs_present", 0),
        "apply_payloads_present": impact.get("apply_payloads_present", 0),
        "rollback_payloads_present": impact.get("rollback_payloads_present", 0),
    }
    task.output_contract = metadata
    task.version_number = int(task.version_number or 1) + 1
    _append_task_event(
        db,
        context=context,
        mission_id=mission_id,
        task_id=task_id,
        event_type="task.change_set.recorded",
        payload={"artifact_id": str(artifact.id), "version_id": str(version.id), "review_state": payload.review_state, "change_count": len(payload.changes)},
    )
    db.commit()
    return api_response(
        {
            "mission_id": str(mission_id),
            "task_id": str(task_id),
            "artifact_id": str(artifact.id),
            "artifact_version_id": str(version.id),
            "review_state": payload.review_state,
            "change_count": len(payload.changes),
            "impact": impact,
            "content_hash": content_hash,
        },
        request,
    )


@router.post("/api/v1/missions/{mission_id}/tasks/{task_id}/change-set/review")
def review_task_change_set(
    mission_id: UUID,
    task_id: UUID,
    payload: ChangeSetReviewActionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("review.complete")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    task = db.query(ArceusTask).filter(ArceusTask.tenant_id == context.tenant_id, ArceusTask.mission_id == mission_id, ArceusTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "TASK_NOT_FOUND", "message": "Task not found.", "retryable": False}})

    artifact, version = _load_change_set_artifact(db, context=context, task=task, payload=payload)
    review_state = _review_state_for_action(payload.action)
    content = dict(version.content or {})
    all_changes = list(content.get("changes") or [])
    requested_paths = [str(item) for item in payload.file_paths if str(item).strip()]
    requested_set = set(requested_paths)
    affected_files: list[str] = []
    updated_changes = []

    for change in all_changes:
        item = dict(change or {})
        change_path = str(item.get("path") or item.get("new_path") or item.get("old_path") or "")
        should_update = not requested_set or change_path in requested_set
        if should_update and change_path:
            affected_files.append(change_path)
            item["review_decision"] = payload.action
            item["review_state"] = review_state
            item["reviewed_by"] = str(context.user_id)
            item["review_reason"] = payload.reason
            if payload.action == "apply":
                item["applied"] = True
            if payload.action == "rollback":
                item["applied"] = False
        updated_changes.append(item)

    if requested_set and not affected_files:
        raise HTTPException(status_code=409, detail={"error": {"code": "CHANGE_SET_FILE_NOT_FOUND", "message": "None of the requested files exist in the recorded change set.", "retryable": False}})

    content["changes"] = updated_changes
    content["review_state"] = review_state
    content["review_action"] = payload.action
    content["reviewed_by"] = str(context.user_id)
    content["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    content["review_reason"] = payload.reason
    content["review_metadata"] = payload.metadata
    content_hash = _stable_hash(content)

    version.content = content
    version.content_hash = content_hash
    version.provenance = {**(version.provenance or {}), "review_state": review_state, "review_action": payload.action, "reviewed_by": str(context.user_id)}
    artifact.trust_status = "rejected" if review_state == "rejected" else "verified" if review_state in {"validated", "applied", "rolled_back"} else "unverified"
    artifact.metadata_json = {**(artifact.metadata_json or {}), "review_state": review_state, "review_action": payload.action, "content_hash": content_hash}

    task_metadata = dict(task.output_contract or {})
    latest = dict(task_metadata.get("latest_change_set") or {})
    latest.update(
        {
            "artifact_id": str(artifact.id),
            "version_id": str(version.id),
            "review_state": review_state,
            "review_action": payload.action,
            "change_count": len(updated_changes),
            "affected_files": affected_files,
        }
    )
    task_metadata["latest_change_set"] = latest
    task.output_contract = task_metadata
    task.version_number = int(task.version_number or 1) + 1

    _append_task_event(
        db,
        context=context,
        mission_id=mission_id,
        task_id=task_id,
        event_type=f"task.change_set.{payload.action}",
        payload={
            "artifact_id": str(artifact.id),
            "version_id": str(version.id),
            "review_state": review_state,
            "action": payload.action,
            "affected_files": affected_files,
            "reason": payload.reason,
        },
    )
    db.commit()
    return api_response(
        ChangeSetReviewActionResponse(
            mission_id=mission_id,
            task_id=task_id,
            action=payload.action,
            review_state=review_state,
            artifact_id=artifact.id,
            artifact_version_id=version.id,
            affected_files=affected_files,
        ).model_dump(mode="json"),
        request,
    )


@router.post("/api/v1/missions/{mission_id}/tasks/{task_id}/change-set/execute")
def execute_task_change_set(
    mission_id: UUID,
    task_id: UUID,
    payload: ChangeSetExecutionRequest,
    request: Request,
    context: RequestContext = Depends(require_permission("tool.execute")),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    task = db.query(ArceusTask).filter(ArceusTask.tenant_id == context.tenant_id, ArceusTask.mission_id == mission_id, ArceusTask.id == task_id).first()
    if task is None:
        raise HTTPException(status_code=404, detail={"error": {"code": "TASK_NOT_FOUND", "message": "Task not found.", "retryable": False}})

    artifact, version = _load_change_set_artifact(db, context=context, task=task, payload=payload)
    content = dict(version.content or {})
    all_changes = [dict(item or {}) for item in content.get("changes") or []]
    selected_changes = _selected_change_set(all_changes, payload.file_paths)
    if payload.action == "apply" and any(item.get("review_required") for item in selected_changes) and content.get("review_state") != "validated":
        _change_set_error(409, "CHANGE_SET_REVIEW_REQUIRED", "Risky change-set operations must be approved before filesystem apply.")

    root = _resolve_workspace_root(payload, task=task, content=content)
    results = _execute_change_set_payloads(root, selected_changes, action=payload.action, dry_run=payload.dry_run)
    affected_files = [item["path"] for item in results]
    review_state = "rolled_back" if payload.action == "rollback" else "applied"

    if not payload.dry_run:
        result_by_path = {item["path"]: item for item in results}
        selected_paths = {_normal_path(item.get("path")) for item in selected_changes}
        selected_paths.update({_normal_path(item.get("old_path")) for item in selected_changes if item.get("old_path")})
        updated_changes: list[dict] = []
        executed_at = datetime.now(timezone.utc).isoformat()
        for change in all_changes:
            item = dict(change or {})
            change_paths = {_normal_path(item.get("path")), _normal_path(item.get("old_path"))}
            if change_paths & selected_paths:
                item["applied"] = payload.action == "apply"
                item["filesystem_action"] = payload.action
                item["filesystem_executed_at"] = executed_at
                item["filesystem_result"] = result_by_path.get(_normal_path(item.get("path"))) or result_by_path.get(_normal_path(item.get("old_path"))) or {}
            updated_changes.append(item)

        content["changes"] = updated_changes
        content["review_state"] = review_state
        content["filesystem_action"] = payload.action
        content["filesystem_executed_by"] = str(context.user_id)
        content["filesystem_executed_at"] = executed_at
        content["filesystem_reason"] = payload.reason
        content["filesystem_metadata"] = payload.metadata
        content["filesystem_results"] = results
        content_hash = _stable_hash(content)

        version.content = content
        version.content_hash = content_hash
        version.provenance = {
            **(version.provenance or {}),
            "review_state": review_state,
            "filesystem_action": payload.action,
            "filesystem_executed_by": str(context.user_id),
        }
        artifact.trust_status = "verified"
        artifact.metadata_json = {
            **(artifact.metadata_json or {}),
            "review_state": review_state,
            "filesystem_action": payload.action,
            "filesystem_executed": True,
            "content_hash": content_hash,
            "affected_files": affected_files,
        }

        task_metadata = dict(task.output_contract or {})
        latest = dict(task_metadata.get("latest_change_set") or {})
        latest.update(
            {
                "artifact_id": str(artifact.id),
                "version_id": str(version.id),
                "review_state": review_state,
                "filesystem_action": payload.action,
                "filesystem_executed": True,
                "affected_files": affected_files,
                "result_count": len(results),
            }
        )
        task_metadata["latest_change_set"] = latest
        task.output_contract = task_metadata
        task.version_number = int(task.version_number or 1) + 1

        _append_task_event(
            db,
            context=context,
            mission_id=mission_id,
            task_id=task_id,
            event_type=f"task.change_set.filesystem.{payload.action}",
            payload={
                "artifact_id": str(artifact.id),
                "version_id": str(version.id),
                "review_state": review_state,
                "affected_files": affected_files,
                "result_count": len(results),
                "reason": payload.reason,
            },
        )
        db.commit()

    return api_response(
        ChangeSetExecutionResponse(
            mission_id=mission_id,
            task_id=task_id,
            action=payload.action,
            review_state=review_state,
            artifact_id=artifact.id,
            artifact_version_id=version.id,
            affected_files=affected_files,
            dry_run=payload.dry_run,
            executed=not payload.dry_run,
            results=[ChangeSetExecutionResult(**item) for item in results],
        ).model_dump(mode="json"),
        request,
    )


@router.get("/api/v1/evidence/{evidence_id}")
def get_evidence(
    evidence_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("evidence.view")),
    db: Session = Depends(get_db),
):
    evidence = _uow(db).evidence.get(tenant_id=context.tenant_id, evidence_id=evidence_id)
    return api_response(_evidence_response(evidence).model_dump(mode="json"), request)


@router.get("/api/v1/missions/{mission_id}/verification-runs")
def list_mission_verification_runs(
    mission_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("verification.view")),
    verification_type: str | None = Query(default=None, max_length=100),
    verification_status: str | None = Query(default=None, alias="status", max_length=60),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    uow = _uow(db)
    uow.missions.get(tenant_id=context.tenant_id, mission_id=mission_id)
    runs = uow.verification_runs.list_for_mission(
        tenant_id=context.tenant_id,
        mission_id=mission_id,
        verification_type=verification_type,
        status=verification_status,
        limit=limit,
    )
    return collection_response([_verification_run_response(item).model_dump(mode="json") for item in runs], request)


@router.get("/api/v1/verification-runs/{verification_run_id}")
def get_verification_run(
    verification_run_id: UUID,
    request: Request,
    context: RequestContext = Depends(require_permission("verification.view")),
    db: Session = Depends(get_db),
):
    run = _uow(db).verification_runs.get(tenant_id=context.tenant_id, verification_run_id=verification_run_id)
    return api_response(_verification_run_response(run).model_dump(mode="json"), request)
