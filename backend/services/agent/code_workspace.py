import difflib
import json
import os
import re
import shlex
import subprocess
import time
import urllib.error
import urllib.request
import zipfile
import hashlib
import uuid
import base64
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse
from uuid import UUID

from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from services.shared.models import AuditLog, CodeProject, CodeSession, FileReference, WorkspaceMember
from .agent_jobs import add_job_artifact, append_job_log, complete_job, heartbeat_job
from .config import settings
from .file_service import delete_object, get_file_text, put_object, storage_provider
from .llm_router import get_chat_llm


CODE_EXTENSIONS = {".py", ".js", ".ts", ".tsx", ".html", ".css", ".json", ".md", ".txt"}
PROJECT_IMPORT_EXTENSIONS = CODE_EXTENSIONS | {".csv", ".yml", ".yaml", ".toml", ".ini", ".env", ".gitignore", ".dockerfile"}
ALLOWED_COMMAND_PREFIXES = (
    ("npm", "test"),
    ("npm", "run", "test"),
    ("npm", "run", "build"),
    ("npm", "run", "lint"),
    ("npm", "run", "typecheck"),
    ("python", "-m", "pytest"),
    ("python3", "-m", "pytest"),
    ("pytest",),
    ("node", "--check"),
)
SAFE_SCRIPT_NAMES = {"build", "test", "lint", "typecheck", "check", "validate"}
MUTATING_COMMAND_PREFIXES = (
    ("npm", "install"),
    ("npm", "ci"),
    ("pnpm", "install"),
    ("yarn", "install"),
)
BLOCKED_TOKENS = {"rm", "del", "erase", "format", "shutdown", "reboot", "curl", "wget", "scp", "ssh", "sudo", "powershell", "cmd", "bash", "sh"}
BLOCKED_COMMAND_MARKERS = ("&&", "||", ";", "|", ">", "<", "`", "$(", "\n", "\r")
INSTALL_COMMAND_PREFIXES = MUTATING_COMMAND_PREFIXES
SECRET_OUTPUT_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password|authorization|bearer)\s*[:=]\s*([^\s'\"`]+)"),
    re.compile(r"(?i)(sk-[A-Za-z0-9_\-]{12,})"),
    re.compile(r"(?i)(gh[pousr]_[A-Za-z0-9_]{20,})"),
)
PREVIEW_PROCESSES: dict[str, subprocess.Popen] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metadata(session: CodeSession) -> dict:
    return dict(session.metadata_json or {})


def _set_metadata(session: CodeSession, metadata: dict) -> None:
    session.metadata_json = metadata


def _activity(kind: str, message: str, detail: str | None = None, diff: str | None = None, receipt: dict | None = None) -> dict:
    event = {"id": f"job-{datetime.now(timezone.utc).timestamp()}", "kind": kind, "message": message, "timestamp": _now()}
    if detail:
        event["detail"] = detail
    if diff:
        event["diff"] = diff
    if receipt:
        event["work_receipt"] = receipt
    return event


def _activity_work_receipt(session: CodeSession, kind: str, message: str, detail: str | None = None, diff: str | None = None, receipt: dict | None = None) -> dict:
    metadata = _metadata(session)
    patch_preview = metadata.get("patch_preview") or []
    changed = []
    for item in patch_preview:
        impact = _patch_impact_from_diff(item.get("diff") or "")
        changed.append({
            "filename": item.get("new_filename") or item.get("filename") or "workspace file",
            "operation": item.get("operation") or item.get("type") or "modify",
            "additions": int(item.get("additions") or impact.get("additions") or 0),
            "deletions": int(item.get("deletions") or impact.get("deletions") or 0),
        })
    checks = []
    checks_passed = len([item for item in checks if re.search(r"pass|success|done|completed", str(item.get("status") or ""), re.I)])
    checks_failed = len([item for item in checks if re.search(r"fail|error|blocked|timeout", str(item.get("status") or ""), re.I)])
    defaults = {
        "summary": message,
        "mode": "error" if kind == "error" else "code",
        "intent": {
            "start": "Start",
            "read": "Inspect",
            "code": "Build",
            "design": "Design",
            "deploy": "Deploy",
            "research": "Research",
            "edit": "Edit",
            "done": "Complete",
            "error": "Error",
        }.get(kind, "Build"),
        "project": session.project.name if session.project else "Workspace",
        "session": str(session.id)[:8],
        "sandbox_provider": settings.SANDBOX_PROVIDER.lower(),
        "plan": detail or "",
        "files_inspected": [
            item.get("filename") or item.get("path")
            for item in (metadata.get("file_tree") or [])
            if item.get("filename") or item.get("path")
        ][:12],
        "files_changed": changed,
        "folders_created": [
            item.get("filename")
            for item in patch_preview
            if (item.get("operation") or item.get("type")) == "folder" and item.get("filename")
        ],
        "commands_run": [{"label": detail, "status": "logged"}] if detail and kind in {"deploy", "error"} and not diff else [],
        "checks": checks,
        "checks_passed": checks_passed,
        "checks_failed": checks_failed,
        "approval_state": "waiting approval" if patch_preview else ("failed" if kind == "error" else "done"),
        "rollback_available": bool(metadata.get("rollback_snapshots")),
        "line_impact": {
            "additions": sum(item.get("additions", 0) for item in changed),
            "deletions": sum(item.get("deletions", 0) for item in changed),
        },
        "next_actions": [
            _serialize_workspace_task(task)
            for task in reversed(_workspace_tasks(metadata))
            if task.get("status") not in {"dismissed", "done", "failed"}
        ][:3],
    }
    if diff:
        defaults["diff_excerpt"] = diff[:2000]
    if receipt:
        merged = {**defaults, **receipt}
        merged["line_impact"] = receipt.get("line_impact") or defaults["line_impact"]
        merged_checks = merged.get("checks") or []
        merged["checks_passed"] = receipt.get(
            "checks_passed",
            len([item for item in merged_checks if re.search(r"pass|success|done|completed", str(item.get("status") or ""), re.I)]),
        )
        merged["checks_failed"] = receipt.get(
            "checks_failed",
            len([item for item in merged_checks if re.search(r"fail|error|blocked|timeout", str(item.get("status") or ""), re.I)]),
        )
        return merged
    return defaults


def append_activity(
    db: Session,
    session: CodeSession,
    kind: str,
    message: str,
    detail: str | None = None,
    diff: str | None = None,
    receipt: dict | None = None,
) -> dict:
    metadata = _metadata(session)
    log = list(metadata.get("activity_log") or [])
    event = _activity(kind, message, detail, diff, _activity_work_receipt(session, kind, message, detail, diff, receipt))
    if metadata.get("active_workspace_task_id"):
        event["task_id"] = metadata["active_workspace_task_id"]
    log.append(event)
    metadata["activity_log"] = log[-200:]
    metadata["last_activity_at"] = _now()
    _set_metadata(session, metadata)
    db.commit()
    return event


def _file_tree_for_records(records: list[FileReference]) -> list[dict]:
    tree = []
    for record in records:
        parts = [part for part in record.filename.replace("\\", "/").split("/") if part]
        tree.append({
            "id": str(record.id),
            "path": record.filename,
            "name": parts[-1] if parts else record.filename,
            "directory": "/".join(parts[:-1]),
            "size_bytes": record.size_bytes,
            "content_type": record.content_type,
        })
    return sorted(tree, key=lambda item: item["path"].lower())


def serialize_code_session(db: Session, user_id: UUID, session: CodeSession, include_files: bool = True) -> dict:
    metadata = _metadata(session)
    files = code_files(db, user_id, session) if include_files else []
    file_tree = _file_tree_for_records(files)
    metadata_tree = metadata.get("file_tree") or []
    return {
        "id": str(session.id),
        "project_id": str(session.project_id) if session.project_id else None,
        "title": session.title,
        "file_ids": session.file_ids or [],
        "status": session.status,
        "metadata_json": metadata,
        "plan_text": session.plan_text,
        "patch_text": session.patch_text,
        "patch_preview": metadata.get("patch_preview") or [],
        "preview_checks": metadata.get("preview_checks") or [],
        "preview_runtime": metadata.get("preview_runtime") or {},
        "workspace_analysis": metadata.get("workspace_analysis") or None,
        "activity_log": metadata.get("activity_log") or [],
        "file_tree": file_tree or metadata_tree,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


def serialize_code_project(project: CodeProject, active_session: CodeSession | None = None) -> dict:
    metadata = project.metadata_json or {}
    file_ids = project.file_ids or []
    return {
        "id": str(project.id),
        "name": project.name,
        "description": project.description or "",
        "repo_url": project.repo_url or "",
        "default_branch": project.default_branch or "",
        "status": project.status,
        "file_ids": file_ids,
        "file_count": len(file_ids),
        "settings": project.settings_json or {},
        "metadata": metadata,
        "local_workspace_path": metadata.get("local_workspace_path") or "",
        "openable": project.status == "active",
        "active_session_id": str(active_session.id) if active_session else None,
        "last_opened_at": project.last_opened_at.isoformat() if project.last_opened_at else None,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def _shared_project_ids(db: Session, user_id: UUID) -> list[UUID]:
    return [
        row[0]
        for row in (
            db.query(CodeSession.project_id)
            .join(WorkspaceMember, WorkspaceMember.code_session_id == CodeSession.id)
            .filter(
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.status == "active",
                CodeSession.project_id.isnot(None),
            )
            .distinct()
            .all()
        )
        if row[0]
    ]


def project_role(db: Session, user_id: UUID, project_id: UUID) -> str | None:
    project = db.query(CodeProject).filter(CodeProject.id == project_id, CodeProject.status != "deleted").first()
    if not project:
        return None
    if project.user_id == user_id:
        return "owner"
    roles = [
        row[0]
        for row in (
            db.query(WorkspaceMember.role)
            .join(CodeSession, CodeSession.id == WorkspaceMember.code_session_id)
            .filter(
                CodeSession.project_id == project_id,
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.status == "active",
            )
            .all()
        )
    ]
    order = {"viewer": 1, "editor": 2, "developer": 2, "admin": 3, "owner": 4}
    return max(roles, key=lambda role: order.get(role, 0), default=None)


def require_project_role(db: Session, user_id: UUID, project_id: UUID, minimum: str = "viewer") -> str:
    role = project_role(db, user_id, project_id)
    order = {"viewer": 1, "editor": 2, "developer": 2, "admin": 3, "owner": 4}
    if not role or order.get(role, 0) < order.get(minimum, 1):
        raise HTTPException(status_code=403, detail=f"{minimum.title()} access required for this project")
    return role


def list_code_projects(db: Session, user_id: UUID, limit: int = 30) -> list[CodeProject]:
    owned = (
        db.query(CodeProject)
        .filter(CodeProject.user_id == user_id, CodeProject.status != "deleted")
        .order_by(CodeProject.last_opened_at.desc().nullslast(), CodeProject.updated_at.desc(), CodeProject.created_at.desc())
        .limit(limit)
        .all()
    )
    owned_ids = {project.id for project in owned}
    shared_ids = [project_id for project_id in _shared_project_ids(db, user_id) if project_id not in owned_ids]
    shared = []
    if shared_ids and len(owned) < limit:
        shared = (
            db.query(CodeProject)
            .filter(CodeProject.id.in_(shared_ids), CodeProject.status != "deleted")
            .order_by(CodeProject.updated_at.desc(), CodeProject.created_at.desc())
            .limit(limit - len(owned))
            .all()
        )
    return (owned + shared)[:limit]


def get_code_project(db: Session, user_id: UUID, project_id: UUID) -> CodeProject:
    project = db.query(CodeProject).filter(CodeProject.id == project_id, CodeProject.status != "deleted").first()
    if not project:
        raise HTTPException(status_code=404, detail="Code project not found")
    require_project_role(db, user_id, project_id, "viewer")
    project.last_opened_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return project


def update_code_project(
    db: Session,
    user_id: UUID,
    project_id: UUID,
    name: str | None = None,
    description: str | None = None,
    repo_url: str | None = None,
    status: str | None = None,
) -> CodeProject:
    project = get_code_project(db, user_id, project_id)
    if name is not None:
        project.name = name.strip() or project.name
    if description is not None:
        project.description = description.strip() or None
    if repo_url is not None:
        project.repo_url = repo_url.strip() or None
    if status is not None:
        allowed = {"active", "archived", "deleted"}
        if status not in allowed:
            raise HTTPException(status_code=400, detail="Invalid code project status")
        project.status = status
    project.last_opened_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return project


def active_session_for_project(db: Session, user_id: UUID, project: CodeProject) -> CodeSession | None:
    require_project_role(db, user_id, project.id, "viewer")
    return (
        db.query(CodeSession)
        .filter(CodeSession.project_id == project.id, CodeSession.status == "active")
        .order_by(CodeSession.updated_at.desc(), CodeSession.created_at.desc())
        .first()
    )


def sessions_for_project(db: Session, user_id: UUID, project_id: UUID, limit: int = 30) -> list[CodeSession]:
    require_project_role(db, user_id, project_id, "viewer")
    return (
        db.query(CodeSession)
        .filter(CodeSession.project_id == project_id, CodeSession.status != "deleted")
        .order_by(CodeSession.updated_at.desc(), CodeSession.created_at.desc())
        .limit(limit)
        .all()
    )


def find_project_by_local_path(db: Session, user_id: UUID, local_path: str) -> CodeProject | None:
    normalized = str(Path(local_path).expanduser().resolve())
    projects = (
        db.query(CodeProject)
        .filter(CodeProject.user_id == user_id, CodeProject.status != "deleted")
        .order_by(CodeProject.updated_at.desc(), CodeProject.created_at.desc())
        .all()
    )
    for project in projects:
        metadata = project.metadata_json or {}
        value = metadata.get("local_workspace_path")
        if not value:
            continue
        try:
            candidate = str(Path(str(value)).expanduser().resolve())
        except Exception:
            candidate = str(value)
        if candidate == normalized:
            return project
    sessions = (
        db.query(CodeSession)
        .filter(CodeSession.user_id == user_id, CodeSession.project_id.isnot(None), CodeSession.status != "deleted")
        .order_by(CodeSession.updated_at.desc(), CodeSession.created_at.desc())
        .all()
    )
    for session in sessions:
        metadata = session.metadata_json or {}
        value = metadata.get("local_workspace_path")
        if not value:
            continue
        try:
            candidate = str(Path(str(value)).expanduser().resolve())
        except Exception:
            candidate = str(value)
        if candidate == normalized:
            project = db.query(CodeProject).filter(CodeProject.id == session.project_id, CodeProject.user_id == user_id, CodeProject.status != "deleted").first()
            if project:
                project_metadata = dict(project.metadata_json or {})
                project_metadata["local_workspace_path"] = normalized
                project_metadata.setdefault("workspace_mode", "local_trusted")
                project.metadata_json = project_metadata
                db.commit()
                db.refresh(project)
                return project
    return None


def create_code_project(
    db: Session,
    user_id: UUID,
    name: str,
    description: str = "",
    repo_url: str = "",
    file_ids: list[str] | None = None,
) -> tuple[CodeProject, CodeSession]:
    parsed_ids: list[UUID] = []
    for value in file_ids or []:
        try:
            parsed_ids.append(UUID(str(value)))
        except ValueError:
            continue
    valid_ids = [
        str(item.id)
        for item in db.query(FileReference.id).filter(FileReference.user_id == user_id, FileReference.id.in_(parsed_ids)).all()
    ] if parsed_ids else []
    now = datetime.now(timezone.utc)
    project = CodeProject(
        user_id=user_id,
        name=name.strip() or "Untitled Code Project",
        description=description.strip() or None,
        repo_url=repo_url.strip() or None,
        file_ids=valid_ids,
        status="active",
        settings_json={},
        metadata_json={"created_from": "nexus_code"},
        last_opened_at=now,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    session = create_code_session(db, user_id, f"{project.name} workspace", valid_ids, project_id=project.id)
    return project, session


def _safe_project_folder_name(name: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", name.strip().lower()).strip(".-")
    return safe[:80] or f"project-{uuid.uuid4().hex[:8]}"


def _unique_merged_filename(folder: str, filename: str, used: set[str]) -> str:
    clean = filename.replace("\\", "/").lstrip("/")
    candidate = f"{folder}/{clean}" if clean else f"{folder}/untitled.txt"
    if candidate not in used:
        used.add(candidate)
        return candidate
    path = Path(candidate)
    stem = path.stem or "file"
    suffix = path.suffix
    parent = path.parent.as_posix()
    index = 1
    while True:
        next_name = f"{parent}/{stem}.copy{index if index > 1 else ''}{suffix}"
        if next_name not in used:
            used.add(next_name)
            return next_name
        index += 1


def merge_code_projects(db: Session, user_id: UUID, source_project_ids: list[UUID], name: str | None = None) -> tuple[CodeProject, CodeSession, dict]:
    unique_ids = []
    for source_id in source_project_ids:
        if source_id not in unique_ids:
            unique_ids.append(source_id)
    if len(unique_ids) != 2:
        raise HTTPException(status_code=400, detail="Select exactly two projects to merge")

    projects = [get_code_project(db, user_id, source_id) for source_id in unique_ids]
    merged_name = (name or f"Merged: {projects[0].name} + {projects[1].name}").strip()[:255]
    project, session = create_code_project(
        db,
        user_id,
        merged_name,
        description="Merged workspace. Source projects remain unchanged.",
        file_ids=[],
    )

    project_metadata = dict(project.metadata_json or {})
    project_metadata.update({
        "created_from": "project_merge",
        "source_project_ids": [str(project.id) for project in projects],
        "source_project_names": [project.name for project in projects],
    })
    project.metadata_json = project_metadata

    copied_file_ids: list[str] = []
    copied: list[dict] = []
    skipped: list[dict] = []
    used_paths: set[str] = set()

    for source_project in projects:
        folder = _safe_project_folder_name(source_project.name)
        source_session = active_session_for_project(db, user_id, source_project)
        source_file_ids = source_session.file_ids if source_session else source_project.file_ids
        parsed_ids = []
        for value in source_file_ids or []:
            try:
                parsed_ids.append(UUID(str(value)))
            except ValueError:
                continue
        if not parsed_ids:
            continue
        records = (
            db.query(FileReference)
            .filter(FileReference.user_id == user_id, FileReference.id.in_(parsed_ids), FileReference.status == "active")
            .all()
        )
        by_id = {record.id: record for record in records}
        for file_id in parsed_ids:
            record = by_id.get(file_id)
            if not record:
                continue
            try:
                text = get_file_text(db, user_id, record.id)
            except Exception as exc:
                skipped.append({"filename": record.filename, "reason": str(exc)})
                continue
            encoded = text.encode("utf-8")
            filename = _unique_merged_filename(folder, record.filename, used_paths)
            new_record = FileReference(
                user_id=user_id,
                filename=filename,
                size_bytes=len(encoded),
                owner_type="code_workspace",
                owner_id=session.id,
                storage_provider=storage_provider(),
                bucket=settings.S3_BUCKET,
                object_key=f"users/{user_id}/code/{session.id}/{uuid.uuid4()}{Path(filename).suffix or '.txt'}",
                content_type=record.content_type or "text/plain",
                checksum_sha256=hashlib.sha256(encoded).hexdigest(),
                status="active",
                metadata_json={
                    "merged_from_project_id": str(source_project.id),
                    "merged_from_project_name": source_project.name,
                    "merged_from_file_id": str(record.id),
                    "source_filename": record.filename,
                },
            )
            db.add(new_record)
            db.flush()
            put_object(new_record.object_key, encoded, new_record.content_type)
            copied_file_ids.append(str(new_record.id))
            copied.append({"id": str(new_record.id), "filename": filename, "source": record.filename})

    session.file_ids = copied_file_ids
    project.file_ids = copied_file_ids
    session.title = f"{project.name} workspace"
    metadata = _metadata(session)
    metadata["activity_log"] = [
        _activity(
            "start",
            "Merged project created",
            f"Copied {len(copied_file_ids)} files from {projects[0].name} and {projects[1].name}.",
        )
    ]
    metadata["merge"] = {
        "source_project_ids": [str(project.id) for project in projects],
        "source_project_names": [project.name for project in projects],
        "copied_count": len(copied_file_ids),
        "skipped": skipped,
    }
    _set_metadata(session, metadata)
    db.commit()
    db.refresh(project)
    db.refresh(session)
    refresh_file_tree(db, user_id, session)
    return project, session, {"copied": copied, "skipped": skipped}


def update_project_files_from_session(db: Session, session: CodeSession) -> None:
    if not session.project_id:
        return
    project = db.query(CodeProject).filter(CodeProject.id == session.project_id, CodeProject.user_id == session.user_id).first()
    if not project:
        return
    project.file_ids = session.file_ids or []
    project.last_opened_at = datetime.now(timezone.utc)
    db.commit()


def list_code_sessions(db: Session, user_id: UUID, limit: int = 20) -> list[CodeSession]:
    return (
        db.query(CodeSession)
        .filter(CodeSession.user_id == user_id)
        .order_by(CodeSession.updated_at.desc(), CodeSession.created_at.desc())
        .limit(limit)
        .all()
    )


def create_code_session(db: Session, user_id: UUID, title: str, file_ids: list[str], project_id: UUID | None = None) -> CodeSession:
    if project_id:
        project = db.query(CodeProject.id).filter(CodeProject.id == project_id, CodeProject.status != "deleted").first()
        if not project:
            raise HTTPException(status_code=404, detail="Code project not found")
        require_project_role(db, user_id, project_id, "editor")
    session = CodeSession(
        user_id=user_id,
        project_id=project_id,
        title=title or "Code workspace",
        file_ids=file_ids,
        status="active",
        metadata_json={
            "activity_log": [_activity("start", "Workspace session created", title or "Code workspace")],
            "file_tree": [],
            "patch_preview": [],
            "rollback_snapshots": [],
        },
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    refresh_file_tree(db, user_id, session)
    return session


def get_code_session(db: Session, user_id: UUID, session_id: UUID) -> CodeSession:
    session = db.query(CodeSession).filter(CodeSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Code session not found")
    if session.user_id != user_id:
        membership = (
            db.query(WorkspaceMember)
            .filter(
                WorkspaceMember.code_session_id == session.id,
                WorkspaceMember.user_id == user_id,
                WorkspaceMember.status == "active",
            )
            .first()
        )
        if not membership:
            raise HTTPException(status_code=404, detail="Code session not found")
    return session


def code_files(db: Session, user_id: UUID, session: CodeSession, file_ids: list[str] | None = None) -> list[FileReference]:
    ids = []
    for value in (session.file_ids if file_ids is None else file_ids) or []:
        try:
            ids.append(UUID(str(value)))
        except ValueError:
            continue
    if not ids:
        return []
    records = (
        db.query(FileReference)
        .filter(
            FileReference.user_id == session.user_id,
            FileReference.id.in_(ids),
            FileReference.status == "active",
        )
        .all()
    )
    by_id = {record.id: record for record in records}
    return [by_id[file_id] for file_id in ids if file_id in by_id]


def refresh_file_tree(db: Session, user_id: UUID, session: CodeSession) -> list[dict]:
    tree = _file_tree_for_records(code_files(db, user_id, session))
    metadata = _metadata(session)
    metadata["file_tree"] = tree
    _set_metadata(session, metadata)
    db.commit()
    return tree


def _safe_workspace_path(root: Path, filename: str) -> Path:
    safe_name = filename.replace("\\", "/").lstrip("/")
    target = (root / safe_name).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise HTTPException(status_code=400, detail=f"Unsafe file path: {filename}")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def _workspace_runtime_root(session: CodeSession) -> Path:
    base = Path(settings.CODE_WORKSPACE_LOCAL_DIR).expanduser().resolve()
    root = (base / str(session.id)).resolve()
    if not str(root).startswith(str(base)):
        raise HTTPException(status_code=400, detail="Unsafe workspace runtime path")
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_local_workspace_file(session: CodeSession, filename: str) -> Path | None:
    local_path = (_metadata(session) or {}).get("local_workspace_path")
    if not local_path:
        return None
    local_root = Path(str(local_path)).expanduser().resolve()
    if not local_root.exists() or not local_root.is_dir():
        raise HTTPException(status_code=400, detail="Local workspace path is no longer available")
    safe_name = filename.replace("\\", "/").lstrip("/")
    target = (local_root / safe_name).resolve()
    try:
        target.relative_to(local_root)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Unsafe local workspace path: {filename}")
    target.parent.mkdir(parents=True, exist_ok=True)
    return target


def get_session_sandbox(session: CodeSession):
    from .sandbox import get_sandbox
    root = _workspace_runtime_root(session)
    return get_sandbox(str(session.id), root, settings)


def _runtime_metadata_update(db: Session, session: CodeSession, **updates) -> dict:
    metadata = _metadata(session)
    runtime = dict(metadata.get("workspace_runtime") or {})
    runtime.update(updates)
    runtime["updated_at"] = _now()
    metadata["workspace_runtime"] = runtime
    _set_metadata(session, metadata)
    db.commit()
    return runtime


def _sandbox_provider_status() -> dict:
    provider = settings.SANDBOX_PROVIDER.lower()
    production = str(settings.APP_ENV).lower() in {"prod", "production"}
    return {
        "provider": provider,
        "production": production,
        "local_allowed": bool(settings.ALLOW_LOCAL_SANDBOX) or not production,
        "e2b_configured": bool(settings.E2B_API_KEY),
        "docker_image": settings.SANDBOX_DOCKER_IMAGE,
        "sandbox_network_allowed_for_installs": bool(settings.SANDBOX_ALLOW_NETWORK),
        "docker_memory_limit": settings.SANDBOX_DOCKER_MEMORY,
        "docker_cpu_quota": settings.SANDBOX_DOCKER_CPU_QUOTA,
    }


def _remove_managed_paths(root: Path, paths: list[str]) -> None:
    for path in paths:
        if not path:
            continue
        target = (root / path).resolve()
        if not str(target).startswith(str(root.resolve())) or not target.exists() or not target.is_file():
            continue
        try:
            target.unlink()
        except OSError:
            continue


def sync_workspace_runtime(db: Session, user_id: UUID, session: CodeSession) -> dict:
    root = _workspace_runtime_root(session)
    _runtime_metadata_update(db, session, status="syncing", provider=settings.SANDBOX_PROVIDER.lower(), root=str(root), last_heartbeat_at=_now())
    metadata = _metadata(session)
    previous_paths = [str(path) for path in metadata.get("workspace_managed_paths") or []]
    _remove_managed_paths(root, previous_paths)

    written = []
    skipped = []
    for record in code_files(db, user_id, session):
        filename = record.filename.replace("\\", "/")
        if not _is_importable_project_file(filename):
            skipped.append(filename)
            continue
        target = _safe_workspace_path(root, filename)
        text = get_file_text(db, user_id, record.id)
        target.write_text(text, encoding="utf-8", errors="ignore")
        written.append(filename)

    metadata["workspace_runtime"] = {
        **(metadata.get("workspace_runtime") or {}),
        "root": str(root),
        "provider": settings.SANDBOX_PROVIDER.lower(),
        "status": "synced",
        "last_synced_at": _now(),
        "files_written": len(written),
        "files_skipped": len(skipped),
        "last_heartbeat_at": _now(),
    }
    metadata["workspace_managed_paths"] = written
    _set_metadata(session, metadata)
    db.commit()
    append_activity(db, session, "read", "Runtime workspace synced", f"{len(written)} file(s) written to persistent session runtime.")
    return {
        "root": str(root),
        "files_written": written,
        "files_skipped": skipped,
        "last_synced_at": metadata["workspace_runtime"]["last_synced_at"],
        "status": metadata["workspace_runtime"]["status"],
        "provider": metadata["workspace_runtime"]["provider"],
    }


def workspace_runtime_status(db: Session, user_id: UUID, session: CodeSession) -> dict:
    root = _workspace_runtime_root(session)
    metadata = _metadata(session)
    runtime = metadata.get("workspace_runtime") or {}
    command_data = discover_workspace_commands(db, user_id, session)
    command_log = list(metadata.get("command_log") or [])
    return {
        **_sandbox_provider_status(),
        "provider": settings.SANDBOX_PROVIDER.lower(),
        "status": runtime.get("status") or "not_synced",
        "root": str(root),
        "root_exists": root.exists(),
        "started_at": runtime.get("started_at"),
        "stopped_at": runtime.get("stopped_at"),
        "last_heartbeat_at": runtime.get("last_heartbeat_at"),
        "cleanup_status": runtime.get("cleanup_status"),
        "install_state": runtime.get("install_state") or "not_installed",
        "last_synced_at": runtime.get("last_synced_at"),
        "files_written": runtime.get("files_written") or 0,
        "files_skipped": runtime.get("files_skipped") or 0,
        "managed_paths": len(metadata.get("workspace_managed_paths") or []),
        "commands": command_data.get("commands") or [],
        "policy": command_data.get("policy") or {},
        "last_command": command_log[-1] if command_log else None,
        "last_check_run": metadata.get("last_check_run"),
        "preview": preview_status(session),
    }


def _safe_archive_name(name: str) -> str | None:
    normalized = name.replace("\\", "/").lstrip("/")
    if not normalized or normalized.endswith("/"):
        return None
    parts = [part for part in normalized.split("/") if part and part not in {".", ".."}]
    if not parts or len(parts) != len([part for part in normalized.split("/") if part]):
        return None
    if any(part.startswith(".git") for part in parts):
        return None
    return "/".join(parts)


def _is_importable_project_file(path: str) -> bool:
    name = Path(path).name.lower()
    suffix = Path(path).suffix.lower()
    if name in {"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "dockerfile", ".gitignore", ".env", ".env.example"}:
        return True
    if suffix in PROJECT_IMPORT_EXTENSIONS:
        return True
    return False


def _github_token() -> str:
    if not settings.GITHUB_TOKEN:
        raise HTTPException(status_code=400, detail="GITHUB_TOKEN is not configured")
    return settings.GITHUB_TOKEN


def _parse_github_repo(repo_url: str) -> tuple[str, str]:
    parsed = urlparse(repo_url.strip())
    if parsed.netloc.lower() != "github.com":
        raise HTTPException(status_code=400, detail="Only github.com repository URLs are supported in v1")
    parts = [part for part in parsed.path.strip("/").split("/") if part]
    if len(parts) < 2:
        raise HTTPException(status_code=400, detail="GitHub URL must include owner and repository")
    return parts[0], parts[1].removesuffix(".git")


def _github_request(method: str, path: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"https://api.github.com{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {_github_token()}",
            "Content-Type": "application/json",
            "User-Agent": "Arceus-Code/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        try:
            parsed = json.loads(detail)
            message = parsed.get("message") or detail
        except Exception:
            message = detail or str(exc)
        raise HTTPException(status_code=min(exc.code, 500), detail=f"GitHub API error: {message}")


def _github_default_branch(owner: str, repo: str) -> str:
    repo_data = _github_request("GET", f"/repos/{owner}/{repo}")
    return repo_data.get("default_branch") or "main"


def _github_branch_sha(owner: str, repo: str, branch: str) -> str:
    ref = _github_request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{quote(branch, safe='')}")
    return ref.get("object", {}).get("sha") or ""


def _github_create_branch(owner: str, repo: str, branch: str, base_sha: str) -> None:
    try:
        _github_request("POST", f"/repos/{owner}/{repo}/git/refs", {"ref": f"refs/heads/{branch}", "sha": base_sha})
    except HTTPException as exc:
        if "Reference already exists" not in str(exc.detail):
            raise


def _github_file_sha(owner: str, repo: str, path: str, branch: str) -> str | None:
    try:
        data = _github_request("GET", f"/repos/{owner}/{repo}/contents/{quote(path, safe='/')}?ref={quote(branch, safe='')}")
        return data.get("sha")
    except HTTPException as exc:
        if "Not Found" in str(exc.detail):
            return None
        raise


def import_github_repository(db: Session, user_id: UUID, session: CodeSession, repo_url: str, branch: str | None = None, max_files: int = 180) -> dict:
    owner, repo = _parse_github_repo(repo_url)
    target_branch = branch or _github_default_branch(owner, repo)
    tree = _github_request("GET", f"/repos/{owner}/{repo}/git/trees/{quote(target_branch, safe='')}?recursive=1")
    imported = []
    skipped = 0
    for item in tree.get("tree") or []:
        path = item.get("path") or ""
        if item.get("type") != "blob" or not _is_importable_project_file(path):
            skipped += 1
            continue
        if item.get("size", 0) > 1_500_000:
            skipped += 1
            continue
        if len(imported) >= max_files:
            skipped += 1
            continue
        blob = _github_request("GET", f"/repos/{owner}/{repo}/git/blobs/{item.get('sha')}")
        if blob.get("encoding") != "base64":
            skipped += 1
            continue
        content = base64.b64decode(blob.get("content", ""))
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            skipped += 1
            continue
        object_key = f"users/{user_id}/files/{uuid.uuid4()}{Path(path).suffix.lower() or '.txt'}"
        put_object(object_key, content, "text/plain")
        record = FileReference(
            user_id=user_id,
            owner_type="code_workspace",
            owner_id=session.id,
            storage_provider=storage_provider(),
            bucket=settings.S3_BUCKET,
            object_key=object_key,
            filename=path,
            content_type="text/plain",
            size_bytes=len(content),
            checksum_sha256=hashlib.sha256(content).hexdigest(),
            status="active",
            metadata_json={"imported_from_github": repo_url, "github_branch": target_branch, "github_sha": item.get("sha")},
        )
        db.add(record)
        db.flush()
        imported.append({"id": str(record.id), "filename": path, "size_bytes": len(content)})

    metadata = _metadata(session)
    metadata["git"] = {
        "repo_url": repo_url.strip(),
        "default_branch": target_branch,
        "provider": "github",
        "owner": owner,
        "repo": repo,
        "connected_at": _now(),
    }
    existing = [str(value) for value in (session.file_ids or [])]
    session.file_ids = existing + [item["id"] for item in imported]
    _set_metadata(session, metadata)
    db.commit()
    refresh_file_tree(db, user_id, session)
    update_project_files_from_session(db, session)
    append_activity(db, session, "read", "GitHub repository imported", f"{len(imported)} file(s) imported from {owner}/{repo}, {skipped} skipped")
    return {"imported": imported, "skipped": skipped, "file_ids": session.file_ids, "git": metadata["git"]}


def import_zip_project(db: Session, user_id: UUID, session: CodeSession, upload, max_files: int = 180) -> dict:
    filename = Path(upload.filename or "project.zip").name
    if not filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="Upload a .zip project archive")
    data = upload.file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded archive is empty")
    if len(data) > 40 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Project archive exceeds 40 MB")

    imported: list[dict] = []
    skipped = 0
    try:
        import io
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            for info in zf.infolist():
                safe_name = _safe_archive_name(info.filename)
                if not safe_name or not _is_importable_project_file(safe_name):
                    skipped += 1
                    continue
                if info.file_size > 1_500_000:
                    skipped += 1
                    continue
                if len(imported) >= max_files:
                    skipped += 1
                    continue
                content = zf.read(info)
                try:
                    content.decode("utf-8")
                except UnicodeDecodeError:
                    skipped += 1
                    continue
                extension = Path(safe_name).suffix.lower() or Path(safe_name).name.lower()
                object_key = f"users/{user_id}/files/{uuid.uuid4()}{Path(safe_name).suffix.lower() or '.txt'}"
                put_object(object_key, content, "text/plain")
                record = FileReference(
                    user_id=user_id,
                    owner_type="code_workspace",
                    owner_id=session.id,
                    storage_provider=storage_provider(),
                    bucket=settings.S3_BUCKET,
                    object_key=object_key,
                    filename=safe_name,
                    content_type="text/plain",
                    size_bytes=len(content),
                    checksum_sha256=hashlib.sha256(content).hexdigest(),
                    status="active",
                    metadata_json={"extension": extension, "imported_from_zip": filename},
                )
                db.add(record)
                db.flush()
                imported.append({"id": str(record.id), "filename": safe_name, "size_bytes": len(content)})
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Invalid zip archive")

    existing = [str(value) for value in (session.file_ids or [])]
    session.file_ids = existing + [item["id"] for item in imported]
    db.commit()
    refresh_file_tree(db, user_id, session)
    update_project_files_from_session(db, session)
    append_activity(db, session, "read", "Project archive imported", f"{len(imported)} file(s) imported, {skipped} skipped")
    return {"imported": imported, "skipped": skipped, "file_ids": session.file_ids}


def _command_parts(command: str) -> list[str]:
    try:
        return shlex.split(command, posix=os.name != "nt")
    except ValueError:
        raise HTTPException(status_code=400, detail="Command could not be parsed")


def _redact_sensitive_output(output: str) -> str:
    redacted = output or ""
    for pattern in SECRET_OUTPUT_PATTERNS:
        def replace(match: re.Match) -> str:
            if match.lastindex and match.lastindex >= 2:
                return f"{match.group(1)}=[redacted]"
            return "[redacted-secret]"

        redacted = pattern.sub(replace, redacted)
    return redacted


def discover_workspace_commands(db: Session, user_id: UUID, session: CodeSession) -> dict:
    commands: list[dict] = []
    seen: set[str] = set()
    files = code_files(db, user_id, session)
    package_files = [record for record in files if Path(record.filename).name == "package.json"]
    for record in package_files[:3]:
        try:
            package = json.loads(get_file_text(db, user_id, record.id))
        except Exception:
            continue
        scripts = package.get("scripts") or {}
        package_manager = "npm"
        filenames = {Path(item.filename).name for item in files}
        if "pnpm-lock.yaml" in filenames:
            package_manager = "pnpm"
        elif "yarn.lock" in filenames:
            package_manager = "yarn"
        for script_name, script_body in scripts.items():
            if script_name not in SAFE_SCRIPT_NAMES:
                continue
            command = f"{package_manager} run {script_name}"
            if script_name == "test" and package_manager == "npm":
                command = "npm test"
            if command in seen:
                continue
            seen.add(command)
            commands.append({
                "label": script_name.title() if script_name != "typecheck" else "Typecheck",
                "command": command,
                "source": record.filename,
                "script": str(script_body)[:180],
            })

    python_files = [record for record in files if Path(record.filename).suffix.lower() == ".py"]
    filenames = {Path(record.filename).name for record in files}
    if python_files and "python -m pytest" not in seen:
        commands.append({
            "label": "Pytest",
            "command": "python -m pytest",
            "source": "Python workspace",
            "script": "Run Python tests with pytest.",
        })
    return {
        "commands": commands[:12],
        "policy": {
            "allowed_prefixes": [" ".join(prefix) for prefix in ALLOWED_COMMAND_PREFIXES],
            "approval_required_prefixes": [" ".join(prefix) for prefix in MUTATING_COMMAND_PREFIXES],
            "blocked_tokens": sorted(BLOCKED_TOKENS),
            "blocked_markers": list(BLOCKED_COMMAND_MARKERS),
            "mode": "exact safe discovered scripts, safe built-in check commands, and approval-gated installs",
        },
    }


def _workspace_preview_port(session: CodeSession) -> int:
    digest = hashlib.sha256(str(session.id).encode("utf-8")).hexdigest()
    return 4300 + (int(digest[:4], 16) % 1000)


def _package_manager_for_files(files: list[FileReference]) -> str:
    filenames = {Path(item.filename).name for item in files}
    if "pnpm-lock.yaml" in filenames:
        return "pnpm"
    if "yarn.lock" in filenames:
        return "yarn"
    return "npm"


def _detect_preview_command(db: Session, user_id: UUID, session: CodeSession) -> dict:
    files = code_files(db, user_id, session)
    package_manager = _package_manager_for_files(files)
    for record in files:
        if Path(record.filename).name != "package.json":
            continue
        try:
            package = json.loads(get_file_text(db, user_id, record.id))
        except Exception:
            continue
        scripts = package.get("scripts") or {}
        for script_name in ("dev", "start"):
            script_body = str(scripts.get(script_name) or "")
            if not script_body:
                continue
            lowered_body = script_body.lower()
            if any(token in lowered_body.split() for token in BLOCKED_TOKENS):
                continue
            return {
                "command": f"{package_manager} run {script_name}",
                "script": script_name,
                "source": record.filename,
                "script_body": script_body[:180],
            }
    raise HTTPException(status_code=400, detail="No safe dev/start preview script was found in package.json")


def preview_status(session: CodeSession) -> dict:
    metadata = _metadata(session)
    preview = metadata.get("preview_runtime") or {}
    provider = settings.SANDBOX_PROVIDER.lower()

    if provider == "local":
        process = PREVIEW_PROCESSES.get(str(session.id))
        running = bool(process and process.poll() is None)
        status = "running" if running else "stopped"
    elif provider == "docker":
        container_name = f"nexus-sandbox-{session.id}"
        try:
            res = subprocess.run(["docker", "inspect", "-f", "{{.State.Running}}", container_name], capture_output=True, text=True)
            running = res.stdout.strip() == "true" and preview.get("port") is not None
            status = "running" if running else "stopped"
        except Exception:
            status = "stopped"
    else:
        status = preview.get("status", "stopped")

    return {
        "status": status,
        "preview_url": preview.get("preview_url"),
        "local_url": preview.get("local_url"),
        "command": preview.get("command"),
        "port": preview.get("port"),
        "started_at": preview.get("started_at"),
    }


def read_preview_logs(session: CodeSession, max_chars: int = 12000) -> dict:
    metadata = _metadata(session)
    preview = metadata.get("preview_runtime") or {}
    log_path = preview.get("log_path")
    text = ""
    if log_path:
        path = Path(str(log_path))
        try:
            if path.exists() and path.is_file():
                raw = path.read_text(encoding="utf-8", errors="ignore")
                text = raw[-max_chars:]
        except OSError:
            text = ""
    markers = [
        "error",
        "failed",
        "exception",
        "traceback",
        "module not found",
        "syntaxerror",
        "typeerror",
        "referenceerror",
        "eaddrinuse",
    ]
    lower = text.lower()
    issues = sorted({marker for marker in markers if marker in lower})
    excerpts = []
    if text:
        for line in text.splitlines():
            lowered = line.lower()
            if any(marker in lowered for marker in markers):
                excerpts.append(line.strip()[:400])
            if len(excerpts) >= 8:
                break
    return {
        "logs": text,
        "issues": issues,
        "excerpts": excerpts,
        "status": preview_status(session).get("status"),
        "command": preview.get("command"),
        "log_path": log_path,
        "updated_at": _now(),
    }


def start_workspace_preview(db: Session, user_id: UUID, session: CodeSession, job=None) -> dict:
    provider = settings.SANDBOX_PROVIDER.lower()
    preview_command = _detect_preview_command(db, user_id, session)
    port = _workspace_preview_port(session)
    token = uuid.uuid4().hex

    append_activity(db, session, "deploy", "Starting workspace preview", preview_command["command"])
    append_job_log(db, job, "deploy", "Starting workspace preview", f"{preview_command['command']} on port {port}")

    if provider == "local":
        existing = PREVIEW_PROCESSES.get(str(session.id))
        if existing and existing.poll() is None:
            return preview_status(session)
        runtime = sync_workspace_runtime(db, user_id, session)
        root = Path(runtime["root"])
        log_dir = root / ".nexus"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_path = log_dir / "preview.log"
        env = {
            **os.environ,
            "PORT": str(port),
            "HOST": "127.0.0.1",
            "HOSTNAME": "127.0.0.1",
            "BROWSER": "none",
        }
        parts = _command_parts(preview_command["command"])
        log_file = log_path.open("a", encoding="utf-8", errors="ignore")
        try:
            process = subprocess.Popen(
                parts,
                cwd=root,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )
        finally:
            log_file.close()
        PREVIEW_PROCESSES[str(session.id)] = process

        local_url = f"http://127.0.0.1:{port}"
        status = "starting"
        for _ in range(16):
            if process.poll() is not None:
                status = "failed"
                break
            try:
                with urllib.request.urlopen(local_url, timeout=1.0) as response:
                    if response.status < 500:
                        status = "running"
                        break
            except Exception:
                time.sleep(0.5)
    else:
        # Docker or E2B Sandbox
        sandbox = get_session_sandbox(session)
        res = sandbox.start_preview_server(preview_command["command"], port)
        status = res.get("status", "running")
        local_url = res.get("proxy_url") or f"http://localhost:{port}"
        log_path = ""

    proxy_url = f"/api/v1/code/sessions/{session.id}/preview/proxy/?token={token}"
    metadata = _metadata(session)
    metadata["preview_runtime"] = {
        "status": status,
        "local_url": local_url,
        "preview_url": proxy_url,
        "port": port,
        "token": token,
        "command": preview_command["command"],
        "log_path": str(log_path) if log_path else "",
        "started_at": _now(),
    }
    _set_metadata(session, metadata)
    db.commit()
    append_activity(db, session, "done" if status == "running" else "error", f"Preview {status}", proxy_url)
    complete_job(db, job, "completed" if status in {"running", "starting"} else "failed", metadata["preview_runtime"])
    return preview_status(session)


def stop_workspace_preview(db: Session, session: CodeSession, job=None) -> dict:
    provider = settings.SANDBOX_PROVIDER.lower()
    stopped = False

    if provider == "local":
        process = PREVIEW_PROCESSES.pop(str(session.id), None)
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
            stopped = True
    else:
        sandbox = get_session_sandbox(session)
        stopped = sandbox.stop_preview_server()

    metadata = _metadata(session)
    preview = metadata.get("preview_runtime") or {}
    preview["status"] = "stopped"
    preview["stopped_at"] = _now()
    metadata["preview_runtime"] = preview
    _set_metadata(session, metadata)
    db.commit()
    append_activity(db, session, "done", "Preview stopped", preview.get("command") or "")
    complete_job(db, job, "completed", {"stopped": stopped, "status": "stopped"})
    return preview_status(session)


def _dynamic_command_allowed(parts: list[str], commands: list[dict]) -> bool:
    command = " ".join(parts).lower()
    return any(command == str(item.get("command") or "").lower() for item in commands)


def _command_policy(command: str, parts: list[str], commands: list[dict] | None = None, approved: bool = False) -> dict:
    lowered = [part.lower() for part in parts]
    allowed_commands = [str(item.get("command") or "") for item in (commands or []) if item.get("command")]
    approval_commands = [" ".join(prefix) for prefix in MUTATING_COMMAND_PREFIXES]
    if not lowered:
        return {"allowed": False, "requires_approval": False, "reason": "Empty command.", "allowed_commands": allowed_commands, "approval_required_prefixes": approval_commands}
    if any(marker in command for marker in BLOCKED_COMMAND_MARKERS):
        return {"allowed": False, "requires_approval": False, "reason": "Shell control operators are blocked. Run one safe command at a time.", "allowed_commands": allowed_commands, "approval_required_prefixes": approval_commands}
    blocked = [token for token in lowered if token in BLOCKED_TOKENS]
    if blocked:
        return {"allowed": False, "requires_approval": False, "reason": f"Blocked token: {blocked[0]}", "allowed_commands": allowed_commands, "approval_required_prefixes": approval_commands}
    if commands and _dynamic_command_allowed(lowered, commands):
        return {"allowed": True, "requires_approval": False, "reason": "Matches a discovered safe workspace script.", "allowed_commands": allowed_commands, "approval_required_prefixes": approval_commands}
    for prefix in ALLOWED_COMMAND_PREFIXES:
        if tuple(lowered[: len(prefix)]) == prefix:
            return {"allowed": True, "requires_approval": False, "reason": f"Matches safe prefix: {' '.join(prefix)}", "allowed_commands": allowed_commands, "approval_required_prefixes": approval_commands}
    for prefix in MUTATING_COMMAND_PREFIXES:
        if tuple(lowered[: len(prefix)]) == prefix:
            if not approved:
                return {"allowed": False, "requires_approval": True, "reason": "Dependency mutation requires explicit approval.", "allowed_commands": allowed_commands, "approval_required_prefixes": approval_commands}
            return {"allowed": True, "requires_approval": True, "reason": f"Approved mutation command: {' '.join(prefix)}", "allowed_commands": allowed_commands, "approval_required_prefixes": approval_commands}
    return {"allowed": False, "requires_approval": False, "reason": "Command is outside the workspace allowlist.", "allowed_commands": allowed_commands, "approval_required_prefixes": approval_commands}


def _install_policy(command: str, approved: bool) -> dict:
    parts = _command_parts(command)
    lowered = [part.lower() for part in parts]
    allowed_commands = [" ".join(prefix) for prefix in INSTALL_COMMAND_PREFIXES]
    if not lowered:
        return {"allowed": False, "requires_approval": True, "reason": "Empty install command.", "allowed_commands": allowed_commands}
    if any(marker in command for marker in BLOCKED_COMMAND_MARKERS):
        return {"allowed": False, "requires_approval": True, "reason": "Shell control operators are blocked for install commands.", "allowed_commands": allowed_commands}
    blocked = [token for token in lowered if token in BLOCKED_TOKENS]
    if blocked:
        return {"allowed": False, "requires_approval": True, "reason": f"Blocked token: {blocked[0]}", "allowed_commands": allowed_commands}
    if not any(tuple(lowered[: len(prefix)]) == prefix for prefix in INSTALL_COMMAND_PREFIXES):
        return {"allowed": False, "requires_approval": True, "reason": "Only package-manager install commands are allowed.", "allowed_commands": allowed_commands}
    if not approved:
        return {"allowed": False, "requires_approval": True, "reason": "Dependency install requires explicit approval.", "allowed_commands": allowed_commands}
    return {"allowed": True, "requires_approval": True, "reason": "Approved package install command.", "allowed_commands": allowed_commands}


def _standard_command_result(command: str, raw: dict, policy: dict, workspace_root: Path) -> dict:
    output = _redact_sensitive_output(str(raw.get("output") or "(no output)"))
    max_chars = max(1000, int(settings.SANDBOX_COMMAND_MAX_OUTPUT_CHARS))
    return {
        "command": command,
        "status": raw.get("status") or "failed",
        "return_code": raw.get("return_code"),
        "provider": raw.get("provider") or settings.SANDBOX_PROVIDER.lower(),
        "sandbox_provider": raw.get("provider") or settings.SANDBOX_PROVIDER.lower(),
        "duration_ms": raw.get("duration_ms"),
        "timeout_seconds": raw.get("timeout_seconds"),
        "output": output[-max_chars:],
        "output_excerpt": _redact_sensitive_output(str(raw.get("output_excerpt") or output[-4000:])),
        "artifacts": raw.get("artifacts") or [],
        "started_at": raw.get("started_at"),
        "completed_at": raw.get("completed_at") or raw.get("ran_at") or _now(),
        "ran_at": raw.get("ran_at") or raw.get("completed_at") or _now(),
        "policy": policy,
        "workspace_root": str(workspace_root),
    }


def _command_allowed(parts: list[str], commands: list[dict] | None = None) -> bool:
    return bool(_command_policy(" ".join(parts), parts, commands).get("allowed"))


def run_workspace_command(
    db: Session,
    user_id: UUID,
    session: CodeSession,
    command: str,
    timeout_seconds: int = 45,
    approved: bool = False,
    job=None,
) -> dict:
    parts = _command_parts(command)
    discovered_commands = discover_workspace_commands(db, user_id, session).get("commands") or []
    policy = _command_policy(command, parts, discovered_commands, approved=approved)
    runtime_root = _workspace_runtime_root(session)
    if not policy.get("allowed"):
        append_activity(db, session, "error", "Command blocked", policy.get("reason") or "Only safe build/test/lint commands are enabled in v1.")
        result = {
            "command": command,
            "status": "blocked",
            "return_code": None,
            "provider": settings.SANDBOX_PROVIDER.lower(),
            "output": policy.get("reason") or "Command is outside the workspace allowlist.",
            "output_excerpt": policy.get("reason") or "Command is outside the workspace allowlist.",
            "policy": policy,
            "workspace_root": str(runtime_root),
            "ran_at": _now(),
        }
        complete_job(db, job, "blocked", result, commands_run=[result])
        raise HTTPException(
            status_code=403 if policy.get("requires_approval") else 400,
            detail={"message": policy.get("reason") or "Command is not allowed for workspace execution.", "policy": policy, "result": result},
        )

    runtime = sync_workspace_runtime(db, user_id, session)
    workspace_root = Path(runtime["root"])
    _runtime_metadata_update(db, session, status="running", provider=settings.SANDBOX_PROVIDER.lower(), active_command=command, last_heartbeat_at=_now())
    heartbeat_job(db, job, "running", command, 45)
    append_activity(db, session, "deploy", f"Running command: {command}", f"Using persistent runtime workspace with {len(runtime['files_written'])} synced file(s).")
    append_job_log(db, job, "deploy", f"Running command: {command}", f"Runtime workspace: {workspace_root}")

    try:
        sandbox = get_session_sandbox(session)
        result_data = sandbox.run_command(command, timeout=max(5, min(timeout_seconds, 120)))

        result = _standard_command_result(command, result_data, policy, workspace_root)
        status = result["status"]
        output = result["output"]

        clipped = output[-12000:] if output else "(no output)"
        event_kind = "done" if status == "passed" else "error"
        append_activity(db, session, event_kind, f"Command {status}: {command}", clipped)

        metadata = _metadata(session)
        command_log = list(metadata.get("command_log") or [])
        command_log.append(result)
        metadata["command_log"] = command_log[-50:]
        runtime_meta = dict(metadata.get("workspace_runtime") or {})
        runtime_meta.update({
            "status": "completed" if status == "passed" else status,
            "provider": result["provider"],
            "last_command": result,
            "last_heartbeat_at": _now(),
        })
        metadata["workspace_runtime"] = runtime_meta
        _set_metadata(session, metadata)
        db.commit()
        complete_job(db, job, "completed" if status == "passed" else "failed", result, commands_run=[result])
        return result
    except FileNotFoundError:
        append_activity(db, session, "error", f"Command unavailable: {parts[0]}", "The runtime image does not include this executable.")
        result = {
            "command": command,
            "status": "failed",
            "return_code": None,
            "provider": settings.SANDBOX_PROVIDER.lower(),
            "output": f"Command unavailable: {parts[0]}",
            "output_excerpt": f"Command unavailable: {parts[0]}",
            "policy": policy,
            "workspace_root": str(workspace_root),
            "ran_at": _now(),
        }
        complete_job(db, job, "failed", result, commands_run=[result])
        raise HTTPException(status_code=400, detail={"message": f"Command unavailable: {parts[0]}", "result": result})
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(part for part in [exc.stdout or "", exc.stderr or ""] if part).strip()
        clipped = output[-12000:] if output else "Command timed out before producing output."
        append_activity(db, session, "error", f"Command timed out: {command}", clipped)
        result = {"command": command, "status": "timeout", "return_code": None, "output": clipped, "workspace_root": str(workspace_root), "ran_at": _now()}
        _runtime_metadata_update(db, session, status="timeout", last_command=result, last_heartbeat_at=_now())
        complete_job(db, job, "timeout", result, commands_run=[result])
        return result
    except Exception as exc:
        clipped = _redact_sensitive_output(str(exc))[-4000:]
        append_activity(db, session, "error", f"Command failed: {command}", clipped)
        result = {
            "command": command,
            "status": "failed",
            "return_code": None,
            "provider": settings.SANDBOX_PROVIDER.lower(),
            "output": clipped,
            "output_excerpt": clipped,
            "policy": policy,
            "workspace_root": str(workspace_root),
            "ran_at": _now(),
        }
        _runtime_metadata_update(db, session, status="failed", last_command=result, last_heartbeat_at=_now())
        complete_job(db, job, "failed", result, commands_run=[result])
        return result


def install_workspace_dependencies(
    db: Session,
    user_id: UUID,
    session: CodeSession,
    command: str | None = None,
    approved: bool = False,
    timeout_seconds: int | None = None,
    job=None,
) -> dict:
    files = code_files(db, user_id, session)
    package_manager = _package_manager_for_files(files)
    install_command = (command or ("npm ci" if any(Path(item.filename).name == "package-lock.json" for item in files) else f"{package_manager} install")).strip()
    policy = _install_policy(install_command, approved)
    if not policy.get("allowed"):
        append_activity(db, session, "error", "Install blocked", policy.get("reason") or "Install requires approval.")
        complete_job(db, job, "blocked", {"error": "Install is not allowed", "policy": policy}, commands_run=[install_command])
        raise HTTPException(status_code=403 if policy.get("requires_approval") else 400, detail={"message": policy.get("reason"), "policy": policy})

    runtime = sync_workspace_runtime(db, user_id, session)
    workspace_root = Path(runtime["root"])
    _runtime_metadata_update(db, session, status="installing", install_state="running", provider=settings.SANDBOX_PROVIDER.lower(), active_command=install_command, last_heartbeat_at=_now())
    heartbeat_job(db, job, "installing", install_command, 35)
    append_activity(db, session, "deploy", "Installing workspace dependencies", install_command)
    append_job_log(db, job, "deploy", "Installing workspace dependencies", install_command)

    sandbox = get_session_sandbox(session)
    raw = sandbox.run_command(
        install_command,
        timeout=max(30, min(timeout_seconds or settings.SANDBOX_INSTALL_TIMEOUT_SECONDS, 900)),
        allow_network=bool(settings.SANDBOX_ALLOW_NETWORK),
    )
    result = _standard_command_result(install_command, raw, policy, workspace_root)
    status = result["status"]
    metadata = _metadata(session)
    command_log = list(metadata.get("command_log") or [])
    command_log.append(result)
    metadata["command_log"] = command_log[-50:]
    runtime_meta = dict(metadata.get("workspace_runtime") or {})
    runtime_meta.update({
        "status": "synced" if status == "passed" else status,
        "install_state": "installed" if status == "passed" else "failed",
        "last_install": result,
        "last_command": result,
        "last_heartbeat_at": _now(),
    })
    metadata["workspace_runtime"] = runtime_meta
    _set_metadata(session, metadata)
    db.commit()
    append_activity(db, session, "done" if status == "passed" else "error", f"Install {status}", result["output"])
    complete_job(db, job, "completed" if status == "passed" else "failed", result, commands_run=[result])
    return result


def run_workspace_checks(
    db: Session,
    user_id: UUID,
    session: CodeSession,
    timeout_seconds: int = 60,
    job=None,
) -> dict:
    discovered_commands = discover_workspace_commands(db, user_id, session).get("commands") or []
    priority = {"build": 0, "typecheck": 1, "lint": 2, "test": 3, "pytest": 3}
    ordered = sorted(
        discovered_commands,
        key=lambda item: priority.get(str(item.get("label") or "").lower(), 9),
    )
    commands = []
    seen: set[str] = set()
    for item in ordered:
        command = str(item.get("command") or "").strip()
        if not command or command in seen:
            continue
        parts = _command_parts(command)
        if not _command_allowed(parts, discovered_commands):
            continue
        commands.append(command)
        seen.add(command)
        if len(commands) >= 6:
            break

    if not commands:
        append_activity(db, session, "error", "No safe checks found", "Add package scripts such as build, test, lint, or typecheck.")
        complete_job(db, job, "blocked", {"error": "No safe checks found"}, commands_run=[])
        raise HTTPException(status_code=400, detail="No safe build/test/lint/typecheck commands found.")

    runtime = sync_workspace_runtime(db, user_id, session)
    workspace_root = Path(runtime["root"])
    _runtime_metadata_update(db, session, status="running", provider=settings.SANDBOX_PROVIDER.lower(), active_command="workspace checks", last_heartbeat_at=_now())
    heartbeat_job(db, job, "running", "Running workspace checks", 35)
    append_activity(db, session, "deploy", "Running workspace checks", ", ".join(commands))
    append_job_log(db, job, "deploy", "Running workspace checks", f"{len(commands)} command(s) in {workspace_root}")

    results = []
    sandbox = get_session_sandbox(session)
    for command in commands:
        res = sandbox.run_command(command, timeout=max(10, min(timeout_seconds, 180)))
        result = _standard_command_result(command, res, _command_policy(command, _command_parts(command), discovered_commands), workspace_root)
        result["output"] = result["output"][-8000:] if result["output"] else "(no output)"
        results.append(result)
        append_activity(db, session, "done" if result["status"] == "passed" else "error", f"Check {result['status']}: {command}", result["output"])
        append_job_log(db, job, "done" if result["status"] == "passed" else "error", f"Check {result['status']}: {command}", result["output"][:1000])

    passed = sum(1 for item in results if item["status"] == "passed")
    summary = {
        "status": "passed" if passed == len(results) else "failed",
        "passed": passed,
        "failed": len(results) - passed,
        "total": len(results),
        "commands": results,
        "workspace_root": str(workspace_root),
        "ran_at": _now(),
    }
    metadata = _metadata(session)
    command_log = list(metadata.get("command_log") or [])
    command_log.extend(results)
    metadata["command_log"] = command_log[-50:]
    metadata["last_check_run"] = summary
    runtime_meta = dict(metadata.get("workspace_runtime") or {})
    runtime_meta.update({
        "status": "completed" if summary["status"] == "passed" else "failed",
        "last_check_run": summary,
        "last_heartbeat_at": _now(),
    })
    metadata["workspace_runtime"] = runtime_meta
    _set_metadata(session, metadata)
    db.commit()
    append_activity(db, session, "done" if summary["status"] == "passed" else "error", f"Workspace checks {summary['status']}", f"{passed}/{len(results)} check(s) passed")
    if summary["status"] == "passed":
        preview_runtime = (session.metadata_json or {}).get("preview_runtime") or {}
        preview_url = preview_runtime.get("local_url") or preview_runtime.get("external_url")
        if preview_runtime.get("status") in {"running", "starting"} and preview_url:
            try:
                check_preview_url(db, session, str(preview_url), job=None)
            except Exception as exc:
                append_activity(db, session, "error", "Preview auto-verification failed", str(exc)[:1000])
    complete_job(db, job, "completed" if summary["status"] == "passed" else "failed", summary, commands_run=results)
    return summary


def check_preview_url(db: Session, session: CodeSession, url: str, job=None) -> dict:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        append_activity(db, session, "error", "Preview URL rejected", "Use a full http or https URL.")
        complete_job(db, job, "failed", {"error": "Invalid preview URL"})
        raise HTTPException(status_code=400, detail="Use a full http or https preview URL.")

    append_activity(db, session, "deploy", "Checking preview", url)
    append_job_log(db, job, "deploy", "Checking preview", url)

    def store_result(result: dict) -> dict:
        metadata = _metadata(session)
        preview_checks = list(metadata.get("preview_checks") or [])
        preview_checks.append(result)
        metadata["preview_checks"] = preview_checks[-30:]
        if result.get("screenshot_base64"):
            last_screenshots = list(metadata.get("last_preview_screenshots") or [])
            last_screenshots.append({
                "checked_at": result.get("checked_at"),
                "status": result.get("status"),
                "url": result.get("url"),
                "blank_page": result.get("blank_page"),
                "screenshot_base64": result.get("screenshot_base64"),
                "console_error_count": len(result.get("console_errors") or []),
                "network_failure_count": len(result.get("network_failures") or []),
            })
            metadata["last_preview_screenshots"] = last_screenshots[-5:]
        metadata["latest_preview_fix_suggestion"] = result.get("fix_suggestion_prompt") or ""
        _set_metadata(session, metadata)
        db.commit()
        return result

    from .preview_verifier import verify_preview_url

    artifacts_dir = _workspace_runtime_root(session) / ".nexus" / "artifacts" / "preview"
    result = verify_preview_url(url, artifacts_dir)
    for artifact in result.get("artifacts") or []:
        path_value = artifact.get("path")
        if path_value and artifact.get("kind") == "screenshot":
            artifact["url"] = f"/api/v1/code/sessions/{session.id}/preview-artifact?path={quote(str(path_value), safe='')}"
            result["screenshot_url"] = artifact["url"]
        elif path_value and artifact.get("kind") == "html_snapshot":
            artifact["url"] = f"/api/v1/code/sessions/{session.id}/preview-artifact?path={quote(str(path_value), safe='')}"
            result["html_snapshot_url"] = artifact["url"]
    for artifact in result.get("artifacts") or []:
        if job and artifact.get("path"):
            add_job_artifact(
                db,
                job,
                artifact.get("name") or Path(str(artifact["path"])).name,
                str(artifact["path"]),
                artifact.get("kind") or "preview_artifact",
                int(artifact.get("size_bytes") or 0),
                {"url": url, "status": result.get("status")},
            )
    detail = f"{result.get('status_code') or ''} {result.get('content_type') or ''}".strip()
    if result.get("title"):
        detail = f"{detail}\nTitle: {result['title']}"
    if result.get("issues"):
        detail = f"{detail}\nPotential issue markers: {', '.join(result['issues'])}"
    append_activity(
        db,
        session,
        "done" if result.get("status") == "passed" else "error",
        f"Preview check {result.get('status')}",
        detail,
        receipt={
            "summary": f"Preview verification {result.get('status')}",
            "mode": "preview",
            "intent": "Verify",
            "checks": [{
                "label": "Browser preview",
                "status": result.get("status"),
                "detail": ", ".join(result.get("issues") or []) or "No visible/runtime issue detected.",
            }],
            "approval_state": "needs fix" if result.get("status") != "passed" else "verified",
            "next_actions": [
                {"title": "Fix preview issue", "summary": "Use screenshot, console, and network evidence to prepare a focused patch.", "mode": "code"},
                {"title": "Open terminal", "summary": "Run build/test commands in the active project.", "mode": "code"},
                {"title": "Review changes", "summary": "Inspect pending diffs before applying anything.", "mode": "code"},
            ] if result.get("status") != "passed" else [],
        },
    )
    complete_job(db, job, "completed" if result.get("status") == "passed" else "failed", result)
    return store_result(result)


def connect_git_repository(db: Session, session: CodeSession, repo_url: str, default_branch: str = "main") -> dict:
    parsed = urlparse(repo_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        append_activity(db, session, "error", "Repository URL rejected", "Use a full GitHub/GitLab HTTPS URL.")
        raise HTTPException(status_code=400, detail="Use a full repository HTTPS URL.")
    if not default_branch.strip():
        default_branch = "main"
    metadata = _metadata(session)
    git = {
        "repo_url": repo_url.strip(),
        "default_branch": default_branch.strip(),
        "connected_at": _now(),
        "provider": "github" if "github.com" in parsed.netloc.lower() else "git",
    }
    metadata["git"] = git
    _set_metadata(session, metadata)
    db.commit()
    append_activity(db, session, "done", "Repository connected", f"{git['repo_url']} ({git['default_branch']})")
    return git


def git_status(session: CodeSession) -> dict:
    metadata = _metadata(session)
    return {
        "git": metadata.get("git") or {},
        "last_pr_plan": metadata.get("last_pr_plan") or {},
        "preview_checks": metadata.get("preview_checks") or [],
    }


def prepare_pull_request(db: Session, session: CodeSession, title: str | None = None, description: str | None = None, job=None) -> dict:
    metadata = _metadata(session)
    git = metadata.get("git") or {}
    if not git.get("repo_url"):
        append_activity(db, session, "error", "No repository connected", "Connect a repository before preparing a PR.")
        complete_job(db, job, "failed", {"error": "No repository connected"})
        raise HTTPException(status_code=400, detail="Connect a repository before preparing a PR.")

    safe_title = (title or session.title or "Arceus Code changes").strip()
    slug = "".join(char.lower() if char.isalnum() else "-" for char in safe_title).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    branch_name = f"nexus/{slug[:48] or 'workspace-update'}"
    preview = metadata.get("patch_preview") or []
    patch_summary = metadata.get("patch_summary") or "Workspace changes prepared by Arceus Code."
    last_applied = metadata.get("last_applied_files") or []
    changed_files = [item.get("filename") for item in preview if item.get("filename")] or [item.get("filename") for item in last_applied if item.get("filename")]
    recent_checks = metadata.get("preview_checks") or []
    last_check = recent_checks[-1] if recent_checks else None
    body_lines = [
        description.strip() if description else patch_summary,
        "",
        "## Changes",
        *(f"- {filename}" for filename in changed_files),
        "",
        "## Verification",
    ]
    if last_check:
        body_lines.append(f"- Preview check: {last_check.get('status')} ({last_check.get('status_code')}) {last_check.get('url')}")
    else:
        body_lines.append("- Preview check not run yet.")
    body_lines.extend([
        "",
        "## Safety",
        "- Generated in an app-managed Arceus Code workspace.",
        "- Review diffs before applying to a real repository.",
    ])
    pr_plan = {
        "repo_url": git["repo_url"],
        "base_branch": git.get("default_branch") or "main",
        "branch_name": branch_name,
        "commit_message": safe_title,
        "pr_title": safe_title,
        "pr_body": "\n".join(body_lines),
        "changed_files": changed_files,
        "created_at": _now(),
        "status": "prepared",
    }
    metadata["last_pr_plan"] = pr_plan
    _set_metadata(session, metadata)
    db.commit()
    append_activity(db, session, "done", "Pull request plan prepared", f"{branch_name} -> {pr_plan['base_branch']}")
    complete_job(db, job, "completed", pr_plan)
    return pr_plan


def open_github_pull_request(db: Session, user_id: UUID, session: CodeSession, job=None) -> dict:
    metadata = _metadata(session)
    git = metadata.get("git") or {}
    pr_plan = metadata.get("last_pr_plan") or {}
    repo_url = git.get("repo_url")
    if not repo_url:
        complete_job(db, job, "failed", {"error": "No GitHub repository connected"})
        raise HTTPException(status_code=400, detail="Connect or import a GitHub repository first")
    owner, repo = _parse_github_repo(repo_url)
    base_branch = pr_plan.get("base_branch") or git.get("default_branch") or _github_default_branch(owner, repo)
    branch_name = pr_plan.get("branch_name") or f"nexus/{uuid.uuid4().hex[:10]}"
    base_sha = _github_branch_sha(owner, repo, base_branch)
    if not base_sha:
        detail = {
            "error_class": "command_failed",
            "message": "Base branch could not be resolved",
            "cause": f"GitHub did not return a SHA for {base_branch}",
            "branch": base_branch,
        }
        complete_job(db, job, "failed", detail)
        raise HTTPException(status_code=400, detail=detail)
    _github_create_branch(owner, repo, branch_name, base_sha)

    target_filenames = set(pr_plan.get("changed_files") or [])
    files = code_files(db, user_id, session)
    if target_filenames:
        files = [record for record in files if record.filename in target_filenames]
    if not files:
        complete_job(db, job, "failed", {"error": "No files available to commit"})
        raise HTTPException(status_code=400, detail="No files available to commit")

    committed = []
    message = pr_plan.get("commit_message") or session.title or "Arceus Code workspace changes"
    for record in files:
        content = get_file_text(db, user_id, record.id)
        payload = {
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch_name,
        }
        existing_sha = _github_file_sha(owner, repo, record.filename, branch_name)
        if existing_sha:
            payload["sha"] = existing_sha
        result = _github_request("PUT", f"/repos/{owner}/{repo}/contents/{quote(record.filename, safe='/')}", payload)
        committed.append({
            "filename": record.filename,
            "commit_sha": result.get("commit", {}).get("sha"),
            "html_url": result.get("content", {}).get("html_url"),
        })

    pr_payload = {
        "title": pr_plan.get("pr_title") or message,
        "head": branch_name,
        "base": base_branch,
        "body": pr_plan.get("pr_body") or "Prepared by Arceus Code.",
    }
    pull = _github_request("POST", f"/repos/{owner}/{repo}/pulls", pr_payload)
    result = {
        "repo_url": repo_url,
        "branch_name": branch_name,
        "base_branch": base_branch,
        "pull_request_url": pull.get("html_url"),
        "pull_request_number": pull.get("number"),
        "committed": committed,
        "status": "opened",
    }
    metadata["last_opened_pr"] = result
    _set_metadata(session, metadata)
    db.commit()
    append_activity(db, session, "done", "GitHub pull request opened", result.get("pull_request_url") or "")
    complete_job(db, job, "completed", result, files_touched=committed, approval_state="approved")
    return result


def update_session_files(db: Session, user_id: UUID, session: CodeSession, file_ids: list[str]) -> CodeSession:
    valid_ids: list[str] = []
    for value in file_ids:
        try:
            valid_ids.append(str(UUID(str(value))))
        except ValueError:
            continue
    session.file_ids = valid_ids
    refresh_file_tree(db, user_id, session)
    update_project_files_from_session(db, session)
    append_activity(db, session, "read", "Workspace file tree updated", f"{len(valid_ids)} selected file(s)")
    db.refresh(session)
    return session


def build_file_bundle(db: Session, user_id: UUID, files: list[FileReference], max_chars: int = 30000) -> str:
    blocks = []
    remaining = max_chars
    for record in files:
        text = get_file_text(db, user_id, record.id)
        if remaining <= 0:
            break
        clipped = text[:remaining]
        remaining -= len(clipped)
        blocks.append(f"FILE_ID: {record.id}\nFILENAME: {record.filename}\n```\n{clipped}\n```")
    return "\n\n".join(blocks)


def search_workspace_files(db: Session, user_id: UUID, session: CodeSession, query: str, limit: int = 40) -> dict:
    needle = query.strip().lower()
    if not needle:
        return {"query": query, "matches": []}
    tokens = [token for token in re.findall(r"[a-zA-Z0-9_.$/@-]+", needle) if len(token) > 1]
    symbol_patterns = [
        re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"),
        re.compile(r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\("),
        re.compile(r"^\s*class\s+([A-Za-z_$][\w$]*)"),
        re.compile(r"^\s*def\s+([A-Za-z_][\w]*)\s*\("),
        re.compile(r"^\s*class\s+([A-Za-z_][\w]*)\s*[:\(]"),
    ]
    import_patterns = [
        re.compile(r"^\s*import\s+(?:.+?\s+from\s+)?['\"]([^'\"]+)['\"]"),
        re.compile(r"^\s*from\s+([\w.]+)\s+import\s+"),
        re.compile(r"require\(['\"]([^'\"]+)['\"]\)"),
    ]

    def add_match(
        bucket: list[dict],
        seen: set[tuple[str, int, str, str]],
        record: FileReference,
        line: int,
        snippet: str,
        kind: str,
        score: int,
        symbol: str | None = None,
    ) -> None:
        key = (str(record.id), line, kind, symbol or snippet[:80])
        if key in seen:
            return
        seen.add(key)
        bucket.append({
            "file_id": str(record.id),
            "filename": record.filename,
            "line": line,
            "snippet": snippet.strip()[:240],
            "kind": kind,
            "score": score,
            "symbol": symbol,
        })

    matches = []
    seen: set[tuple[str, int, str, str]] = set()
    for record in code_files(db, user_id, session):
        try:
            text = get_file_text(db, user_id, record.id)
        except Exception:
            continue
        filename = record.filename.replace("\\", "/")
        filename_lower = filename.lower()
        basename = Path(filename_lower).name
        if needle in filename_lower or any(token in filename_lower for token in tokens):
            name_score = 95 if needle in basename else 78
            add_match(matches, seen, record, 1, filename, "file", name_score)

        lines = text.splitlines()
        for index, line in enumerate(lines, start=1):
            lowered = line.lower()
            stripped = line.strip()
            symbol_name = None
            for pattern in symbol_patterns:
                symbol_match = pattern.search(line)
                if symbol_match:
                    symbol_name = symbol_match.group(1)
                    if needle in symbol_name.lower() or any(token in symbol_name.lower() for token in tokens):
                        add_match(matches, seen, record, index, stripped, "symbol", 100, symbol_name)
                    break
            for pattern in import_patterns:
                import_match = pattern.search(line)
                if import_match:
                    dependency = import_match.group(1)
                    if needle in dependency.lower() or any(token in dependency.lower() for token in tokens):
                        add_match(matches, seen, record, index, stripped, "dependency", 86, dependency)
                    break
            if "/api/" in filename_lower or filename_lower.startswith("api/") or "routes" in filename_lower:
                if needle in filename_lower or any(token in lowered for token in tokens):
                    add_match(matches, seen, record, index, stripped or filename, "route", 82)
            if needle in lowered:
                score = 72
                if re.search(r"\b(def|class|function|const|export|import|from)\b", lowered):
                    score += 8
                add_match(matches, seen, record, index, stripped, "text", score, symbol_name)
            elif tokens:
                token_hits = sum(1 for token in tokens if token in lowered)
                if token_hits >= max(1, min(2, len(tokens))):
                    add_match(matches, seen, record, index, stripped, "text", 54 + token_hits * 6, symbol_name)
    matches.sort(key=lambda item: (-int(item.get("score") or 0), item.get("filename") or "", int(item.get("line") or 0)))
    matches = matches[:limit]
    append_activity(db, session, "read", "Workspace search complete", f"{len(matches)} match(es) for '{query}'")
    return {
        "query": query,
        "matches": matches,
        "summary": {
            "files": sum(1 for item in matches if item.get("kind") == "file"),
            "symbols": sum(1 for item in matches if item.get("kind") == "symbol"),
            "dependencies": sum(1 for item in matches if item.get("kind") == "dependency"),
            "routes": sum(1 for item in matches if item.get("kind") == "route"),
            "text": sum(1 for item in matches if item.get("kind") == "text"),
        },
    }


WORKSPACE_TASK_STATUSES = {
    "suggested",
    "typed",
    "accepted",
    "running",
    "waiting_approval",
    "done",
    "failed",
    "dismissed",
}


def _workspace_tasks(metadata: dict) -> list[dict]:
    tasks = metadata.get("workspace_tasks") or []
    return [task for task in tasks if isinstance(task, dict)]


def _write_workspace_tasks(db: Session, session: CodeSession, tasks: list[dict]) -> None:
    metadata = _metadata(session)
    metadata["workspace_tasks"] = tasks[-80:]
    _set_metadata(session, metadata)
    db.commit()


def _serialize_workspace_task(task: dict) -> dict:
    return {
        "id": str(task.get("id") or ""),
        "session_id": str(task.get("session_id") or ""),
        "title": task.get("title") or "Workspace task",
        "description": task.get("description") or "",
        "summary": task.get("summary") or task.get("description") or "",
        "mode": task.get("mode") or "code",
        "status": task.get("status") or "suggested",
        "risk": task.get("risk") or "medium",
        "requires_approval": bool(task.get("requires_approval")),
        "files": task.get("files") or [],
        "folders": task.get("folders") or [],
        "steps": task.get("steps") or [],
        "commands": task.get("commands") or [],
        "expected_commands": task.get("expected_commands") or task.get("commands") or [],
        "suggested_prompt": task.get("suggested_prompt") or "",
        "prompt": task.get("suggested_prompt") or task.get("prompt") or "",
        "impact": task.get("impact") or "",
        "file_hint": task.get("file_hint") or "",
        "check_hint": task.get("check_hint") or "",
        "confidence": task.get("confidence"),
        "decision_reason": task.get("decision_reason") or "",
        "tradeoffs": task.get("tradeoffs") or [],
        "thinking_prompt": task.get("thinking_prompt") or "",
        "coach_lens": task.get("coach_lens") or [],
        "alternatives": task.get("alternatives") or [],
        "next_after_done": task.get("next_after_done") or "",
        "metadata": task.get("metadata") or {},
        "created_at": task.get("created_at"),
        "updated_at": task.get("updated_at"),
        "accepted_at": task.get("accepted_at"),
        "completed_at": task.get("completed_at"),
    }


def list_workspace_tasks(db: Session, user_id: UUID, session: CodeSession, include_dismissed: bool = False) -> dict:
    tasks = _workspace_tasks(_metadata(session))
    if not include_dismissed:
        tasks = [task for task in tasks if task.get("status") != "dismissed"]
    return {
        "session_id": str(session.id),
        "tasks": [_serialize_workspace_task(task) for task in reversed(tasks)],
    }


def upsert_workspace_task(
    db: Session,
    user_id: UUID,
    session: CodeSession,
    payload: dict,
    status: str = "typed",
) -> dict:
    if status not in WORKSPACE_TASK_STATUSES:
        raise HTTPException(status_code=400, detail="Unsupported workspace task status")
    metadata = _metadata(session)
    tasks = _workspace_tasks(metadata)
    original_id = str(payload.get("id") or "")
    try:
        task_id = str(UUID(original_id)) if original_id else str(uuid.uuid4())
    except Exception:
        task_id = str(uuid.uuid4())
    now = _now()
    existing_index = next((index for index, task in enumerate(tasks) if str(task.get("id")) == task_id), None)
    task = dict(tasks[existing_index]) if existing_index is not None else {
        "id": task_id,
        "session_id": str(session.id),
        "created_at": now,
    }
    task.update({
        "title": str(payload.get("title") or task.get("title") or "Workspace task")[:255],
        "description": payload.get("description") or payload.get("summary") or task.get("description") or "",
        "summary": payload.get("summary") or task.get("summary") or "",
        "mode": payload.get("mode") or task.get("mode") or "code",
        "status": status,
        "risk": payload.get("risk") or payload.get("risk_level") or task.get("risk") or "medium",
        "requires_approval": bool(payload.get("requires_approval", task.get("requires_approval", False))),
        "files": payload.get("files") or task.get("files") or [],
        "folders": payload.get("folders") or task.get("folders") or [],
        "steps": payload.get("steps") or task.get("steps") or [],
        "commands": payload.get("commands") or payload.get("expected_commands") or task.get("commands") or [],
        "expected_commands": payload.get("expected_commands") or payload.get("commands") or task.get("expected_commands") or [],
        "suggested_prompt": payload.get("suggested_prompt") or payload.get("prompt") or task.get("suggested_prompt") or "",
        "impact": payload.get("impact") or task.get("impact") or "",
        "file_hint": payload.get("file_hint") or payload.get("fileHint") or task.get("file_hint") or "",
        "check_hint": payload.get("check_hint") or payload.get("checkHint") or task.get("check_hint") or "",
        "confidence": payload.get("confidence", task.get("confidence")),
        "decision_reason": payload.get("decision_reason") or payload.get("decisionReason") or task.get("decision_reason") or "",
        "tradeoffs": payload.get("tradeoffs") or task.get("tradeoffs") or [],
        "thinking_prompt": payload.get("thinking_prompt") or payload.get("thinkingPrompt") or task.get("thinking_prompt") or "",
        "coach_lens": payload.get("coach_lens") or payload.get("coachLens") or task.get("coach_lens") or [],
        "alternatives": payload.get("alternatives") or task.get("alternatives") or [],
        "next_after_done": payload.get("next_after_done") or payload.get("nextAfterDone") or task.get("next_after_done") or "",
        "metadata": {
            **(task.get("metadata") or {}),
            **(payload.get("metadata") or {}),
            **({"client_suggestion_id": original_id} if original_id and original_id != task_id else {}),
        },
        "updated_at": now,
    })
    if status == "accepted" and not task.get("accepted_at"):
        task["accepted_at"] = now
    if status in {"done", "failed"} and not task.get("completed_at"):
        task["completed_at"] = now
    if existing_index is None:
        tasks.append(task)
    else:
        tasks[existing_index] = task
    metadata["workspace_tasks"] = tasks[-80:]
    metadata["active_workspace_task_id"] = task_id if status in {"typed", "accepted", "running", "waiting_approval"} else metadata.get("active_workspace_task_id")
    if status in {"done", "failed", "dismissed"} and metadata.get("active_workspace_task_id") == task_id:
        metadata.pop("active_workspace_task_id", None)
    _set_metadata(session, metadata)
    db.commit()
    append_activity(db, session, "code", f"Task {status}: {task['title']}", task.get("summary") or task.get("description") or None)
    return _serialize_workspace_task(task)


def update_workspace_task(
    db: Session,
    user_id: UUID,
    task_id: UUID,
    payload: dict,
) -> dict:
    from services.shared.models import CodeSession as CodeSessionModel

    sessions = db.query(CodeSessionModel).filter(CodeSessionModel.user_id == user_id).all()
    for session in sessions:
        metadata = _metadata(session)
        tasks = _workspace_tasks(metadata)
        for index, task in enumerate(tasks):
            if str(task.get("id")) != str(task_id):
                continue
            next_task = {**task, **{key: value for key, value in payload.items() if value is not None}}
            status = next_task.get("status") or task.get("status") or "suggested"
            if status not in WORKSPACE_TASK_STATUSES:
                raise HTTPException(status_code=400, detail="Unsupported workspace task status")
            next_task["updated_at"] = _now()
            if status == "accepted" and not next_task.get("accepted_at"):
                next_task["accepted_at"] = next_task["updated_at"]
            if status in {"done", "failed"} and not next_task.get("completed_at"):
                next_task["completed_at"] = next_task["updated_at"]
            tasks[index] = next_task
            metadata["workspace_tasks"] = tasks
            if status in {"done", "failed", "dismissed"} and metadata.get("active_workspace_task_id") == str(task_id):
                metadata.pop("active_workspace_task_id", None)
            _set_metadata(session, metadata)
            db.commit()
            return _serialize_workspace_task(next_task)
    raise HTTPException(status_code=404, detail="Workspace task not found")


def set_workspace_task_status(db: Session, user_id: UUID, task_id: UUID, status: str) -> dict:
    return update_workspace_task(db, user_id, task_id, {"status": status})


def _selected_records(db: Session, user_id: UUID, ids: list[str]) -> list[FileReference]:
    if not ids:
        return []
    parsed = []
    for item in ids:
        try:
            parsed.append(UUID(str(item)))
        except Exception:
            continue
    if not parsed:
        return []
    return (
        db.query(FileReference)
        .filter(FileReference.user_id == user_id, FileReference.id.in_(parsed))
        .all()
    )


def _commands_for_suggestion(db: Session, user_id: UUID, session: CodeSession) -> list[str]:
    discovered = discover_workspace_commands(db, user_id, session).get("commands") or []
    preferred = []
    for command in discovered:
        value = command.get("command") if isinstance(command, dict) else ""
        if value and any(name in value for name in ("test", "build", "lint", "typecheck")):
            preferred.append(value)
    return preferred[:3] or ["Run discovered build/test/lint checks"]


def workspace_suggestion_context(
    db: Session,
    user_id: UUID,
    session: CodeSession,
    selected_file_ids: list[str] | None = None,
    open_file_ids: list[str] | None = None,
) -> dict:
    metadata = _metadata(session)
    files = code_files(db, user_id, session)
    selected_records = _selected_records(db, user_id, selected_file_ids or [])
    open_records = _selected_records(db, user_id, open_file_ids or [])
    patch_preview = metadata.get("patch_preview") or []
    preview_checks = metadata.get("preview_checks") or []
    activity_log = metadata.get("activity_log") or []
    failed_preview = next((check for check in reversed(preview_checks) if check.get("status") != "passed"), None)
    from services.shared.models import AgentJob
    jobs = (
        db.query(AgentJob)
        .filter(AgentJob.user_id == user_id, AgentJob.code_session_id == session.id)
        .order_by(AgentJob.created_at.desc())
        .limit(8)
        .all()
    )
    failed_jobs = [
        {"id": str(job.id), "mode": job.mode, "status": job.status, "prompt": job.prompt}
        for job in jobs
        if job.status in {"failed", "timeout", "interrupted"}
    ]
    return {
        "session_id": str(session.id),
        "title": session.title,
        "file_count": len(files),
        "file_tree": _file_tree_for_records(files)[:80],
        "selected_files": _file_tree_for_records(selected_records),
        "open_files": _file_tree_for_records(open_records),
        "recent_activity": activity_log[-8:],
        "failed_jobs": failed_jobs[:5],
        "running_jobs": [
            {"id": str(job.id), "mode": job.mode, "status": job.status, "prompt": job.prompt}
            for job in jobs
            if job.status in {"queued", "running"}
        ][:5],
        "pending_patch": {
            "exists": bool(patch_preview),
            "files": [
                {
                    "file_id": item.get("file_id"),
                    "filename": item.get("filename"),
                    "additions": item.get("additions") or 0,
                    "deletions": item.get("deletions") or 0,
                    "status": item.get("status") or "pending",
                }
                for item in patch_preview
            ],
        },
        "preview_error": failed_preview,
        "github": metadata.get("github") or metadata.get("git") or {},
        "commands": _commands_for_suggestion(db, user_id, session),
        "analysis": metadata.get("workspace_analysis") or {},
        "tasks": [_serialize_workspace_task(task) for task in _workspace_tasks(metadata)[-8:]],
    }


def _compact_task_text(value: str, max_chars: int = 120) -> str:
    normalized = re.sub(r"\s+", " ", value or "").strip()
    return normalized[: max_chars - 3].rstrip() + "..." if len(normalized) > max_chars else normalized


def _infer_suggestion_mode(text: str, selected_mode: str) -> str:
    if selected_mode and selected_mode != "auto":
        return selected_mode
    lowered = text.lower()
    if re.search(r"\b(design|ui|ux|layout|screen|component)\b", lowered):
        return "design"
    if re.search(r"\b(deploy|production|railway|vercel|render|release)\b", lowered):
        return "deploy"
    if re.search(r"\b(research|latest|compare|find|search)\b", lowered):
        return "research"
    if re.search(r"\b(plan|architecture|roadmap|steps)\b", lowered):
        return "plan"
    return "code"


def _coach_lenses(text: str, mode: str) -> list[str]:
    lowered = f"{text} {mode}".lower()
    lenses: list[str] = []
    if re.search(r"\b(auth|login|jwt|token|password|permission|role|privacy|secret)\b", lowered):
        lenses.extend(["security", "maintainability"])
    if re.search(r"\b(scale|architecture|database|api|realtime|queue|payment|cache|microservice)\b", lowered):
        lenses.extend(["architecture", "performance", "cost"])
    if re.search(r"\b(ui|ux|design|screen|layout|mobile|responsive|component)\b", lowered):
        lenses.extend(["user experience", "accessibility"])
    if re.search(r"\b(deploy|production|release|monitor|log|error|preview|build|test)\b", lowered):
        lenses.extend(["reliability", "operability"])
    if not lenses:
        lenses.extend(["architecture", "maintainability"])
    unique: list[str] = []
    for lens in lenses:
        if lens not in unique:
            unique.append(lens)
    return unique[:4]


def _suggestion_payload(
    *,
    session: CodeSession,
    title: str,
    summary: str,
    mode: str,
    risk: str,
    files: list[str],
    folders: list[str],
    steps: list[str],
    commands: list[str],
    requires_approval: bool,
    prompt: str,
    impact: str,
    file_hint: str,
    check_hint: str,
    source: str,
    confidence: float,
    decision_reason: str,
    tradeoffs: list[str],
    thinking_prompt: str,
    coach_lens: list[str],
    alternatives: list[str] | None = None,
    next_after_done: str = "",
) -> dict:
    now = _now()
    return _serialize_workspace_task({
        "id": str(uuid.uuid4()),
        "session_id": str(session.id),
        "title": title,
        "summary": summary,
        "description": summary,
        "mode": mode,
        "status": "suggested",
        "risk": risk,
        "requires_approval": requires_approval,
        "files": files,
        "folders": folders,
        "steps": steps,
        "commands": commands,
        "expected_commands": commands,
        "suggested_prompt": prompt,
        "impact": impact,
        "file_hint": file_hint,
        "check_hint": check_hint,
        "confidence": confidence,
        "decision_reason": decision_reason,
        "tradeoffs": tradeoffs,
        "thinking_prompt": thinking_prompt,
        "coach_lens": coach_lens,
        "alternatives": alternatives or [],
        "next_after_done": next_after_done,
        "metadata": {"source": source},
        "created_at": now,
        "updated_at": now,
    })


def suggest_next_actions(
    db: Session,
    user_id: UUID,
    session: CodeSession,
    user_description: str,
    selected_mode: str = "auto",
    selected_file_ids: list[str] | None = None,
    open_file_ids: list[str] | None = None,
    current_prompt: str = "",
    recent_messages: list[dict] | None = None,
) -> dict:
    description = _compact_task_text(user_description or current_prompt or "the current workspace task", 180)
    context = workspace_suggestion_context(db, user_id, session, selected_file_ids, open_file_ids)
    mode = _infer_suggestion_mode(description, selected_mode)
    selected_files = [item["path"] for item in context["selected_files"]]
    open_files = [item["path"] for item in context["open_files"]]
    target_files = selected_files or open_files
    if not target_files and context["pending_patch"]["files"]:
        target_files = [item["filename"] for item in context["pending_patch"]["files"] if item.get("filename")]
    if not target_files:
        target_files = [item["path"] for item in context["file_tree"][:5]]

    folders = sorted({str(Path(path).parent).replace("\\", "/") for path in target_files if str(Path(path).parent) not in {".", ""}})[:5]
    commands = context["commands"]
    coach_lens = _coach_lenses(description, mode)
    suggestions: list[dict] = []

    if context["file_count"] == 0:
        suggestions.append(_suggestion_payload(
            session=session,
            title="Open or import a project",
            summary="Start by adding repo files so Arceus can inspect real code instead of guessing from the prompt.",
            mode="code",
            risk="low",
            files=[],
            folders=[],
            steps=["Open a local folder, upload a ZIP, or connect GitHub.", "Index the project structure.", "Then ask for the first change."],
            commands=[],
            requires_approval=False,
            prompt="Help me import or open a project for this workspace, then summarize the file structure and recommended first checks.",
            impact="No code changes. Creates useful workspace context first.",
            file_hint="No files are available yet.",
            check_hint="Checks are suggested after import.",
            source="no_files",
            confidence=0.94,
            decision_reason="Without repo files, any code answer would be guesswork. The highest-value move is to establish real project context first.",
            tradeoffs=["Slower than asking for code immediately.", "Prevents wrong architecture and file guesses later."],
            thinking_prompt="What project should Arceus understand before it writes or reviews anything?",
            coach_lens=["project context", "architecture", "maintainability"],
            alternatives=["Paste a small snippet for one-off help.", "Connect GitHub if this is an existing repo."],
            next_after_done="Generate a project roadmap and first safe check command.",
        ))
    if context["pending_patch"]["exists"]:
        files = [item["filename"] for item in context["pending_patch"]["files"] if item.get("filename")]
        suggestions.append(_suggestion_payload(
            session=session,
            title="Review pending changes",
            summary="A patch is already waiting. Review the changed files, line counts, and approval risk before doing more work.",
            mode="code",
            risk="medium",
            files=files,
            folders=folders,
            steps=["Open the pending diff.", "Review additions/deletions by file.", "Approve, reject, or ask Arceus for a smaller patch."],
            commands=commands[:2],
            requires_approval=True,
            prompt="Review the pending patch. Summarize changed files, additions/deletions, risk, and the exact checks I should run before approval.",
            impact="No new patch unless you ask. Focuses on safe review.",
            file_hint=", ".join(files[:4]) or "Pending patch files",
            check_hint=", ".join(commands[:2]) or "Run checks after review.",
            source="pending_patch",
            confidence=0.91,
            decision_reason="Stacking new work on an unreviewed patch increases confusion. Reviewing the pending diff protects the current task boundary.",
            tradeoffs=["Pauses new feature work briefly.", "Reduces accidental unrelated changes and rollback risk."],
            thinking_prompt="Do these changes match the intended task, or should the patch be split smaller?",
            coach_lens=["maintainability", "reliability"],
            alternatives=["Reject the patch and regenerate smaller.", "Approve first, then continue with a new task."],
            next_after_done="Run checks or continue with the next milestone.",
        ))
    if context["failed_jobs"]:
        failed = context["failed_jobs"][0]
        suggestions.append(_suggestion_payload(
            session=session,
            title="Fix the failed job",
            summary="Use the latest failed job and workspace diagnostics to create a focused recovery plan.",
            mode="code",
            risk="medium",
            files=target_files,
            folders=folders,
            steps=["Read the failed job output.", "Find files connected to the failure.", "Prepare a small fix and rerun checks."],
            commands=commands[:3],
            requires_approval=True,
            prompt=f"Fix the latest failed workspace job: {failed.get('prompt') or description}. Inspect only relevant files, explain root cause, prepare a small patch, and recommend checks.",
            impact="Creates a reviewable fix for a known failure.",
            file_hint=", ".join(target_files[:4]) or "Relevant files from failure context.",
            check_hint=", ".join(commands[:3]) or "Rerun the failed command.",
            source="failed_job",
            confidence=0.88,
            decision_reason="A known failure is stronger evidence than a fresh guess. Fixing it first improves the workspace baseline.",
            tradeoffs=["May delay the original feature.", "Usually saves time because future patches start from a healthier build."],
            thinking_prompt="What changed right before this failure, and can the fix be isolated to that area?",
            coach_lens=["reliability", "debugging", "maintainability"],
            alternatives=["Open logs only and decide manually.", "Rollback the latest applied patch if the failure came from it."],
            next_after_done="Rerun the failed check and summarize root cause.",
        ))
    if context.get("preview_error"):
        suggestions.append(_suggestion_payload(
            session=session,
            title="Fix preview issue",
            summary="Use the latest preview evidence, console/network errors, and source files to repair the visible UI/runtime issue.",
            mode="code",
            risk="medium",
            files=target_files,
            folders=folders,
            steps=["Read preview errors.", "Map error to source files.", "Patch the smallest UI/runtime fix.", "Recheck preview."],
            commands=commands[:2],
            requires_approval=True,
            prompt=f"Fix the latest preview issue for: {description}. Use console/network evidence first, then patch the smallest relevant files and summarize visual impact.",
            impact="Creates a reviewable patch for the preview failure.",
            file_hint=", ".join(target_files[:4]) or "Preview-related source files.",
            check_hint="Run preview check after patch.",
            source="preview_error",
            confidence=0.86,
            decision_reason="Preview evidence tells us what the user actually sees. That makes this more actionable than a broad refactor.",
            tradeoffs=["Focuses on the visible/runtime issue, not every underlying design concern.", "May require another pass after the first visual fix."],
            thinking_prompt="Is this a source-code bug, a missing asset, or a runtime/config problem?",
            coach_lens=["user experience", "reliability", "debugging"],
            alternatives=["Inspect screenshot and logs without patching.", "Run build checks before fixing UI."],
            next_after_done="Recheck the preview and inspect remaining console/network errors.",
        ))
    github = context.get("github") or {}
    github_connected = bool(github.get("repo_url") or github.get("selected_repo") or github.get("repo_full_name"))
    if github_connected and context["pending_patch"]["exists"]:
        suggestions.append(_suggestion_payload(
            session=session,
            title="Prepare GitHub PR",
            summary="Package the approved workspace change into a branch and pull request instead of leaving it as a local patch.",
            mode="deploy",
            risk="medium",
            files=[item["filename"] for item in context["pending_patch"]["files"] if item.get("filename")],
            folders=folders,
            steps=["Review or approve the pending patch.", "Create or confirm a working branch.", "Commit approved files.", "Open the PR and check status."],
            commands=[],
            requires_approval=True,
            prompt="Prepare this pending change for GitHub PR. Summarize changed files, branch name, PR title/body, and checks to confirm before opening.",
            impact="No force push. PR actions stay approval-gated.",
            file_hint="Pending changed files.",
            check_hint="Run checks before PR when available.",
            source="github_pr",
            confidence=0.82,
            decision_reason="GitHub is connected and a patch exists, so the next professional step is review, branch, commit, and PR.",
            tradeoffs=["Adds Git workflow overhead.", "Creates a clean review trail for the work."],
            thinking_prompt="Is this patch complete enough to become a reviewable PR?",
            coach_lens=["collaboration", "release safety", "maintainability"],
            alternatives=["Run checks first.", "Split the patch before opening a PR."],
            next_after_done="Watch PR checks and fix failures.",
        ))
    if not github_connected and context["file_count"] > 0:
        suggestions.append(_suggestion_payload(
            session=session,
            title="Connect GitHub",
            summary="Connect a repository so Arceus can turn approved changes into branches, commits, and pull requests.",
            mode="deploy",
            risk="low",
            files=[],
            folders=[],
            steps=["Open the Git panel.", "Install or connect GitHub.", "Choose a repo.", "Import or map files."],
            commands=[],
            requires_approval=False,
            prompt="Help me connect this workspace to GitHub, choose the correct repository, and prepare the safest branch/PR workflow.",
            impact="No code changes. Enables professional source-control flow.",
            file_hint="Current workspace files remain unchanged.",
            check_hint="GitHub connection required before PR automation.",
            source="github_connect",
            confidence=0.76,
            decision_reason="The workspace has files but no connected repo, so GitHub is the missing path from local work to reviewable delivery.",
            tradeoffs=["Requires one-time setup.", "Unlocks branch, commit, PR, and check status workflows."],
            thinking_prompt="Which repo should own this workspace and who needs to review changes?",
            coach_lens=["collaboration", "delivery"],
            alternatives=["Keep working locally.", "Export a ZIP instead of connecting GitHub."],
            next_after_done="Import repo files or prepare the first PR branch.",
        ))

    base_files = target_files[:6]
    suggestions.extend([
        _suggestion_payload(
            session=session,
            title="Plan with exact files",
            summary="Turn the request into a concise task plan with exact files/folders, steps, commands, and approval risk.",
            mode="plan",
            risk="low",
            files=base_files,
            folders=folders,
            steps=["Inspect workspace context.", "List impacted files/folders.", "Define three execution steps.", "Name checks before editing."],
            commands=commands[:3],
            requires_approval=False,
            prompt=f"Create a concise implementation plan for: {description}\n\nUse current workspace context. Return exact files/folders, three steps, expected commands, risk, and approval requirement. Do not edit files yet.",
            impact="No code changes. Best when the task is broad or unclear.",
            file_hint=", ".join(base_files[:4]) or "Inspect project file tree first.",
            check_hint=", ".join(commands[:3]) or "Recommend checks from project scripts.",
            source="general_plan",
            confidence=0.84,
            decision_reason="The request has enough ambiguity that planning first will reduce rework and produce clearer task boundaries.",
            tradeoffs=["No immediate code output.", "Creates a sharper implementation path with fewer blind edits."],
            thinking_prompt="What should be true when this task is complete, and what files prove it?",
            coach_lens=coach_lens,
            alternatives=["Implement a small patch immediately.", "Verify current state before planning."],
            next_after_done="Pick one planned step and convert it into a reviewed patch.",
        ),
        _suggestion_payload(
            session=session,
            title="Implement reviewed patch",
            summary="Make the smallest useful change, then report files created/modified and line impact before approval.",
            mode=mode if mode in {"code", "design", "deploy", "research"} else "code",
            risk="medium",
            files=base_files,
            folders=folders,
            steps=["Inspect relevant files.", "Prepare minimal patch.", "Compute changed lines.", "Show diff for approval."],
            commands=commands[:3],
            requires_approval=True,
            prompt=f"Implement this as a reviewed patch: {description}\n\nUse exact workspace files only. Report files inspected, files created/modified/deleted, folders created, additions/deletions, and checks to run. Do not apply without approval.",
            impact="Creates a pending patch; user approval is required before applying.",
            file_hint=", ".join(base_files[:4]) or "Relevant files selected by workspace analysis.",
            check_hint=", ".join(commands[:3]) or "Run build/test/lint if available.",
            source="general_patch",
            confidence=0.78,
            decision_reason="There is enough workspace context to attempt a narrow implementation while keeping approval and diff review in place.",
            tradeoffs=["Faster than planning, but may miss broader architecture questions.", "Approval gate keeps the edit reversible."],
            thinking_prompt="What is the smallest useful change that proves progress without touching unrelated files?",
            coach_lens=coach_lens,
            alternatives=["Plan first if the goal is broad.", "Verify current errors before changing code."],
            next_after_done="Review the diff, then run the most relevant check.",
        ),
        _suggestion_payload(
            session=session,
            title="Verify and suggest next fix",
            summary="Check build quality, pending changes, preview state, and propose the next highest-impact fix.",
            mode="code",
            risk="low",
            files=base_files,
            folders=folders,
            steps=["Review recent activity.", "Check pending/failed states.", "Recommend one next fix.", "List commands to verify."],
            commands=commands[:3],
            requires_approval=False,
            prompt=f"Verify the current workspace state for: {description}\n\nSummarize pending changes, failed jobs, preview problems, risky files, and the next best fix. Do not create a patch unless I ask.",
            impact="No direct code changes. Reduces blind execution.",
            file_hint=", ".join(base_files[:4]) or "Uses current workspace state.",
            check_hint=", ".join(commands[:3]) or "Suggest available checks.",
            source="general_verify",
            confidence=0.8,
            decision_reason="A verification pass turns the workspace state into evidence: pending changes, failed jobs, risky files, and next best fix.",
            tradeoffs=["Does not build new features directly.", "Improves confidence before committing more work."],
            thinking_prompt="What signal would prove this workspace is ready for the next task?",
            coach_lens=["reliability", "maintainability", *coach_lens[:2]],
            alternatives=["Run a specific build/test command.", "Review pending changes first if a patch exists."],
            next_after_done="Use the verification result to choose fix, test, or PR.",
        ),
    ])

    unique: list[dict] = []
    seen_titles: set[str] = set()
    for suggestion in suggestions:
        title = suggestion["title"]
        if title in seen_titles:
            continue
        seen_titles.add(title)
        unique.append(suggestion)
        if len(unique) == 3:
            break

    return {
        "session_id": str(session.id),
        "context": {
            "file_count": context["file_count"],
            "selected_files": context["selected_files"],
            "open_files": context["open_files"],
            "pending_patch": context["pending_patch"],
            "failed_jobs": context["failed_jobs"],
            "preview_error": context["preview_error"],
            "commands": context["commands"],
        },
        "suggestions": unique,
    }


def analyze_workspace_structure(db: Session, user_id: UUID, session: CodeSession) -> dict:
    files = code_files(db, user_id, session)
    language_counts: dict[str, int] = {}
    imports: list[dict] = []
    exports: list[dict] = []
    routes: list[dict] = []
    components: list[dict] = []
    hotspots: list[dict] = []
    symbols: list[dict] = []
    dependencies: dict[str, list[str]] = {}
    entrypoints: list[dict] = []
    risk_files: list[dict] = []
    total_lines = 0
    total_bytes = 0

    import_patterns = [
        re.compile(r"^\s*import\s+(?:.+?\s+from\s+)?['\"]([^'\"]+)['\"]"),
        re.compile(r"^\s*from\s+([\w.]+)\s+import\s+"),
        re.compile(r"require\(['\"]([^'\"]+)['\"]\)"),
    ]
    export_pattern = re.compile(r"^\s*export\s+(?:default\s+)?(?:function|const|class)\s+([A-Za-z0-9_]+)?")
    component_pattern = re.compile(r"(?:function|const)\s+([A-Z][A-Za-z0-9_]*)")
    function_patterns = [
        re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][\w$]*)"),
        re.compile(r"^\s*(?:export\s+)?const\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\("),
        re.compile(r"^\s*class\s+([A-Za-z_$][\w$]*)"),
        re.compile(r"^\s*def\s+([A-Za-z_][\w]*)\s*\("),
        re.compile(r"^\s*class\s+([A-Za-z_][\w]*)\s*[:\(]"),
    ]
    entry_names = {
        "main.py", "app.py", "server.py", "index.js", "index.ts", "index.tsx", "main.tsx", "main.ts",
        "app.tsx", "page.tsx", "layout.tsx", "package.json", "dockerfile", "Dockerfile",
    }

    for record in files:
        filename = record.filename.replace("\\", "/")
        suffix = Path(filename).suffix.lower() or Path(filename).name.lower()
        language = suffix.lstrip(".") or "text"
        language_counts[language] = language_counts.get(language, 0) + 1
        total_bytes += int(record.size_bytes or 0)
        try:
            text = get_file_text(db, user_id, record.id)
        except Exception:
            continue
        lines = text.splitlines()
        total_lines += len(lines)
        file_imports: list[str] = []
        file_hotspots = 0
        file_symbols: list[str] = []

        path_name = Path(filename).name
        if path_name in entry_names or filename.startswith(("src/main", "src/index", "app/page", "pages/index")):
            entrypoints.append({"filename": filename, "kind": "entrypoint"})

        if any(segment in filename for segment in ["/app/", "/pages/", "/routes/", "/api/"]) or filename.startswith(("app/", "pages/", "routes/", "api/")):
            if suffix in {".tsx", ".ts", ".jsx", ".js", ".py"}:
                routes.append({"filename": filename, "kind": "route_or_page"})

        for index, line in enumerate(lines, start=1):
            if len(imports) < 200:
                for pattern in import_patterns:
                    match = pattern.search(line)
                    if match:
                        module = match.group(1)[:160]
                        imports.append({"filename": filename, "line": index, "module": module})
                        file_imports.append(module)
                        break
            if len(exports) < 120:
                match = export_pattern.search(line)
                if match:
                    exports.append({"filename": filename, "line": index, "symbol": match.group(1) or "default"})
            if len(components) < 120 and suffix in {".tsx", ".jsx"}:
                match = component_pattern.search(line)
                if match:
                    components.append({"filename": filename, "line": index, "name": match.group(1)})
            if len(symbols) < 240:
                for pattern in function_patterns:
                    match = pattern.search(line)
                    if match:
                        name = match.group(1)
                        kind = "class" if line.lstrip().startswith("class ") or " class " in line else "function"
                        symbols.append({"filename": filename, "line": index, "name": name, "kind": kind})
                        file_symbols.append(name)
                        break
            lowered = line.lower()
            if any(marker in lowered for marker in ["todo", "fixme", "hack", "any", "dangerouslysetinnerhtml", "eval(", "innerhtml", "password", "secret", "api_key"]):
                hotspots.append({"filename": filename, "line": index, "snippet": line.strip()[:220]})
                file_hotspots += 1

        if file_imports:
            dependencies[filename] = sorted(set(file_imports))[:40]
        if file_hotspots or len(lines) > 500:
            risk_files.append({
                "filename": filename,
                "hotspots": file_hotspots,
                "lines": len(lines),
                "symbols": file_symbols[:12],
                "reason": "hotspots" if file_hotspots else "large_file",
            })

    analysis = {
        "summary": {
            "files": len(files),
            "total_lines": total_lines,
            "total_bytes": total_bytes,
            "languages": language_counts,
        },
        "imports": imports[:80],
        "exports": exports[:60],
        "routes": routes[:80],
        "components": components[:80],
        "symbols": symbols[:160],
        "dependencies": dict(list(dependencies.items())[:120]),
        "entrypoints": entrypoints[:80],
        "hotspots": hotspots[:80],
        "risk_files": sorted(risk_files, key=lambda item: (item["hotspots"], item["lines"]), reverse=True)[:40],
        "analyzed_at": _now(),
    }
    metadata = _metadata(session)
    metadata["workspace_analysis"] = analysis
    _set_metadata(session, metadata)
    db.commit()
    append_activity(db, session, "read", "Workspace analysis complete", f"{len(files)} file(s), {total_lines} line(s), {len(imports)} import signal(s), {len(symbols)} symbol(s).")
    return analysis


def _build_diagnostics_context(session: CodeSession) -> str:
    metadata = _metadata(session)
    check_run = metadata.get("last_check_run")
    if not check_run:
        return ""
    diagnostics = f"\n\nActive Sandbox Diagnostics (Last build/test/lint run):\nStatus: {check_run.get('status')}\nPassed: {check_run.get('passed')}/{check_run.get('total')}\nCommands Output:\n"
    for cmd_res in check_run.get("commands") or []:
        diagnostics += f"- Command: {cmd_res.get('command')}\n  Status: {cmd_res.get('status')}\n  Output:\n{cmd_res.get('output')[:1500]}\n"
    return diagnostics


def generate_plan(
    db: Session,
    user_id: UUID,
    session: CodeSession,
    instruction: str,
    provider: str | None,
    model: str | None,
    job=None,
    finalize_job: bool = True,
    file_ids: list[str] | None = None,
) -> str:
    context_files = code_files(db, user_id, session, file_ids)
    bundle = build_file_bundle(db, user_id, context_files)
    metadata = _metadata(session)
    analysis = metadata.get("workspace_analysis") or {}
    diagnostics = _build_diagnostics_context(session)
    append_activity(db, session, "code", "Planning code changes", instruction[:180])
    append_job_log(db, job, "code", "Planning code changes", instruction[:180])
    llm = get_chat_llm(role="planning", provider=provider, model=model)
    response = llm.invoke([
        SystemMessage(content="You are Autonomus AI in coding workspace mode. Produce a concise implementation plan grounded in the provided files."),
        HumanMessage(content=f"Instruction:\n{instruction}{diagnostics}\n\nWorkspace analysis:\n{json.dumps(analysis, indent=2)[:12000]}\n\nWorkspace files:\n{bundle}"),
    ])
    session.plan_text = str(response.content)
    metadata = _metadata(session)
    metadata["last_instruction"] = instruction
    metadata["last_context_file_ids"] = [str(record.id) for record in context_files]
    metadata["last_context_files"] = [record.filename for record in context_files]
    _set_metadata(session, metadata)
    db.commit()
    append_activity(db, session, "done", "Implementation plan stored", (session.plan_text or "")[:220])
    if finalize_job:
        complete_job(db, job, "completed", {"plan": session.plan_text or ""})
    return session.plan_text or ""


def generate_patch(
    db: Session,
    user_id: UUID,
    session: CodeSession,
    instruction: str,
    provider: str | None,
    model: str | None,
    job=None,
    finalize_job: bool = True,
    file_ids: list[str] | None = None,
) -> str:
    files = code_files(db, user_id, session, file_ids)
    bundle = build_file_bundle(db, user_id, files)
    diagnostics = _build_diagnostics_context(session)
    append_activity(db, session, "edit", "Generating reviewable patch", "The patch will remain pending until approved.")
    append_job_log(db, job, "edit", "Generating reviewable patch", "Patch remains pending until user approval.")
    llm = get_chat_llm(role="reasoning", provider=provider, model=model)
    response = llm.invoke([
        SystemMessage(content=(
            "You are Autonomus AI in coding workspace mode. Return ONLY JSON. Prefer this shape: "
            "{\"operations\":["
            "{\"type\":\"modify\",\"file_id\":\"...\",\"filename\":\"...\",\"content\":\"full updated file content\"},"
            "{\"type\":\"create\",\"filename\":\"path/new-file.ts\",\"content\":\"new file content\"},"
            "{\"type\":\"delete\",\"file_id\":\"...\",\"filename\":\"path/file.ts\"},"
            "{\"type\":\"rename\",\"file_id\":\"...\",\"filename\":\"old.ts\",\"new_filename\":\"new.ts\",\"content\":\"optional updated content\"},"
            "{\"type\":\"folder\",\"filename\":\"path/new-folder\"}"
            "],\"summary\":\"...\",\"checks\":[\"npm run build\"]}. "
            "Use full replacement content for modify/create/rename so the app can review and rollback safely. "
            "For backwards compatibility, {\"files\":[...]} is also accepted, but operations are preferred."
        )),
        HumanMessage(content=f"Instruction:\n{instruction}{diagnostics}\n\nCurrent plan:\n{session.plan_text or ''}\n\nWorkspace files:\n{bundle}"),
    ])
    raw = str(response.content)
    session.patch_text = raw
    metadata = _metadata(session)
    metadata["last_context_file_ids"] = [str(record.id) for record in files]
    metadata["last_context_files"] = [record.filename for record in files]
    _set_metadata(session, metadata)
    db.commit()
    preview = preview_patch_payload(db, user_id, session)
    append_activity(db, session, "edit", "Patch ready for review", f"{len(preview)} file diff(s) prepared")
    if finalize_job:
        complete_job(
            db,
            job,
            "completed",
            {"patch_preview": preview, "summary": (_metadata(session).get("patch_summary") or "")},
            files_touched=[{"file_id": item["file_id"], "filename": item["filename"]} for item in preview],
            approval_state="pending",
        )
    return raw


def _parse_patch_payload(patch_text: str) -> dict:
    try:
        return json.loads(patch_text)
    except Exception:
        start = patch_text.find("{")
        end = patch_text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(patch_text[start:end + 1])
    raise HTTPException(status_code=400, detail="Patch is not valid replacement JSON")


def _safe_patch_filename(value: str) -> str:
    filename = str(value or "").replace("\\", "/").lstrip("/")
    if not filename or filename.startswith("../") or "/../" in f"/{filename}/":
        raise HTTPException(status_code=400, detail=f"Unsafe patch filename: {value}")
    return filename[:500]


def _normalize_patch_operations(payload: dict) -> list[dict]:
    operations: list[dict] = []
    if isinstance(payload.get("operations"), list):
        for index, raw in enumerate(payload.get("operations") or []):
            if not isinstance(raw, dict):
                continue
            op_type = str(raw.get("type") or raw.get("operation") or "modify").lower().strip()
            if op_type in {"mkdir", "directory"}:
                op_type = "folder"
            if op_type not in {"create", "modify", "delete", "rename", "folder"}:
                raise HTTPException(status_code=400, detail=f"Unsupported patch operation: {op_type}")
            operation = dict(raw)
            operation["type"] = op_type
            operation["operation_id"] = str(raw.get("operation_id") or raw.get("id") or f"op-{index}")
            if operation.get("filename"):
                operation["filename"] = _safe_patch_filename(operation["filename"])
            if operation.get("new_filename"):
                operation["new_filename"] = _safe_patch_filename(operation["new_filename"])
            operations.append(operation)

    for index, raw in enumerate(payload.get("files") or []):
        if not isinstance(raw, dict):
            continue
        operation = dict(raw)
        operation["type"] = "modify"
        operation["operation_id"] = str(raw.get("operation_id") or raw.get("id") or f"file-{index}")
        if operation.get("filename"):
            operation["filename"] = _safe_patch_filename(operation["filename"])
        operations.append(operation)
    return operations


def _record_by_operation(db: Session, user_id: UUID, operation: dict) -> FileReference | None:
    file_id = operation.get("file_id")
    if file_id:
        try:
            record = (
                db.query(FileReference)
                .filter(FileReference.id == UUID(str(file_id)), FileReference.user_id == user_id)
                .first()
            )
            if record:
                return record
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid file_id in patch operation: {file_id}")
    filename = operation.get("filename")
    if filename:
        return (
            db.query(FileReference)
            .filter(
                FileReference.user_id == user_id,
                FileReference.owner_type == "code_workspace",
                FileReference.owner_id == operation.get("owner_id"),
                FileReference.filename == filename,
                FileReference.status == "active",
            )
            .first()
        )
    return None


def _patch_impact_from_diff(diff: str) -> dict:
    return {
        "additions": sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")),
        "deletions": sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")),
    }


def _patch_impact_summary(changed: list[dict], folders_created: list[str] | None = None) -> dict:
    folders = folders_created or []
    changed_files = []
    for item in changed:
        diff_impact = _patch_impact_from_diff(item.get("diff") or "")
        changed_files.append({
            "operation_id": item.get("operation_id") or "",
            "operation": item.get("operation") or "modify",
            "file_id": item.get("file_id") or "",
            "filename": item.get("new_filename") or item.get("filename") or "",
            "previous_filename": item.get("filename") if item.get("new_filename") else "",
            "additions": int(item.get("additions") or diff_impact.get("additions") or 0),
            "deletions": int(item.get("deletions") or diff_impact.get("deletions") or 0),
        })
    return {
        "changed_files": changed_files,
        "created_files": [item["filename"] for item in changed_files if item.get("operation") == "create"],
        "modified_files": [item["filename"] for item in changed_files if item.get("operation") == "modify"],
        "deleted_files": [item.get("previous_filename") or item["filename"] for item in changed_files if item.get("operation") == "delete"],
        "renamed_files": [
            {"from": item.get("previous_filename"), "to": item.get("filename")}
            for item in changed_files
            if item.get("operation") == "rename"
        ],
        "folders_created": folders,
        "total_additions": sum(item.get("additions", 0) for item in changed_files),
        "total_deletions": sum(item.get("deletions", 0) for item in changed_files),
    }


def build_work_receipt(
    session: CodeSession,
    summary: str,
    mode: str = "code",
    intent: str = "Build",
    plan: str | None = None,
    preview: list[dict] | None = None,
    commands: list[dict] | None = None,
    checks: list[dict] | None = None,
    next_actions: list[dict] | None = None,
    approval_state: str = "done",
) -> dict:
    metadata = _metadata(session)
    changed = preview if preview is not None else metadata.get("patch_preview") or []
    action_source = next_actions if next_actions is not None else [
        _serialize_workspace_task(task)
        for task in reversed(_workspace_tasks(metadata))
        if task.get("status") not in {"dismissed", "done", "failed"}
    ][:3]
    inspected = list(metadata.get("last_context_files") or [])
    if not inspected:
        inspected = [
            item.get("filename") or item.get("path")
            for item in (metadata.get("file_tree") or [])
            if item.get("filename") or item.get("path")
        ][:12]
    files_changed = [
        {
            "filename": item.get("new_filename") or item.get("filename") or "workspace file",
            "operation": item.get("operation") or item.get("type") or "modify",
            "additions": int(item.get("additions") or _patch_impact_from_diff(item.get("diff") or "").get("additions") or 0),
            "deletions": int(item.get("deletions") or _patch_impact_from_diff(item.get("diff") or "").get("deletions") or 0),
        }
        for item in changed
    ]
    receipt_checks = checks or [{"label": "Review patch before apply", "status": "pending approval"}] if approval_state == "waiting approval" else checks or []
    checks_passed = len([item for item in receipt_checks if re.search(r"pass|success|done|completed", str(item.get("status") or ""), re.I)])
    checks_failed = len([item for item in receipt_checks if re.search(r"fail|error|blocked|timeout", str(item.get("status") or ""), re.I)])
    return {
        "summary": summary,
        "mode": mode,
        "intent": intent,
        "project": session.project.name if session.project else "Workspace",
        "session": str(session.id)[:8],
        "sandbox_provider": settings.SANDBOX_PROVIDER.lower(),
        "plan": plan if plan is not None else session.plan_text or "",
        "files_inspected": inspected,
        "files_changed": files_changed,
        "folders_created": [
            item.get("filename")
            for item in changed
            if (item.get("operation") or item.get("type")) == "folder" and item.get("filename")
        ],
        "commands_run": commands or [],
        "checks": receipt_checks,
        "checks_passed": checks_passed,
        "checks_failed": checks_failed,
        "approval_state": approval_state,
        "rollback_available": bool(metadata.get("rollback_snapshots")) or approval_state in {"approved", "restored"},
        "line_impact": {
            "additions": sum(item.get("additions", 0) for item in files_changed),
            "deletions": sum(item.get("deletions", 0) for item in files_changed),
        },
        "next_actions": action_source[:3],
    }


def parse_diff_to_hunks(old_text: str, new_text: str) -> list[dict]:
    import difflib
    diff = list(difflib.unified_diff(
        old_text.splitlines(),
        new_text.splitlines(),
        lineterm=""
    ))

    hunks = []
    current_hunk = None
    hunk_idx = 0

    for line in diff:
        if line.startswith("---") or line.startswith("+++"):
            continue
        if line.startswith("@@"):
            match = re.match(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@", line)
            if match:
                old_start = int(match.group(1))
                old_len = int(match.group(2)) if match.group(2) else 1
                new_start = int(match.group(3))
                new_len = int(match.group(4)) if match.group(4) else 1

                if current_hunk:
                    hunks.append(current_hunk)

                current_hunk = {
                    "index": hunk_idx,
                    "old_start": old_start,
                    "old_len": old_len,
                    "new_start": new_start,
                    "new_len": new_len,
                    "header": line,
                    "lines": [],
                    "old_lines": [],
                    "new_lines": [],
                    "status": "pending",
                }
                hunk_idx += 1
            continue

        if current_hunk is not None:
            current_hunk["lines"].append(line)
            if line.startswith("-"):
                current_hunk["old_lines"].append(line[1:])
            elif line.startswith("+"):
                current_hunk["new_lines"].append(line[1:])
            else:
                current_hunk["old_lines"].append(line[1:])
                current_hunk["new_lines"].append(line[1:])

    if current_hunk:
        hunks.append(current_hunk)

    return hunks


def apply_hunks_to_file(old_text: str, hunks: list[dict]) -> str:
    lines = old_text.splitlines()
    sorted_hunks = sorted(hunks, key=lambda h: h["old_start"])

    offset = 0
    for hunk in sorted_hunks:
        if hunk.get("status") == "rejected":
            continue

        start_idx = hunk["old_start"] + offset - 1
        end_idx = start_idx + hunk["old_len"]

        lines[start_idx:end_idx] = hunk["new_lines"]

        shift = len(hunk["new_lines"]) - hunk["old_len"]
        offset += shift

    return "\n".join(lines)


def preview_patch_payload(db: Session, user_id: UUID, session: CodeSession) -> list[dict]:
    if not session.patch_text:
        return []
    payload = _parse_patch_payload(session.patch_text)
    metadata = _metadata(session)
    hunks_state = metadata.get("patch_hunks_state") or {}
    previous_preview = {
        str(item.get("operation_id") or item.get("file_id") or item.get("filename") or ""): item
        for item in (metadata.get("patch_preview") or [])
    }
    previews = []
    operations = _normalize_patch_operations(payload)
    for item in operations:
        op_type = item.get("type") or "modify"
        record: FileReference | None = None
        file_id_value = item.get("file_id")
        if file_id_value:
            record = db.query(FileReference).filter(FileReference.id == UUID(str(file_id_value)), FileReference.user_id == user_id).first()
        filename = item.get("filename") or (record.filename if record else "")
        new_filename = item.get("new_filename") or filename
        previous = previous_preview.get(str(item.get("operation_id") or item.get("file_id") or filename or ""))
        base_checksum = previous.get("base_checksum") if previous else None
        current_checksum = record.checksum_sha256 if record else ""

        if op_type in {"modify", "delete", "rename"} and not record:
            continue
        if op_type == "folder":
            previews.append({
                "operation_id": item["operation_id"],
                "operation": "folder",
                "file_id": "",
                "filename": _safe_patch_filename(filename),
                "new_filename": "",
                "diff": "",
                "additions": 0,
                "deletions": 0,
                "hunks": [],
                "status": "pending",
                "base_checksum": "",
                "current_checksum": "",
                "conflict": False,
            })
            continue

        old_text = get_file_text(db, user_id, record.id) if record and op_type != "create" else ""
        if not base_checksum and record:
            base_checksum = record.checksum_sha256
        if op_type == "delete":
            new_text = ""
        else:
            new_text = str(item.get("content") or (old_text if op_type == "rename" else ""))
        fromfile = f"a/{filename}"
        tofile = f"b/{new_filename}"
        diff = "\n".join(difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=fromfile,
            tofile=tofile,
            lineterm="",
        ))

        # Parse hunks and assign status
        hunks = parse_diff_to_hunks(old_text, new_text)
        for hunk in hunks:
            hunk_id = f"{item['operation_id']}-{record.id if record else 'new'}-{hunk['index']}"
            hunk["id"] = hunk_id
            if hunk_id in hunks_state:
                hunk["status"] = hunks_state[hunk_id]

        impact = _patch_impact_from_diff(diff)
        previews.append({
            "operation_id": item["operation_id"],
            "operation": op_type,
            "file_id": str(record.id) if record else "",
            "filename": filename,
            "new_filename": new_filename if new_filename != filename else "",
            "diff": diff,
            "additions": impact["additions"],
            "deletions": impact["deletions"],
            "hunks": hunks,
            "status": "pending",
            "base_checksum": base_checksum or "",
            "current_checksum": current_checksum or "",
            "conflict": bool(base_checksum and current_checksum and base_checksum != current_checksum),
        })
    metadata["patch_preview"] = previews
    metadata["patch_summary"] = payload.get("summary") or ""
    metadata["patch_checks"] = payload.get("checks") or []
    _set_metadata(session, metadata)
    db.commit()
    return previews


def check_patch_conflicts(db: Session, user_id: UUID, session: CodeSession) -> dict:
    previews = preview_patch_payload(db, user_id, session)
    conflicts = [
        {
            "operation_id": item.get("operation_id") or "",
            "file_id": item.get("file_id") or "",
            "filename": item.get("new_filename") or item.get("filename") or "",
            "operation": item.get("operation") or "modify",
            "base_checksum": item.get("base_checksum") or "",
            "current_checksum": item.get("current_checksum") or "",
        }
        for item in previews
        if item.get("conflict")
    ]
    return {
        "status": "conflicts" if conflicts else "clean",
        "conflicts": conflicts,
        "count": len(conflicts),
        "patch_preview": previews,
    }


def _selected_file_id_set(file_ids: list[str] | None) -> set[str]:
    selected: set[str] = set()
    for value in file_ids or []:
        try:
            selected.add(str(UUID(str(value))))
        except ValueError:
            continue
    return selected


def _selected_operation_id_set(operation_ids: list[str] | None) -> set[str]:
    return {str(value) for value in (operation_ids or []) if str(value).strip()}


def _selected_hunk_id_set(hunk_ids: list[str] | None) -> set[str]:
    return {str(value) for value in (hunk_ids or []) if str(value).strip()}


def reject_patch_payload(db: Session, session: CodeSession, file_ids: list[str] | None = None, operation_ids: list[str] | None = None) -> dict:
    metadata = _metadata(session)
    selected = _selected_file_id_set(file_ids)
    selected_ops = _selected_operation_id_set(operation_ids)
    rejected = []
    if (selected or selected_ops) and session.patch_text:
        payload = _parse_patch_payload(session.patch_text)
        if payload.get("operations"):
            remaining_ops = []
            for item in _normalize_patch_operations(payload):
                file_id = str(item.get("file_id") or "")
                operation_id = str(item.get("operation_id") or "")
                if file_id in selected or operation_id in selected_ops:
                    rejected.append({"file_id": file_id, "filename": item.get("filename") or "", "operation": item.get("type")})
                else:
                    remaining_ops.append(item)
            if remaining_ops:
                payload["operations"] = remaining_ops
                payload.pop("files", None)
                session.patch_text = json.dumps(payload)
            else:
                payload["operations"] = []
                metadata["patch_summary"] = ""
                session.patch_text = None
            metadata["patch_preview"] = [
                item for item in (metadata.get("patch_preview") or [])
                if str(item.get("file_id") or "") not in selected
                and str(item.get("operation_id") or "") not in selected_ops
            ]
        else:
            remaining_files = []
            for item in payload.get("files") or []:
                file_id = str(item.get("file_id") or "")
                operation_id = str(item.get("operation_id") or "")
                if file_id in selected or operation_id in selected_ops:
                    rejected.append({"file_id": file_id, "filename": item.get("filename") or ""})
                else:
                    remaining_files.append(item)
            if remaining_files:
                payload["files"] = remaining_files
                session.patch_text = json.dumps(payload)
                metadata["patch_preview"] = [
                    item for item in (metadata.get("patch_preview") or [])
                    if str(item.get("file_id") or "") not in selected
                    and str(item.get("operation_id") or "") not in selected_ops
                ]
            else:
                metadata["patch_preview"] = []
                metadata["patch_summary"] = ""
                session.patch_text = None
    else:
        rejected = [
            {"file_id": str(item.get("file_id") or ""), "filename": item.get("filename") or "", "operation": item.get("operation") or "modify"}
            for item in (metadata.get("patch_preview") or [])
        ]
        metadata["patch_preview"] = []
        metadata["patch_summary"] = ""
        session.patch_text = None
    _set_metadata(session, metadata)
    db.commit()
    detail = f"{len(rejected)} file(s) removed from the pending patch." if rejected else "No workspace files were changed."
    append_activity(db, session, "done", "Pending patch rejected", detail)
    return {"status": "rejected", "rejected": rejected, "remaining": metadata.get("patch_preview") or []}


def apply_patch_payload(
    db: Session,
    user_id: UUID,
    session: CodeSession,
    job=None,
    file_ids: list[str] | None = None,
    operation_ids: list[str] | None = None,
    hunk_ids: list[str] | None = None,
    allow_conflicts: bool = False,
) -> dict:
    if not session.patch_text:
        raise HTTPException(status_code=400, detail="No patch has been generated")
    payload = _parse_patch_payload(session.patch_text)
    selected = _selected_file_id_set(file_ids)
    selected_ops = _selected_operation_id_set(operation_ids)
    selected_hunks = _selected_hunk_id_set(hunk_ids)
    all_operations = _normalize_patch_operations(payload)
    selection_metadata = _metadata(session)
    selection_hunks_state = selection_metadata.get("patch_hunks_state") or {}
    applied_hunk_ids: set[str] = set()

    def operation_has_selected_hunk(item: dict) -> bool:
        if not selected_hunks:
            return False
        operation_id = str(item.get("operation_id") or "")
        return any(hunk_id.startswith(f"{operation_id}-") for hunk_id in selected_hunks)

    def operation_hunks_fully_selected(item: dict) -> bool:
        if not selected_hunks or not operation_has_selected_hunk(item):
            return False
        op_type = item.get("type") or "modify"
        if op_type not in {"modify", "create", "rename"}:
            return True
        record: FileReference | None = None
        if item.get("file_id"):
            record = db.query(FileReference).filter(FileReference.id == UUID(str(item.get("file_id"))), FileReference.user_id == user_id).first()
        old_text = get_file_text(db, user_id, record.id) if record and record.status == "active" else ""
        if op_type == "delete":
            new_text = ""
        else:
            new_text = str(item.get("content") or (old_text if op_type == "rename" else ""))
        operation_id = str(item.get("operation_id") or "")
        hunk_owner = str(record.id) if record else "new"
        pending_hunk_ids = {
            f"{operation_id}-{hunk_owner}-{hunk['index']}"
            for hunk in parse_diff_to_hunks(old_text, new_text)
            if selection_hunks_state.get(f"{operation_id}-{hunk_owner}-{hunk['index']}") != "rejected"
        }
        return bool(pending_hunk_ids) and pending_hunk_ids.issubset(selected_hunks)

    operations = [
        item for item in all_operations
        if (
            (not selected and not selected_ops and not selected_hunks)
            or str(item.get("file_id") or "") in selected
            or str(item.get("operation_id") or "") in selected_ops
            or operation_has_selected_hunk(item)
        )
    ]
    remaining_operations = [
        item for item in all_operations
        if (
            (selected or selected_ops or selected_hunks)
            and str(item.get("file_id") or "") not in selected
            and str(item.get("operation_id") or "") not in selected_ops
            and (not operation_has_selected_hunk(item) or not operation_hunks_fully_selected(item))
        )
    ]
    if (selected or selected_ops or selected_hunks) and not operations:
        raise HTTPException(status_code=400, detail={
            "error_class": "patch_conflict",
            "message": "Selected patch items are no longer available",
            "cause": "The selected files, operations, or hunks are not present in the pending patch.",
        })
    if not allow_conflicts:
        previews = preview_patch_payload(db, user_id, session)
        selected_operation_ids = {str(item.get("operation_id") or "") for item in operations}
        selected_file_ids = {str(item.get("file_id") or "") for item in operations if item.get("file_id")}
        conflicts = [
            {
                "operation_id": item.get("operation_id") or "",
                "file_id": item.get("file_id") or "",
                "filename": item.get("new_filename") or item.get("filename") or "",
                "operation": item.get("operation") or "modify",
                "base_checksum": item.get("base_checksum") or "",
                "current_checksum": item.get("current_checksum") or "",
            }
            for item in previews
            if item.get("conflict")
            and (
                str(item.get("operation_id") or "") in selected_operation_ids
                or str(item.get("file_id") or "") in selected_file_ids
            )
        ]
        if conflicts:
            raise HTTPException(status_code=409, detail={
                "error_class": "patch_conflict",
                "message": "Patch conflict detected",
                "cause": f"{len(conflicts)} file(s) changed after this patch was generated.",
                "conflicts": conflicts,
            })
    changed = []
    rollback_snapshots = []
    session_file_ids = [str(value) for value in (session.file_ids or [])]
    folders_created: list[str] = []
    for item in operations:
        op_type = item.get("type") or "modify"
        session_metadata = _metadata(session)
        hunks_state = session_metadata.get("patch_hunks_state") or {}
        operation_id = item["operation_id"]

        if op_type == "folder":
            folder = _safe_patch_filename(item.get("filename") or "")
            metadata_now = _metadata(session)
            workspace_folders = list(metadata_now.get("workspace_folders") or [])
            if folder not in workspace_folders:
                workspace_folders.append(folder)
            metadata_now["workspace_folders"] = workspace_folders
            _set_metadata(session, metadata_now)
            local_folder = _safe_local_workspace_file(session, f"{folder}/.nexus-folder")
            if local_folder:
                local_folder.parent.mkdir(parents=True, exist_ok=True)
            runtime_folder = _safe_workspace_path(_workspace_runtime_root(session), f"{folder}/.nexus-folder")
            runtime_folder.parent.mkdir(parents=True, exist_ok=True)
            folders_created.append(folder)
            rollback_snapshots.append({"operation": "folder", "filename": folder, "captured_at": _now()})
            changed.append({
                "operation_id": operation_id,
                "operation": "folder",
                "file_id": "",
                "filename": folder,
                "diff": "",
                "additions": 0,
                "deletions": 0,
            })
            continue

        record: FileReference | None = None
        if item.get("file_id"):
            record = db.query(FileReference).filter(FileReference.id == UUID(str(item.get("file_id"))), FileReference.user_id == user_id).first()
        if op_type in {"modify", "delete", "rename"} and not record:
            raise HTTPException(status_code=404, detail={
                "error_class": "patch_conflict",
                "message": "Patch target file is missing",
                "cause": f"File not found: {item.get('file_id')}",
            })

        old_filename = record.filename if record else _safe_patch_filename(item.get("filename") or "")
        target_filename = _safe_patch_filename(item.get("new_filename") or old_filename)
        old_text = get_file_text(db, user_id, record.id) if record and record.status == "active" else ""
        if op_type == "delete":
            new_text = ""
        else:
            new_text = str(item.get("content") or (old_text if op_type == "rename" else ""))

        if op_type in {"modify", "create", "rename"}:
            hunks = parse_diff_to_hunks(old_text, new_text)
            hunks_modified = False
            for hunk in hunks:
                hunk_id = f"{operation_id}-{record.id if record else 'new'}-{hunk['index']}"
                if selected_hunks and hunk_id not in selected_hunks:
                    hunk["status"] = "rejected"
                    hunks_modified = True
                elif hunks_state.get(hunk_id) == "rejected":
                    hunk["status"] = "rejected"
                    hunks_modified = True
                elif selected_hunks and hunk_id in selected_hunks:
                    applied_hunk_ids.add(hunk_id)
            if hunks_modified:
                new_text = apply_hunks_to_file(old_text, hunks)

        if op_type == "create":
            content_bytes = new_text.encode("utf-8")
            object_key = f"users/{user_id}/files/{uuid.uuid4()}{Path(target_filename).suffix.lower() or '.txt'}"
            put_object(object_key, content_bytes, "text/plain")
            record = FileReference(
                user_id=user_id,
                owner_type="code_workspace",
                owner_id=session.id,
                storage_provider=storage_provider(),
                bucket=settings.S3_BUCKET,
                object_key=object_key,
                filename=target_filename,
                content_type="text/plain",
                size_bytes=len(content_bytes),
                checksum_sha256=hashlib.sha256(content_bytes).hexdigest(),
                status="active",
                metadata_json={"created_by_code_session_id": str(session.id)},
            )
            db.add(record)
            db.flush()
            session_file_ids.append(str(record.id))
            rollback_snapshots.append({
                "operation": "create",
                "file_id": str(record.id),
                "filename": target_filename,
                "original_content": None,
                "object_key": object_key,
                "captured_at": _now(),
            })
        elif op_type == "delete":
            rollback_snapshots.append({
                "operation": "delete",
                "file_id": str(record.id),
                "filename": record.filename,
                "content": old_text,
                "original_content": old_text,
                "metadata_json": record.metadata_json or {},
                "captured_at": _now(),
            })
            record.status = "deleted"
            if str(record.id) in session_file_ids:
                session_file_ids.remove(str(record.id))
        elif op_type == "rename":
            rollback_snapshots.append({
                "operation": "rename",
                "file_id": str(record.id),
                "filename": old_filename,
                "new_filename": target_filename,
                "content": old_text,
                "original_content": old_text,
                "original_name": old_filename,
                "metadata_json": record.metadata_json or {},
                "captured_at": _now(),
            })
            if new_text != old_text:
                put_object(record.object_key, new_text.encode("utf-8"), record.content_type or "text/plain")
                record.size_bytes = len(new_text.encode("utf-8"))
                record.checksum_sha256 = hashlib.sha256(new_text.encode("utf-8")).hexdigest()
            record.filename = target_filename
        else:
            rollback_snapshots.append({
                "operation": "modify",
                "file_id": str(record.id),
                "filename": record.filename,
                "content": old_text,
                "original_content": old_text,
                "captured_at": _now(),
            })
            put_object(record.object_key, new_text.encode("utf-8"), record.content_type or "text/plain")
            record.size_bytes = len(new_text.encode("utf-8"))
            record.checksum_sha256 = hashlib.sha256(new_text.encode("utf-8")).hexdigest()

        if op_type != "delete":
            # Desktop/local mode and persistent runtime mirror approved patches back into selected projects.
            local_file = _safe_local_workspace_file(session, target_filename)
            if local_file:
                local_file.parent.mkdir(parents=True, exist_ok=True)
                local_file.write_text(new_text, encoding="utf-8")
            runtime_file = _safe_workspace_path(_workspace_runtime_root(session), target_filename)
            runtime_file.parent.mkdir(parents=True, exist_ok=True)
            runtime_file.write_text(new_text, encoding="utf-8")
        else:
            local_file = _safe_local_workspace_file(session, old_filename)
            if local_file and local_file.exists():
                local_file.unlink()
            runtime_file = (_workspace_runtime_root(session) / old_filename).resolve()
            if str(runtime_file).startswith(str(_workspace_runtime_root(session))) and runtime_file.exists():
                runtime_file.unlink()

        record.metadata_json = {**(record.metadata_json or {}), "last_code_session_id": str(session.id)}
        diff_text = "\n".join(difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=f"a/{old_filename}",
            tofile=f"b/{target_filename}",
            lineterm="",
        ))
        diff_impact = _patch_impact_from_diff(diff_text)
        changed.append({
            "operation_id": operation_id,
            "operation": op_type,
            "file_id": str(record.id),
            "filename": old_filename,
            "new_filename": target_filename if target_filename != old_filename else "",
            "diff": diff_text,
            "additions": diff_impact["additions"],
            "deletions": diff_impact["deletions"],
        })

    session.file_ids = session_file_ids
    if remaining_operations:
        payload.pop("files", None)
        payload["operations"] = remaining_operations
        session.patch_text = json.dumps(payload)
        session.status = "active"
    else:
        session.status = "applied"
        session.applied_at = datetime.now(timezone.utc)
        session.patch_text = None
    metadata = _metadata(session)
    if applied_hunk_ids:
        hunk_state = dict(metadata.get("patch_hunks_state") or {})
        for hunk_id in applied_hunk_ids:
            hunk_state.pop(hunk_id, None)
        metadata["patch_hunks_state"] = hunk_state
    metadata["patch_preview"] = preview_patch_payload(db, user_id, session) if remaining_operations else []
    metadata["patch_summary"] = payload.get("summary") or ""
    metadata["last_applied_files"] = [
        {
            "operation": item.get("operation"),
            "file_id": item.get("file_id"),
            "filename": item.get("new_filename") or item.get("filename") or "",
            "previous_filename": item.get("filename") if item.get("new_filename") else "",
            "additions": item.get("additions") or 0,
            "deletions": item.get("deletions") or 0,
            "applied_at": _now(),
        }
        for item in changed
        if item.get("file_id") or item.get("filename") or item.get("new_filename")
    ]
    impact_result = {
        **_patch_impact_summary(changed, folders_created),
        "summary": payload.get("summary") or "",
    }
    active_task_id = metadata.get("active_workspace_task_id")
    if active_task_id:
        tasks = _workspace_tasks(metadata)
        for index, task in enumerate(tasks):
            if str(task.get("id")) != str(active_task_id):
                continue
            next_task = dict(task)
            next_task["status"] = "waiting_approval" if remaining_operations else "done"
            next_task["updated_at"] = _now()
            next_task["metadata"] = {**(next_task.get("metadata") or {}), "last_apply": impact_result}
            next_task["impact"] = (
                f"Applied {len(changed)} file(s), +{impact_result['total_additions']} / -{impact_result['total_deletions']}."
                if changed else next_task.get("impact") or ""
            )
            if not remaining_operations:
                next_task["completed_at"] = next_task["updated_at"]
                metadata.pop("active_workspace_task_id", None)
            tasks[index] = next_task
            metadata["workspace_tasks"] = tasks
            break
    metadata["rollback_snapshots"] = (metadata.get("rollback_snapshots") or [])[-10:] + [{
        "snapshot_id": uuid.uuid4().hex,
        "applied_at": _now(),
        "files": rollback_snapshots,
        "summary": payload.get("summary") or "",
        "impact": {
            "created_files": [item.get("new_filename") or item.get("filename") for item in changed if item.get("operation") == "create"],
            "deleted_files": [item.get("filename") for item in changed if item.get("operation") == "delete"],
            "renamed_files": [{"from": item.get("filename"), "to": item.get("new_filename")} for item in changed if item.get("operation") == "rename"],
            "folders_created": folders_created,
        },
    }]
    _set_metadata(session, metadata)
    db.add(AuditLog(
        user_id=user_id,
        entity_type="code_session",
        entity_id=session.id,
        actor_type="ai",
        actor_id="autonomus-ai",
        event_type="code_patch_applied",
        action="Applied code workspace patch after user request",
        new_value={"changed": changed, "summary": payload.get("summary")},
    ))
    db.commit()
    refresh_file_tree(db, user_id, session)
    append_activity(db, session, "done", "Approved patch applied", f"{len(changed)} file(s) changed")
    complete_job(
        db,
        job,
        "completed",
        {"changed": changed, "summary": payload.get("summary") or ""},
        files_touched=[{"file_id": item["file_id"], "filename": item["filename"]} for item in changed],
        approval_state="approved",
    )
    return {
        "changed": changed,
        "summary": payload.get("summary") or "",
        "impact": impact_result,
        "remaining": metadata.get("patch_preview") or [],
    }


def list_rollback_snapshots(session: CodeSession) -> dict:
    metadata = _metadata(session)
    snapshots = list(metadata.get("rollback_snapshots") or [])
    summarized = []
    for index, snapshot in enumerate(snapshots):
        files = snapshot.get("files") or []
        summarized.append({
            "snapshot_id": snapshot.get("snapshot_id") or f"legacy-{index}",
            "index": index,
            "applied_at": snapshot.get("applied_at"),
            "summary": snapshot.get("summary") or "",
            "impact": snapshot.get("impact") or {},
            "operation_types": sorted({str(item.get("operation") or "modify") for item in files}),
            "files": [
                {"file_id": item.get("file_id"), "filename": item.get("filename"), "operation": item.get("operation") or "modify"}
                for item in files
            ],
            "file_count": len(files),
        })
    return {"snapshots": list(reversed(summarized))}


def rollback_snapshot(db: Session, user_id: UUID, session: CodeSession, snapshot_id: str | None = None, job=None) -> dict:
    metadata = _metadata(session)
    snapshots = list(metadata.get("rollback_snapshots") or [])
    if not snapshots:
        append_activity(db, session, "error", "Rollback unavailable", "No applied patch snapshot exists for this workspace.")
        complete_job(db, job, "failed", {"error": "No rollback snapshot available"})
        raise HTTPException(status_code=400, detail="No rollback snapshot available")

    target_index = len(snapshots) - 1
    if snapshot_id:
        for index, item in enumerate(snapshots):
            if item.get("snapshot_id") == snapshot_id or f"legacy-{index}" == snapshot_id:
                target_index = index
                break
        else:
            raise HTTPException(status_code=404, detail="Rollback snapshot not found")

    snapshot = snapshots.pop(target_index)
    restored = []
    for item in snapshot.get("files") or []:
        operation = item.get("operation") or "modify"
        if operation == "folder":
            folder = str(item.get("filename") or "")
            folders = [value for value in (metadata.get("workspace_folders") or []) if value != folder]
            metadata["workspace_folders"] = folders
            for marker in (".nexus-folder", ".arceus-folder"):
                for root in [_safe_local_workspace_file(session, f"{folder}/{marker}"), _safe_workspace_path(_workspace_runtime_root(session), f"{folder}/{marker}")]:
                    if root and root.exists():
                        try:
                            root.unlink()
                        except OSError:
                            pass
                    if root:
                        try:
                            root.parent.rmdir()
                        except OSError:
                            pass
            restored.append({"operation": "folder", "file_id": "", "filename": folder})
            continue

        file_id = UUID(str(item.get("file_id")))
        record = db.query(FileReference).filter(FileReference.id == file_id, FileReference.user_id == user_id).first()
        if not record:
            continue

        if operation == "create":
            record.status = "deleted"
            session.file_ids = [str(value) for value in (session.file_ids or []) if str(value) != str(record.id)]
            local_file = _safe_local_workspace_file(session, record.filename)
            if local_file and local_file.exists():
                local_file.unlink()
            runtime_file = (_workspace_runtime_root(session) / record.filename).resolve()
            if str(runtime_file).startswith(str(_workspace_runtime_root(session))) and runtime_file.exists():
                runtime_file.unlink()
            try:
                delete_object(record.object_key)
            except Exception:
                pass
            restored.append({"operation": "remove_created", "file_id": str(record.id), "filename": record.filename})
            continue

        content = str(item.get("original_content") if item.get("original_content") is not None else item.get("content") or "")
        if operation == "delete":
            record.status = "active"
            if str(record.id) not in [str(value) for value in (session.file_ids or [])]:
                session.file_ids = [str(value) for value in (session.file_ids or [])] + [str(record.id)]
            record.metadata_json = item.get("metadata_json") or record.metadata_json or {}
        if operation == "rename":
            renamed_local = _safe_local_workspace_file(session, record.filename)
            if renamed_local and renamed_local.exists():
                try:
                    renamed_local.unlink()
                except OSError:
                    pass
            renamed_runtime = (_workspace_runtime_root(session) / record.filename).resolve()
            if str(renamed_runtime).startswith(str(_workspace_runtime_root(session))) and renamed_runtime.exists():
                try:
                    renamed_runtime.unlink()
                except OSError:
                    pass
            record.filename = str(item.get("original_name") or item.get("filename") or record.filename)
            record.metadata_json = item.get("metadata_json") or record.metadata_json or {}

        put_object(record.object_key, content.encode("utf-8"), record.content_type or "text/plain")
        record.size_bytes = len(content.encode("utf-8"))
        record.checksum_sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()

        local_file = _safe_local_workspace_file(session, record.filename)
        if local_file:
            local_file.parent.mkdir(parents=True, exist_ok=True)
            local_file.write_text(content, encoding="utf-8")
        runtime_file = _safe_workspace_path(_workspace_runtime_root(session), record.filename)
        runtime_file.parent.mkdir(parents=True, exist_ok=True)
        runtime_file.write_text(content, encoding="utf-8")
        restored.append({"operation": operation, "file_id": str(record.id), "filename": record.filename})

    metadata["rollback_snapshots"] = snapshots
    restore_impact = {
        "changed_files": [
            {
                "operation": item.get("operation") or "restore",
                "file_id": item.get("file_id") or "",
                "filename": item.get("filename") or "",
                "additions": 0,
                "deletions": 0,
            }
            for item in restored
        ],
        "created_files": [],
        "modified_files": [item.get("filename") for item in restored if item.get("operation") in {"modify", "delete", "rename"}],
        "deleted_files": [item.get("filename") for item in restored if item.get("operation") == "remove_created"],
        "renamed_files": [],
        "folders_created": [],
        "total_additions": 0,
        "total_deletions": 0,
        "summary": snapshot.get("summary") or "",
    }
    _set_metadata(session, metadata)
    session.status = "rolled_back"
    db.commit()
    refresh_file_tree(db, user_id, session)
    append_activity(db, session, "done", "Rolled back applied patch", f"{len(restored)} file(s) restored")
    complete_job(db, job, "completed", {"restored": restored, "snapshot": snapshot, "impact": restore_impact}, files_touched=restored, approval_state="approved")
    return {"restored": restored, "status": "rolled_back", "snapshot": {
        "snapshot_id": snapshot.get("snapshot_id"),
        "applied_at": snapshot.get("applied_at"),
        "summary": snapshot.get("summary") or "",
    }, "impact": restore_impact}


def rollback_last_apply(db: Session, user_id: UUID, session: CodeSession, job=None) -> dict:
    return rollback_snapshot(db, user_id, session, None, job)
