from uuid import uuid4

import jwt
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
