import os
import subprocess
import shlex
import time
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger("nexus-sandbox")

class CodeSandbox(ABC):
    def __init__(self, session_id: str, workspace_root: Path):
        self.session_id = session_id
        self.workspace_root = Path(workspace_root).resolve()
        self.workspace_root.mkdir(parents=True, exist_ok=True)

    @abstractmethod
    def run_command(self, command: str, timeout: int = 60) -> Dict[str, Any]:
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

    def run_command(self, command: str, timeout: int = 60) -> Dict[str, Any]:
        logger.info(f"Running local command: {command} in {self.workspace_root}")
        # Parse command safely
        parts = shlex.split(command)
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
            return {
                "status": "passed" if completed.returncode == 0 else "failed",
                "return_code": completed.returncode,
                "output": output or "(no output)",
                "ran_at": datetime_now_iso(),
            }
        except subprocess.TimeoutExpired as e:
            output = "\n".join(filter(None, [e.stdout or "", e.stderr or ""])).strip()
            return {
                "status": "timeout",
                "return_code": None,
                "output": output or "Command timed out before producing output.",
                "ran_at": datetime_now_iso(),
            }
        except Exception as e:
            return {
                "status": "failed",
                "return_code": -1,
                "output": f"Internal Sandbox Error: {str(e)}",
                "ran_at": datetime_now_iso(),
            }

    def start_preview_server(self, command: str, port: int) -> Dict[str, Any]:
        self.stop_preview_server()
        parts = shlex.split(command)
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
        self.container_name = f"nexus-sandbox-{session_id}"
        self.preview_port: Optional[int] = None
        self._ensure_container_running()

    def _ensure_container_running(self):
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
            self.image,
            "tail", "-f", "/dev/null"
        ]
        logger.info(f"Starting Docker sandbox container: {self.container_name}")
        subprocess.run(run_cmd, capture_output=True, check=True)

    def run_command(self, command: str, timeout: int = 60) -> Dict[str, Any]:
        self._ensure_container_running()
        # shlex.split the user command and build the docker exec call
        exec_cmd = ["docker", "exec", self.container_name] + shlex.split(command)
        try:
            completed = subprocess.run(
                exec_cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False
            )
            output = "\n".join(filter(None, [completed.stdout, completed.stderr])).strip()
            return {
                "status": "passed" if completed.returncode == 0 else "failed",
                "return_code": completed.returncode,
                "output": output or "(no output)",
                "ran_at": datetime_now_iso(),
            }
        except subprocess.TimeoutExpired as e:
            output = "\n".join(filter(None, [e.stdout or "", e.stderr or ""])).strip()
            return {
                "status": "timeout",
                "return_code": None,
                "output": output or "Command timed out inside container.",
                "ran_at": datetime_now_iso(),
            }
        except Exception as e:
            return {
                "status": "failed",
                "return_code": -1,
                "output": f"Docker Exec Error: {str(e)}",
                "ran_at": datetime_now_iso(),
            }

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
            self.image,
            "tail", "-f", "/dev/null"
        ]
        subprocess.run(run_cmd, capture_output=True, check=True)
        
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

    def run_command(self, command: str, timeout: int = 60) -> Dict[str, Any]:
        if not self.sandbox:
            self._init_sandbox()
        try:
            cmd_res = self.sandbox.commands.run(command, timeout=timeout)
            # Sync back modifications to local dir so local workspace is up to date
            self._sync_files_from_e2b()
            return {
                "status": "passed" if cmd_res.exit_code == 0 else "failed",
                "return_code": cmd_res.exit_code,
                "output": cmd_res.stdout + cmd_res.stderr,
                "ran_at": datetime_now_iso(),
            }
        except Exception as e:
            return {
                "status": "failed",
                "return_code": -1,
                "output": f"E2B Run Error: {str(e)}",
                "ran_at": datetime_now_iso(),
            }

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
    from datetime import datetime, UTC
    return datetime.now(UTC).isoformat() + "Z"


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
        logger.warning("Docker daemon not running/accessible. Falling back to local subprocess sandbox.")

    elif provider == "e2b":
        api_key = getattr(settings, "E2B_API_KEY", None)
        if api_key:
            try:
                return E2BSandbox(session_id, workspace_root, api_key=api_key)
            except Exception as e:
                logger.error(f"Failed to initialize E2B Sandbox: {e}. Falling back to local.")
        else:
            logger.warning("E2B_API_KEY missing. Falling back to local subprocess sandbox.")

    return LocalSandbox(session_id, workspace_root)
