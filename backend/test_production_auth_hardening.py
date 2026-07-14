from uuid import UUID

import pytest
from fastapi import HTTPException

from services.shared.production import enforce_production_startup, production_readiness
from services.shared.security import dev_auth_fallback_enabled, resolve_user_id_from_auth


DEV_USER_ID = "00000000-0000-0000-0000-000000000000"


def test_local_dev_auth_fallback_still_allows_x_user_id(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("ALLOW_DEV_AUTH_FALLBACK", "true")

    assert dev_auth_fallback_enabled() is True
    assert resolve_user_id_from_auth(None, DEV_USER_ID, "secret") == UUID(DEV_USER_ID)


def test_staging_disables_x_user_id_even_if_env_flag_is_true(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ALLOW_DEV_AUTH_FALLBACK", "true")

    assert dev_auth_fallback_enabled() is False
    with pytest.raises(HTTPException) as exc:
        resolve_user_id_from_auth(None, DEV_USER_ID, "secret")
    assert exc.value.status_code == 401


def test_staging_startup_refuses_dev_auth_and_demo_user(monkeypatch):
    monkeypatch.setenv("APP_ENV", "staging")
    monkeypatch.setenv("ALLOW_DEV_AUTH_FALLBACK", "true")
    monkeypatch.setenv("ALLOW_DEMO_USER", "true")
    monkeypatch.setenv("JWT_SECRET", "supersecretkeyforlocaldevelopmentonlychangeinprod!")
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)
    monkeypatch.delenv("ARCEUS_STRICT_PRODUCTION_STARTUP", raising=False)

    readiness = production_readiness("agent-service")
    failed_names = {check["name"] for check in readiness["checks"] if check["status"] == "fail"}
    assert {"dev_auth_fallback", "demo_user", "jwt_secret", "clerk_auth"}.issubset(failed_names)

    with pytest.raises(RuntimeError) as exc:
        enforce_production_startup("agent-service")
    assert "refused unsafe production startup" in str(exc.value)


def test_strict_startup_can_be_disabled_for_recovery_only(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ALLOW_DEV_AUTH_FALLBACK", "true")
    monkeypatch.setenv("ARCEUS_STRICT_PRODUCTION_STARTUP", "false")

    enforce_production_startup("agent-service")
