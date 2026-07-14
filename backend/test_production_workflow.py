from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.testclient import TestClient
import jwt
import pytest
from uuid import UUID

from services.shared.api import install_api_foundation
from services.shared.production import enforce_production_startup, production_readiness
from services.shared.rate_limiter import route_limit_profile
from services.shared.security import resolve_user_id_from_auth_or_clerk


def test_ready_endpoint_reports_dependency_shape():
    app = FastAPI(title="test-service")
    install_api_foundation(app, "test-service")

    response = TestClient(app).get("/api/v1/ready")

    assert response.status_code in {200, 503}
    body = response.json()
    assert body["service"] == "test-service"
    assert body["status"] in {"ready", "degraded", "blocked"}
    assert "database" in body["dependencies"]
    assert "redis" in body["dependencies"]


def test_production_readiness_blocks_demo_and_dev_auth(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "production-jwt-secret")
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "production-field-encryption-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db.example.com:5432/arceus")
    monkeypatch.setenv("REDIS_URL", "redis://redis.example.com:6379/0")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("EMBEDDING_PROVIDER", "openai")
    monkeypatch.setenv("ALLOW_DEMO_USER", "true")
    monkeypatch.setenv("ALLOW_DEV_AUTH_FALLBACK", "true")

    readiness = production_readiness("test-service")
    checks = {check["name"]: check for check in readiness["checks"]}

    assert checks["demo_user"]["status"] == "fail"
    assert checks["dev_auth_fallback"]["status"] == "fail"
    assert checks["clerk_auth"]["status"] == "fail"
    assert readiness["status"] == "blocked"


def test_production_startup_refuses_unsafe_auth(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("JWT_SECRET", "production-jwt-secret")
    monkeypatch.setenv("APP_ENCRYPTION_KEY", "production-field-encryption-secret")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://user:pass@db.example.com:5432/arceus")
    monkeypatch.setenv("REDIS_URL", "redis://redis.example.com:6379/0")
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("ALLOW_DEMO_USER", "false")
    monkeypatch.setenv("ALLOW_DEV_AUTH_FALLBACK", "false")
    monkeypatch.delenv("CLERK_ISSUER", raising=False)
    monkeypatch.delenv("CLERK_JWKS_URL", raising=False)
    monkeypatch.delenv("CLERK_SECRET_KEY", raising=False)

    with pytest.raises(RuntimeError, match="clerk_auth"):
        enforce_production_startup("test-service")


def test_production_clerk_mode_rejects_x_user_id_fallback(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ALLOW_DEV_AUTH_FALLBACK", "true")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://clerk.example.test/.well-known/jwks.json")

    with pytest.raises(HTTPException) as exc:
        resolve_user_id_from_auth_or_clerk(
            db=None,
            authorization=None,
            x_user_id="00000000-0000-0000-0000-000000000000",
            jwt_secret="production-jwt-secret",
        )

    assert exc.value.status_code == 401
    assert "Clerk session token" in str(exc.value.detail)


def test_production_clerk_mode_rejects_legacy_local_jwt(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ALLOW_DEV_AUTH_FALLBACK", "false")
    monkeypatch.setenv("CLERK_JWKS_URL", "https://clerk.example.test/.well-known/jwks.json")

    def reject_clerk_token(_token):
        raise HTTPException(status_code=401, detail="Clerk session token is invalid")

    monkeypatch.setattr("services.shared.security.verify_clerk_token", reject_clerk_token)
    legacy_token = jwt.encode(
        {"type": "access", "sub": str(UUID("00000000-0000-0000-0000-000000000000"))},
        "production-jwt-secret",
        algorithm="HS256",
    )

    with pytest.raises(HTTPException) as exc:
        resolve_user_id_from_auth_or_clerk(
            db=None,
            authorization=f"Bearer {legacy_token}",
            x_user_id=None,
            jwt_secret="production-jwt-secret",
        )

    assert exc.value.status_code == 401
    assert "Clerk" in str(exc.value.detail)


def test_route_limit_profiles_are_classified_by_product_area():
    assert route_limit_profile("/api/v1/auth/login").name == "auth"
    assert route_limit_profile("/api/v1/files").name == "upload"
    assert route_limit_profile("/api/v1/pa/command").name == "pa"
    assert route_limit_profile("/api/v1/interview/answer").name == "interview"
    assert route_limit_profile("/api/v1/code/sessions/123/stream").name == "model"
    assert route_limit_profile("/api/v1/code/terminal/123/input").name == "code_runtime"
    assert route_limit_profile("/api/v1/admin/summary").name == "admin"


def test_download_manifest_marks_configured_release_artifacts(monkeypatch):
    from services.agent.downloads import build_download_manifest

    monkeypatch.setenv("ARCEUS_RELEASE_VERSION", "arceus-code-v1.2.3")
    monkeypatch.setenv("ARCEUS_RELEASE_SIGNED", "true")
    monkeypatch.setenv("ARCEUS_DOWNLOAD_WINDOWS_X64_INSTALLER_URL", "https://example.com/Arceus-Code-Setup.exe")
    monkeypatch.setenv("ARCEUS_DOWNLOAD_WINDOWS_X64_INSTALLER_SHA256", "abc123")

    manifest = build_download_manifest()
    windows = manifest["downloads"]["windows"][0]

    assert manifest["product"] == "arceus-code"
    assert manifest["version"] == "arceus-code-v1.2.3"
    assert manifest["signed"] is True
    assert windows["available"] is True
    assert windows["status"] == "available"
    assert windows["url"] == "https://example.com/Arceus-Code-Setup.exe"
    assert windows["checksum_sha256"] == "abc123"


def test_billing_configuration_exposes_required_webhook_events(monkeypatch):
    from services.agent.billing import billing_configuration_status

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_test")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STRIPE_PRICE_STARTER_MONTHLY", "price_starter_monthly")
    monkeypatch.setenv("STRIPE_PRICE_STARTER_ANNUAL", "price_starter_annual")
    monkeypatch.setenv("STRIPE_PRICE_PRO_MONTHLY", "price_pro_monthly")
    monkeypatch.setenv("STRIPE_PRICE_PRO_ANNUAL", "price_pro_annual")
    monkeypatch.setenv("STRIPE_PRICE_ENTERPRISE_MONTHLY", "price_enterprise_monthly")
    monkeypatch.setenv("STRIPE_PRICE_ENTERPRISE_ANNUAL", "price_enterprise_annual")

    status = billing_configuration_status()

    assert status["mode"] == "live"
    assert "checkout.session.completed" in status["required_webhook_events"]
    assert "invoice.payment_failed" in status["required_webhook_events"]
    assert status["missing_prices"] == []


def test_stripe_price_mapping_prefers_configured_price_ids(monkeypatch):
    from services.agent.billing import _stripe_price_plan_cycle

    monkeypatch.setenv("STRIPE_PRICE_PRO_ANNUAL", "price_pro_annual_123")

    plan, cycle = _stripe_price_plan_cycle(
        {"id": "price_pro_annual_123", "recurring": {"interval": "year"}},
        {},
    )

    assert plan == "pro"
    assert cycle == "annual"
