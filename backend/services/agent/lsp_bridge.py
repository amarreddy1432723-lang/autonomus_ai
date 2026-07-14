import asyncio
import json
import os
from pathlib import Path
import shlex
from asyncio.subprocess import PIPE
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _node_bin_command(binary: str, *args: str) -> list[str]:
    local_bin = _repo_root() / "frontend" / "node_modules" / ".bin" / binary
    if os.name == "nt":
        local_bin = local_bin.with_suffix(".cmd")
        if local_bin.exists():
            return ["cmd", "/c", str(local_bin), *args]
    elif local_bin.exists():
        return [str(local_bin), *args]
    return ["npx", "--yes", binary, *args]


def _language_command(language: str) -> list[str] | None:
    key = language.lower()
    if key in {"typescript", "javascript", "tsx", "ts", "jsx", "js"}:
        configured = os.getenv("TYPESCRIPT_LANGUAGE_SERVER_CMD")
        if configured:
            return shlex.split(configured)
        return _node_bin_command("typescript-language-server", "--stdio")
    elif key in {"python", "py"}:
        command = os.getenv("PYTHON_LSP_SERVER_CMD", "pylsp --stdio")
    elif key in {"css", "scss", "less"}:
        configured = os.getenv("CSS_LSP_SERVER_CMD")
        if configured:
            return shlex.split(configured)
        return _node_bin_command("vscode-css-language-server", "--stdio")
    elif key in {"json", "jsonc"}:
        configured = os.getenv("JSON_LSP_SERVER_CMD")
        if configured:
            return shlex.split(configured)
        return _node_bin_command("vscode-json-language-server", "--stdio")
    else:
        return None
    return shlex.split(command)


def _workspace_cwd(root: str | None) -> Path:
    if not root:
        return _repo_root()
    try:
        candidate = Path(root).expanduser().resolve()
        if candidate.exists() and candidate.is_dir():
            return candidate
    except Exception:
        pass
    return _repo_root()


def _json_rpc_frame(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body


async def _read_lsp_message(stdout: asyncio.StreamReader) -> dict[str, Any] | None:
    content_length: int | None = None
    while True:
        line = await stdout.readline()
        if not line:
            return None
        stripped = line.decode("ascii", errors="ignore").strip()
        if not stripped:
            break
        if stripped.lower().startswith("content-length:"):
            try:
                content_length = int(stripped.split(":", 1)[1].strip())
            except ValueError:
                return None
    if not content_length:
        return None
    body = await stdout.readexactly(content_length)
    return json.loads(body.decode("utf-8"))


async def _pump_lsp_to_socket(process: asyncio.subprocess.Process, websocket: WebSocket) -> None:
    if not process.stdout:
        return
    while True:
        try:
            message = await _read_lsp_message(process.stdout)
        except Exception as exc:
            await websocket.send_text(json.dumps({"method": "window/logMessage", "params": {"type": 1, "message": f"LSP read failed: {exc}"}}))
            return
        if message is None:
            return
        await websocket.send_text(json.dumps(message, separators=(",", ":")))


async def _pump_stderr_to_socket(process: asyncio.subprocess.Process, websocket: WebSocket) -> None:
    if not process.stderr:
        return
    while True:
        line = await process.stderr.readline()
        if not line:
            return
        message = line.decode("utf-8", errors="replace").strip()
        if message:
            await websocket.send_text(json.dumps({"method": "window/logMessage", "params": {"type": 3, "message": message}}))


@router.websocket("/api/v1/code/lsp/{language}")
@router.websocket("/api/v1/lsp/{language}")
async def lsp_bridge(websocket: WebSocket, language: str, root: str | None = None):
    await websocket.accept()
    command = _language_command(language)
    if not command:
        await websocket.send_text(json.dumps({"error": {"code": -32000, "message": f"No LSP server configured for {language}."}}))
        await websocket.close(code=1003)
        return

    try:
        cwd = _workspace_cwd(root)
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=PIPE,
            stdout=PIPE,
            stderr=PIPE,
            cwd=str(cwd),
        )
    except FileNotFoundError:
        await websocket.send_text(json.dumps({
            "error": {
                "code": -32001,
                "message": f"LSP server is not installed: {command[0]}. Install it or set the language server command env var.",
            }
        }))
        await websocket.close(code=1011)
        return
    except Exception as exc:
        await websocket.send_text(json.dumps({"error": {"code": -32002, "message": f"Could not start LSP server: {exc}"}}))
        await websocket.close(code=1011)
        return

    stdout_task = asyncio.create_task(_pump_lsp_to_socket(process, websocket))
    stderr_task = asyncio.create_task(_pump_stderr_to_socket(process, websocket))
    try:
        while True:
            raw = await websocket.receive_text()
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": {"code": -32700, "message": "Invalid JSON-RPC payload."}}))
                continue
            if process.stdin:
                process.stdin.write(_json_rpc_frame(payload))
                await process.stdin.drain()
    except WebSocketDisconnect:
        pass
    finally:
        stdout_task.cancel()
        stderr_task.cancel()
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=2)
            except asyncio.TimeoutError:
                process.kill()
