import pytest
from pathlib import Path
from uuid import uuid4
import subprocess
from services.agent.sandbox import LocalSandbox, DockerSandbox, get_sandbox, _redact
from services.agent.config import settings

def test_local_sandbox_command_execution():
    session_id = str(uuid4())
    workspace_root = Path("runtime/test-workspaces") / session_id
    
    sandbox = LocalSandbox(session_id, workspace_root)
    try:
        # Run a simple Python command that prints a test string
        result = sandbox.run_command("python -c \"print('nexus_sandbox_test')\"", timeout=10)
        assert result["status"] == "passed"
        assert result["return_code"] == 0
        assert "nexus_sandbox_test" in result["output"]
    finally:
        sandbox.cleanup()
        # Clean up directory
        import shutil
        if workspace_root.exists():
            shutil.rmtree(workspace_root)

def test_sandbox_resolver_defaults_to_local():
    session_id = str(uuid4())
    workspace_root = Path("runtime/test-workspaces") / session_id
    
    # Mock settings
    class MockSettings:
        SANDBOX_PROVIDER = "local"
        APP_ENV = "local"
        ALLOW_LOCAL_SANDBOX = True
        
    sandbox = get_sandbox(session_id, workspace_root, MockSettings())
    assert isinstance(sandbox, LocalSandbox)

def test_sandbox_resolver_rejects_local_in_production_without_explicit_allow():
    session_id = str(uuid4())
    workspace_root = Path("runtime/test-workspaces") / session_id

    class MockSettings:
        SANDBOX_PROVIDER = "local"
        APP_ENV = "production"
        ALLOW_LOCAL_SANDBOX = False

    with pytest.raises(RuntimeError, match="local subprocess execution is disabled"):
        get_sandbox(session_id, workspace_root, MockSettings())

def test_e2b_requires_api_key_in_production():
    session_id = str(uuid4())
    workspace_root = Path("runtime/test-workspaces") / session_id

    class MockSettings:
        SANDBOX_PROVIDER = "e2b"
        APP_ENV = "production"
        ALLOW_LOCAL_SANDBOX = False
        E2B_API_KEY = None

    with pytest.raises(RuntimeError, match="E2B_API_KEY is required"):
        get_sandbox(session_id, workspace_root, MockSettings())


def test_docker_sandbox_policy_blocks_network_by_default(tmp_path, monkeypatch):
    monkeypatch.delenv("SANDBOX_ALLOW_NETWORK", raising=False)
    sandbox = DockerSandbox(str(uuid4()), tmp_path, image="arceus-code-sandbox:local")

    policy = sandbox._policy(allow_network=True)
    flags = sandbox._docker_limits(allow_network=True)

    assert policy["network_mode"] == "none"
    assert "--network" in flags
    assert flags[flags.index("--network") + 1] == "none"


def test_docker_sandbox_policy_allows_network_only_when_enabled(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDBOX_ALLOW_NETWORK", "true")
    sandbox = DockerSandbox(str(uuid4()), tmp_path, image="arceus-code-sandbox:local")

    policy = sandbox._policy(allow_network=True)
    flags = sandbox._docker_limits(allow_network=True)

    assert policy["network_mode"] == "bridge"
    assert flags[flags.index("--network") + 1] == "bridge"


def test_docker_sandbox_limits_are_enforced_in_flags(tmp_path):
    sandbox = DockerSandbox(str(uuid4()), tmp_path, image="arceus-code-sandbox:local")
    flags = sandbox._docker_limits()

    expected_flags = {
        "--user": "1000:1000",
        "--memory": "512m",
        "--memory-swap": "512m",
        "--cpu-period": "100000",
        "--cpu-quota": "50000",
        "--pids-limit": "64",
        "--network": "none",
        "--security-opt": "no-new-privileges",
        "--cap-drop": "ALL",
        "--ulimit": "nofile=1024:1024",
    }
    for flag, value in expected_flags.items():
        assert flag in flags
        assert flags[flags.index(flag) + 1] == value
    assert "--read-only" in flags
    assert "--tmpfs" in flags


def test_docker_sandbox_timeout_removes_container_and_redacts_output(tmp_path, monkeypatch):
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        if cmd[:2] == ["docker", "run"]:
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=1, output="token=abc123", stderr="Bearer secret-value")
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    sandbox = DockerSandbox(str(uuid4()), tmp_path, image="arceus-code-sandbox:local")

    result = sandbox.run_command("python -c print(1)", timeout=1)

    assert result["status"] == "timeout"
    assert "abc123" not in result["output"]
    assert "secret-value" not in result["output"]
    assert "[REDACTED]" in result["output"]
    assert any(call[:3] == ["docker", "rm", "-f"] for call in calls)


def test_secret_redaction_covers_common_tokens():
    output = "sk-abcDEF1234567890 token=my-secret password=hunter2 Bearer ghp_abcdefghijklmnopqrst"
    redacted = _redact(output)

    assert "sk-abc" not in redacted
    assert "my-secret" not in redacted
    assert "hunter2" not in redacted
    assert "ghp_" not in redacted
    assert "[REDACTED]" in redacted
