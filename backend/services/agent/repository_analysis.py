from __future__ import annotations

import os
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .arceus_runtime.repository.service import index_repository_path


router = APIRouter(prefix="/api/v1/repositories", tags=["repository-analysis"])

_ANALYSIS_CACHE: dict[str, dict[str, Any]] = {}


class RepositoryAnalyzeRequest(BaseModel):
    workspace_id: str = Field(default="local-workspace", min_length=1, max_length=240)
    root_path: str = Field(min_length=1, max_length=2_000)
    force: bool = False
    max_files: int = Field(default=2_000, ge=1, le=20_000)
    max_file_bytes: int = Field(default=250_000, ge=1_000, le=1_000_000)


class RepositoryAnalyzeResponse(BaseModel):
    repository_id: str
    workspace_id: str
    status: str
    cached: bool = False
    scanned_files: int
    skipped_files: int
    languages: list[str]
    frameworks: list[str]
    package_managers: list[str]
    entry_points: list[str]
    services: list[str]
    test_commands: list[str]
    database_usage: list[str] = Field(default_factory=list)
    authentication: list[str] = Field(default_factory=list)
    architecture_style: str | None = None
    summary: str
    cache_key: str
    analyzed_at: str


def _git_commit(root: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        return result.stdout.strip() if result.returncode == 0 else "no-git"
    except Exception:
        return "no-git"


def _fingerprint(root: Path, max_files: int = 5_000) -> str:
    count = 0
    latest = 0
    total_size = 0
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [
            name for name in dirnames
            if name not in {".git", "node_modules", ".next", "dist", "build", "__pycache__", ".pytest_cache", ".venv", "venv"}
        ]
        for filename in filenames:
            if count >= max_files:
                break
            path = Path(current) / filename
            try:
                stat = path.stat()
            except OSError:
                continue
            count += 1
            latest = max(latest, int(stat.st_mtime))
            total_size += int(stat.st_size)
        if count >= max_files:
            break
    return f"{count}:{latest}:{total_size}"


def _paths(index: dict[str, Any]) -> set[str]:
    return {str(item.get("path") or "") for item in index.get("files") or [] if item.get("path")}


def _entry_points(paths: set[str]) -> list[str]:
    candidates = [
        "frontend/src/app/page.tsx",
        "src/app/page.tsx",
        "pages/index.tsx",
        "src/main.tsx",
        "src/index.tsx",
        "backend/services/agent/main.py",
        "backend/services/auth/main.py",
        "backend/services/goals/main.py",
        "main.py",
        "app.py",
        "server.py",
    ]
    found = [path for path in candidates if path in paths]
    if not found:
        found = [
            path for path in sorted(paths)
            if PurePosixPath(path).name.lower() in {"main.py", "app.py", "server.py", "page.tsx", "index.tsx", "main.tsx"}
        ][:8]
    return found[:12]


def _services(paths: set[str]) -> list[str]:
    services = set()
    for path in paths:
        parts = PurePosixPath(path).parts
        if not parts:
            continue
        if parts[0] in {"frontend", "desktop", "backend"}:
            services.add(parts[0])
        if len(parts) >= 3 and parts[0] == "backend" and parts[1] == "services":
            services.add(parts[2])
        if len(parts) >= 2 and parts[0] in {"apps", "packages", "services"}:
            services.add(parts[1])
    return sorted(services)[:20]


def _test_commands(paths: set[str], package_managers: list[str]) -> list[str]:
    commands: list[str] = []
    if "package.json" in paths:
        commands.extend(["npm run lint", "npm run build", "npm test"])
    if "pnpm-lock.yaml" in paths or "pnpm-workspace.yaml" in paths:
        commands.extend(["pnpm lint", "pnpm build", "pnpm test"])
    if "pytest.ini" in paths or "pyproject.toml" in paths or "requirements.txt" in paths or "pip" in package_managers:
        commands.extend(["python -m compileall .", "python -m pytest"])
    if "go.mod" in paths:
        commands.append("go test ./...")
    if "Cargo.toml" in paths:
        commands.append("cargo test")
    return list(dict.fromkeys(commands))[:8]


def _manifest_text(root: Path, paths: set[str]) -> str:
    manifest_names = {
        "package.json",
        "requirements.txt",
        "pyproject.toml",
        "poetry.lock",
        "Pipfile",
        "go.mod",
        "Cargo.toml",
    }
    chunks: list[str] = []
    for path in sorted(paths):
        if PurePosixPath(path).name not in manifest_names:
            continue
        try:
            chunks.append((root / path).read_text(encoding="utf-8", errors="ignore")[:20_000])
        except OSError:
            continue
    return "\n".join(chunks).lower()


def _signal_counts(index: dict[str, Any], manifest_text: str = "") -> Counter:
    signals: Counter = Counter()
    signal_sources = [manifest_text]
    for item in index.get("files") or []:
        path = str(item.get("path") or "").lower()
        imports = " ".join(str(value).lower() for value in item.get("imports") or [])
        signal_sources.append(f"{path} {imports}")
    for text in signal_sources:
        for name, keywords in {
            "PostgreSQL": ("postgres", "psycopg", "pgvector", "sqlalchemy"),
            "SQLite": ("sqlite",),
            "Redis": ("redis",),
            "MongoDB": ("mongo", "mongoose"),
            "Clerk": ("clerk", "@clerk"),
            "JWT": ("jwt", "jsonwebtoken", "pyjwt"),
            "OAuth": ("oauth", "openid", "google-auth"),
            "NextAuth": ("nextauth", "auth.js"),
        }.items():
            if any(keyword in text for keyword in keywords):
                signals[name] += 1
    return signals


def analyze_repository_path(payload: RepositoryAnalyzeRequest) -> dict[str, Any]:
    root = Path(payload.root_path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError("Repository root does not exist or is not a directory.")

    commit = _git_commit(root)
    fingerprint = _fingerprint(root)
    cache_key = f"{root}:{commit}:{fingerprint}"
    if not payload.force and cache_key in _ANALYSIS_CACHE:
        cached = dict(_ANALYSIS_CACHE[cache_key])
        cached["cached"] = True
        cached["analyzed_at"] = datetime.now(timezone.utc).isoformat()
        return cached

    index = index_repository_path(
        str(root),
        max_files=payload.max_files,
        max_file_bytes=payload.max_file_bytes,
    )
    profile = index["profile"]
    paths = _paths(index)
    package_managers = [item["name"] for item in profile.get("package_managers") or []]
    frameworks = [item["name"] for item in profile.get("frameworks") or []]
    languages = [
        str(item["language"]).replace("typescript", "TypeScript").replace("javascript", "JavaScript").replace("python", "Python")
        for item in sorted(profile.get("languages") or [], key=lambda value: value.get("file_count", 0), reverse=True)
    ]
    signals = _signal_counts(index, _manifest_text(root, paths))
    database_usage = [name for name in ["PostgreSQL", "SQLite", "Redis", "MongoDB"] if signals[name] > 0]
    authentication = [name for name in ["Clerk", "JWT", "OAuth", "NextAuth"] if signals[name] > 0]
    services = _services(paths)
    entry_points = _entry_points(paths)
    architecture = index.get("architecture") or {}

    summary_bits = []
    if frameworks:
        summary_bits.append(", ".join(frameworks[:3]))
    if services:
        summary_bits.append(f"{len(services)} service/module area(s)")
    if database_usage:
        summary_bits.append(f"data layer: {', '.join(database_usage)}")
    summary = (
        f"{profile.get('name')} is a {architecture.get('style') or profile.get('repository_type', 'repository')} with "
        + (", ".join(summary_bits) if summary_bits else f"{profile.get('indexed_file_count', 0)} indexed files")
        + "."
    )

    result = {
        "repository_id": profile["id"],
        "workspace_id": payload.workspace_id,
        "status": "completed",
        "cached": False,
        "scanned_files": int(profile.get("indexed_file_count") or 0),
        "skipped_files": int(profile.get("skipped_file_count") or 0),
        "languages": languages,
        "frameworks": frameworks,
        "package_managers": package_managers,
        "entry_points": entry_points,
        "services": services,
        "test_commands": _test_commands(paths, package_managers),
        "database_usage": database_usage,
        "authentication": authentication,
        "architecture_style": architecture.get("style"),
        "summary": summary,
        "cache_key": cache_key,
        "analyzed_at": datetime.now(timezone.utc).isoformat(),
    }
    _ANALYSIS_CACHE[cache_key] = dict(result)
    return result


@router.post("/analyze", response_model=RepositoryAnalyzeResponse)
def analyze_repository(payload: RepositoryAnalyzeRequest):
    try:
        return analyze_repository_path(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail={"error_class": "repository_invalid", "message": str(exc)}) from exc
