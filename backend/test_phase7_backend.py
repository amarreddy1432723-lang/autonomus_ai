from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from services.auth.main import app as auth_app
from services.goals.main import app as goals_app
from services.shared.database import SessionLocal, verify_default_user
from services.shared.models import Goal, User, UserSession


USER_ID = UUID("00000000-0000-0000-0000-000000000000")
TEST_EMAIL = "phase7-test@example.com"


@pytest.fixture()
def db():
    session = SessionLocal()
    verify_default_user(session)
    session.query(Goal).filter(Goal.user_id == USER_ID, Goal.title.like("Phase7 test%")).delete()
    old_user = session.query(User).filter(User.email == TEST_EMAIL).first()
    if old_user:
        session.delete(old_user)
    session.commit()
    try:
        yield session
    finally:
        session.query(Goal).filter(Goal.user_id == USER_ID, Goal.title.like("Phase7 test%")).delete()
        old_user = session.query(User).filter(User.email == TEST_EMAIL).first()
        if old_user:
            session.delete(old_user)
        session.commit()
        session.close()


def test_health_and_request_id_headers():
    client = TestClient(goals_app)
    response = client.get("/api/v1/health", headers={"x-request-id": "phase7-request-id"})

    assert response.status_code == 200
    assert response.json()["service"] == "goals-service"
    assert response.headers["x-request-id"] == "phase7-request-id"
    assert response.headers["x-api-version"] == "v1"


def test_auth_register_login_refresh_and_session_revoke(db):
    client = TestClient(auth_app)
    register = client.post(
        "/api/v1/auth/register",
        json={"email": TEST_EMAIL, "password": "phase7-password-123"},
    )
    assert register.status_code == 201, register.text

    login = client.post(
        "/api/v1/auth/login",
        json={"email": TEST_EMAIL, "password": "phase7-password-123"},
    )
    assert login.status_code == 200, login.text
    tokens = login.json()
    assert tokens["access_token"]
    assert tokens["refresh_token"]

    user = db.query(User).filter(User.email == TEST_EMAIL).first()
    assert user is not None
    assert db.query(UserSession).filter(UserSession.user_id == user.id, UserSession.is_active == True).count() == 1

    refresh = client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert refresh.status_code == 200, refresh.text
    rotated = refresh.json()
    assert rotated["refresh_token"] != tokens["refresh_token"]

    sessions = client.get("/api/v1/auth/sessions", headers={"Authorization": f"Bearer {rotated['access_token']}"})
    assert sessions.status_code == 200, sessions.text
    assert len(sessions.json()) == 1

    logout = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {rotated['access_token']}"},
        json={"refresh_token": rotated["refresh_token"]},
    )
    assert logout.status_code == 200, logout.text
    db.expire_all()
    assert db.query(UserSession).filter(UserSession.user_id == user.id, UserSession.is_active == True).count() == 0


def test_goal_list_is_paginated_and_filterable(db):
    client = TestClient(goals_app)
    headers = {"x-user-id": str(USER_ID)}
    for index in range(2):
        response = client.post(
            "/api/v1/goals",
            headers=headers,
            json={
                "title": f"Phase7 test paginated goal {index}",
                "description": "Verify bounded list endpoints.",
                "category": "software",
            },
        )
        assert response.status_code == 201, response.text

    first_page = client.get("/api/v1/goals?page=1&page_size=1&category=software", headers=headers)
    second_page = client.get("/api/v1/goals?page=2&page_size=1&category=software", headers=headers)

    assert first_page.status_code == 200, first_page.text
    assert second_page.status_code == 200, second_page.text
    assert len(first_page.json()) == 1
    assert len(second_page.json()) == 1
