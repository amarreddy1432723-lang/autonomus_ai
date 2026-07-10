import os
import shutil
import pytest
from uuid import UUID
from fastapi.testclient import TestClient
from services.agent.main import app as agent_app
from services.shared.database import SessionLocal, verify_default_user
from services.shared.models import CodeProject, CodeSession, FileReference

USER_ID = UUID("00000000-0000-0000-0000-000000000000")
TEST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "test-desktop-sync-dir"))

@pytest.fixture(autouse=True)
def setup_teardown_dir():
    # Setup test directory
    os.makedirs(TEST_DIR, exist_ok=True)
    with open(os.path.join(TEST_DIR, "main.py"), "w", encoding="utf-8") as f:
        f.write("print('Original content')\n")
        
    yield
    
    # Clean up test directory
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)

def test_sync_local_workspace_file_endpoint():
    # Prepare DB
    db = SessionLocal()
    verify_default_user(db)
    
    # Create project and session
    project = CodeProject(user_id=USER_ID, name="test-project", status="active")
    db.add(project)
    db.commit()
    db.refresh(project)
    
    session = CodeSession(
        user_id=USER_ID,
        project_id=project.id,
        title="test-project workspace",
        file_ids=[],
        status="active",
        metadata_json={
            "local_workspace_path": TEST_DIR,
            "activity_log": [],
            "file_tree": [],
            "patch_preview": [],
            "rollback_snapshots": [],
        }
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    db.close()
    
    client = TestClient(agent_app)
    
    # 1. Sync file ADD
    response = client.post(
        f"/api/v1/code/sessions/{session.id}/sync-local-file",
        headers={"x-user-id": str(USER_ID)},
        json={"action": "add", "relative_path": "main.py"}
    )
    assert response.status_code == 200, response.text
    session_data = response.json()
    assert len(session_data["file_ids"]) == 1
    
    # Verify in DB
    db = SessionLocal()
    files = db.query(FileReference).filter(FileReference.owner_id == session.id).all()
    assert len(files) == 1
    assert files[0].filename == "main.py"
    assert files[0].size_bytes == len("print('Original content')\n")
    
    # 2. Sync file CHANGE
    # Update file contents
    with open(os.path.join(TEST_DIR, "main.py"), "w", encoding="utf-8") as f:
        f.write("print('Modified content')\n")
        
    response = client.post(
        f"/api/v1/code/sessions/{session.id}/sync-local-file",
        headers={"x-user-id": str(USER_ID)},
        json={"action": "change", "relative_path": "main.py"}
    )
    assert response.status_code == 200, response.text
    
    db.refresh(files[0])
    assert files[0].size_bytes == len("print('Modified content')\n")
    
    # 3. Sync file DELETE (unlink)
    response = client.post(
        f"/api/v1/code/sessions/{session.id}/sync-local-file",
        headers={"x-user-id": str(USER_ID)},
        json={"action": "unlink", "relative_path": "main.py"}
    )
    assert response.status_code == 200, response.text
    session_data = response.json()
    assert len(session_data["file_ids"]) == 0
    
    files_after = db.query(FileReference).filter(FileReference.owner_id == session.id).all()
    assert len(files_after) == 0
    
    # Clean up project/session records
    db.delete(session)
    db.delete(project)
    db.commit()
    db.close()
