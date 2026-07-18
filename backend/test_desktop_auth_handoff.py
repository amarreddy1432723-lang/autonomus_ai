import pytest
from uuid import UUID
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError
from services.auth.main import app as auth_app
from services.shared.database import Base, engine, SessionLocal, verify_default_user
from services.shared.models import User

USER_ID = UUID("00000000-0000-0000-0000-000000000000")

@pytest.fixture(autouse=True, scope="module")
def setup_test_db():
    # Ensure all tables are created in the target test database (e.g. SQLite memory or file)
    try:
        Base.metadata.create_all(bind=engine)
    except OperationalError as exc:
        pytest.skip(f"database unavailable for desktop auth handoff test: {exc}")
    yield

def test_desktop_auth_handoff_lifecycle():
    # Setup test user in database
    db = SessionLocal()
    verify_default_user(db)
    user = db.query(User).filter(User.id == USER_ID).first()
    assert user is not None
    db.close()

    client = TestClient(auth_app)

    # 1. Create desktop auth code (fails with invalid redirect URI)
    response = client.post(
        "/api/v1/auth/desktop/code",
        headers={"x-user-id": str(USER_ID)},
        json={"redirect_uri": "http://invalid-redirect"}
    )
    assert response.status_code == 400
    assert "Desktop redirect URI must use arceus://auth/callback" in response.json()["detail"]

    # 2. Create desktop auth code (succeeds with valid redirect URI)
    response = client.post(
        "/api/v1/auth/desktop/code",
        headers={"x-user-id": str(USER_ID)},
        json={"redirect_uri": "arceus://auth/callback"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "redirect_url" in data
    assert "code=" in data["redirect_url"]
    assert data["code_expires_in_seconds"] == 300

    # Extract code from redirect URL
    redirect_url = data["redirect_url"]
    code = redirect_url.split("code=")[1]

    # 3. Exchange desktop auth code (succeeds with valid code)
    exchange_response = client.post(
        "/api/v1/auth/desktop/exchange",
        json={"code": code}
    )
    assert exchange_response.status_code == 200
    token_data = exchange_response.json()
    assert "access_token" in token_data
    assert "refresh_token" in token_data
    assert token_data["token_type"] == "bearer"

    # 4. Exchange desktop auth code (fails with invalid code)
    invalid_response = client.post(
        "/api/v1/auth/desktop/exchange",
        json={"code": "invalid_code_payload"}
    )
    assert invalid_response.status_code == 401
    assert "invalid or expired" in invalid_response.json()["detail"]
