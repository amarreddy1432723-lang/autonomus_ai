from __future__ import annotations

import atexit
import asyncio
import os
import re
import shlex
import signal
import sys
import uuid
import time
from pathlib import Path
from typing import Any
from uuid import UUID

import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from services.shared.database import SessionLocal
from services.shared.models import CodeSession
from services.shared.security import (
    clerk_auth_enabled,
    clerk_only_auth_required,
    dev_auth_fallback_enabled,
    resolve_clerk_user_id,
    verify_clerk_token,
)

try:  # Linux/cloud path. Windows local terminals use Electron node-pty.
    from ptyprocess import PtyProcess
except Exception:  # pragma: no cover - optional platform dependency
    PtyProcess = None  # type: ignore


router = APIRouter()
ACTIVE_PROCESSES: dict[str, Any] = {}
PTY_SESSIONS: dict[str, dict[str, Any]] = {}
IDLE_TIMEOUT_SECONDS = int(os.getenv("ARCEUS_PTY_IDLE_TIMEOUT_SECONDS", "1800"))
MAX_BUFFER_BYTES = int(os.getenv("ARCEUS_PTY_BUFFER_BYTES", "1000000"))

SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)([A-Za-z0-9\-\._~\+\/]+=*)"),
    re.compile(r"(?i)(password\s*[:=]\s*['\"]?)([^'\"\s]+)"),
    re.compile(r"(?i)(token\s*[:=]\s*['\"]?)([^'\"\s]+)"),
    re.compile(r"(?i)(api[_-]?key\s*[:=]\s*['\"]?)([^'\"\s]+)"),
    re.compile(r"(?i)()(sk-[A-Za-z0-9_\-]{12,})"),
    re.compile(r"(?i)()(gh[pousr]_[A-Za-z0-9_]{20,})"),
)

DANGEROUS_PATTERNS = (
    re.compile(r"rm\s+-[^\n\r;|&]*r[^\n\r;|&]*\s+/", re.IGNORECASE),
    re.compile(r"del\s+/[sq]\s+[a-z]:\\", re.IGNORECASE),
    re.compile(r"format\s+[a-z]:", re.IGNORECASE),
    re.compile(r":\s*\(\s*\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;", re.IGNORECASE),
    re.compile(r"while\s+true\s*;\s*do\s+.*done", re.IGNORECASE | re.DOTALL),
)


def redact(value: str) -> str:
    text = value
    for pattern in SECRET_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1) or ''}[REDACTED]", text)
    return text


def is_dangerous_input(value: str) -> bool:
    return any(pattern.search(value or "") for pattern in DANGEROUS_PATTERNS)


async def send_frame(websocket: WebSocket, frame_type: str, payload: dict[str, Any] | None = None) -> None:
    await websocket.send_json({"type": frame_type, "event": frame_type, **(payload or {})})


def allowed_shell(profile: str | None = None) -> list[str]:
    requested = (profile or "").strip().lower()
    if sys.platform == "win32":
        shells = {
            "powershell": ["powershell.exe", "-NoLogo"],
            "pwsh": ["pwsh.exe", "-NoLogo"],
            "cmd": [os.environ.get("COMSPEC", "cmd.exe")],
        }
        return shells.get(requested) or shells.get("pwsh") or shells["cmd"]
    candidates = {
        "bash": ["/bin/bash"],
        "zsh": ["/bin/zsh"],
        "sh": ["/bin/sh"],
        "pwsh": ["pwsh"],
        "powershell": ["pwsh"],
    }
    if requested in candidates and Path(candidates[requested][0]).exists():
        return candidates[requested]
    shell = os.environ.get("SHELL", "/bin/bash")
    return [shell if Path(shell).exists() else "/bin/sh"]


def default_shell() -> list[str]:
    return allowed_shell(None)


def decode_token_user(token: str | None) -> UUID | None:
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            os.getenv("JWT_SECRET", "supersecretkeyforlocaldevelopmentonlychangeinprod!"),
            algorithms=[os.getenv("JWT_ALGORITHM", "HS256")],
            options={"verify_aud": False},
        )
        if payload.get("type") == "access" and payload.get("sub"):
            return UUID(str(payload["sub"]))
    except Exception:
        return None
    return None


def resolve_user_id(websocket: WebSocket) -> UUID:
    token = websocket.query_params.get("token")
    if token and clerk_auth_enabled():
        db = SessionLocal()
        try:
            return resolve_clerk_user_id(db, verify_clerk_token(token))
        except Exception:
            if clerk_only_auth_required():
                raise PermissionError("A valid Clerk session token is required to open a PTY terminal.")
        finally:
            db.close()
    if clerk_only_auth_required():
        raise PermissionError("A valid Clerk session token is required to open a PTY terminal.")
    user_id = decode_token_user(token)
    if user_id:
        return user_id
    raw_user_id = websocket.query_params.get("user_id") or websocket.headers.get("x-user-id")
    if raw_user_id and dev_auth_fallback_enabled():
        return UUID(str(raw_user_id))
    raise PermissionError("Authentication is required to open a PTY terminal.")


def session_workspace(session: CodeSession) -> Path:
    metadata = session.metadata_json or {}
    project = session.project
    candidates = [
        metadata.get("runtime_root"),
        (metadata.get("workspace_runtime") or {}).get("root"),
        (metadata.get("git") or {}).get("runtime_root"),
        metadata.get("local_workspace_path"),
        (project.metadata_json or {}).get("local_workspace_path") if project else None,
    ]
    for raw in candidates:
        if raw:
            path = Path(str(raw)).expanduser().resolve()
            path.mkdir(parents=True, exist_ok=True)
            return path
    root = Path(os.getenv("ARCEUS_TERMINAL_WORKSPACE") or os.getenv("NEXUS_TERMINAL_WORKSPACE") or os.getcwd()).expanduser().resolve()
    session_root = root / "sessions" / str(session.id)
    session_root.mkdir(parents=True, exist_ok=True)
    return session_root


def resolve_session_and_cwd(session_id: str, user_id: UUID, raw_cwd: str | None) -> tuple[CodeSession, Path]:
    db = SessionLocal()
    try:
        session = db.query(CodeSession).filter(CodeSession.id == UUID(session_id), CodeSession.user_id == user_id).first()
        if not session:
            raise PermissionError("Code session not found for this user.")
        root = session_workspace(session)
        target = (root / raw_cwd).resolve() if raw_cwd else root
        if target != root and root not in target.parents:
            raise PermissionError("Terminal cwd must stay inside the workspace.")
        target.mkdir(parents=True, exist_ok=True)
        return session, target
    finally:
        db.close()


def kill_process(terminal_id: str) -> None:
    process = ACTIVE_PROCESSES.pop(terminal_id, None)
    PTY_SESSIONS.pop(terminal_id, None)
    if not process:
        return
    try:
        if hasattr(process, "terminate"):
            process.terminate(force=True)
        elif getattr(process, "returncode", None) is None:
            if sys.platform == "win32":
                process.terminate()
            else:
                os.kill(process.pid, signal.SIGTERM)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def cleanup_processes() -> None:
    for terminal_id in list(ACTIVE_PROCESSES.keys()):
        kill_process(terminal_id)


atexit.register(cleanup_processes)


def _append_session_output(session: dict[str, Any], data: str) -> dict[str, Any]:
    text = redact(data)
    encoded = text.encode("utf-8", errors="replace")
    session["total_bytes"] = int(session.get("total_bytes") or 0) + len(encoded)
    session["buffer"].append((session["total_bytes"], text))
    while sum(len(item[1].encode("utf-8", errors="replace")) for item in session["buffer"]) > MAX_BUFFER_BYTES and session["buffer"]:
        session["buffer"].pop(0)
    session["last_activity"] = time.monotonic()
    return {"data": text, "byte_offset": session["total_bytes"], "byte_length": len(encoded)}


async def _broadcast_output(terminal_id: str, frame: dict[str, Any]) -> None:
    session = PTY_SESSIONS.get(terminal_id)
    if not session:
        return
    for queue in list(session.get("queues", set())):
        try:
            queue.put_nowait(frame)
        except Exception:
            pass


def _session_alive(session: dict[str, Any]) -> bool:
    process = session.get("process")
    if not process:
        return False
    if PtyProcess is not None and sys.platform != "win32" and hasattr(process, "isalive"):
        return bool(process.isalive())
    return getattr(process, "returncode", None) is None


async def _idle_watch(terminal_id: str) -> None:
    while terminal_id in PTY_SESSIONS:
        await asyncio.sleep(15)
        session = PTY_SESSIONS.get(terminal_id)
        if not session:
            return
        if time.monotonic() - float(session.get("last_activity") or time.monotonic()) > IDLE_TIMEOUT_SECONDS:
            await _broadcast_output(terminal_id, {"type": "exit", "event": "exit", "terminal_id": terminal_id, "code": None, "reason": "idle_timeout"})
            kill_process(terminal_id)
            return


async def _start_session(terminal_id: str, cwd: Path, shell: list[str]) -> dict[str, Any]:
    session: dict[str, Any] = {
        "terminal_id": terminal_id,
        "cwd": str(cwd),
        "shell": shell,
        "buffer": [],
        "total_bytes": 0,
        "last_activity": time.monotonic(),
        "queues": set(),
        "reader_task": None,
        "idle_task": None,
    }
    if PtyProcess is not None and sys.platform != "win32":
        process = PtyProcess.spawn(shell, cwd=str(cwd), env=os.environ.copy(), dimensions=(28, 100))
        session["process"] = process
        session["backend"] = "ptyprocess"
        ACTIVE_PROCESSES[terminal_id] = process

        async def read_pty() -> None:
            while terminal_id in PTY_SESSIONS and process.isalive():
                try:
                    data = await asyncio.to_thread(process.read, 4096)
                except EOFError:
                    break
                except Exception as exc:
                    await _broadcast_output(terminal_id, {"type": "error", "event": "error", "terminal_id": terminal_id, "message": redact(str(exc))})
                    break
                if data:
                    frame = _append_session_output(session, str(data))
                    await _broadcast_output(terminal_id, {"type": "output", "event": "output", "terminal_id": terminal_id, **frame})
            await _broadcast_output(terminal_id, {"type": "exit", "event": "exit", "terminal_id": terminal_id, "code": getattr(process, "exitstatus", None)})
    else:
        process = await asyncio.create_subprocess_exec(
            *shell,
            cwd=str(cwd),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )
        session["process"] = process
        session["backend"] = "subprocess-fallback"
        ACTIVE_PROCESSES[terminal_id] = process

        async def pipe_output(stream: asyncio.StreamReader | None, stream_name: str) -> None:
            if stream is None:
                return
            while terminal_id in PTY_SESSIONS:
                data = await stream.read(4096)
                if not data:
                    break
                frame = _append_session_output(session, data.decode(errors="replace"))
                await _broadcast_output(terminal_id, {"type": "output", "event": "output", "terminal_id": terminal_id, "stream": stream_name, **frame})

        async def read_pty() -> None:
            await asyncio.gather(pipe_output(process.stdout, "stdout"), pipe_output(process.stderr, "stderr"), return_exceptions=True)
            await _broadcast_output(terminal_id, {"type": "exit", "event": "exit", "terminal_id": terminal_id, "code": process.returncode})

    PTY_SESSIONS[terminal_id] = session
    session["reader_task"] = asyncio.create_task(read_pty())
    session["idle_task"] = asyncio.create_task(_idle_watch(terminal_id))
    return session


async def _send_buffer_since(websocket: WebSocket, session: dict[str, Any], terminal_id: str, last_byte_offset: int) -> int:
    max_sent = last_byte_offset
    for byte_offset, data in session.get("buffer", []):
        if int(byte_offset) <= last_byte_offset:
            continue
        await send_frame(websocket, "output", {
            "terminal_id": terminal_id,
            "data": data,
            "byte_offset": int(byte_offset),
            "byte_length": len(data.encode("utf-8", errors="replace")),
            "replay": True,
        })
        max_sent = max(max_sent, int(byte_offset))
    return max_sent


@router.websocket("/api/v1/terminal/pty")
async def terminal_pty(websocket: WebSocket):
    await websocket.accept()
    terminal_id = websocket.query_params.get("terminal_id") or f"pty-{uuid.uuid4().hex}"
    if os.getenv("ARCEUS_ENABLE_CLOUD_PTY", os.getenv("NEXUS_ENABLE_CLOUD_PTY", "true")).lower() not in {"1", "true", "yes", "on"}:
        await send_frame(websocket, "blocked", {"terminal_id": terminal_id, "reason": "Cloud PTY terminal is disabled."})
        await websocket.close(code=1008)
        return
    try:
        user_id = resolve_user_id(websocket)
        session_id = websocket.query_params.get("session_id")
        if not session_id:
            raise PermissionError("session_id is required.")
        _, cwd = resolve_session_and_cwd(session_id, user_id, websocket.query_params.get("cwd"))
        shell = allowed_shell(websocket.query_params.get("shell"))
    except Exception as exc:
        await send_frame(websocket, "error", {"terminal_id": terminal_id, "message": redact(str(exc))})
        await websocket.close(code=1008)
        return

    queue: asyncio.Queue = asyncio.Queue(maxsize=500)
    sender_task: asyncio.Task | None = None

    try:
        session = PTY_SESSIONS.get(terminal_id)
        if not session or not _session_alive(session):
            session = await _start_session(terminal_id, cwd, shell)
        session.setdefault("queues", set()).add(queue)
        process = session.get("process")

        async def send_queue() -> None:
            while True:
                frame = await queue.get()
                await websocket.send_json(frame)

        sender_task = asyncio.create_task(send_queue())

        await send_frame(websocket, "ready", {
            "terminal_id": terminal_id,
            "cwd": session.get("cwd") or str(cwd),
            "pid": getattr(process, "pid", None),
            "backend": session.get("backend") or "pty",
            "shell": " ".join(session.get("shell") or shell),
            "total_bytes": int(session.get("total_bytes") or 0),
        })
        try:
            initial_offset = int(websocket.query_params.get("lastByteOffset") or websocket.query_params.get("last_byte_offset") or 0)
        except ValueError:
            initial_offset = 0
        last_sent_offset = await _send_buffer_since(websocket, session, terminal_id, initial_offset)

        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=IDLE_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                await send_frame(websocket, "exit", {"terminal_id": terminal_id, "code": None, "reason": "idle_timeout"})
                kill_process(terminal_id)
                break
            event = message.get("type") or message.get("event")
            session["last_activity"] = time.monotonic()
            if event == "resume":
                try:
                    offset = int(message.get("lastByteOffset") or message.get("last_byte_offset") or 0)
                except (TypeError, ValueError):
                    offset = 0
                if offset < last_sent_offset:
                    last_sent_offset = await _send_buffer_since(websocket, session, terminal_id, offset)
            elif event == "input":
                data = str(message.get("data") or "")
                if is_dangerous_input(data):
                    await send_frame(websocket, "blocked", {"terminal_id": terminal_id, "reason": "Blocked dangerous terminal input."})
                    continue
                if PtyProcess is not None and sys.platform != "win32" and hasattr(process, "write"):
                    process.write(data)
                elif process.stdin:
                    process.stdin.write(data.encode())
                    await process.stdin.drain()
            elif event == "resize":
                cols = int(message.get("cols") or 100)
                rows = int(message.get("rows") or 28)
                if hasattr(process, "setwinsize"):
                    process.setwinsize(rows, cols)
            elif event in {"kill", "close"}:
                kill_process(terminal_id)
                break
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        try:
            await send_frame(websocket, "error", {"terminal_id": terminal_id, "message": redact(str(exc))})
        except Exception:
            pass
    finally:
        session = PTY_SESSIONS.get(terminal_id)
        if session:
            try:
                session.get("queues", set()).discard(queue)
            except Exception:
                pass
        if sender_task:
            sender_task.cancel()
