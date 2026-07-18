from __future__ import annotations

import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from services.shared.arceus_core_models import ArceusToolProfile

from .api_schemas import ToolExecutionRequest
from .service import stable_hash


SECRET_PATTERNS = (
    re.compile(r"(?i)(Bearer\s+)[^\s'\"`]+"),
    re.compile(r"(?i)((?:password|token|secret)=)[^\s'\"`]+"),
    re.compile(r"(?i)sk-[A-Za-z0-9_\-]{12,}"),
)


@dataclass(frozen=True)
class ToolExecutionResult:
    status: str
    output: dict[str, Any]
    evidence: dict[str, Any]
    latency_ms: int
    output_hash: str


class ToolAdapter(Protocol):
    def execute(self, *, profile: ArceusToolProfile, request: ToolExecutionRequest) -> ToolExecutionResult:
        ...


def redact_output(value: str) -> str:
    redacted = value or ""
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED]", redacted)
    return redacted


def resolve_workspace_path(workspace_root: str, relative_path: str = ".") -> Path:
    root = Path(workspace_root).expanduser().resolve()
    candidate = (root / relative_path).resolve()
    if root != candidate and root not in candidate.parents:
        raise ValueError("Path escapes execution boundary.")
    return candidate


class ReadOnlyShellToolAdapter:
    def execute(self, *, profile: ArceusToolProfile, request: ToolExecutionRequest) -> ToolExecutionResult:
        if profile.side_effect_class != "READ_ONLY":
            raise ValueError("ReadOnlyShellToolAdapter only supports READ_ONLY tools.")
        started = time.perf_counter()
        if request.action_key == "search":
            output = self._search(request)
        elif request.action_key == "list":
            output = self._list(request)
        elif request.action_key == "read":
            output = self._read(request)
        else:
            raise ValueError(f"Unsupported read-only action: {request.action_key}")
        latency_ms = int((time.perf_counter() - started) * 1000)
        evidence = {
            "tool_key": request.tool_key,
            "action_key": request.action_key,
            "side_effect_class": profile.side_effect_class,
            "dry_run": request.dry_run,
            "rollback_required": False,
        }
        return ToolExecutionResult(
            status="completed",
            output=output,
            evidence=evidence,
            latency_ms=latency_ms,
            output_hash=stable_hash(output),
        )

    def _workspace_and_path(self, request: ToolExecutionRequest) -> tuple[Path, Path]:
        workspace_root = request.arguments.get("workspace_root")
        if not workspace_root:
            raise ValueError("workspace_root is required for read-only tool execution.")
        relative_path = str(request.arguments.get("path") or ".")
        root = Path(str(workspace_root)).expanduser().resolve()
        return root, resolve_workspace_path(str(root), relative_path)

    def _search(self, request: ToolExecutionRequest) -> dict[str, Any]:
        root, path = self._workspace_and_path(request)
        query = str(request.arguments.get("query") or "").strip()
        if not query:
            raise ValueError("query is required for search.")
        max_results = int(request.arguments.get("max_results") or 100)
        if request.dry_run:
            return {"would_run": "rg", "query": query, "path": str(path), "max_results": max_results}
        cmd = ["rg", "--line-number", "--no-heading", "--color", "never", "--", query, str(path)]
        completed = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=request.timeout_seconds, check=False)
        lines = redact_output("\n".join(filter(None, [completed.stdout, completed.stderr]))).splitlines()
        return {
            "return_code": completed.returncode,
            "matches": lines[:max_results],
            "truncated": len(lines) > max_results,
        }

    def _list(self, request: ToolExecutionRequest) -> dict[str, Any]:
        _, path = self._workspace_and_path(request)
        max_results = int(request.arguments.get("max_results") or 200)
        if request.dry_run:
            return {"would_list": str(path), "max_results": max_results}
        if not path.exists():
            raise ValueError("Path does not exist.")
        entries = []
        for item in sorted(path.iterdir(), key=lambda value: (not value.is_dir(), value.name.lower()))[:max_results]:
            entries.append({"name": item.name, "type": "directory" if item.is_dir() else "file", "size": item.stat().st_size if item.is_file() else None})
        return {"path": str(path), "entries": entries, "truncated": len(entries) >= max_results}

    def _read(self, request: ToolExecutionRequest) -> dict[str, Any]:
        _, path = self._workspace_and_path(request)
        max_bytes = int(request.arguments.get("max_bytes") or 20000)
        if request.dry_run:
            return {"would_read": str(path), "max_bytes": max_bytes}
        if not path.is_file():
            raise ValueError("Path is not a file.")
        data = path.read_bytes()[:max_bytes]
        text = redact_output(data.decode("utf-8", errors="replace"))
        return {"path": str(path), "content": text, "truncated": path.stat().st_size > max_bytes}


def adapter_for_tool(profile: ArceusToolProfile) -> ToolAdapter:
    adapter_type = (profile.adapter_type or "").lower()
    if adapter_type in {"shell", "read_only_shell", "search", "filesystem_read"}:
        return ReadOnlyShellToolAdapter()
    raise ValueError(f"Unsupported tool adapter: {profile.adapter_type}")
