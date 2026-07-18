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


class FilesystemMutationToolAdapter:
    def execute(self, *, profile: ArceusToolProfile, request: ToolExecutionRequest) -> ToolExecutionResult:
        if profile.side_effect_class not in {"LOCAL_MUTATION", "REPOSITORY_MUTATION"}:
            raise ValueError("FilesystemMutationToolAdapter only supports local or repository mutations.")
        started = time.perf_counter()
        if request.action_key == "create_file":
            output = self._create_file(request)
        elif request.action_key == "modify_file":
            output = self._modify_file(request)
        elif request.action_key == "mkdir":
            output = self._mkdir(request)
        else:
            raise ValueError(f"Unsupported filesystem mutation action: {request.action_key}")
        latency_ms = int((time.perf_counter() - started) * 1000)
        evidence = {
            "tool_key": request.tool_key,
            "action_key": request.action_key,
            "side_effect_class": profile.side_effect_class,
            "dry_run": request.dry_run,
            "rollback_required": True,
            "rollback": output.get("rollback"),
            "idempotency_key": request.idempotency_key,
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
            raise ValueError("workspace_root is required for filesystem mutation.")
        relative_path = str(request.arguments.get("path") or "")
        if not relative_path:
            raise ValueError("path is required for filesystem mutation.")
        root = Path(str(workspace_root)).expanduser().resolve()
        return root, resolve_workspace_path(str(root), relative_path)

    def _existing_file_snapshot(self, path: Path) -> dict[str, Any]:
        if not path.exists():
            return {"operation": "create", "existed": False, "path": str(path)}
        if not path.is_file():
            raise ValueError("Path exists and is not a file.")
        content = path.read_text(encoding="utf-8", errors="replace")
        return {
            "operation": "modify",
            "existed": True,
            "path": str(path),
            "original_content": content,
            "original_hash": stable_hash(content),
        }

    def _create_file(self, request: ToolExecutionRequest) -> dict[str, Any]:
        _, path = self._workspace_and_path(request)
        content = str(request.arguments.get("content") or "")
        overwrite = bool(request.arguments.get("overwrite", False))
        rollback = self._existing_file_snapshot(path)
        if rollback["existed"] and not overwrite:
            raise ValueError("File already exists; set overwrite=true to replace it.")
        if request.dry_run:
            return {"would_create": str(path), "bytes": len(content.encode("utf-8")), "rollback": rollback}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {
            "path": str(path),
            "operation": "create_file",
            "bytes": len(content.encode("utf-8")),
            "content_hash": stable_hash(content),
            "rollback": rollback,
        }

    def _modify_file(self, request: ToolExecutionRequest) -> dict[str, Any]:
        _, path = self._workspace_and_path(request)
        content = str(request.arguments.get("content") or "")
        rollback = self._existing_file_snapshot(path)
        if not rollback["existed"]:
            raise ValueError("File does not exist; use create_file for new files.")
        expected_hash = request.arguments.get("expected_hash")
        if expected_hash and rollback.get("original_hash") != expected_hash:
            raise ValueError("File hash changed since the mutation was prepared.")
        if request.dry_run:
            return {"would_modify": str(path), "bytes": len(content.encode("utf-8")), "rollback": rollback}
        path.write_text(content, encoding="utf-8")
        return {
            "path": str(path),
            "operation": "modify_file",
            "bytes": len(content.encode("utf-8")),
            "content_hash": stable_hash(content),
            "rollback": rollback,
        }

    def _mkdir(self, request: ToolExecutionRequest) -> dict[str, Any]:
        _, path = self._workspace_and_path(request)
        existed = path.exists()
        if existed and not path.is_dir():
            raise ValueError("Path exists and is not a directory.")
        rollback = {"operation": "mkdir", "existed": existed, "path": str(path)}
        if request.dry_run:
            return {"would_mkdir": str(path), "rollback": rollback}
        path.mkdir(parents=True, exist_ok=True)
        return {"path": str(path), "operation": "mkdir", "rollback": rollback}


class GitToolAdapter:
    def execute(self, *, profile: ArceusToolProfile, request: ToolExecutionRequest) -> ToolExecutionResult:
        if profile.side_effect_class not in {"READ_ONLY", "REPOSITORY_MUTATION"}:
            raise ValueError("GitToolAdapter only supports read-only or repository mutation tools.")
        started = time.perf_counter()
        if request.action_key == "status":
            output = self._status(request)
        elif request.action_key == "diff":
            output = self._diff(request)
        elif request.action_key == "create_branch":
            if profile.side_effect_class != "REPOSITORY_MUTATION":
                raise ValueError("create_branch requires a REPOSITORY_MUTATION git profile.")
            output = self._create_branch(request)
        elif request.action_key == "commit_approved":
            if profile.side_effect_class != "REPOSITORY_MUTATION":
                raise ValueError("commit_approved requires a REPOSITORY_MUTATION git profile.")
            output = self._commit_approved(request)
        else:
            raise ValueError(f"Unsupported git action: {request.action_key}")
        latency_ms = int((time.perf_counter() - started) * 1000)
        rollback_required = request.action_key in {"create_branch", "commit_approved"} and bool(output.get("rollback"))
        evidence = {
            "tool_key": request.tool_key,
            "action_key": request.action_key,
            "side_effect_class": profile.side_effect_class,
            "dry_run": request.dry_run,
            "rollback_required": rollback_required,
            "rollback": output.get("rollback"),
            "idempotency_key": request.idempotency_key,
        }
        return ToolExecutionResult(
            status="completed",
            output=output,
            evidence=evidence,
            latency_ms=latency_ms,
            output_hash=stable_hash(output),
        )

    def _workspace_root(self, request: ToolExecutionRequest) -> Path:
        workspace_root = request.arguments.get("workspace_root")
        if not workspace_root:
            raise ValueError("workspace_root is required for git tool execution.")
        return Path(str(workspace_root)).expanduser().resolve()

    def _workspace_relative_path(self, request: ToolExecutionRequest) -> str | None:
        relative_path = request.arguments.get("path")
        if relative_path is None:
            return None
        root = self._workspace_root(request)
        path = resolve_workspace_path(str(root), str(relative_path))
        return "." if path == root else path.relative_to(root).as_posix()

    def _relative_path_from_value(self, request: ToolExecutionRequest, path_value: Any) -> str:
        root = self._workspace_root(request)
        path = resolve_workspace_path(str(root), str(path_value))
        if path == root:
            raise ValueError("Git artifact path must identify a file, not the workspace root.")
        return path.relative_to(root).as_posix()

    def _run_git(self, request: ToolExecutionRequest, args: list[str]) -> dict[str, Any]:
        root = self._workspace_root(request)
        command = ["git", *args]
        if request.dry_run:
            return {"would_run": command, "cwd": str(root)}
        completed = subprocess.run(
            command,
            cwd=root,
            capture_output=True,
            text=True,
            timeout=request.timeout_seconds,
            check=False,
        )
        combined = redact_output("\n".join(filter(None, [completed.stdout, completed.stderr])))
        return {
            "command": command,
            "cwd": str(root),
            "return_code": completed.returncode,
            "lines": combined.splitlines(),
        }

    def _status(self, request: ToolExecutionRequest) -> dict[str, Any]:
        return self._run_git(request, ["status", "--porcelain=v1", "--branch"])

    def _diff(self, request: ToolExecutionRequest) -> dict[str, Any]:
        args = ["diff"]
        if bool(request.arguments.get("staged", False)):
            args.append("--cached")
        relative_path = self._workspace_relative_path(request)
        if relative_path:
            args.extend(["--", relative_path])
        return self._run_git(request, args)

    def _validate_branch_name(self, branch: str) -> None:
        if not branch:
            raise ValueError("branch is required for create_branch.")
        if not re.fullmatch(r"[A-Za-z0-9._/\-]+", branch):
            raise ValueError("branch contains unsupported characters.")
        invalid = branch.startswith("/") or branch.endswith("/") or ".." in branch or branch.endswith(".lock")
        invalid = invalid or "//" in branch or branch.startswith("-")
        if invalid:
            raise ValueError("branch name is not allowed.")

    def _create_branch(self, request: ToolExecutionRequest) -> dict[str, Any]:
        branch = str(request.arguments.get("branch") or "").strip()
        self._validate_branch_name(branch)
        start_point = request.arguments.get("start_point")
        verify = self._run_git(request, ["rev-parse", "--verify", branch])
        if request.dry_run:
            return {"would_create_branch": branch, "verify": verify}
        if verify["return_code"] == 0:
            return {"branch": branch, "operation": "create_branch", "created": False, "existed": True}
        args = ["branch", branch]
        if start_point:
            args.append(str(start_point))
        result = self._run_git(request, args)
        if result["return_code"] != 0:
            raise ValueError("Git branch creation failed: " + "\n".join(result["lines"]))
        return {
            "branch": branch,
            "operation": "create_branch",
            "created": True,
            "existed": False,
            "result": result,
            "rollback": {"operation": "delete_branch", "branch": branch},
        }

    def _approved_artifact_paths(self, request: ToolExecutionRequest) -> list[str]:
        approved_artifacts = request.arguments.get("approved_artifacts")
        if not isinstance(approved_artifacts, list) or not approved_artifacts:
            raise ValueError("approved_artifacts is required for commit_approved.")
        paths: list[str] = []
        for artifact in approved_artifacts:
            if not isinstance(artifact, dict) or not artifact.get("path"):
                raise ValueError("Each approved artifact must include a path.")
            relative_path = self._relative_path_from_value(request, artifact["path"])
            if relative_path not in paths:
                paths.append(relative_path)
        return paths

    def _verify_artifact_hashes(self, request: ToolExecutionRequest) -> None:
        root = self._workspace_root(request)
        for artifact in request.arguments.get("approved_artifacts") or []:
            expected_hash = artifact.get("expected_hash")
            if not expected_hash:
                continue
            relative_path = self._relative_path_from_value(request, artifact["path"])
            path = root / relative_path
            if not path.is_file():
                raise ValueError(f"Approved artifact is not a file: {relative_path}")
            content = path.read_text(encoding="utf-8", errors="replace")
            if stable_hash(content) != expected_hash:
                raise ValueError(f"Approved artifact hash changed before commit: {relative_path}")

    def _name_only(self, request: ToolExecutionRequest, args: list[str]) -> list[str]:
        result = self._run_git(request, args)
        if result.get("return_code") != 0:
            raise ValueError("Git inspection failed: " + "\n".join(result.get("lines") or []))
        return [line.strip() for line in result.get("lines") or [] if line.strip()]

    def _commit_approved(self, request: ToolExecutionRequest) -> dict[str, Any]:
        if not request.task_id:
            raise ValueError("task_id is required for commit_approved.")
        if not request.approval_id and not request.dry_run:
            raise ValueError("approval_id is required for commit_approved.")
        message = str(request.arguments.get("message") or "").strip()
        if not message:
            raise ValueError("message is required for commit_approved.")
        approved_paths = self._approved_artifact_paths(request)
        self._verify_artifact_hashes(request)
        if request.dry_run:
            return {"would_commit": approved_paths, "message": message, "task_id": str(request.task_id), "approval_id": str(request.approval_id)}
        existing_staged = self._name_only(request, ["diff", "--cached", "--name-only"])
        unexpected_staged = sorted(set(existing_staged) - set(approved_paths))
        if unexpected_staged:
            raise ValueError("Unapproved files are already staged: " + ", ".join(unexpected_staged))
        add_result = self._run_git(request, ["add", "--", *approved_paths])
        if add_result["return_code"] != 0:
            raise ValueError("Git add failed: " + "\n".join(add_result["lines"]))
        staged_after_add = self._name_only(request, ["diff", "--cached", "--name-only"])
        unexpected_after_add = sorted(set(staged_after_add) - set(approved_paths))
        if unexpected_after_add:
            raise ValueError("Git staged unapproved files: " + ", ".join(unexpected_after_add))
        if not staged_after_add:
            raise ValueError("No approved changes are staged for commit.")
        commit_result = self._run_git(request, ["commit", "-m", message])
        if commit_result["return_code"] != 0:
            raise ValueError("Git commit failed: " + "\n".join(commit_result["lines"]))
        head = self._run_git(request, ["rev-parse", "HEAD"])
        commit_sha = head["lines"][0].strip() if head["return_code"] == 0 and head["lines"] else None
        return {
            "operation": "commit_approved",
            "commit_sha": commit_sha,
            "approved_paths": approved_paths,
            "message": message,
            "task_id": str(request.task_id),
            "approval_id": str(request.approval_id),
            "result": commit_result,
            "rollback": {"operation": "revert_commit", "commit_sha": commit_sha},
        }


def adapter_for_tool(profile: ArceusToolProfile) -> ToolAdapter:
    adapter_type = (profile.adapter_type or "").lower()
    if adapter_type in {"shell", "read_only_shell", "search", "filesystem_read"}:
        return ReadOnlyShellToolAdapter()
    if adapter_type in {"filesystem_mutation", "filesystem_write"}:
        return FilesystemMutationToolAdapter()
    if adapter_type in {"git", "git_adapter"}:
        return GitToolAdapter()
    raise ValueError(f"Unsupported tool adapter: {profile.adapter_type}")
