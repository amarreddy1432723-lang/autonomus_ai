from __future__ import annotations

import json
import os
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from services.shared.database import get_db
from services.shared.models import AuditLog

from .deps import get_current_user_id

router = APIRouter()


class BillingCheckoutRequest(BaseModel):
    plan: str
    billing_cycle: str = "monthly"


@router.get("/api/v1/usage/summary")
def get_usage_summary(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .usage import usage_summary

    return usage_summary(db, user_id)


@router.get("/api/v1/billing/summary")
def get_billing_summary(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import billing_summary

    return billing_summary(db, user_id)


@router.get("/api/v1/billing/plans")
def get_billing_plans(user_id: UUID = Depends(get_current_user_id)):
    from .billing import PLAN_CATALOG

    return {"plans": PLAN_CATALOG}


@router.get("/api/v1/billing/entitlement/{feature}")
def get_feature_entitlement(feature: str, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import check_entitlement

    return check_entitlement(db, user_id, feature)


@router.get("/api/v1/billing/interview-access")
def get_interview_access(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import check_entitlement

    return check_entitlement(db, user_id, "interview_session")


@router.post("/api/v1/billing/interview-session")
def record_interview_access(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import record_interview_session

    return record_interview_session(db, user_id)


@router.post("/api/v1/billing/checkout")
def create_billing_checkout(request: BillingCheckoutRequest, user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import create_checkout_session

    if request.plan not in {"starter", "pro", "enterprise"}:
        raise HTTPException(status_code=400, detail="Unsupported plan")
    if request.billing_cycle not in {"monthly", "annual"}:
        raise HTTPException(status_code=400, detail="Unsupported billing cycle")
    return create_checkout_session(db, user_id, request.plan, request.billing_cycle)


@router.post("/api/v1/billing/portal")
def create_billing_portal(user_id: UUID = Depends(get_current_user_id), db: Session = Depends(get_db)):
    from .billing import create_portal_session

    return create_portal_session(db, user_id)


@router.post("/api/v1/billing/webhook")
async def post_billing_webhook(request: Request, stripe_signature: str | None = Header(default=None, alias="stripe-signature"), db: Session = Depends(get_db)):
    from .billing import sync_stripe_webhook_event

    body = await request.body()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    live_environment = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "local")).lower() in {"staging", "prod", "production"}
    if not webhook_secret:
        if live_environment:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "stripe_webhook_not_configured",
                    "message": "STRIPE_WEBHOOK_SECRET is required before live Stripe webhooks can be accepted.",
                },
            )
        return {"status": "not_configured", "message": "Stripe webhook secret is not configured."}
    try:
        import stripe  # type: ignore
        event = stripe.Webhook.construct_event(body, stripe_signature or "", webhook_secret)
    except ImportError:
        if live_environment:
            raise HTTPException(
                status_code=503,
                detail={
                    "code": "stripe_sdk_required",
                    "message": "The stripe Python package is required to verify live webhook signatures.",
                },
            )
        try:
            event = json.loads(body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail={"code": "invalid_webhook", "message": "Webhook body must be valid JSON."})
    except Exception as exc:
        raise HTTPException(status_code=400, detail={"code": "invalid_signature", "message": str(exc)})
    if not isinstance(event, dict):
        raise HTTPException(status_code=400, detail={"code": "invalid_webhook", "message": "Webhook body must be valid JSON."})

    result = sync_stripe_webhook_event(db, event)
    db.add(
        AuditLog(
            user_id=UUID("00000000-0000-0000-0000-000000000000"),
            event_type="billing.webhook",
            entity_type="stripe_event",
            actor_type="system",
            action="billing.webhook.received",
            metadata_json=result,
        )
    )
    db.commit()
    return {"status": "received", **result}
