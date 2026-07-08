import difflib
import json
import os
import shlex
import subprocess
import tempfile
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

from services.shared.models import AuditLog, CodeSession, FileReference
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
        "title": session.title,
        "file_ids": session.file_ids or [],
        "status": session.status,
        "plan_text": session.plan_text,
        "patch_text": session.patch_text,
        "patch_preview": metadata.get("patch_preview") or [],
        "activity_log": metadata.get("activity_log") or [],
        "file_tree": file_tree or metadata_tree,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


def list_code_sessions(db: Session, user_id: UUID, limit: int = 20) -> list[CodeSession]:
    return (
        db.query(CodeSession)
        .filter(CodeSession.user_id == user_id)
        .order_by(CodeSession.updated_at.desc(), CodeSession.created_at.desc())
        .limit(limit)
        .all()
    )


def create_code_session(db: Session, user_id: UUID, title: str, file_ids: list[str]) -> CodeSession:
    session = CodeSession(
        user_id=user_id,
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

    files = code_files(db, user_id, session)
    append_activity(db, session, "deploy", f"Running command: {command}", "Creating an isolated temporary workspace from selected files.")
    append_job_log(db, job, "deploy", f"Running command: {command}", "Temporary isolated workspace created from selected files.")
    with tempfile.TemporaryDirectory(prefix="nexus-code-") as temp_dir:
        workspace_root = Path(temp_dir)
        for record in files:
            if Path(record.filename).suffix.lower() not in CODE_EXTENSIONS and Path(record.filename).name not in {"package.json", "package-lock.json"}:
                continue
            target = _safe_workspace_path(workspace_root, record.filename)
            target.write_text(get_file_text(db, user_id, record.id), encoding="utf-8", errors="ignore")

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
            result = {"command": command, "status": "timeout", "return_code": None, "output": clipped, "ran_at": _now()}
            complete_job(db, job, "timeout", result, commands_run=[result])
            return result


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
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            status_code = response.getcode()
            content_type = response.headers.get("content-type", "")
            body = response.read(250_000).decode("utf-8", errors="ignore")
    except urllib.error.HTTPError as exc:
        result = {"url": url, "status": "failed", "status_code": exc.code, "title": "", "issues": [f"HTTP {exc.code}"]}
        append_activity(db, session, "error", "Preview check failed", f"HTTP {exc.code}")
        complete_job(db, job, "failed", result)
        return result
    except Exception as exc:
        result = {"url": url, "status": "failed", "status_code": None, "title": "", "issues": [str(exc)]}
        append_activity(db, session, "error", "Preview check failed", str(exc))
        complete_job(db, job, "failed", result)
        return result

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
    metadata = _metadata(session)
    preview_checks = list(metadata.get("preview_checks") or [])
    preview_checks.append(result)
    metadata["preview_checks"] = preview_checks[-30:]
    _set_metadata(session, metadata)
    db.commit()
    complete_job(db, job, "completed" if status == "passed" else "failed", result)
    return result


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


def generate_plan(db: Session, user_id: UUID, session: CodeSession, instruction: str, provider: str | None, model: str | None, job=None) -> str:
    bundle = build_file_bundle(db, user_id, code_files(db, user_id, session))
    append_activity(db, session, "code", "Planning code changes", instruction[:180])
    append_job_log(db, job, "code", "Planning code changes", instruction[:180])
    llm = get_chat_llm(role="planning", provider=provider, model=model)
    response = llm.invoke([
        SystemMessage(content="You are Autonomus AI in coding workspace mode. Produce a concise implementation plan grounded in the provided files."),
        HumanMessage(content=f"Instruction:\n{instruction}\n\nWorkspace files:\n{bundle}"),
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


def rollback_last_apply(db: Session, user_id: UUID, session: CodeSession, job=None) -> dict:
    metadata = _metadata(session)
    snapshots = list(metadata.get("rollback_snapshots") or [])
    if not snapshots:
        append_activity(db, session, "error", "Rollback unavailable", "No applied patch snapshot exists for this workspace.")
        complete_job(db, job, "failed", {"error": "No rollback snapshot available"})
        raise HTTPException(status_code=400, detail="No rollback snapshot available")

    snapshot = snapshots.pop()
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
    append_activity(db, session, "done", "Rolled back last apply", f"{len(restored)} file(s) restored")
    complete_job(db, job, "completed", {"restored": restored}, files_touched=restored, approval_state="approved")
    return {"restored": restored, "status": "rolled_back"}
