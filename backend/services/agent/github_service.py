from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import UUID

import jwt
import urllib.error
import urllib.request
from fastapi import HTTPException
from sqlalchemy.orm import Session

from services.agent.config import settings
from services.agent.file_service import get_file_text, put_object, storage_provider
from services.shared.models import AuditLog, CodeSession, FileReference, Integration


GITHUB_API = "https://api.github.com"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_private_key(value: str | None) -> str:
    raw = (value or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="GITHUB_APP_PRIVATE_KEY is not configured")
    if raw.startswith("-----BEGIN"):
        return raw.replace("\\n", "\n")
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        if decoded.startswith("-----BEGIN"):
            return decoded
    except Exception:
        pass
    return raw.replace("\\n", "\n")


def github_app_configured() -> bool:
    return bool(settings.GITHUB_APP_ID and settings.GITHUB_APP_PRIVATE_KEY and settings.GITHUB_APP_NAME)


def github_app_jwt() -> str:
    if not settings.GITHUB_APP_ID:
        raise HTTPException(status_code=400, detail="GITHUB_APP_ID is not configured")
    now = int(time.time())
    payload = {
        "iat": now - 60,
        "exp": now + 9 * 60,
        "iss": str(settings.GITHUB_APP_ID),
    }
    return jwt.encode(payload, _normalize_private_key(settings.GITHUB_APP_PRIVATE_KEY), algorithm="RS256")


def _github_request(method: str, path: str, token: str, payload: dict | None = None) -> dict:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{GITHUB_API}{path}",
        data=data,
        method=method,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "NEXUS-Code/1.0",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="ignore")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        try:
            message = json.loads(detail).get("message") or detail
        except Exception:
            message = detail or str(exc)
        raise HTTPException(status_code=min(exc.code, 500), detail=f"GitHub API error: {message}")


def _app_request(method: str, path: str, payload: dict | None = None) -> dict:
    return _github_request(method, path, github_app_jwt(), payload)


def _dev_token() -> str | None:
    return settings.GITHUB_TOKEN


def _integration(db: Session, user_id: UUID) -> Integration | None:
    return (
        db.query(Integration)
        .filter(Integration.user_id == user_id, Integration.provider == "github", Integration.status == "active")
        .order_by(Integration.updated_at.desc(), Integration.created_at.desc())
        .first()
    )


def github_status(db: Session, user_id: UUID) -> dict:
    integration = _integration(db, user_id)
    metadata = integration.metadata_json if integration else {}
    return {
        "configured": github_app_configured(),
        "connected": bool(integration and metadata.get("installation_id")),
        "app_name": settings.GITHUB_APP_NAME,
        "account": metadata.get("account") or {},
        "installation_id": metadata.get("installation_id"),
        "repositories": metadata.get("repositories") or [],
        "connected_at": metadata.get("connected_at"),
        "dev_fallback_available": bool(_dev_token()),
    }


def github_install_url(user_id: UUID, jwt_secret: str) -> dict:
    if not github_app_configured():
        raise HTTPException(status_code=400, detail="GitHub App is not configured")
    state = jwt.encode(
        {
            "sub": str(user_id),
            "type": "github_app_install",
            "iat": int(time.time()),
            "exp": int(time.time()) + 15 * 60,
        },
        jwt_secret,
        algorithm="HS256",
    )
    app_slug = settings.GITHUB_APP_NAME.strip().strip("/")
    return {
        "install_url": f"https://github.com/apps/{quote(app_slug, safe='')}/installations/new?state={quote(state, safe='')}",
        "state": state,
    }


def handle_github_callback(db: Session, installation_id: str, state: str, jwt_secret: str) -> dict:
    try:
        payload = jwt.decode(state, jwt_secret, algorithms=["HS256"])
    except Exception:
        raise HTTPException(status_code=400, detail="GitHub install state is invalid or expired")
    if payload.get("type") != "github_app_install":
        raise HTTPException(status_code=400, detail="GitHub install state is invalid")
    user_id = UUID(str(payload["sub"]))
    token_data = installation_token_for_id(installation_id)
    installation = _app_request("GET", f"/app/installations/{installation_id}")
    account = installation.get("account") or {}
    repos = list_installation_repositories_with_token(token_data["token"])
    metadata = {
        "installation_id": str(installation_id),
        "account": {
            "login": account.get("login"),
            "type": account.get("type"),
            "id": account.get("id"),
            "avatar_url": account.get("avatar_url"),
        },
        "permissions": installation.get("permissions") or {},
        "repository_selection": installation.get("repository_selection"),
        "repositories": repos.get("repositories") or [],
        "connected_at": _now(),
    }
    integration = _integration(db, user_id)
    if not integration:
        integration = Integration(
            user_id=user_id,
            provider="github",
            provider_user_id=str(installation_id),
            status="active",
            scopes=["github_app_installation"],
            metadata_json=metadata,
        )
        db.add(integration)
    else:
        integration.provider_user_id = str(installation_id)
        integration.status = "active"
        integration.scopes = ["github_app_installation"]
        integration.metadata_json = metadata
    db.add(AuditLog(
        user_id=user_id,
        event_type="github_connected",
        entity_type="integration",
        actor_type="user",
        actor_id=str(user_id),
        action="Connected GitHub App installation",
        new_value={"installation_id": str(installation_id), "account": metadata["account"]},
    ))
    db.commit()
    return {"connected": True, **metadata}


def installation_token_for_id(installation_id: str) -> dict:
    data = _app_request("POST", f"/app/installations/{quote(str(installation_id), safe='')}/access_tokens")
    token = data.get("token")
    if not token:
        raise HTTPException(status_code=400, detail="GitHub installation token was not returned")
    return {"token": token, "expires_at": data.get("expires_at"), "permissions": data.get("permissions") or {}}


def installation_token(db: Session, user_id: UUID) -> dict:
    integration = _integration(db, user_id)
    metadata = integration.metadata_json if integration else {}
    installation_id = metadata.get("installation_id")
    if installation_id:
        return installation_token_for_id(str(installation_id))
    if _dev_token():
        return {"token": _dev_token(), "expires_at": None, "permissions": {"dev_fallback": True}}
    raise HTTPException(status_code=409, detail="GitHub is not connected. Install the NEXUS GitHub App first.")


def list_installation_repositories_with_token(token: str) -> dict:
    data = _github_request("GET", "/installation/repositories?per_page=100", token)
    repos = []
    for repo in data.get("repositories") or []:
        repos.append({
            "id": repo.get("id"),
            "full_name": repo.get("full_name"),
            "name": repo.get("name"),
            "owner": (repo.get("owner") or {}).get("login"),
            "private": repo.get("private"),
            "default_branch": repo.get("default_branch") or "main",
            "html_url": repo.get("html_url"),
        })
    return {"repositories": repos}


def list_repositories(db: Session, user_id: UUID) -> dict:
    token_data = installation_token(db, user_id)
    repos = list_installation_repositories_with_token(token_data["token"])
    integration = _integration(db, user_id)
    if integration:
        metadata = dict(integration.metadata_json or {})
        metadata["repositories"] = repos["repositories"]
        metadata["repositories_refreshed_at"] = _now()
        integration.metadata_json = metadata
        db.commit()
    return repos


def _repo_owner_name(repo_full_name: str) -> tuple[str, str]:
    parts = [part for part in str(repo_full_name or "").strip("/").split("/") if part]
    if len(parts) != 2:
        raise HTTPException(status_code=400, detail="Repository must be owner/name")
    return parts[0], parts[1]


def _importable_project_file(path: str) -> bool:
    name = Path(path).name.lower()
    suffix = Path(path).suffix.lower()
    if name in {"package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock", "dockerfile", ".gitignore", ".env.example"}:
        return True
    return suffix in {".py", ".js", ".ts", ".tsx", ".html", ".css", ".json", ".md", ".txt", ".csv", ".yml", ".yaml", ".toml", ".ini"}


def _branch_sha(owner: str, repo: str, branch: str, token: str) -> str:
    ref = _github_request("GET", f"/repos/{owner}/{repo}/git/ref/heads/{quote(branch, safe='')}", token)
    return ref.get("object", {}).get("sha") or ""


def _default_branch(owner: str, repo: str, token: str) -> str:
    data = _github_request("GET", f"/repos/{owner}/{repo}", token)
    return data.get("default_branch") or "main"


def import_repository(
    db: Session,
    user_id: UUID,
    session: CodeSession,
    repo_full_name: str,
    branch: str | None = None,
    max_files: int = 180,
) -> dict:
    token = installation_token(db, user_id)["token"]
    owner, repo = _repo_owner_name(repo_full_name)
    target_branch = branch or _default_branch(owner, repo, token)
    tree = _github_request("GET", f"/repos/{owner}/{repo}/git/trees/{quote(target_branch, safe='')}?recursive=1", token)
    imported = []
    skipped = 0
    for item in tree.get("tree") or []:
        path = item.get("path") or ""
        if item.get("type") != "blob" or not _importable_project_file(path) or item.get("size", 0) > 1_500_000:
            skipped += 1
            continue
        if len(imported) >= max_files:
            skipped += 1
            continue
        blob = _github_request("GET", f"/repos/{owner}/{repo}/git/blobs/{item.get('sha')}", token)
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
            metadata_json={"github_repo": repo_full_name, "github_branch": target_branch, "github_sha": item.get("sha")},
        )
        db.add(record)
        db.flush()
        imported.append({"id": str(record.id), "filename": path, "size_bytes": len(content), "github_sha": item.get("sha")})

    metadata = dict(session.metadata_json or {})
    metadata["git"] = {
        "provider": "github_app",
        "repo_full_name": repo_full_name,
        "repo_url": f"https://github.com/{repo_full_name}",
        "owner": owner,
        "repo": repo,
        "default_branch": target_branch,
        "selected_branch": target_branch,
        "imported_at": _now(),
    }
    existing = [str(value) for value in (session.file_ids or [])]
    session.file_ids = existing + [item["id"] for item in imported]
    session.metadata_json = metadata
    db.add(AuditLog(
        user_id=user_id,
        session_id=session.id,
        event_type="github_import",
        entity_type="code_session",
        entity_id=session.id,
        actor_type="user",
        actor_id=str(user_id),
        action="Imported GitHub repository through GitHub App",
        new_value={"repo": repo_full_name, "branch": target_branch, "imported": len(imported), "skipped": skipped},
    ))
    db.commit()
    return {"imported": imported, "skipped": skipped, "file_ids": session.file_ids, "git": metadata["git"]}


def create_branch(db: Session, user_id: UUID, session: CodeSession, branch_name: str | None = None, base_branch: str | None = None) -> dict:
    token = installation_token(db, user_id)["token"]
    metadata = dict(session.metadata_json or {})
    git = metadata.get("git") or {}
    repo_full_name = git.get("repo_full_name") or re.sub(r"^https://github.com/", "", str(git.get("repo_url") or ""))
    owner, repo = _repo_owner_name(repo_full_name)
    base = base_branch or git.get("default_branch") or _default_branch(owner, repo, token)
    safe = re.sub(r"[^a-zA-Z0-9._/-]+", "-", branch_name or f"nexus/{session.title or 'workspace'}-{uuid.uuid4().hex[:8]}").strip("-")
    if not safe.startswith("nexus/"):
        safe = f"nexus/{safe[:70]}"
    base_sha = _branch_sha(owner, repo, base, token)
    if not base_sha:
        raise HTTPException(status_code=400, detail=f"Could not resolve base branch {base}")
    try:
        _github_request("POST", f"/repos/{owner}/{repo}/git/refs", token, {"ref": f"refs/heads/{safe}", "sha": base_sha})
    except HTTPException as exc:
        if "Reference already exists" not in str(exc.detail):
            raise
    git.update({"working_branch": safe, "base_branch": base, "base_sha": base_sha, "branch_created_at": _now()})
    metadata["git"] = git
    session.metadata_json = metadata
    db.add(AuditLog(
        user_id=user_id,
        session_id=session.id,
        event_type="github_branch_created",
        entity_type="code_session",
        entity_id=session.id,
        actor_type="user",
        actor_id=str(user_id),
        action="Created GitHub branch",
        new_value={"repo": repo_full_name, "branch": safe, "base": base},
    ))
    db.commit()
    return {"repo_full_name": repo_full_name, "branch_name": safe, "base_branch": base, "base_sha": base_sha}


def _file_sha(owner: str, repo: str, path: str, branch: str, token: str) -> str | None:
    try:
        data = _github_request("GET", f"/repos/{owner}/{repo}/contents/{quote(path, safe='/')}?ref={quote(branch, safe='')}", token)
        return data.get("sha")
    except HTTPException as exc:
        if "Not Found" in str(exc.detail):
            return None
        raise


def _commit_files_from_metadata(session: CodeSession) -> list[dict]:
    metadata = session.metadata_json or {}
    files = metadata.get("last_applied_files") or []
    if not files:
        files = [{"filename": name} for name in ((metadata.get("last_pr_plan") or {}).get("changed_files") or [])]
    return [item for item in files if item.get("filename")]


def commit_approved_changes(
    db: Session,
    user_id: UUID,
    session: CodeSession,
    message: str | None = None,
) -> dict:
    token = installation_token(db, user_id)["token"]
    metadata = dict(session.metadata_json or {})
    git = metadata.get("git") or {}
    repo_full_name = git.get("repo_full_name") or re.sub(r"^https://github.com/", "", str(git.get("repo_url") or ""))
    owner, repo = _repo_owner_name(repo_full_name)
    branch = git.get("working_branch")
    if not branch:
        branch = create_branch(db, user_id, session).get("branch_name")
        metadata = dict(session.metadata_json or {})
        git = metadata.get("git") or {}

    approved_files = _commit_files_from_metadata(session)
    if not approved_files:
        raise HTTPException(status_code=400, detail="No approved applied files are available to commit. Apply a reviewed patch first.")
    filenames = {item["filename"] for item in approved_files}
    records = [record for record in db.query(FileReference).filter(FileReference.user_id == user_id).all() if record.filename in filenames and str(record.id) in set(session.file_ids or [])]
    if not records:
        raise HTTPException(status_code=400, detail="Approved files are no longer available in the workspace.")

    commit_message = (message or (metadata.get("last_pr_plan") or {}).get("commit_message") or session.title or "NEXUS Code workspace changes").strip()
    committed = []
    latest_sha = None
    for record in records:
        content = get_file_text(db, user_id, record.id)
        payload = {
            "message": commit_message,
            "content": base64.b64encode(content.encode("utf-8")).decode("ascii"),
            "branch": branch,
        }
        existing_sha = _file_sha(owner, repo, record.filename, branch, token)
        if existing_sha:
            payload["sha"] = existing_sha
        result = _github_request("PUT", f"/repos/{owner}/{repo}/contents/{quote(record.filename, safe='/')}", token, payload)
        latest_sha = result.get("commit", {}).get("sha") or latest_sha
        committed.append({
            "filename": record.filename,
            "commit_sha": result.get("commit", {}).get("sha"),
            "html_url": result.get("content", {}).get("html_url"),
        })

    git.update({"latest_commit_sha": latest_sha, "latest_commit_message": commit_message, "committed_at": _now()})
    metadata["git"] = git
    session.metadata_json = metadata
    db.add(AuditLog(
        user_id=user_id,
        session_id=session.id,
        event_type="github_commit",
        entity_type="code_session",
        entity_id=session.id,
        actor_type="user",
        actor_id=str(user_id),
        action="Committed approved NEXUS Code changes",
        new_value={"repo": repo_full_name, "branch": branch, "files": [item["filename"] for item in committed], "commit_sha": latest_sha},
    ))
    db.commit()
    return {"repo_full_name": repo_full_name, "branch_name": branch, "commit_sha": latest_sha, "committed": committed}


def open_pull_request(db: Session, user_id: UUID, session: CodeSession, title: str | None = None, body: str | None = None) -> dict:
    token = installation_token(db, user_id)["token"]
    metadata = dict(session.metadata_json or {})
    git = metadata.get("git") or {}
    repo_full_name = git.get("repo_full_name") or re.sub(r"^https://github.com/", "", str(git.get("repo_url") or ""))
    owner, repo = _repo_owner_name(repo_full_name)
    branch = git.get("working_branch")
    if not branch:
        raise HTTPException(status_code=400, detail="Create and commit to a working branch before opening a PR.")
    if not git.get("latest_commit_sha"):
        raise HTTPException(status_code=400, detail="Commit approved changes before opening a PR.")
    base = git.get("base_branch") or git.get("default_branch") or "main"
    plan = metadata.get("last_pr_plan") or {}
    payload = {
        "title": title or plan.get("pr_title") or git.get("latest_commit_message") or "NEXUS Code workspace changes",
        "head": branch,
        "base": base,
        "body": body or plan.get("pr_body") or "Prepared by NEXUS Code.",
    }
    pull = _github_request("POST", f"/repos/{owner}/{repo}/pulls", token, payload)
    pr = {
        "repo_full_name": repo_full_name,
        "pull_request_url": pull.get("html_url"),
        "pull_request_number": pull.get("number"),
        "head_branch": branch,
        "base_branch": base,
        "status": "opened",
        "opened_at": _now(),
    }
    git["pull_request"] = pr
    metadata["git"] = git
    metadata["last_opened_pr"] = pr
    session.metadata_json = metadata
    db.add(AuditLog(
        user_id=user_id,
        session_id=session.id,
        event_type="github_pr_opened",
        entity_type="code_session",
        entity_id=session.id,
        actor_type="user",
        actor_id=str(user_id),
        action="Opened GitHub pull request",
        new_value=pr,
    ))
    db.commit()
    return pr


def pr_status(db: Session, user_id: UUID, session: CodeSession) -> dict:
    token = installation_token(db, user_id)["token"]
    metadata = session.metadata_json or {}
    git = metadata.get("git") or {}
    repo_full_name = git.get("repo_full_name") or re.sub(r"^https://github.com/", "", str(git.get("repo_url") or ""))
    owner, repo = _repo_owner_name(repo_full_name)
    pr = git.get("pull_request") or metadata.get("last_opened_pr") or {}
    commit_sha = git.get("latest_commit_sha")
    checks = {}
    if commit_sha:
        checks = _github_request("GET", f"/repos/{owner}/{repo}/commits/{quote(commit_sha, safe='')}/check-runs", token)
    return {
        "repo_full_name": repo_full_name,
        "pull_request": pr,
        "latest_commit_sha": commit_sha,
        "checks": [
            {
                "name": item.get("name"),
                "status": item.get("status"),
                "conclusion": item.get("conclusion"),
                "html_url": item.get("html_url"),
            }
            for item in (checks.get("check_runs") or [])
        ],
        "checked_at": _now(),
    }


def create_pull_request(
    db: Session,
    user_id: UUID,
    project,
    session: CodeSession,
    branch_name: str,
    title: str,
    body: str,
) -> dict:
    """Legacy compatibility wrapper for the older /create-pr endpoint."""
    create_branch(db, user_id, session, branch_name, project.default_branch if project else None)
    commit_approved_changes(db, user_id, session, title)
    pr = open_pull_request(db, user_id, session, title, body)
    return {"success": True, "pr_url": pr.get("pull_request_url"), "pr_number": pr.get("pull_request_number"), **pr}
