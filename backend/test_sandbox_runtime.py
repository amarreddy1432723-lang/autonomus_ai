import pytest
from pathlib import Path
from uuid import uuid4
from services.agent.sandbox import LocalSandbox, DockerSandbox, get_sandbox
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
        
    sandbox = get_sandbox(session_id, workspace_root, MockSettings())
    assert isinstance(sandbox, LocalSandbox)
