from uuid import uuid4
from types import SimpleNamespace

import jwt
import pytest
from fastapi import HTTPException
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from services.agent import github_service
from services.agent.config import settings


def _private_key_pem() -> tuple[str, str]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("utf-8")
    public_pem = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode("utf-8")
    return private_pem, public_pem


def test_github_app_jwt_generation(monkeypatch):
    private_pem, public_pem = _private_key_pem()
    monkeypatch.setattr(settings, "GITHUB_APP_ID", "12345")
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY", private_pem)

    token = github_service.github_app_jwt()
    payload = jwt.decode(token, public_pem, algorithms=["RS256"], options={"verify_aud": False})

    assert payload["iss"] == "12345"
    assert payload["exp"] > payload["iat"]


def test_github_install_url_contains_signed_user_state(monkeypatch):
    private_pem, _ = _private_key_pem()
    user_id = uuid4()
    monkeypatch.setattr(settings, "GITHUB_APP_ID", "12345")
    monkeypatch.setattr(settings, "GITHUB_APP_PRIVATE_KEY", private_pem)
    monkeypatch.setattr(settings, "GITHUB_APP_NAME", "nexus-ai")

    result = github_service.github_install_url(user_id, "test-secret")
    payload = jwt.decode(result["state"], "test-secret", algorithms=["HS256"])

    assert "github.com/apps/nexus-ai/installations/new" in result["install_url"]
    assert payload["sub"] == str(user_id)
    assert payload["type"] == "github_app_install"


def test_commit_readiness_requires_applied_files():
    session = SimpleNamespace(metadata_json={})

    with pytest.raises(HTTPException) as exc:
        github_service.validate_commit_readiness(session)

    assert exc.value.status_code == 400
    assert "No approved files" in str(exc.value.detail)


def test_commit_readiness_rejects_unapproved_selection():
    session = SimpleNamespace(metadata_json={
        "last_applied_files": [{"filename": "src/app.ts", "operation": "modify", "additions": 2, "deletions": 1}]
    })

    with pytest.raises(HTTPException) as exc:
        github_service.validate_commit_readiness(session, ["src/other.ts"])

    assert exc.value.status_code == 409
    assert exc.value.detail["error_class"] == "patch_conflict"
    assert exc.value.detail["files"] == ["src/other.ts"]


def test_commit_readiness_blocks_pending_review_for_commit_all():
    session = SimpleNamespace(metadata_json={
        "last_applied_files": [{"filename": "src/app.ts", "operation": "modify", "additions": 2, "deletions": 1}],
        "patch_preview": [{"filename": "src/pending.ts", "operation": "modify"}],
    })

    with pytest.raises(HTTPException) as exc:
        github_service.validate_commit_readiness(session)

    assert exc.value.status_code == 409
    assert exc.value.detail["message"] == "Patch review is still pending"


def test_staged_changes_exposes_commit_blockers_without_throwing():
    session = SimpleNamespace(metadata_json={
        "last_applied_files": [{"filename": "src/app.ts", "operation": "modify", "additions": 2, "deletions": 1}],
        "patch_preview": [{"filename": "src/pending.ts", "operation": "modify"}],
    })

    staged = github_service.staged_approved_changes(session)

    assert staged["approval_state"] == "blocked"
    assert staged["commit_ready"] is False
    assert staged["commit_blockers"][0]["code"] == "pending_review"
    assert staged["staged"][0]["filename"] == "src/app.ts"


def test_staged_changes_marks_approved_files_ready():
    session = SimpleNamespace(metadata_json={
        "last_applied_files": [{"filename": "src/app.ts", "operation": "modify", "additions": 2, "deletions": 1}],
    })

    staged = github_service.staged_approved_changes(session)

    assert staged["approval_state"] == "approved"
    assert staged["commit_ready"] is True
    assert staged["commit_blockers"] == []
