import os
import time
import pytest
from pathlib import Path
from services.agent.sandbox import (
    LocalSandbox,
    DockerSandbox,
    _redact,
    _resolve_local_command_parts,
    _command_result,
    get_sandbox,
)

class MockSettings:
    SANDBOX_PROVIDER = "local"
    ALLOW_LOCAL_SANDBOX = True
    APP_ENV = "test"
    SANDBOX_DOCKER_IMAGE = "python:3.11-slim"

def test_secret_redaction():
    raw_output = (
        "Server started with api_key: abc123supersecret\n"
        "Authorization: Bearer my-secret-jwt-token-12345\n"
        "OpenAI Key: sk-1234567890abcdefghij\n"
        "GitHub Token: ghp_123456789012345678901234567890\n"
        "Normal output line 42"
    )
    redacted = _redact(raw_output)
    assert "abc123supersecret" not in redacted
    assert "my-secret-jwt-token-12345" not in redacted
    assert "sk-1234567890abcdefghij" not in redacted
    assert "ghp_123456789012345678901234567890" not in redacted
    assert "[REDACTED]" in redacted
    assert "Normal output line 42" in redacted

def test_local_sandbox_command_execution(tmp_path: Path):
    sandbox = LocalSandbox(session_id="test-session-1", workspace_root=tmp_path)
    
    # Run a simple echo command
    if os.name == "nt":
        result = sandbox.run_command("cmd /c echo Hello Arceus Sandbox")
    else:
        result = sandbox.run_command("echo Hello Arceus Sandbox")
        
    assert result["status"] == "passed"
    assert result["return_code"] == 0
    assert "Hello Arceus Sandbox" in result["output"]
    assert result["provider"] == "local"
    assert "duration_ms" in result
    assert result["duration_ms"] >= 0

def test_local_sandbox_timeout(tmp_path: Path):
    sandbox = LocalSandbox(session_id="test-session-timeout", workspace_root=tmp_path)
    
    # Run a command that sleeps longer than timeout (1 second timeout)
    if os.name == "nt":
        result = sandbox.run_command("powershell -Command Start-Sleep -Seconds 5", timeout=1)
    else:
        result = sandbox.run_command("sleep 5", timeout=1)
        
    assert result["status"] == "timeout"
    assert result["return_code"] is None

def test_docker_sandbox_policy(tmp_path: Path):
    sandbox = DockerSandbox(session_id="test-docker-policy", workspace_root=tmp_path)
    policy = sandbox._policy(preview=False, allow_network=False)
    
    assert policy["network_mode"] == "none"
    assert policy["read_only"] is True
    assert policy["security_opt"] == "no-new-privileges"
    assert policy["cap_drop"] == "ALL"
    assert "512m" in policy["memory"]

    docker_args = sandbox._docker_limits(preview=False, allow_network=False)
    assert "--read-only" in docker_args
    assert "--security-opt" in docker_args
    assert "no-new-privileges" in docker_args
    assert "--cap-drop" in docker_args
    assert "ALL" in docker_args

def test_get_sandbox_factory(tmp_path: Path):
    settings = MockSettings()
    sandbox = get_sandbox(session_id="factory-test", workspace_root=tmp_path, settings=settings)
    assert isinstance(sandbox, LocalSandbox)
    assert sandbox.session_id == "factory-test"
    assert sandbox.workspace_root == tmp_path.resolve()
