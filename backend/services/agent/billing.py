from __future__ import annotations

import os
import importlib.util
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from fastapi import HTTPException

from services.shared.models import AuditLog, FileReference, Memory, Subscription, UsageEvent


def _live_billing_environment() -> bool:
    return os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "local")).lower() in {"staging", "prod", "production"}


PLAN_CATALOG = {
    "free": {
        "name": "Free",
        "monthly_usd": 0,
        "monthly_inr": 0,
        "features": {
            "chat_message": {"limit": 30, "period": "daily"},
            "code_generation": {"limit": 10, "period": "daily"},
            "code_job": {"limit": 10, "period": "daily"},
            "code_runtime_command": {"limit": 5, "period": "daily"},
            "code_preview_check": {"limit": 3, "period": "daily"},
            "code_github_operation": {"limit": 0, "period": "daily"},
            "code_file_storage": {"limit": 3, "period": "lifetime"},
            "web_search": {"limit": 5, "period": "daily"},
            "ui_generation": {"limit": 2, "period": "daily"},
            "deployment": {"limit": 0, "period": "monthly"},
            "interview_session": {"limit": 2, "period": "lifetime"},
            "memory_store": {"limit": 50, "period": "lifetime"},
            "file_upload": {"limit": 3, "period": "lifetime", "max_file_mb": 5},
            "nexus_pa": {"limit": 0, "period": "monthly"},
            "pa_command": {"limit": 0, "period": "daily"},
            "pa_reminder": {"limit": 0, "period": "lifetime"},
            "pa_automation": {"limit": 0, "period": "lifetime"},
            "pa_daily_brief": {"limit": 0, "period": "daily"},
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
            "code_job": {"limit": 100, "period": "daily"},
            "code_runtime_command": {"limit": 50, "period": "daily"},
            "code_preview_check": {"limit": 30, "period": "daily"},
            "code_github_operation": {"limit": 20, "period": "daily"},
            "code_file_storage": {"limit": 20, "period": "lifetime"},
            "web_search": {"limit": 50, "period": "daily"},
            "ui_generation": {"limit": 20, "period": "daily"},
            "deployment": {"limit": 3, "period": "monthly"},
            "interview_session": {"limit": 0, "period": "lifetime"},
            "memory_store": {"limit": 500, "period": "lifetime"},
            "file_upload": {"limit": 20, "period": "lifetime", "max_file_mb": 25},
            "nexus_pa": {"limit": 0, "period": "monthly"},
            "pa_command": {"limit": 0, "period": "daily"},
            "pa_reminder": {"limit": 0, "period": "lifetime"},
            "pa_automation": {"limit": 0, "period": "lifetime"},
            "pa_daily_brief": {"limit": 0, "period": "daily"},
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
            "code_job": {"limit": None, "period": "daily"},
            "code_runtime_command": {"limit": None, "period": "daily"},
            "code_preview_check": {"limit": None, "period": "daily"},
            "code_github_operation": {"limit": None, "period": "daily"},
            "code_file_storage": {"limit": 100, "period": "lifetime"},
            "web_search": {"limit": None, "period": "daily"},
            "ui_generation": {"limit": None, "period": "daily"},
            "deployment": {"limit": None, "period": "monthly"},
            "interview_session": {"limit": None, "period": "lifetime"},
            "memory_store": {"limit": 10000, "period": "lifetime"},
            "file_upload": {"limit": 100, "period": "lifetime", "max_file_mb": 100},
            "nexus_pa": {"limit": None, "period": "monthly"},
            "pa_command": {"limit": None, "period": "daily"},
            "pa_reminder": {"limit": 1000, "period": "lifetime"},
            "pa_automation": {"limit": 100, "period": "lifetime"},
            "pa_daily_brief": {"limit": None, "period": "daily"},
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
            "code_job": {"limit": None, "period": "daily"},
            "code_runtime_command": {"limit": None, "period": "daily"},
            "code_preview_check": {"limit": None, "period": "daily"},
            "code_github_operation": {"limit": None, "period": "daily"},
            "code_file_storage": {"limit": None, "period": "lifetime"},
            "web_search": {"limit": None, "period": "daily"},
            "ui_generation": {"limit": None, "period": "daily"},
            "deployment": {"limit": None, "period": "monthly"},
            "interview_session": {"limit": None, "period": "lifetime"},
            "memory_store": {"limit": None, "period": "lifetime"},
            "file_upload": {"limit": None, "period": "lifetime", "max_file_mb": None},
            "nexus_pa": {"limit": None, "period": "monthly"},
            "pa_command": {"limit": None, "period": "daily"},
            "pa_reminder": {"limit": None, "period": "lifetime"},
            "pa_automation": {"limit": None, "period": "lifetime"},
            "pa_daily_brief": {"limit": None, "period": "daily"},
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
    elif metric == "code_job":
        from services.shared.models import AgentJob
        job_query = db.query(func.count(AgentJob.id)).filter(AgentJob.user_id == user_id)
        if start is not None:
            job_query = job_query.filter(AgentJob.created_at >= start)
        return int(job_query.scalar() or 0)
    elif metric == "code_runtime_command":
        from services.shared.models import AgentJob
        job_query = db.query(func.count(AgentJob.id)).filter(AgentJob.user_id == user_id, AgentJob.mode.in_(["runtime_command", "command", "checks", "runtime_install", "runtime_sync", "sandbox_start", "sandbox_stop", "apply", "rollback", "terminal", "terminal_input"]))
        if start is not None:
            job_query = job_query.filter(AgentJob.created_at >= start)
        return int(job_query.scalar() or 0)
    elif metric == "code_preview_check":
        from services.shared.models import AgentJob
        job_query = db.query(func.count(AgentJob.id)).filter(AgentJob.user_id == user_id, AgentJob.mode.in_(["preview", "preview_start", "preview_stop", "fix_preview"]))
        if start is not None:
            job_query = job_query.filter(AgentJob.created_at >= start)
        return int(job_query.scalar() or 0)
    elif metric == "code_github_operation":
        from services.shared.models import AgentJob
        job_query = db.query(func.count(AgentJob.id)).filter(AgentJob.user_id == user_id, AgentJob.mode.in_(["github_import", "github_branch", "github_commit", "github_pr", "git"]))
        if start is not None:
            job_query = job_query.filter(AgentJob.created_at >= start)
        return int(job_query.scalar() or 0)
    elif metric == "web_search":
        query = query.filter(UsageEvent.route.like("/api/v1/internet%"))
    elif metric == "ui_generation":
        query = query.filter(UsageEvent.route.like("/api/v1/design%"))
    elif metric == "deployment":
        query = query.filter(UsageEvent.route.like("/api/v1/deploy%"))
    elif metric == "pa_command":
        query = query.filter(UsageEvent.route == "/api/v1/pa/command")
    elif metric == "pa_daily_brief":
        query = query.filter(UsageEvent.route == "/api/v1/pa/daily-brief")
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
    if metric == "code_file_storage":
        return int(db.query(func.count(FileReference.id)).filter(FileReference.user_id == user_id, FileReference.owner_type == "code_workspace", FileReference.status == "active").scalar() or 0)
    if metric == "pa_reminder":
        from services.shared.models import Schedule
        return int(db.query(func.count(Schedule.id)).filter(Schedule.user_id == user_id, Schedule.trigger_payload["pa_type"].as_string() == "reminder").scalar() or 0)
    if metric == "pa_automation":
        from services.shared.models import Schedule
        return int(db.query(func.count(Schedule.id)).filter(Schedule.user_id == user_id, Schedule.trigger_payload["pa_type"].as_string() == "automation").scalar() or 0)
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


UNLIMITED_MODE = os.getenv("NEXUS_UNLIMITED_MODE", "false").lower() == "true"


FEATURE_UPGRADE_COPY = {
    "chat_message": ("Starter", "You have reached today's chat limit."),
    "code_generation": ("Starter", "You have reached today's Arceus Code generation limit."),
    "code_job": ("Starter", "You have reached today's Arceus Code job limit."),
    "code_runtime_command": ("Starter", "You have reached today's terminal/runtime command limit."),
    "code_preview_check": ("Starter", "You have reached today's preview verification limit."),
    "code_github_operation": ("Starter", "GitHub import, commit, and PR actions require a paid plan."),
    "code_file_storage": ("Starter", "You have reached your Arceus Code project file storage limit."),
    "file_upload": ("Starter", "You have reached your file upload limit."),
    "interview_session": ("Pro", "You have reached your Interview Assist limit."),
    "pa_command": ("Pro", "Arceus PA commands require a PA-enabled plan."),
    "pa_reminder": ("Pro", "You have reached your PA reminder limit."),
    "pa_automation": ("Pro", "You have reached your PA automation limit."),
    "pa_daily_brief": ("Pro", "You have reached your daily brief refresh limit."),
}


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


def entitlement_denial_payload(feature: str, access: dict) -> dict:
    upgrade_name, message = FEATURE_UPGRADE_COPY.get(
        feature,
        ("Starter", "This action is not available on your current plan."),
    )
    upgrade_target = access.get("upgrade_target") or upgrade_name.lower()
    return {
        "code": "QUOTA_EXCEEDED" if access.get("reason") == "usage_limit" else "PLAN_LOCKED",
        "message": message,
        "action": feature,
        "feature": feature,
        "plan": access.get("plan"),
        "used": access.get("used"),
        "limit": access.get("limit"),
        "remaining": access.get("remaining"),
        "reason": access.get("reason"),
        "upgrade_url": "/settings?tab=billing",
        "upgrade_target": upgrade_target,
        "upgrade_label": upgrade_name,
        "upgrade_prompt": f"Upgrade to {upgrade_name} to continue.",
    }


def require_feature_entitlement(db: Session, user_id: UUID, feature: str) -> dict:
    access = check_entitlement(db, user_id, feature)
    if access.get("allowed"):
        return access
    raise HTTPException(status_code=402, detail=entitlement_denial_payload(feature, access))


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


def _stripe_price_id(plan: str, billing_cycle: str) -> str | None:
    prices = {
        ("starter", "monthly"): os.getenv("STRIPE_PRICE_STARTER_MONTHLY"),
        ("starter", "annual"): os.getenv("STRIPE_PRICE_STARTER_ANNUAL"),
        ("pro", "monthly"): os.getenv("STRIPE_PRICE_PRO_MONTHLY"),
        ("pro", "annual"): os.getenv("STRIPE_PRICE_PRO_ANNUAL"),
        ("enterprise", "monthly"): os.getenv("STRIPE_PRICE_ENTERPRISE_MONTHLY"),
        ("enterprise", "annual"): os.getenv("STRIPE_PRICE_ENTERPRISE_ANNUAL"),
    }
    return prices.get((plan, billing_cycle))


def _stripe_price_plan_cycle(price: dict, metadata: dict) -> tuple[str, str]:
    metadata_plan = str(metadata.get("plan") or "").lower()
    metadata_cycle = str(metadata.get("billing_cycle") or "").lower()
    price_id = str(price.get("id") or "")
    lookup = str(price.get("lookup_key") or price.get("nickname") or "").lower()

    for plan in ("starter", "pro", "enterprise"):
        if metadata_plan == plan or plan in lookup:
            cycle = "annual" if metadata_cycle == "annual" or str((price.get("recurring") or {}).get("interval")) == "year" else "monthly"
            return plan, cycle

    configured_prices = {
        _stripe_price_id("starter", "monthly"): ("starter", "monthly"),
        _stripe_price_id("starter", "annual"): ("starter", "annual"),
        _stripe_price_id("pro", "monthly"): ("pro", "monthly"),
        _stripe_price_id("pro", "annual"): ("pro", "annual"),
        _stripe_price_id("enterprise", "monthly"): ("enterprise", "monthly"),
        _stripe_price_id("enterprise", "annual"): ("enterprise", "annual"),
    }
    if price_id in configured_prices:
        return configured_prices[price_id]

    return (
        metadata_plan if metadata_plan in PLAN_CATALOG else "free",
        metadata_cycle if metadata_cycle in {"monthly", "annual"} else "monthly",
    )


def billing_configuration_status() -> dict:
    """Return production-readiness status without exposing secrets."""
    price_env = {
        "starter_monthly": "STRIPE_PRICE_STARTER_MONTHLY",
        "starter_annual": "STRIPE_PRICE_STARTER_ANNUAL",
        "pro_monthly": "STRIPE_PRICE_PRO_MONTHLY",
        "pro_annual": "STRIPE_PRICE_PRO_ANNUAL",
        "enterprise_monthly": "STRIPE_PRICE_ENTERPRISE_MONTHLY",
        "enterprise_annual": "STRIPE_PRICE_ENTERPRISE_ANNUAL",
    }
    configured_prices = {
        key: bool(os.getenv(env_name))
        for key, env_name in price_env.items()
    }
    missing_prices = [key for key, configured in configured_prices.items() if not configured]
    stripe_secret = bool(os.getenv("STRIPE_SECRET_KEY"))
    webhook_secret = bool(os.getenv("STRIPE_WEBHOOK_SECRET"))
    stripe_sdk = importlib.util.find_spec("stripe") is not None
    live_environment = _live_billing_environment()
    require_all_prices = os.getenv(
        "STRIPE_REQUIRE_ALL_PRICES",
        "true" if live_environment else "false",
    ).lower() in {"1", "true", "yes", "on"}
    blockers = []
    warnings = []
    if not stripe_secret:
        blockers.append("STRIPE_SECRET_KEY is missing")
    if not webhook_secret:
        blockers.append("STRIPE_WEBHOOK_SECRET is missing")
    if not stripe_sdk:
        blockers.append("stripe Python package is not installed")
    if missing_prices:
        message = f"Missing Stripe price ids: {', '.join(missing_prices)}"
        if require_all_prices:
            blockers.append(message)
        else:
            warnings.append(message)
    key_mode = "live" if (os.getenv("STRIPE_SECRET_KEY") or "").startswith("sk_live_") else "test" if stripe_secret else "not_configured"
    return {
        "ready": not blockers,
        "mode": key_mode,
        "live_environment": live_environment,
        "require_all_prices": require_all_prices,
        "stripe_secret_configured": stripe_secret,
        "webhook_secret_configured": webhook_secret,
        "stripe_sdk_available": stripe_sdk,
        "configured_prices": configured_prices,
        "missing_prices": missing_prices,
        "blockers": blockers,
        "warnings": warnings,
        "plans": list(PLAN_CATALOG.keys()),
        "required_webhook_events": [
            "checkout.session.completed",
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
            "invoice.payment_failed",
        ],
    }


def create_checkout_session(db: Session, user_id: UUID, plan: str, billing_cycle: str) -> dict:
    if plan not in {"starter", "pro", "enterprise"}:
        raise HTTPException(status_code=400, detail={"code": "unsupported_plan", "message": "Unsupported billing plan."})
    if billing_cycle not in {"monthly", "annual"}:
        raise HTTPException(status_code=400, detail={"code": "unsupported_billing_cycle", "message": "Unsupported billing cycle."})
    subscription = get_or_create_subscription(db, user_id)
    price_id = _stripe_price_id(plan, billing_cycle)
    if not os.getenv("STRIPE_SECRET_KEY") or not price_id:
        return {
            "status": "not_configured",
            "message": "Stripe checkout is not configured yet. Add STRIPE_SECRET_KEY and price IDs to enable paid upgrades.",
            "plan": plan,
            "billing_cycle": billing_cycle,
        }
    try:
        import stripe  # type: ignore
    except Exception:
        return {
            "status": "requires_stripe_sdk",
            "message": "Stripe keys are configured. Install the stripe Python package to create hosted checkout sessions.",
            "price_id": price_id,
        }
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    frontend = os.getenv("FRONTEND_URL") or os.getenv("NEXUS_FRONTEND_URL") or "http://localhost:3000"
    metadata = {"user_id": str(user_id), "plan": plan, "billing_cycle": billing_cycle}
    session_kwargs = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": f"{frontend.rstrip('/')}/settings?tab=billing&checkout=success",
        "cancel_url": f"{frontend.rstrip('/')}/settings?tab=billing&checkout=cancelled",
        "metadata": metadata,
        "subscription_data": {"metadata": metadata},
        "client_reference_id": str(user_id),
        "allow_promotion_codes": True,
    }
    if os.getenv("STRIPE_AUTOMATIC_TAX", "false").lower() in {"1", "true", "yes", "on"}:
        session_kwargs["automatic_tax"] = {"enabled": True}
    if subscription.provider_customer_id:
        session_kwargs["customer"] = subscription.provider_customer_id
    else:
        session_kwargs["customer_creation"] = "always"
    checkout = stripe.checkout.Session.create(**session_kwargs)
    return {
        "status": "ready",
        "checkout_url": checkout.url,
        "session_id": checkout.id,
        "price_id": price_id,
        "plan": plan,
        "billing_cycle": billing_cycle,
    }


def create_portal_session(db: Session, user_id: UUID) -> dict:
    subscription = get_or_create_subscription(db, user_id)
    if not os.getenv("STRIPE_SECRET_KEY") or not subscription.provider_customer_id:
        return {
            "status": "not_configured",
            "message": "Stripe Billing Portal needs STRIPE_SECRET_KEY and a Stripe customer id.",
            "customer_id": subscription.provider_customer_id,
        }
    try:
        import stripe  # type: ignore
    except Exception:
        return {
            "status": "requires_stripe_sdk",
            "message": "Stripe key is configured. Install the stripe Python package to create a hosted portal session.",
            "customer_id": subscription.provider_customer_id,
        }
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
    frontend = os.getenv("FRONTEND_URL") or os.getenv("NEXUS_FRONTEND_URL") or "http://localhost:3000"
    portal = stripe.billing_portal.Session.create(
        customer=subscription.provider_customer_id,
        return_url=f"{frontend.rstrip('/')}/settings?tab=billing",
    )
    return {"status": "ready", "portal_url": portal.url, "customer_id": subscription.provider_customer_id}


def stripe_event_processed(db: Session, event_id: str | None) -> bool:
    if not event_id:
        return False
    try:
        return bool(
            db.query(AuditLog)
            .filter(
                AuditLog.event_type == "billing.webhook",
                AuditLog.metadata_json["event_id"].as_string() == event_id,
                AuditLog.metadata_json["synced"].as_boolean() == True,  # noqa: E712
            )
            .first()
        )
    except Exception:
        return False


def sync_stripe_webhook_event(db: Session, event: dict) -> dict:
    event_id = event.get("id")
    event_type = event.get("type")
    if stripe_event_processed(db, event_id):
        return {"event_type": event_type, "event_id": event_id, "synced": False, "duplicate": True}

    data_object = ((event.get("data") or {}).get("object") or {}) if isinstance(event, dict) else {}
    synced = False
    user_id: UUID | None = None
    subscription: Subscription | None = None

    if event_type == "checkout.session.completed":
        provider_customer_id = data_object.get("customer")
        provider_subscription_id = data_object.get("subscription")
        metadata = data_object.get("metadata") or {}
        if metadata.get("user_id"):
            try:
                user_id = UUID(str(metadata["user_id"]))
            except ValueError:
                user_id = None
        if user_id:
            subscription = get_or_create_subscription(db, user_id)
            subscription.provider = "stripe"
            subscription.provider_customer_id = provider_customer_id or subscription.provider_customer_id
            subscription.provider_subscription_id = provider_subscription_id or subscription.provider_subscription_id
            subscription.plan_type = str(metadata.get("plan") or subscription.plan_type or "free")
            subscription.billing_cycle = str(metadata.get("billing_cycle") or subscription.billing_cycle or "monthly")
            subscription.status = "active"
            synced = True

    elif event_type in {"customer.subscription.created", "customer.subscription.updated", "customer.subscription.deleted"}:
        provider_subscription_id = data_object.get("id")
        provider_customer_id = data_object.get("customer")
        metadata = data_object.get("metadata") or {}
        if provider_subscription_id:
            subscription = db.query(Subscription).filter(
                Subscription.provider == "stripe",
                Subscription.provider_subscription_id == provider_subscription_id,
            ).first()
        if not subscription and provider_customer_id:
            subscription = db.query(Subscription).filter(
                Subscription.provider == "stripe",
                Subscription.provider_customer_id == provider_customer_id,
            ).order_by(Subscription.created_at.desc()).first()
        if not subscription and metadata.get("user_id"):
            try:
                user_id = UUID(str(metadata["user_id"]))
                subscription = get_or_create_subscription(db, user_id)
            except ValueError:
                subscription = None
        if subscription:
            price = (((data_object.get("items") or {}).get("data") or [{}])[0].get("price") or {})
            plan, cycle = _stripe_price_plan_cycle(price, metadata)
            subscription.provider = "stripe"
            subscription.provider_customer_id = provider_customer_id or subscription.provider_customer_id
            subscription.provider_subscription_id = provider_subscription_id or subscription.provider_subscription_id
            subscription.plan_type = plan
            subscription.billing_cycle = cycle
            subscription.status = "cancelled" if event_type == "customer.subscription.deleted" else str(data_object.get("status") or subscription.status or "active")
            if data_object.get("current_period_start"):
                subscription.current_period_start = datetime.fromtimestamp(int(data_object["current_period_start"]), tz=timezone.utc)
            if data_object.get("current_period_end"):
                subscription.current_period_end = datetime.fromtimestamp(int(data_object["current_period_end"]), tz=timezone.utc)
                subscription.next_billing_at = subscription.current_period_end
            subscription.cancel_at = datetime.fromtimestamp(int(data_object["cancel_at"]), tz=timezone.utc) if data_object.get("cancel_at") else None
            synced = True

    elif event_type in {"invoice.payment_failed", "customer.subscription.paused"}:
        provider_customer_id = data_object.get("customer")
        if provider_customer_id:
            subscription = db.query(Subscription).filter(
                Subscription.provider == "stripe",
                Subscription.provider_customer_id == provider_customer_id,
            ).order_by(Subscription.created_at.desc()).first()
        if subscription:
            subscription.plan_type = "free"
            subscription.status = "past_due"
            subscription.entitlements = {**(subscription.entitlements or {}), "payment_failure_at": datetime.now(timezone.utc).isoformat()}
            synced = True

    return {
        "event_type": event_type,
        "event_id": event_id,
        "synced": synced,
        "duplicate": False,
        "subscription_id": str(subscription.id) if subscription else None,
        "provider_subscription_id": getattr(subscription, "provider_subscription_id", None) if subscription else None,
    }
