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
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote, urlparse
from uuid import UUID

from fastapi import HTTPException
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.orm import Session

from services.shared.models import AuditLog, CodeProject, CodeSession, FileReference
from .agent_jobs import append_job_log, complete_job
from .config import settings
from .file_service import get_file_text, put_object, storage_provider
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
BLOCKED_TOKENS = {"rm", "del", "erase", "format", "shutdown", "reboot", "curl", "wget", "scp", "ssh", "sudo"}
PREVIEW_PROCESSES: dict[str, subprocess.Popen] = {}


class _TitleParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_title = False
        self.title_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self.in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)

    @property
    def title(self) -> str:
        return " ".join(part.strip() for part in self.title_parts if part.strip())[:180]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _metadata(session: CodeSession) -> dict:
    return dict(session.metadata_json or {})


def _set_metadata(session: CodeSession, metadata: dict) -> None:
    session.metadata_json = metadata


def _activity(kind: str, message: str, detail: str | None = None, diff: str | None = None) -> dict:
    event = {"id": f"job-{datetime.now(timezone.utc).timestamp()}", "kind": kind, "message": message, "timestamp": _now()}
    if detail:
        event["detail"] = detail
    if diff:
        event["diff"] = diff
    return event


def append_activity(db: Session, session: CodeSession, kind: str, message: str, detail: str | None = None, diff: str | None = None) -> dict:
    metadata = _metadata(session)
    log = list(metadata.get("activity_log") or [])
    event = _activity(kind, message, detail, diff)
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
    return {
        "id": str(project.id),
        "name": project.name,
        "description": project.description or "",
        "repo_url": project.repo_url or "",
        "default_branch": project.default_branch or "",
        "status": project.status,
        "file_ids": project.file_ids or [],
        "settings": project.settings_json or {},
        "metadata": project.metadata_json or {},
        "active_session_id": str(active_session.id) if active_session else None,
        "last_opened_at": project.last_opened_at.isoformat() if project.last_opened_at else None,
        "created_at": project.created_at.isoformat() if project.created_at else None,
        "updated_at": project.updated_at.isoformat() if project.updated_at else None,
    }


def list_code_projects(db: Session, user_id: UUID, limit: int = 30) -> list[CodeProject]:
    return (
        db.query(CodeProject)
        .filter(CodeProject.user_id == user_id, CodeProject.status != "deleted")
        .order_by(CodeProject.last_opened_at.desc().nullslast(), CodeProject.updated_at.desc(), CodeProject.created_at.desc())
        .limit(limit)
        .all()
    )


def get_code_project(db: Session, user_id: UUID, project_id: UUID) -> CodeProject:
    project = db.query(CodeProject).filter(CodeProject.id == project_id, CodeProject.user_id == user_id, CodeProject.status != "deleted").first()
    if not project:
        raise HTTPException(status_code=404, detail="Code project not found")
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
    return (
        db.query(CodeSession)
        .filter(CodeSession.user_id == user_id, CodeSession.project_id == project.id, CodeSession.status == "active")
        .order_by(CodeSession.updated_at.desc(), CodeSession.created_at.desc())
        .first()
    )


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
        project = db.query(CodeProject.id).filter(CodeProject.id == project_id, CodeProject.user_id == user_id, CodeProject.status != "deleted").first()
        if not project:
            raise HTTPException(status_code=404, detail="Code project not found")
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
    session = db.query(CodeSession).filter(CodeSession.id == session_id, CodeSession.user_id == user_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Code session not found")
    return session


def code_files(db: Session, user_id: UUID, session: CodeSession) -> list[FileReference]:
    ids = []
    for value in session.file_ids or []:
        try:
            ids.append(UUID(str(value)))
        except ValueError:
            continue
    if not ids:
        return []
    records = db.query(FileReference).filter(FileReference.user_id == user_id, FileReference.id.in_(ids)).all()
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
        "root": str(root),
        "last_synced_at": _now(),
        "files_written": len(written),
        "files_skipped": len(skipped),
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
            "User-Agent": "NEXUS-Code/1.0",
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
    return {"commands": commands[:12]}


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
    process = PREVIEW_PROCESSES.get(str(session.id))
    running = bool(process and process.poll() is None)
    return {
        "status": "running" if running else "stopped",
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
    existing = PREVIEW_PROCESSES.get(str(session.id))
    if existing and existing.poll() is None:
        return preview_status(session)

    runtime = sync_workspace_runtime(db, user_id, session)
    root = Path(runtime["root"])
    preview_command = _detect_preview_command(db, user_id, session)
    port = _workspace_preview_port(session)
    token = uuid.uuid4().hex
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
    append_activity(db, session, "deploy", "Starting workspace preview", preview_command["command"])
    append_job_log(db, job, "deploy", "Starting workspace preview", f"{preview_command['command']} on port {port}")
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

    proxy_url = f"/api/v1/code/sessions/{session.id}/preview/proxy/?token={token}"
    metadata = _metadata(session)
    metadata["preview_runtime"] = {
        "status": status,
        "local_url": local_url,
        "preview_url": proxy_url,
        "port": port,
        "token": token,
        "command": preview_command["command"],
        "log_path": str(log_path),
        "started_at": _now(),
    }
    _set_metadata(session, metadata)
    db.commit()
    append_activity(db, session, "done" if status == "running" else "error", f"Preview {status}", proxy_url)
    complete_job(db, job, "completed" if status in {"running", "starting"} else "failed", metadata["preview_runtime"])
    return preview_status(session)


def stop_workspace_preview(db: Session, session: CodeSession, job=None) -> dict:
    process = PREVIEW_PROCESSES.pop(str(session.id), None)
    stopped = False
    if process and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
        stopped = True
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


def _command_allowed(parts: list[str], commands: list[dict] | None = None) -> bool:
    lowered = [part.lower() for part in parts]
    if not lowered or any(token in BLOCKED_TOKENS for token in lowered):
        return False
    if commands and _dynamic_command_allowed(lowered, commands):
        return True
    return any(tuple(lowered[: len(prefix)]) == prefix for prefix in ALLOWED_COMMAND_PREFIXES)


def run_workspace_command(
    db: Session,
    user_id: UUID,
    session: CodeSession,
    command: str,
    timeout_seconds: int = 45,
    job=None,
) -> dict:
    parts = _command_parts(command)
    discovered_commands = discover_workspace_commands(db, user_id, session).get("commands") or []
    if not _command_allowed(parts, discovered_commands):
        append_activity(db, session, "error", "Command blocked", "Only safe build/test/lint commands are enabled in v1.")
        complete_job(db, job, "blocked", {"error": "Command is not allowed"}, commands_run=[command])
        raise HTTPException(status_code=400, detail="Command is not allowed for workspace execution.")

    runtime = sync_workspace_runtime(db, user_id, session)
    workspace_root = Path(runtime["root"])
    append_activity(db, session, "deploy", f"Running command: {command}", f"Using persistent runtime workspace with {len(runtime['files_written'])} synced file(s).")
    append_job_log(db, job, "deploy", f"Running command: {command}", f"Runtime workspace: {workspace_root}")

    try:
        completed = subprocess.run(
            parts,
            cwd=workspace_root,
            capture_output=True,
            text=True,
            timeout=max(5, min(timeout_seconds, 120)),
            check=False,
        )
        output = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
        clipped = output[-12000:] if output else "(no output)"
        status = "passed" if completed.returncode == 0 else "failed"
        event_kind = "done" if completed.returncode == 0 else "error"
        append_activity(db, session, event_kind, f"Command {status}: {command}", clipped)
        metadata = _metadata(session)
        command_log = list(metadata.get("command_log") or [])
        result = {
            "command": command,
            "status": status,
            "return_code": completed.returncode,
            "output": clipped,
            "workspace_root": str(workspace_root),
            "ran_at": _now(),
        }
        command_log.append(result)
        metadata["command_log"] = command_log[-50:]
        _set_metadata(session, metadata)
        db.commit()
        complete_job(db, job, "completed" if status == "passed" else "failed", result, commands_run=[result])
        return result
    except FileNotFoundError:
        append_activity(db, session, "error", f"Command unavailable: {parts[0]}", "The runtime image does not include this executable.")
        complete_job(db, job, "failed", {"error": f"Command unavailable: {parts[0]}"}, commands_run=[command])
        raise HTTPException(status_code=400, detail=f"Command unavailable: {parts[0]}")
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(part for part in [exc.stdout or "", exc.stderr or ""] if part).strip()
        clipped = output[-12000:] if output else "Command timed out before producing output."
        append_activity(db, session, "error", f"Command timed out: {command}", clipped)
        result = {"command": command, "status": "timeout", "return_code": None, "output": clipped, "workspace_root": str(workspace_root), "ran_at": _now()}
        complete_job(db, job, "timeout", result, commands_run=[result])
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
    append_activity(db, session, "deploy", "Running workspace checks", ", ".join(commands))
    append_job_log(db, job, "deploy", "Running workspace checks", f"{len(commands)} command(s) in {workspace_root}")

    results = []
    for command in commands:
        parts = _command_parts(command)
        try:
            completed = subprocess.run(
                parts,
                cwd=workspace_root,
                capture_output=True,
                text=True,
                timeout=max(10, min(timeout_seconds, 180)),
                check=False,
            )
            output = "\n".join(part for part in [completed.stdout, completed.stderr] if part).strip()
            clipped = output[-8000:] if output else "(no output)"
            status = "passed" if completed.returncode == 0 else "failed"
            result = {
                "command": command,
                "status": status,
                "return_code": completed.returncode,
                "output": clipped,
                "workspace_root": str(workspace_root),
                "ran_at": _now(),
            }
        except FileNotFoundError:
            result = {
                "command": command,
                "status": "failed",
                "return_code": None,
                "output": f"Command unavailable: {parts[0]}",
                "workspace_root": str(workspace_root),
                "ran_at": _now(),
            }
        except subprocess.TimeoutExpired as exc:
            output = "\n".join(part for part in [exc.stdout or "", exc.stderr or ""] if part).strip()
            result = {
                "command": command,
                "status": "timeout",
                "return_code": None,
                "output": output[-8000:] if output else "Command timed out before producing output.",
                "workspace_root": str(workspace_root),
                "ran_at": _now(),
            }
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
    _set_metadata(session, metadata)
    db.commit()
    append_activity(db, session, "done" if summary["status"] == "passed" else "error", f"Workspace checks {summary['status']}", f"{passed}/{len(results)} check(s) passed")
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
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "NEXUS-Code-Preview/1.0"},
        method="GET",
    )
    metadata = _metadata(session)

    def store_result(result: dict) -> dict:
        preview_checks = list(metadata.get("preview_checks") or [])
        preview_checks.append(result)
        metadata["preview_checks"] = preview_checks[-30:]
        _set_metadata(session, metadata)
        db.commit()
        return result

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status_code = response.getcode()
            content_type = response.headers.get("content-type", "")
            body = response.read(250_000).decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        result = {"url": url, "status": "failed", "status_code": exc.code, "title": "", "issues": [f"HTTP {exc.code}"], "checked_at": _now()}
        append_activity(db, session, "error", "Preview check failed", f"HTTP {exc.code}")
        complete_job(db, job, "failed", result)
        return store_result(result)
    except Exception as exc:
        result = {"url": url, "status": "failed", "status_code": None, "title": "", "issues": [str(exc)], "checked_at": _now()}
        append_activity(db, session, "error", "Preview check failed", str(exc))
        complete_job(db, job, "failed", result)
        return store_result(result)

    parser = _TitleParser()
    if "html" in content_type.lower():
        parser.feed(body)
    markers = [
        "Unhandled Runtime Error",
        "Application error",
        "Traceback",
        "Module not found",
        "ReferenceError",
        "TypeError:",
        "SyntaxError:",
        "Internal Server Error",
    ]
    issues = [marker for marker in markers if marker.lower() in body.lower()]
    status = "passed" if 200 <= status_code < 400 and not issues else "failed"
    result = {
        "url": url,
        "status": status,
        "status_code": status_code,
        "content_type": content_type,
        "title": parser.title,
        "issues": issues,
        "checked_at": _now(),
    }
    detail = f"{status_code} {content_type}".strip()
    if parser.title:
        detail = f"{detail}\nTitle: {parser.title}"
    if issues:
        detail = f"{detail}\nPotential issue markers: {', '.join(issues)}"
    append_activity(db, session, "done" if status == "passed" else "error", f"Preview check {status}", detail)
    complete_job(db, job, "completed" if status == "passed" else "failed", result)
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

    safe_title = (title or session.title or "NEXUS Code changes").strip()
    slug = "".join(char.lower() if char.isalnum() else "-" for char in safe_title).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    branch_name = f"nexus/{slug[:48] or 'workspace-update'}"
    preview = metadata.get("patch_preview") or []
    patch_summary = metadata.get("patch_summary") or "Workspace changes prepared by NEXUS Code."
    changed_files = [item.get("filename") for item in preview if item.get("filename")]
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
        "- Generated in an app-managed NEXUS Code workspace.",
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
        complete_job(db, job, "failed", {"error": f"Could not resolve base branch {base_branch}"})
        raise HTTPException(status_code=400, detail=f"Could not resolve base branch {base_branch}")
    _github_create_branch(owner, repo, branch_name, base_sha)

    target_filenames = set(pr_plan.get("changed_files") or [])
    files = code_files(db, user_id, session)
    if target_filenames:
        files = [record for record in files if record.filename in target_filenames]
    if not files:
        complete_job(db, job, "failed", {"error": "No files available to commit"})
        raise HTTPException(status_code=400, detail="No files available to commit")

    committed = []
    message = pr_plan.get("commit_message") or session.title or "NEXUS Code workspace changes"
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
        "body": pr_plan.get("pr_body") or "Prepared by NEXUS Code.",
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
    matches = []
    for record in code_files(db, user_id, session):
        if len(matches) >= limit:
            break
        try:
            text = get_file_text(db, user_id, record.id)
        except Exception:
            continue
        lines = text.splitlines()
        for index, line in enumerate(lines, start=1):
            if needle in line.lower():
                matches.append({
                    "file_id": str(record.id),
                    "filename": record.filename,
                    "line": index,
                    "snippet": line.strip()[:240],
                })
                if len(matches) >= limit:
                    break
    append_activity(db, session, "read", "Workspace search complete", f"{len(matches)} match(es) for '{query}'")
    return {"query": query, "matches": matches}


def analyze_workspace_structure(db: Session, user_id: UUID, session: CodeSession) -> dict:
    files = code_files(db, user_id, session)
    language_counts: dict[str, int] = {}
    imports: list[dict] = []
    exports: list[dict] = []
    routes: list[dict] = []
    components: list[dict] = []
    hotspots: list[dict] = []
    total_lines = 0
    total_bytes = 0

    import_patterns = [
        re.compile(r"^\s*import\s+(?:.+?\s+from\s+)?['\"]([^'\"]+)['\"]"),
        re.compile(r"^\s*from\s+([\w.]+)\s+import\s+"),
        re.compile(r"require\(['\"]([^'\"]+)['\"]\)"),
    ]
    export_pattern = re.compile(r"^\s*export\s+(?:default\s+)?(?:function|const|class)\s+([A-Za-z0-9_]+)?")
    component_pattern = re.compile(r"(?:function|const)\s+([A-Z][A-Za-z0-9_]*)")

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

        if any(segment in filename for segment in ["/app/", "/pages/", "/routes/"]) or filename.startswith(("app/", "pages/", "routes/")):
            if suffix in {".tsx", ".ts", ".jsx", ".js", ".py"}:
                routes.append({"filename": filename, "kind": "route_or_page"})

        for index, line in enumerate(lines, start=1):
            if len(imports) < 200:
                for pattern in import_patterns:
                    match = pattern.search(line)
                    if match:
                        imports.append({"filename": filename, "line": index, "module": match.group(1)[:160]})
                        break
            if len(exports) < 120:
                match = export_pattern.search(line)
                if match:
                    exports.append({"filename": filename, "line": index, "symbol": match.group(1) or "default"})
            if len(components) < 120 and suffix in {".tsx", ".jsx"}:
                match = component_pattern.search(line)
                if match:
                    components.append({"filename": filename, "line": index, "name": match.group(1)})
            lowered = line.lower()
            if any(marker in lowered for marker in ["todo", "fixme", "hack", "any", "dangerouslysetinnerhtml", "eval("]):
                hotspots.append({"filename": filename, "line": index, "snippet": line.strip()[:220]})

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
        "hotspots": hotspots[:80],
        "analyzed_at": _now(),
    }
    metadata = _metadata(session)
    metadata["workspace_analysis"] = analysis
    _set_metadata(session, metadata)
    db.commit()
    append_activity(db, session, "read", "Workspace analysis complete", f"{len(files)} file(s), {total_lines} line(s), {len(imports)} import signal(s).")
    return analysis


def generate_plan(db: Session, user_id: UUID, session: CodeSession, instruction: str, provider: str | None, model: str | None, job=None) -> str:
    bundle = build_file_bundle(db, user_id, code_files(db, user_id, session))
    metadata = _metadata(session)
    analysis = metadata.get("workspace_analysis") or {}
    append_activity(db, session, "code", "Planning code changes", instruction[:180])
    append_job_log(db, job, "code", "Planning code changes", instruction[:180])
    llm = get_chat_llm(role="planning", provider=provider, model=model)
    response = llm.invoke([
        SystemMessage(content="You are Autonomus AI in coding workspace mode. Produce a concise implementation plan grounded in the provided files."),
        HumanMessage(content=f"Instruction:\n{instruction}\n\nWorkspace analysis:\n{json.dumps(analysis, indent=2)[:12000]}\n\nWorkspace files:\n{bundle}"),
    ])
    session.plan_text = str(response.content)
    metadata = _metadata(session)
    metadata["last_instruction"] = instruction
    _set_metadata(session, metadata)
    db.commit()
    append_activity(db, session, "done", "Implementation plan stored", (session.plan_text or "")[:220])
    complete_job(db, job, "completed", {"plan": session.plan_text or ""})
    return session.plan_text or ""


def generate_patch(db: Session, user_id: UUID, session: CodeSession, instruction: str, provider: str | None, model: str | None, job=None) -> str:
    files = code_files(db, user_id, session)
    bundle = build_file_bundle(db, user_id, files)
    append_activity(db, session, "edit", "Generating reviewable patch", "The patch will remain pending until approved.")
    append_job_log(db, job, "edit", "Generating reviewable patch", "Patch remains pending until user approval.")
    llm = get_chat_llm(role="reasoning", provider=provider, model=model)
    response = llm.invoke([
        SystemMessage(content=(
            "You are Autonomus AI in coding workspace mode. Return ONLY JSON with this shape: "
            "{\"files\":[{\"file_id\":\"...\",\"filename\":\"...\",\"content\":\"full updated file content\"}],\"summary\":\"...\"}. "
            "Use full replacement content so the app can apply safely."
        )),
        HumanMessage(content=f"Instruction:\n{instruction}\n\nCurrent plan:\n{session.plan_text or ''}\n\nWorkspace files:\n{bundle}"),
    ])
    raw = str(response.content)
    session.patch_text = raw
    db.commit()
    preview = preview_patch_payload(db, user_id, session)
    append_activity(db, session, "edit", "Patch ready for review", f"{len(preview)} file diff(s) prepared")
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


def preview_patch_payload(db: Session, user_id: UUID, session: CodeSession) -> list[dict]:
    if not session.patch_text:
        return []
    payload = _parse_patch_payload(session.patch_text)
    previews = []
    for item in payload.get("files") or []:
        file_id = UUID(str(item.get("file_id")))
        record = db.query(FileReference).filter(FileReference.id == file_id, FileReference.user_id == user_id).first()
        if not record:
            continue
        old_text = get_file_text(db, user_id, record.id)
        new_text = str(item.get("content") or "")
        diff = "\n".join(difflib.unified_diff(
            old_text.splitlines(),
            new_text.splitlines(),
            fromfile=f"a/{record.filename}",
            tofile=f"b/{record.filename}",
            lineterm="",
        ))
        previews.append({
            "file_id": str(record.id),
            "filename": record.filename,
            "diff": diff,
            "additions": sum(1 for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++")),
            "deletions": sum(1 for line in diff.splitlines() if line.startswith("-") and not line.startswith("---")),
        })
    metadata = _metadata(session)
    metadata["patch_preview"] = previews
    metadata["patch_summary"] = payload.get("summary") or ""
    _set_metadata(session, metadata)
    db.commit()
    return previews


def _selected_file_id_set(file_ids: list[str] | None) -> set[str]:
    selected: set[str] = set()
    for value in file_ids or []:
        try:
            selected.add(str(UUID(str(value))))
        except ValueError:
            continue
    return selected


def reject_patch_payload(db: Session, session: CodeSession, file_ids: list[str] | None = None) -> dict:
    metadata = _metadata(session)
    selected = _selected_file_id_set(file_ids)
    rejected = []
    if selected and session.patch_text:
        payload = _parse_patch_payload(session.patch_text)
        remaining_files = []
        for item in payload.get("files") or []:
            file_id = str(item.get("file_id") or "")
            if file_id in selected:
                rejected.append({"file_id": file_id, "filename": item.get("filename") or ""})
            else:
                remaining_files.append(item)
        if remaining_files:
            payload["files"] = remaining_files
            session.patch_text = json.dumps(payload)
            metadata["patch_preview"] = [
                item for item in (metadata.get("patch_preview") or [])
                if str(item.get("file_id") or "") not in selected
            ]
        else:
            metadata["patch_preview"] = []
            metadata["patch_summary"] = ""
            session.patch_text = None
    else:
        rejected = [
            {"file_id": str(item.get("file_id") or ""), "filename": item.get("filename") or ""}
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


def apply_patch_payload(db: Session, user_id: UUID, session: CodeSession, job=None, file_ids: list[str] | None = None) -> dict:
    if not session.patch_text:
        raise HTTPException(status_code=400, detail="No patch has been generated")
    payload = _parse_patch_payload(session.patch_text)
    selected = _selected_file_id_set(file_ids)
    all_replacements = payload.get("files") or []
    replacements = [
        item for item in all_replacements
        if not selected or str(item.get("file_id") or "") in selected
    ]
    remaining_replacements = [
        item for item in all_replacements
        if selected and str(item.get("file_id") or "") not in selected
    ]
    if selected and not replacements:
        raise HTTPException(status_code=400, detail="Selected files are not present in the pending patch")
    changed = []
    rollback_snapshots = []
    for item in replacements:
        file_id = UUID(str(item.get("file_id")))
        record = db.query(FileReference).filter(FileReference.id == file_id, FileReference.user_id == user_id).first()
        if not record:
            raise HTTPException(status_code=404, detail=f"File not found: {file_id}")
        old_text = get_file_text(db, user_id, record.id)
        new_text = str(item.get("content") or "")
        if not new_text:
            continue
        rollback_snapshots.append({
            "file_id": str(record.id),
            "filename": record.filename,
            "content": old_text,
            "captured_at": _now(),
        })
        put_object(record.object_key, new_text.encode("utf-8"), record.content_type or "text/plain")
        record.size_bytes = len(new_text.encode("utf-8"))
        record.metadata_json = {**(record.metadata_json or {}), "last_code_session_id": str(session.id)}
        changed.append({
            "file_id": str(record.id),
            "filename": record.filename,
            "diff": "\n".join(difflib.unified_diff(
                old_text.splitlines(),
                new_text.splitlines(),
                fromfile=f"a/{record.filename}",
                tofile=f"b/{record.filename}",
                lineterm="",
            )),
        })

    if remaining_replacements:
        payload["files"] = remaining_replacements
        session.patch_text = json.dumps(payload)
        session.status = "active"
    else:
        session.status = "applied"
        session.applied_at = datetime.now(timezone.utc)
        session.patch_text = None
    metadata = _metadata(session)
    metadata["patch_preview"] = [
        item for item in (metadata.get("patch_preview") or [])
        if str(item.get("file_id") or "") not in {entry["file_id"] for entry in changed}
    ] if remaining_replacements else []
    metadata["patch_summary"] = payload.get("summary") or ""
    metadata["rollback_snapshots"] = (metadata.get("rollback_snapshots") or [])[-10:] + [{
        "snapshot_id": uuid.uuid4().hex,
        "applied_at": _now(),
        "files": rollback_snapshots,
        "summary": payload.get("summary") or "",
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
            "files": [
                {"file_id": item.get("file_id"), "filename": item.get("filename")}
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
        file_id = UUID(str(item.get("file_id")))
        record = db.query(FileReference).filter(FileReference.id == file_id, FileReference.user_id == user_id).first()
        if not record:
            continue
        content = str(item.get("content") or "")
        put_object(record.object_key, content.encode("utf-8"), record.content_type or "text/plain")
        record.size_bytes = len(content.encode("utf-8"))
        restored.append({"file_id": str(record.id), "filename": record.filename})

    metadata["rollback_snapshots"] = snapshots
    _set_metadata(session, metadata)
    session.status = "rolled_back"
    db.commit()
    refresh_file_tree(db, user_id, session)
    append_activity(db, session, "done", "Rolled back applied patch", f"{len(restored)} file(s) restored")
    complete_job(db, job, "completed", {"restored": restored, "snapshot": snapshot}, files_touched=restored, approval_state="approved")
    return {"restored": restored, "status": "rolled_back", "snapshot": {
        "snapshot_id": snapshot.get("snapshot_id"),
        "applied_at": snapshot.get("applied_at"),
        "summary": snapshot.get("summary") or "",
    }}


def rollback_last_apply(db: Session, user_id: UUID, session: CodeSession, job=None) -> dict:
    return rollback_snapshot(db, user_id, session, None, job)
