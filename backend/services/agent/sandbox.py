import os
import subprocess
import shlex
import time
import logging
import re
import atexit
import uuid
import shutil
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pathlib import Path
from datetime import datetime, UTC

logger = logging.getLogger("arceus-sandbox")
SECRET_OUTPUT_PATTERNS = (
    re.compile(r"(?i)(api[_-]?key|secret|token|password|authorization|bearer)\s*[:=]\s*([^\s'\"`]+)"),
    re.compile(r"(?i)(Bearer\s+)([^\s'\"`]+)"),
    re.compile(r"(?i)((?:password|token|secret)=)([^\s'\"`]+)"),
    re.compile(r"(?i)(sk-[A-Za-z0-9_\-]{12,})"),
    re.compile(r"(?i)(gh[pousr]_[A-Za-z0-9_]{20,})"),
)
ACTIVE_DOCKER_CONTAINERS: set[str] = set()


def _resolve_local_command_parts(parts: List[str]) -> List[str]:
    if not parts:
        return parts
    executable = parts[0]
    if os.name == "nt" and not Path(executable).suffix:
        resolved = shutil.which(executable)
        if resolved:
            return [resolved, *parts[1:]]
    return parts


def _redact(output: str) -> str:
    redacted = output or ""
    for pattern in SECRET_OUTPUT_PATTERNS:
        def repl(match: re.Match) -> str:
            if match.lastindex and match.lastindex >= 2:
                return f"{match.group(1)}[REDACTED]"
            return "[REDACTED]"
        redacted = pattern.sub(repl, redacted)
    return redacted


def _cleanup_active_docker_containers() -> None:
    for container_name in list(ACTIVE_DOCKER_CONTAINERS):
        try:
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10, check=False)
        except Exception:
            pass
        ACTIVE_DOCKER_CONTAINERS.discard(container_name)


atexit.register(_cleanup_active_docker_containers)


def _command_result(
    provider: str,
    status: str,
    return_code: int | None,
    output: str,
    started: float,
    timeout: int,
    workspace_root: Path,
    policy: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    completed_at = datetime_now_iso()
    safe_output = _redact(output or "(no output)")
    return {
        "provider": provider,
        "status": status,
        "return_code": return_code,
        "output": safe_output[-20000:],
        "output_excerpt": safe_output[-4000:],
        "artifacts": [],
        "started_at": datetime_from_monotonic(started),
        "completed_at": completed_at,
        "ran_at": completed_at,
        "duration_ms": int((time.monotonic() - started) * 1000),
        "timeout_seconds": timeout,
        "workspace_root": str(workspace_root),
        "sandbox_policy": policy or {},
    }

class CodeSandbox(ABC):
    def __init__(self, session_id: str, workspace_root: Path):
        self.session_id = session_id
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def run_command(self, command: str, timeout: int = 60, allow_network: bool = False) -> Dict[str, Any]:
        """Execute a shell command inside the sandbox."""
        pass

    @abstractmethod
    def start_preview_server(self, command: str, port: int) -> Dict[str, Any]:
        """Start a long-running background preview/dev server."""
        pass

    @abstractmethod
    def stop_preview_server(self) -> bool:
        """Stop any active preview server."""
        pass

    @abstractmethod
    def cleanup(self) -> None:
        """Terminate and clean up sandbox resources."""
        pass


class LocalSandbox(CodeSandbox):
    def __init__(self, session_id: str, workspace_root: Path):
        super().__init__(session_id, workspace_root)
        self.preview_process: Optional[subprocess.Popen] = None

    def run_command(self, command: str, timeout: int = 60, allow_network: bool = False) -> Dict[str, Any]:
        logger.info(f"Running local command: {command} in {self.workspace_root}")
        # Parse command safely
        parts = _resolve_local_command_parts(shlex.split(command))
        started = time.monotonic()
        try:
            completed = subprocess.run(
                parts,
                cwd=self.workspace_root,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            output = "\n".join(filter(None, [completed.stdout, completed.stderr])).strip()
            return _command_result("local", "passed" if completed.returncode == 0 else "failed", completed.returncode, output, started, timeout, self.workspace_root)
        except subprocess.TimeoutExpired as e:
            output = "\n".join(filter(None, [e.stdout or "", e.stderr or ""])).strip()
            return _command_result("local", "timeout", None, output or "Command timed out before producing output.", started, timeout, self.workspace_root)
        except Exception as e:
            return _command_result("local", "failed", -1, f"Internal Sandbox Error: {str(e)}", started, timeout, self.workspace_root)

    def start_preview_server(self, command: str, port: int) -> Dict[str, Any]:
        self.stop_preview_server()
        parts = _resolve_local_command_parts(shlex.split(command))
        try:
            # Run in background
            proc = subprocess.Popen(
                parts,
                cwd=self.workspace_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.preview_process = proc
            # Wait a moment to see if it crashed immediately
            time.sleep(1.0)
            if proc.poll() is not None:
                _, stderr = proc.communicate()
                return {"status": "stopped", "error": f"Process exited immediately: {stderr}"}
            
            return {
                "status": "running",
                "port": port,
                "proxy_url": f"http://localhost:{port}",
            }
        except Exception as e:
            return {"status": "stopped", "error": f"Failed to start: {str(e)}"}

    def stop_preview_server(self) -> bool:
        if self.preview_process:
            try:
                self.preview_process.terminate()
                self.preview_process.wait(timeout=3)
                self.preview_process = None
                return True
            except Exception:
                try:
                    self.preview_process.kill()
                    self.preview_process = None
                    return True
                except Exception:
                    pass
        return False

    def cleanup(self) -> None:
        self.stop_preview_server()


class DockerSandbox(CodeSandbox):
    def __init__(self, session_id: str, workspace_root: Path, image: str = "python:3.11-slim"):
        super().__init__(session_id, workspace_root)
        self.image = image
        self.container_name = f"arceus-sandbox-{session_id}"
        self.preview_port: Optional[int] = None
        self._cleanup_expired_containers()

    def _network_mode(self, preview: bool = False, allow_network: bool = False) -> str:
        if preview:
            return os.getenv("SANDBOX_DOCKER_PREVIEW_NETWORK", "bridge")
        network_allowed = allow_network and os.getenv("SANDBOX_ALLOW_NETWORK", "false").lower() == "true"
        return "bridge" if network_allowed else "none"

    def _policy(self, preview: bool = False, allow_network: bool = False) -> Dict[str, Any]:
        memory = os.getenv("SANDBOX_DOCKER_MEMORY", "512m")
        return {
            "network_mode": self._network_mode(preview=preview, allow_network=allow_network),
            "memory": memory,
            "memory_swap": memory,
            "cpu_period": os.getenv("SANDBOX_DOCKER_CPU_PERIOD", "100000"),
            "cpu_quota": os.getenv("SANDBOX_DOCKER_CPU_QUOTA", "50000"),
            "pids_limit": os.getenv("SANDBOX_DOCKER_PIDS_LIMIT", "64"),
            "user": os.getenv("SANDBOX_DOCKER_USER", "1000:1000"),
            "read_only": True,
            "tmpfs": ["/tmp:rw,nosuid,size=64m", "/home/appuser:rw,nosuid,size=64m"],
            "security_opt": "no-new-privileges",
            "cap_drop": "ALL",
            "workspace_mount": f"{self.workspace_root}:/workspace:rw",
        }

    def _docker_limits(self, preview: bool = False, allow_network: bool = False) -> list[str]:
        policy = self._policy(preview=preview, allow_network=allow_network)
        memory = str(policy["memory"])
        return [
            "--init",
            "--user", str(policy["user"]),
            "--memory", memory,
            "--memory-swap", memory,
            "--cpu-period", str(policy["cpu_period"]),
            "--cpu-quota", str(policy["cpu_quota"]),
            "--pids-limit", str(policy["pids_limit"]),
            "--network", str(policy["network_mode"]),
            "--read-only",
            "--tmpfs", "/tmp:rw,nosuid,size=64m",
            "--tmpfs", "/home/appuser:rw,nosuid,size=64m",
            "--security-opt", "no-new-privileges",
            "--cap-drop", "ALL",
            "--ulimit", "nofile=1024:1024",
            "--label", "arceus.sandbox=true",
            "--label", f"arceus.session_id={self.session_id}",
            "--label", f"arceus.cleanup_after={int(time.time()) + int(os.getenv('SANDBOX_DOCKER_CLEANUP_TTL_SECONDS', '300'))}",
        ]

    def _ensure_container_running(self):
        self._cleanup_expired_containers()
        # Check if container already exists
        check_cmd = ["docker", "inspect", self.container_name]
        res = subprocess.run(check_cmd, capture_output=True)
        if res.returncode == 0:
            # Check if running
            status_res = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", self.container_name],
                capture_output=True,
                text=True
            )
            if status_res.stdout.strip() == "true":
                return
            # If not running, start it
            subprocess.run(["docker", "start", self.container_name], capture_output=True)
            return

        # Start new background container
        # Mount host workspace_root to /workspace
        run_cmd = [
            "docker", "run", "-d",
            "--name", self.container_name,
            "-v", f"{self.workspace_root}:/workspace",
            "-w", "/workspace",
        ] + self._docker_limits(preview=False) + [self.image, "tail", "-f", "/dev/null"]
        logger.info(f"Starting Docker sandbox container: {self.container_name}")
        ACTIVE_DOCKER_CONTAINERS.add(self.container_name)
        try:
            subprocess.run(run_cmd, capture_output=True, check=True)
        except Exception:
            ACTIVE_DOCKER_CONTAINERS.discard(self.container_name)
            raise

    def _cleanup_expired_containers(self) -> None:
        try:
            listed = subprocess.run(
                ["docker", "ps", "-aq", "--filter", "label=arceus.sandbox=true"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            now = int(time.time())
            for container_id in [line.strip() for line in listed.stdout.splitlines() if line.strip()]:
                inspected = subprocess.run(
                    ["docker", "inspect", "-f", "{{ index .Config.Labels \"arceus.cleanup_after\" }}", container_id],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
                try:
                    cleanup_after = int((inspected.stdout or "0").strip() or "0")
                except ValueError:
                    cleanup_after = 0
                if cleanup_after and cleanup_after < now:
                    subprocess.run(["docker", "rm", "-f", container_id], capture_output=True, timeout=10, check=False)
        except Exception as exc:
            logger.debug("Sandbox TTL cleanup skipped: %s", exc)

    def run_command(self, command: str, timeout: int = 60, allow_network: bool = False) -> Dict[str, Any]:
        container_name = f"{self.container_name}-{uuid.uuid4().hex[:8]}"
        ACTIVE_DOCKER_CONTAINERS.add(container_name)
        policy = self._policy(preview=False, allow_network=allow_network)
        exec_cmd = [
            "docker", "run", "--rm",
            "--name", container_name,
            "-v", f"{self.workspace_root}:/workspace:rw",
            "-w", "/workspace",
        ] + self._docker_limits(preview=False, allow_network=allow_network) + [self.image] + shlex.split(command)
        started = time.monotonic()
        try:
            completed = subprocess.run(
                exec_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )
            output = "\n".join(filter(None, [completed.stdout, completed.stderr])).strip()
            ACTIVE_DOCKER_CONTAINERS.discard(container_name)
            return _command_result("docker", "passed" if completed.returncode == 0 else "failed", completed.returncode, output, started, timeout, self.workspace_root, policy)
        except subprocess.TimeoutExpired as e:
            output = "\n".join(filter(None, [e.stdout or "", e.stderr or ""])).strip()
            result = _command_result("docker", "timeout", None, output or "Command timed out inside container.", started, timeout, self.workspace_root, policy)
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10, check=False)
            ACTIVE_DOCKER_CONTAINERS.discard(container_name)
            return result
        except Exception as e:
            subprocess.run(["docker", "rm", "-f", container_name], capture_output=True, timeout=10, check=False)
            ACTIVE_DOCKER_CONTAINERS.discard(container_name)
            return _command_result("docker", "failed", -1, f"Docker Exec Error: {str(e)}", started, timeout, self.workspace_root, policy)

    def start_preview_server(self, command: str, port: int) -> Dict[str, Any]:
        # To run a preview server in Docker, we need port forwarding.
        # Since standard containers cannot add port mappings dynamically after launch,
        # we will stop the current container, and restart it with the mapped port.
        self.cleanup()
        self.preview_port = port
        
        run_cmd = [
            "docker", "run", "-d",
            "--name", self.container_name,
            "-v", f"{self.workspace_root}:/workspace",
            "-p", f"{port}:{port}",
            "-w", "/workspace",
        ] + self._docker_limits(preview=True) + [self.image, "tail", "-f", "/dev/null"]
        ACTIVE_DOCKER_CONTAINERS.add(self.container_name)
        try:
            subprocess.run(run_cmd, capture_output=True, check=True)
        except Exception:
            ACTIVE_DOCKER_CONTAINERS.discard(self.container_name)
            raise
        
        # Now launch the server in the background inside the container
        exec_cmd = ["docker", "exec", "-d", self.container_name] + shlex.split(command)
        subprocess.run(exec_cmd, capture_output=True)
        
        return {
            "status": "running",
            "port": port,
            "proxy_url": f"http://localhost:{port}",
        }

    def stop_preview_server(self) -> bool:
        if self.preview_port:
            self.cleanup()
            self.preview_port = None
            self._ensure_container_running()
            return True
        return False

    def cleanup(self) -> None:
        logger.info(f"Removing Docker container: {self.container_name}")
        subprocess.run(["docker", "rm", "-f", self.container_name], capture_output=True)
        ACTIVE_DOCKER_CONTAINERS.discard(self.container_name)

class E2BSandbox(CodeSandbox):
    def __init__(self, session_id: str, workspace_root: Path, api_key: str):
        super().__init__(session_id, workspace_root)
        self.api_key = api_key
        self.sandbox: Optional[Any] = None
        self.preview_port: Optional[int] = None
        self._init_sandbox()

    def _init_sandbox(self):
        try:
            from e2b import Sandbox
            os.environ["E2B_API_KEY"] = self.api_key
            self.sandbox = Sandbox()
            self._sync_files_to_e2b()
        except ImportError:
            raise RuntimeError("e2b python SDK not installed")

    def _sync_files_to_e2b(self):
        # Recursively upload files from local workspace to E2B sandbox
        for root_dir, _, files in os.walk(self.workspace_root):
            for file in files:
                local_path = Path(root_dir) / file
                rel_path = local_path.relative_to(self.workspace_root)
                content = local_path.read_bytes()
                # Create parent directories in E2B
                self.sandbox.filesystem.make_dir(str(rel_path.parent))
                self.sandbox.filesystem.write(str(rel_path), content)

    def _sync_files_from_e2b(self):
        # Sync E2B workspace files back to local workspace root
        try:
            entries = self.sandbox.filesystem.list(".")
            for entry in entries:
                if not entry.is_dir:
                    content = self.sandbox.filesystem.read(entry.name)
                    local_path = self.workspace_root / entry.name
                    local_path.write_bytes(content)
        except Exception as e:
            logger.error(f"Error syncing files from E2B: {e}")

    def run_command(self, command: str, timeout: int = 60, allow_network: bool = False) -> Dict[str, Any]:
        if not self.sandbox:
            self._init_sandbox()
        started = time.monotonic()
        try:
            cmd_res = self.sandbox.commands.run(command, timeout=timeout)
            # Sync back modifications to local dir so local workspace is up to date
            self._sync_files_from_e2b()
            output = f"{cmd_res.stdout or ''}{cmd_res.stderr or ''}"
            return _command_result("e2b", "passed" if cmd_res.exit_code == 0 else "failed", cmd_res.exit_code, output, started, timeout, self.workspace_root)
        except Exception as e:
            return _command_result("e2b", "failed", -1, f"E2B Run Error: {str(e)}", started, timeout, self.workspace_root)

    def start_preview_server(self, command: str, port: int) -> Dict[str, Any]:
        if not self.sandbox:
            self._init_sandbox()
        self.preview_port = port
        self.sandbox.commands.run(command, background=True)
        hostname = self.sandbox.get_host(port)
        return {
            "status": "running",
            "port": port,
            "proxy_url": f"https://{hostname}",
        }

    def stop_preview_server(self) -> bool:
        return True

    def cleanup(self) -> None:
        if self.sandbox:
            self.sandbox.close()
            self.sandbox = None


def datetime_now_iso() -> str:
    return datetime.now(UTC).isoformat() + "Z"


def datetime_from_monotonic(started: float) -> str:
    elapsed = time.monotonic() - started
    return datetime.fromtimestamp(time.time() - elapsed, UTC).isoformat() + "Z"


def _is_production(settings) -> bool:
    env = str(getattr(settings, "APP_ENV", os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "local")))).lower()
    return env in {"prod", "production"}


def _local_allowed(settings) -> bool:
    provider = str(getattr(settings, "SANDBOX_PROVIDER", "local")).lower()
    explicit = bool(getattr(settings, "ALLOW_LOCAL_SANDBOX", False))
    return provider == "local" and (explicit or not _is_production(settings))


def _provider_error(provider: str, reason: str) -> RuntimeError:
    return RuntimeError(f"Sandbox provider '{provider}' is unavailable: {reason}")


def get_sandbox(session_id: str, workspace_root: Path, settings) -> CodeSandbox:
    provider = getattr(settings, "SANDBOX_PROVIDER", "local").lower()
    if provider == "docker":
        try:
            res = subprocess.run(["docker", "info"], capture_output=True)
            if res.returncode == 0:
                image = getattr(settings, "SANDBOX_DOCKER_IMAGE", "python:3.11-slim")
                return DockerSandbox(session_id, workspace_root, image=image)
        except Exception:
            pass
        if _is_production(settings):
            raise _provider_error("docker", "Docker daemon is not running and local fallback is disabled in production.")
        logger.warning("Docker daemon not running/accessible.")

    elif provider == "e2b":
        api_key = getattr(settings, "E2B_API_KEY", None)
        if api_key:
            try:
                return E2BSandbox(session_id, workspace_root, api_key=api_key)
            except Exception as e:
                logger.error(f"Failed to initialize E2B Sandbox: {e}.")
                if _is_production(settings):
                    raise _provider_error("e2b", str(e))
        else:
            logger.warning("E2B_API_KEY missing.")
            if _is_production(settings):
                raise _provider_error("e2b", "E2B_API_KEY is required in production.")

    if _local_allowed(settings):
        return LocalSandbox(session_id, workspace_root)
    raise _provider_error(provider, "local subprocess execution is disabled. Set ALLOW_LOCAL_SANDBOX=true only for development.")
