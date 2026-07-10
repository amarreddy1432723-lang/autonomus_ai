import os
import shutil
import pytest
from uuid import UUID
from fastapi.testclient import TestClient
from services.agent.main import app as agent_app
from services.shared.database import SessionLocal, verify_default_user
from services.shared.models import CodeSession, FileReference

USER_ID = UUID("00000000-0000-0000-0000-000000000000")
TEST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "test-local-import-dir"))

@pytest.fixture(autouse=True)
def setup_teardown_dir():
    # Setup test directory
    os.makedirs(TEST_DIR, exist_ok=True)
    with open(os.path.join(TEST_DIR, "main.py"), "w", encoding="utf-8") as f:
        f.write("print('Hello from local import')\n")
    with open(os.path.join(TEST_DIR, "utils.py"), "w", encoding="utf-8") as f:
        f.write("def helper(): return True\n")
        
    yield
    
    # Clean up test directory
    if os.path.exists(TEST_DIR):
        shutil.rmtree(TEST_DIR)

def test_import_local_workspace_endpoint():
    # Prepare DB
    db = SessionLocal()
    try:
        verify_default_user(db)
    except Exception as exc:
        pytest.skip(f"Local test database is not compatible with UUID test fixtures: {exc}")
    finally:
        db.close()
    
    client = TestClient(agent_app)
    response = client.post(
        "/api/v1/code/sessions/import-local",
        headers={"x-user-id": str(USER_ID)},
        json={"local_path": TEST_DIR}
    )
    
    assert response.status_code == 201, response.text
    session_data = response.json()
    assert session_data["title"] == "test-local-import-dir workspace"
    assert len(session_data["file_ids"]) == 2

    # Verify records in database
    db = SessionLocal()
    session = db.query(CodeSession).filter(CodeSession.id == session_data["id"]).first()
    assert session is not None
    assert len(session.file_ids) == 2
    assert session.metadata_json["local_workspace_path"] == TEST_DIR
    
    files = db.query(FileReference).filter(FileReference.owner_id == session.id).all()
    assert len(files) == 2
    filenames = {f.filename for f in files}
    assert filenames == {"main.py", "utils.py"}
    
    db.close()
