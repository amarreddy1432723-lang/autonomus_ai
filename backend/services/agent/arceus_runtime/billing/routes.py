from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusBillingPlan, ArceusBillingSubscription, ArceusBillingUsageEvent, ArceusInvoice
from services.shared.database import get_db

from ..api.dependencies import RequestContext, require_permission
from ..api.responses import api_response, collection_response
from .api_schemas import (
    BudgetEnforcementRequest,
    BudgetPolicyRequest,
    CreditTransactionRequest,
    InvoiceDraftRequest,
    LedgerPostingRequest,
    SubscriptionRequest,
    UsageMeterRequest,
)
from .service import (
    billing_summary,
    builtin_plans,
    create_or_update_subscription,
    draft_invoice,
    ensure_builtin_plans,
    evaluate_budget,
    invoice_response,
    ledger_response,
    meter_usage,
    post_ledger_entries,
    subscription_response,
    upsert_budget_policy,
    usage_response,
    wallet_response,
    apply_credit_transaction,
)


router = APIRouter(tags=["arceus-billing"])


@router.get("/api/v1/billing/plans")
def list_billing_plans(request: Request, context: RequestContext = Depends(require_permission("billing.view")), db: Session = Depends(get_db)):
    ensure_builtin_plans(db)
    db.commit()
    rows = db.query(ArceusBillingPlan).order_by(ArceusBillingPlan.monthly_price_cents.asc(), ArceusBillingPlan.plan_key.asc()).all()
    data = [
        {
            "plan_key": row.plan_key,
            "display_name": row.display_name,
            "billing_model": row.billing_model,
            "monthly_price_cents": row.monthly_price_cents,
            "annual_price_cents": row.annual_price_cents,
            "currency": row.currency,
            "included_credits_cents": row.included_credits_cents,
            "feature_limits": row.feature_limits,
            "stripe_price_ids": row.stripe_price_ids,
        }
        for row in rows
    ] or builtin_plans()
    return collection_response(data, request)


@router.post("/api/v1/billing/subscribe")
def subscribe(payload: SubscriptionRequest, request: Request, context: RequestContext = Depends(require_permission("billing.manage")), db: Session = Depends(get_db)):
    ensure_builtin_plans(db)
    item = create_or_update_subscription(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response(subscription_response(db, item).model_dump(mode="json"), request)


@router.get("/api/v1/billing/subscriptions")
def list_subscriptions(request: Request, context: RequestContext = Depends(require_permission("billing.view")), db: Session = Depends(get_db)):
    rows = db.query(ArceusBillingSubscription).filter(ArceusBillingSubscription.tenant_id == context.tenant_id).order_by(ArceusBillingSubscription.created_at.desc()).all()
    return collection_response([subscription_response(db, row).model_dump(mode="json") for row in rows], request)


@router.post("/api/v1/billing/usage")
def record_usage(payload: UsageMeterRequest, request: Request, context: RequestContext = Depends(require_permission("billing.meter")), db: Session = Depends(get_db)):
    item = meter_usage(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response(usage_response(item).model_dump(mode="json"), request)


@router.get("/api/v1/billing/usage")
def list_usage(request: Request, context: RequestContext = Depends(require_permission("billing.view")), db: Session = Depends(get_db), metric: str | None = None):
    query = db.query(ArceusBillingUsageEvent).filter(ArceusBillingUsageEvent.tenant_id == context.tenant_id)
    if metric:
        query = query.filter(ArceusBillingUsageEvent.metric == metric)
    rows = query.order_by(ArceusBillingUsageEvent.occurred_at.desc()).limit(200).all()
    return collection_response([usage_response(row).model_dump(mode="json") for row in rows], request)


@router.post("/api/v1/billing/budget")
def set_budget(payload: BudgetPolicyRequest, request: Request, context: RequestContext = Depends(require_permission("billing.manage")), db: Session = Depends(get_db)):
    item = upsert_budget_policy(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response(
        {
            "id": str(item.id),
            "scope_type": item.scope_type,
            "scope_id": str(item.scope_id),
            "currency": item.currency,
            "limit_amount_cents": str(item.limit_amount),
            "reserved_amount_cents": str(item.reserved_amount),
            "actual_amount_cents": str(item.actual_amount),
            "warning_threshold_percent": item.warning_threshold_percent,
            "status": item.status,
        },
        request,
    )


@router.post("/api/v1/billing/budget/check")
def check_budget(payload: BudgetEnforcementRequest, request: Request, context: RequestContext = Depends(require_permission("billing.enforce")), db: Session = Depends(get_db)):
    response = evaluate_budget(db, tenant_id=context.tenant_id, payload=payload)
    if not response.allowed:
        raise HTTPException(status_code=402, detail={"code": "BUDGET_EXCEEDED", **response.model_dump(mode="json")})
    return api_response(response.model_dump(mode="json"), request)


@router.post("/api/v1/billing/credits")
def apply_credits(payload: CreditTransactionRequest, request: Request, context: RequestContext = Depends(require_permission("billing.manage")), db: Session = Depends(get_db)):
    try:
        wallet, tx = apply_credit_transaction(db, tenant_id=context.tenant_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=402, detail={"code": str(exc), "message": "Credit wallet balance is insufficient."}) from exc
    db.commit()
    db.refresh(wallet)
    if tx is not None:
        db.refresh(tx)
    return api_response(wallet_response(wallet, tx).model_dump(mode="json"), request)


@router.post("/api/v1/billing/invoices")
def create_invoice(payload: InvoiceDraftRequest, request: Request, context: RequestContext = Depends(require_permission("billing.manage")), db: Session = Depends(get_db)):
    item = draft_invoice(db, tenant_id=context.tenant_id, payload=payload)
    db.commit()
    db.refresh(item)
    return api_response(invoice_response(db, item).model_dump(mode="json"), request)


@router.get("/api/v1/billing/invoices")
def list_invoices(request: Request, context: RequestContext = Depends(require_permission("billing.view")), db: Session = Depends(get_db)):
    rows = db.query(ArceusInvoice).filter(ArceusInvoice.tenant_id == context.tenant_id).order_by(ArceusInvoice.created_at.desc()).limit(100).all()
    return collection_response([invoice_response(db, row).model_dump(mode="json") for row in rows], request)


@router.post("/api/v1/billing/ledger")
def post_ledger(payload: LedgerPostingRequest, request: Request, context: RequestContext = Depends(require_permission("billing.manage")), db: Session = Depends(get_db)):
    try:
        rows = post_ledger_entries(db, tenant_id=context.tenant_id, payload=payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail={"code": str(exc), "message": "Financial ledger postings must balance before they can be committed."}) from exc
    db.commit()
    for row in rows:
        db.refresh(row)
    return api_response(ledger_response(rows).model_dump(mode="json"), request)


@router.get("/api/v1/billing/summary")
def get_billing_summary(request: Request, context: RequestContext = Depends(require_permission("billing.view")), db: Session = Depends(get_db), currency: str = "USD"):
    return api_response(billing_summary(db, tenant_id=context.tenant_id, currency=currency).model_dump(mode="json"), request)

