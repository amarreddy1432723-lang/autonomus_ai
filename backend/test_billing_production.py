from uuid import UUID, uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from services.agent.main import app
from services.shared.database import SessionLocal, verify_default_user
from services.shared.models import Subscription


USER_ID = UUID("00000000-0000-0000-0000-000000000000")


@pytest.fixture()
def db():
    session = SessionLocal()
    verify_default_user(session)
    session.query(Subscription).filter(Subscription.user_id == USER_ID).delete()
    session.commit()
    try:
        yield session
    finally:
        session.query(Subscription).filter(Subscription.user_id == USER_ID).delete()
        session.commit()
        session.close()


def _clear_stripe_env(monkeypatch):
    for name in [
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
        "STRIPE_PRICE_STARTER_MONTHLY",
        "STRIPE_PRICE_STARTER_ANNUAL",
        "STRIPE_PRICE_PRO_MONTHLY",
        "STRIPE_PRICE_PRO_ANNUAL",
        "STRIPE_PRICE_ENTERPRISE_MONTHLY",
        "STRIPE_PRICE_ENTERPRISE_ANNUAL",
        "STRIPE_REQUIRE_ALL_PRICES",
    ]:
        monkeypatch.delenv(name, raising=False)


def test_billing_configuration_blocks_missing_prices_in_live_env(monkeypatch):
    from services.agent.billing import billing_configuration_status

    _clear_stripe_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_test")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")
    monkeypatch.setenv("STRIPE_PRICE_PRO_MONTHLY", "price_pro_monthly")

    status = billing_configuration_status()

    assert status["live_environment"] is True
    assert status["require_all_prices"] is True
    assert status["ready"] is False
    assert any("Missing Stripe price ids" in blocker for blocker in status["blockers"])
    assert "pro_monthly" not in status["missing_prices"]


def test_billing_configuration_treats_missing_prices_as_local_warning(monkeypatch):
    from services.agent.billing import billing_configuration_status

    _clear_stripe_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_local")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_test")

    status = billing_configuration_status()

    assert status["live_environment"] is False
    assert status["require_all_prices"] is False
    assert not any("Missing Stripe price ids" in blocker for blocker in status["blockers"])
    assert any("Missing Stripe price ids" in warning for warning in status["warnings"])


def test_free_plan_blocks_github_operations_with_upgrade_payload(db):
    from services.agent.billing import require_feature_entitlement

    with pytest.raises(HTTPException) as exc:
        require_feature_entitlement(db, USER_ID, "code_github_operation")

    assert exc.value.status_code == 402
    assert exc.value.detail["code"] == "PLAN_LOCKED"
    assert exc.value.detail["feature"] == "code_github_operation"
    assert exc.value.detail["upgrade_url"] == "/settings?tab=billing"


def test_checkout_validates_plan_and_cycle(db):
    from services.agent.billing import create_checkout_session

    with pytest.raises(HTTPException) as exc:
        create_checkout_session(db, USER_ID, "invalid", "monthly")
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "unsupported_plan"

    with pytest.raises(HTTPException) as exc:
        create_checkout_session(db, USER_ID, "pro", "weekly")
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "unsupported_billing_cycle"


def test_stripe_checkout_webhook_syncs_subscription(db):
    from services.agent.billing import sync_stripe_webhook_event

    event = {
        "id": "evt_billing_test_checkout",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_test_123",
                "subscription": "sub_test_123",
                "metadata": {
                    "user_id": str(USER_ID),
                    "plan": "pro",
                    "billing_cycle": "annual",
                },
            }
        },
    }

    result = sync_stripe_webhook_event(db, event)
    db.commit()
    subscription = db.query(Subscription).filter(Subscription.user_id == USER_ID).first()

    assert result["synced"] is True
    assert subscription.provider == "stripe"
    assert subscription.provider_customer_id == "cus_test_123"
    assert subscription.provider_subscription_id == "sub_test_123"
    assert subscription.plan_type == "pro"
    assert subscription.billing_cycle == "annual"
    assert subscription.status == "active"


def test_stripe_payment_failure_downgrades_to_free(db):
    from services.agent.billing import sync_stripe_webhook_event

    subscription = Subscription(
        user_id=USER_ID,
        plan_type="pro",
        status="active",
        provider="stripe",
        provider_customer_id="cus_failed_payment",
        provider_subscription_id="sub_failed_payment",
    )
    db.add(subscription)
    db.commit()

    result = sync_stripe_webhook_event(db, {
        "id": "evt_billing_test_failed",
        "type": "invoice.payment_failed",
        "data": {"object": {"customer": "cus_failed_payment"}},
    })
    db.commit()
    db.refresh(subscription)

    assert result["synced"] is True
    assert subscription.plan_type == "free"
    assert subscription.status == "past_due"
    assert "payment_failure_at" in (subscription.entitlements or {})


def test_live_webhook_fails_closed_when_secret_missing(monkeypatch):
    _clear_stripe_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")

    response = TestClient(app).post("/api/v1/billing/webhook", json={"id": "evt_missing_secret"})

    assert response.status_code == 503
    assert "stripe_webhook_not_configured" in response.text


def test_live_webhook_fails_closed_without_stripe_sdk(monkeypatch):
    import builtins

    _clear_stripe_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_live")
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "stripe":
            raise ImportError("stripe unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    response = TestClient(app).post(
        "/api/v1/billing/webhook",
        headers={"stripe-signature": "test"},
        json={"id": "evt_without_sdk"},
    )

    assert response.status_code == 503
    assert "stripe_sdk_required" in response.text


def test_local_webhook_can_use_json_fallback_when_sdk_missing(monkeypatch, db):
    import builtins

    _clear_stripe_env(monkeypatch)
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "whsec_local")
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "stripe":
            raise ImportError("stripe unavailable")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    response = TestClient(app).post(
        "/api/v1/billing/webhook",
        json={
            "id": f"evt_billing_test_local_json_fallback_{uuid4().hex}",
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "customer": "cus_local_json",
                    "subscription": "sub_local_json",
                    "metadata": {"user_id": str(USER_ID), "plan": "starter", "billing_cycle": "monthly"},
                }
            },
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["synced"] is True


def test_code_pa_and_interview_expensive_actions_return_402_payloads(db):
    from services.agent.billing import require_feature_entitlement, record_interview_session

    github_denial = None
    with pytest.raises(HTTPException) as exc:
        require_feature_entitlement(db, USER_ID, "code_github_operation")
    github_denial = exc.value.detail

    pa_denial = None
    with pytest.raises(HTTPException) as exc:
        require_feature_entitlement(db, USER_ID, "pa_command")
    pa_denial = exc.value.detail

    record_interview_session(db, USER_ID)
    record_interview_session(db, USER_ID)
    third_interview = record_interview_session(db, USER_ID)

    assert github_denial["code"] == "PLAN_LOCKED"
    assert github_denial["upgrade_url"] == "/settings?tab=billing"
    assert pa_denial["code"] == "PLAN_LOCKED"
    assert pa_denial["upgrade_target"] == "pro"
    assert third_interview["recorded"] is False
    assert third_interview["allowed"] is False
