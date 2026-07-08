from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from services.shared.models import FileReference, Memory, Subscription, UsageEvent


PLAN_CATALOG = {
    "free": {
        "name": "Free",
        "monthly_usd": 0,
        "monthly_inr": 0,
        "features": {
            "chat_message": {"limit": 30, "period": "daily"},
            "code_generation": {"limit": 10, "period": "daily"},
            "web_search": {"limit": 5, "period": "daily"},
            "ui_generation": {"limit": 2, "period": "daily"},
            "deployment": {"limit": 0, "period": "monthly"},
            "interview_session": {"limit": 2, "period": "lifetime"},
            "memory_store": {"limit": 50, "period": "lifetime"},
            "file_upload": {"limit": 3, "period": "lifetime", "max_file_mb": 5},
        },
        "models": ["Groq Llama 3.3"],
    },
    "starter": {
        "name": "Starter",
        "monthly_usd": 12,
        "annual_usd_per_month": 9,
        "monthly_inr": 999,
        "features": {
            "chat_message": {"limit": 300, "period": "daily"},
            "code_generation": {"limit": 100, "period": "daily"},
            "web_search": {"limit": 50, "period": "daily"},
            "ui_generation": {"limit": 20, "period": "daily"},
            "deployment": {"limit": 3, "period": "monthly"},
            "interview_session": {"limit": 0, "period": "lifetime"},
            "memory_store": {"limit": 500, "period": "lifetime"},
            "file_upload": {"limit": 20, "period": "lifetime", "max_file_mb": 25},
        },
        "models": ["GPT-4o Mini", "Groq"],
    },
    "pro": {
        "name": "Pro",
        "monthly_usd": 29,
        "annual_usd_per_month": 22,
        "monthly_inr": 2499,
        "features": {
            "chat_message": {"limit": None, "period": "daily"},
            "code_generation": {"limit": None, "period": "daily"},
            "web_search": {"limit": None, "period": "daily"},
            "ui_generation": {"limit": None, "period": "daily"},
            "deployment": {"limit": None, "period": "monthly"},
            "interview_session": {"limit": None, "period": "lifetime"},
            "memory_store": {"limit": 10000, "period": "lifetime"},
            "file_upload": {"limit": 100, "period": "lifetime", "max_file_mb": 100},
        },
        "models": ["GPT-4o", "Groq", "Gemini", "Claude"],
    },
    "enterprise": {
        "name": "Enterprise",
        "monthly_usd": 79,
        "annual_usd_per_month": 59,
        "monthly_inr": 6499,
        "features": {
            "chat_message": {"limit": None, "period": "daily"},
            "code_generation": {"limit": None, "period": "daily"},
            "web_search": {"limit": None, "period": "daily"},
            "ui_generation": {"limit": None, "period": "daily"},
            "deployment": {"limit": None, "period": "monthly"},
            "interview_session": {"limit": None, "period": "lifetime"},
            "memory_store": {"limit": None, "period": "lifetime"},
            "file_upload": {"limit": None, "period": "lifetime", "max_file_mb": None},
        },
        "models": ["All models", "BYOK", "Custom fine-tuning"],
    },
}


def get_or_create_subscription(db: Session, user_id: UUID) -> Subscription:
    subscription = (
        db.query(Subscription)
        .filter(Subscription.user_id == user_id)
        .order_by(Subscription.created_at.desc())
        .first()
    )
    if subscription:
        return subscription
    subscription = Subscription(
        user_id=user_id,
        plan_type="free",
        status="active",
        billing_cycle="monthly",
        provider="internal",
        entitlements={"interview_sessions_used": 0},
    )
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def _period_start(period: str) -> datetime | None:
    now = datetime.now(timezone.utc)
    if period == "daily":
        return now - timedelta(days=1)
    if period == "monthly":
        return now - timedelta(days=30)
    return None


def _count_usage_metric(db: Session, user_id: UUID, metric: str, period: str) -> int:
    start = _period_start(period)
    query = db.query(func.count(UsageEvent.id)).filter(UsageEvent.user_id == user_id)
    if start is not None:
        query = query.filter(UsageEvent.created_at >= start)

    if metric == "chat_message":
        query = query.filter(UsageEvent.route == "/api/v1/agents/chat")
    elif metric == "code_generation":
        query = query.filter(UsageEvent.route.like("/api/v1/code%"))
    elif metric == "web_search":
        query = query.filter(UsageEvent.route.like("/api/v1/internet%"))
    elif metric == "ui_generation":
        query = query.filter(UsageEvent.route.like("/api/v1/design%"))
    elif metric == "deployment":
        query = query.filter(UsageEvent.route.like("/api/v1/deploy%"))
    else:
        return 0
    return int(query.scalar() or 0)


def _lifetime_count(db: Session, user_id: UUID, metric: str, subscription: Subscription) -> int:
    if metric == "interview_session":
        return int((subscription.entitlements or {}).get("interview_sessions_used") or 0)
    if metric == "memory_store":
        return int(db.query(func.count(Memory.id)).filter(Memory.user_id == user_id, Memory.is_archived == False).scalar() or 0)  # noqa: E712
    if metric == "file_upload":
        return int(db.query(func.count(FileReference.id)).filter(FileReference.user_id == user_id, FileReference.status == "active").scalar() or 0)
    return 0


def billing_summary(db: Session, user_id: UUID) -> dict:
    subscription = get_or_create_subscription(db, user_id)
    plan_key = (subscription.plan_type or "free").lower()
    effective_plan_key = "enterprise" if UNLIMITED_MODE else plan_key
    plan = PLAN_CATALOG.get(effective_plan_key, PLAN_CATALOG["free"])
    usage = []
    for metric, rule in plan["features"].items():
        period = rule["period"]
        used = _lifetime_count(db, user_id, metric, subscription) if period == "lifetime" else _count_usage_metric(db, user_id, metric, period)
        limit = rule["limit"]
        usage.append({
            "metric": metric,
            "label": metric.replace("_", " ").title(),
            "period": period,
            "used": used,
            "limit": limit,
            "remaining": None if limit is None else max(limit - used, 0),
            "percent": 0 if limit in (None, 0) else min(round(used / limit * 100), 100),
            "locked": limit == 0,
        })
    return {
        "plan": {
            "key": effective_plan_key,
            "actual_key": plan_key,
            "name": "Unlimited Development" if UNLIMITED_MODE else plan["name"],
            "status": subscription.status,
            "billing_cycle": subscription.billing_cycle or "monthly",
            "monthly_usd": plan["monthly_usd"],
            "monthly_inr": plan["monthly_inr"],
            "current_period_end": subscription.current_period_end.isoformat() if subscription.current_period_end else None,
            "cancel_at_period_end": bool(subscription.cancel_at),
            "models": plan["models"],
        },
        "unlimited_mode": UNLIMITED_MODE,
        "usage": usage,
        "stripe": {
            "configured": bool(os.getenv("STRIPE_SECRET_KEY")),
            "customer_id": subscription.provider_customer_id,
            "subscription_id": subscription.provider_subscription_id,
        },
        "plans": PLAN_CATALOG,
    }


UNLIMITED_MODE = os.getenv("NEXUS_UNLIMITED_MODE", "true").lower() == "true"


def check_entitlement(db: Session, user_id: UUID, feature: str) -> dict:
    if UNLIMITED_MODE:
        return {"allowed": True, "reason": "unlimited_mode", "plan": "pro", "remaining": None}
    summary = billing_summary(db, user_id)
    plan_key = summary["plan"]["key"]
    plan = PLAN_CATALOG.get(plan_key, PLAN_CATALOG["free"])
    rule = plan["features"].get(feature)
    if not rule:
        return {"allowed": True, "reason": "unmetered"}
    item = next((entry for entry in summary["usage"] if entry["metric"] == feature), None)
    limit = rule["limit"]
    if limit is None:
        return {"allowed": True, "reason": "paid_plan", "plan": plan_key, "remaining": None}
    if limit == 0:
        return {"allowed": False, "reason": "plan_locked", "plan": plan_key, "upgrade_target": "pro" if feature == "interview_session" else "starter"}
    used = item["used"] if item else 0
    return {
        "allowed": used < limit,
        "reason": "free_trial" if feature == "interview_session" and plan_key == "free" else "usage_limit",
        "plan": plan_key,
        "used": used,
        "limit": limit,
        "remaining": max(limit - used, 0),
        "upgrade_target": "pro" if feature == "interview_session" else "starter",
    }


def record_interview_session(db: Session, user_id: UUID) -> dict:
    access = check_entitlement(db, user_id, "interview_session")
    if not access["allowed"]:
        return {**access, "recorded": False}
    subscription = get_or_create_subscription(db, user_id)
    entitlements = dict(subscription.entitlements or {})
    entitlements["interview_sessions_used"] = int(entitlements.get("interview_sessions_used") or 0) + 1
    subscription.entitlements = entitlements
    db.commit()
    return {**check_entitlement(db, user_id, "interview_session"), "recorded": True}


def create_checkout_session(plan: str, billing_cycle: str) -> dict:
    prices = {
        ("starter", "monthly"): os.getenv("STRIPE_PRICE_STARTER_MONTHLY"),
        ("starter", "annual"): os.getenv("STRIPE_PRICE_STARTER_ANNUAL"),
        ("pro", "monthly"): os.getenv("STRIPE_PRICE_PRO_MONTHLY"),
        ("pro", "annual"): os.getenv("STRIPE_PRICE_PRO_ANNUAL"),
        ("enterprise", "monthly"): os.getenv("STRIPE_PRICE_ENTERPRISE_MONTHLY"),
        ("enterprise", "annual"): os.getenv("STRIPE_PRICE_ENTERPRISE_ANNUAL"),
    }
    price_id = prices.get((plan, billing_cycle))
    if not os.getenv("STRIPE_SECRET_KEY") or not price_id:
        return {
            "status": "not_configured",
            "message": "Stripe checkout is not configured yet. Add STRIPE_SECRET_KEY and price IDs to enable paid upgrades.",
            "plan": plan,
            "billing_cycle": billing_cycle,
        }
    return {
        "status": "requires_stripe_sdk",
        "message": "Stripe keys are configured. Install and wire Stripe Checkout SDK to create hosted checkout sessions.",
        "price_id": price_id,
    }
