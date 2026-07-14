from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from services.shared.models import CodeSession, FileReference

from .agent_jobs import append_job_log, complete_job, heartbeat_job
from .code_workspace import (
    analyze_workspace_structure,
    code_files,
    generate_patch,
    preview_patch_payload,
    run_workspace_checks,
    run_workspace_command,
    search_workspace_files,
    workspace_suggestion_context,
)
from .file_service import get_file_text
from .model_gateway import model_gateway
from .tool_registry import select_tools, validate_tool_request


def _clip(value: Any, limit: int = 6000) -> Any:
    if isinstance(value, str):
        return value[:limit]
    if isinstance(value, dict):
        return {key: _clip(item, limit) for key, item in value.items()}
    if isinstance(value, list):
        return [_clip(item, limit) for item in value[:40]]
    return value


def _find_workspace_file(db: Session, user_id: UUID, session: CodeSession, file_id: str | None = None, path: str | None = None) -> FileReference:
    records = code_files(db, user_id, session)
    if file_id:
        for record in records:
            if str(record.id) == str(file_id):
                return record
    if path:
        normalized = path.replace("\\", "/").strip("/")
        for record in records:
            if record.filename.replace("\\", "/").strip("/") == normalized:
                return record
    raise HTTPException(status_code=404, detail="Workspace file not found")


def _git_diff_summary(db: Session, user_id: UUID, session: CodeSession) -> dict:
    preview = preview_patch_payload(db, user_id, session)
    return {
        "pending": bool(preview),
        "files": [
            {
                "file_id": item.get("file_id"),
                "filename": item.get("filename"),
                "additions": item.get("additions") or 0,
                "deletions": item.get("deletions") or 0,
                "status": item.get("status") or "pending",
                "diff": (item.get("diff") or "")[:6000],
            }
            for item in preview
        ],
    }


def execute_workspace_tool(
    db: Session,
    user_id: UUID,
    session: CodeSession,
    tool_name: str,
    arguments: dict[str, Any],
    approved: bool = False,
) -> dict:
    policy = validate_tool_request(tool_name, approved=approved)
    if not policy.get("allowed"):
        return {
            "status": "approval_required" if policy.get("requires_approval") else "blocked",
            "tool": tool_name,
            "arguments": arguments,
            "policy": policy,
        }

    if tool_name == "list_files":
        return {
            "status": "completed",
            "tool": tool_name,
            "result": workspace_suggestion_context(db, user_id, session).get("file_tree") or [],
        }
    if tool_name == "read_file":
        record = _find_workspace_file(db, user_id, session, arguments.get("file_id"), arguments.get("path"))
        return {
            "status": "completed",
            "tool": tool_name,
            "result": {
                "file_id": str(record.id),
                "filename": record.filename,
                "content": get_file_text(db, user_id, record.id)[:20000],
            },
        }
    if tool_name == "search_code":
        query = str(arguments.get("query") or "")
        limit = int(arguments.get("limit") or 40)
        return {
            "status": "completed",
            "tool": tool_name,
            "result": search_workspace_files(db, user_id, session, query, limit=max(1, min(limit, 100))),
        }
    if tool_name == "analyze_workspace":
        return {
            "status": "completed",
            "tool": tool_name,
            "result": analyze_workspace_structure(db, user_id, session),
        }
    if tool_name == "git_diff":
        return {
            "status": "completed",
            "tool": tool_name,
            "result": _git_diff_summary(db, user_id, session),
        }
    if tool_name == "run_tests":
        return {
            "status": "completed",
            "tool": tool_name,
            "result": run_workspace_checks(db, user_id, session, timeout_seconds=int(arguments.get("timeout_seconds") or 60), job=None),
        }
    if tool_name == "run_command":
        return {
            "status": "completed",
            "tool": tool_name,
            "result": run_workspace_command(
                db,
                user_id,
                session,
                str(arguments.get("command") or ""),
                timeout_seconds=int(arguments.get("timeout_seconds") or 45),
                approved=True,
                job=None,
            ),
        }
    if tool_name == "apply_patch":
        instruction = str(arguments.get("instruction") or "")
        generate_patch(db, user_id, session, instruction, provider=None, model=None, job=None, finalize_job=False)
        return {
            "status": "completed",
            "tool": tool_name,
            "result": _git_diff_summary(db, user_id, session),
        }

    return {
        "status": "blocked",
        "tool": tool_name,
        "arguments": arguments,
        "policy": {"allowed": False, "reason": "Tool execution is not wired for workspace sessions yet."},
    }


async def run_controlled_workspace_agent(
    db: Session,
    user_id: UUID,
    session: CodeSession,
    task: str,
    provider_name: str | None = None,
    model_name: str | None = None,
    max_steps: int = 8,
    approved_tools: list[str] | None = None,
    job=None,
) -> dict:
    approved_tool_names = set(approved_tools or [])
    selection = select_tools(task, selected_mode="code", max_tools=8, include_high_risk=True)
    allowed_names = {tool["name"] for tool in selection.get("tools") or []}
    provider = model_gateway.get_provider(provider_name or "nexus")
    context = workspace_suggestion_context(db, user_id, session)
    conversation: list[dict[str, Any]] = [
        {
            "role": "developer",
            "content": (
                "You are Arceus Code, a controlled software-development agent. "
                "Use only the selected tools. Never invent tool results. "
                "Inspect relevant files before proposing changes. "
                "If a tool needs approval, request it instead of bypassing policy."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Task:\n{task}\n\n"
                f"Workspace context:\n{json.dumps(_clip(context, 3000), indent=2)}"
            ),
        },
    ]
    trace: list[dict[str, Any]] = []
    heartbeat_job(db, job, "running", "Controlled agent loop started", 10)

    for step_number in range(1, max(1, min(max_steps, 20)) + 1):
        heartbeat_job(db, job, "running", f"Agent step {step_number}", min(95, 10 + step_number * 8))
        model_result = await provider.generate(
            messages=conversation,
            tools=selection.get("llm_tools") or [],
            model=model_name,
        )
        if not model_result.tool_requests:
            result = {
                "status": "completed",
                "answer": model_result.text or "",
                "steps": trace,
                "selected_tools": selection,
            }
            complete_job(db, job, "completed", result)
            return result

        if model_result.text:
            conversation.append({"role": "assistant", "content": model_result.text})

        for request in model_result.tool_requests:
            if request.name not in allowed_names:
                result = {
                    "status": "blocked",
                    "answer": f"Tool '{request.name}' is not allowed for this task.",
                    "steps": trace,
                    "selected_tools": selection,
                }
                complete_job(db, job, "blocked", result)
                return result

            approved = request.name in approved_tool_names or bool(request.arguments.get("approved"))
            tool_result = execute_workspace_tool(db, user_id, session, request.name, request.arguments, approved=approved)
            step = {
                "step": step_number,
                "tool": request.name,
                "arguments": request.arguments,
                "status": tool_result.get("status"),
                "result": _clip(tool_result.get("result") or tool_result.get("policy") or tool_result, 5000),
            }
            trace.append(step)
            append_job_log(db, job, "tool", f"{request.name}: {tool_result.get('status')}", json.dumps(_clip(step, 1200)))

            if tool_result.get("status") == "approval_required":
                result = {
                    "status": "approval_required",
                    "answer": f"Approval required before running {request.name}.",
                    "approval": {
                        "tool": request.name,
                        "arguments": request.arguments,
                        "policy": tool_result.get("policy"),
                    },
                    "steps": trace,
                    "selected_tools": selection,
                }
                complete_job(db, job, "waiting_approval", result, approval_state="pending")
                return result

            conversation.append({
                "type": "function_call_output",
                "call_id": request.call_id,
                "output": json.dumps(_clip(tool_result, 6000)),
            })

    result = {
        "status": "step_limit_reached",
        "answer": "The agent stopped because it reached the maximum number of execution steps.",
        "steps": trace,
        "selected_tools": selection,
    }
    complete_job(db, job, "timeout", result)
    return result
