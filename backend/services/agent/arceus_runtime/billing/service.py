from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from services.shared.arceus_core_models import (
    ArceusBillingEntitlement,
    ArceusBillingPlan,
    ArceusBillingSubscription,
    ArceusBillingUsageEvent,
    ArceusBudget,
    ArceusCreditTransaction,
    ArceusCreditWallet,
    ArceusFinancialLedgerEntry,
    ArceusInvoice,
    ArceusInvoiceItem,
)

from .api_schemas import (
    BillingSummaryResponse,
    BudgetEnforcementResponse,
    BudgetPolicyRequest,
    CreditTransactionRequest,
    CreditWalletResponse,
    InvoiceDraftRequest,
    InvoiceResponse,
    LedgerPostingRequest,
    LedgerPostingResponse,
    SubscriptionRequest,
    SubscriptionResponse,
    UsageEventResponse,
    UsageMeterRequest,
)


PLAN_CATALOG: dict[str, dict[str, Any]] = {
    "community": {
        "display_name": "Community",
        "billing_model": "free",
        "monthly_price_cents": 0,
        "annual_price_cents": 0,
        "included_credits_cents": 100,
        "feature_limits": {"monthly_ai_credits_cents": 100, "concurrent_agents": 1, "private_marketplace": False},
    },
    "pro": {
        "display_name": "Pro",
        "billing_model": "subscription",
        "monthly_price_cents": 2900,
        "annual_price_cents": 27840,
        "included_credits_cents": 2500,
        "feature_limits": {"monthly_ai_credits_cents": 2500, "concurrent_agents": 5, "private_marketplace": False},
    },
    "team": {
        "display_name": "Team",
        "billing_model": "seat_plus_usage",
        "monthly_price_cents": 9900,
        "annual_price_cents": 95040,
        "included_credits_cents": 15000,
        "feature_limits": {"monthly_ai_credits_cents": 15000, "concurrent_agents": 20, "private_marketplace": True},
    },
    "enterprise": {
        "display_name": "Enterprise",
        "billing_model": "contract",
        "monthly_price_cents": 0,
        "annual_price_cents": 0,
        "included_credits_cents": 0,
        "feature_limits": {"monthly_ai_credits_cents": "contract", "concurrent_agents": "contract", "private_marketplace": True, "sso": True},
    },
}

USAGE_PRICE_CENTS: dict[str, Decimal] = {
    "model.input_tokens": Decimal("0.0002"),
    "model.output_tokens": Decimal("0.0010"),
    "model.cached_tokens": Decimal("0.00005"),
    "embedding.tokens": Decimal("0.00002"),
    "mission.run": Decimal("25"),
    "tool.execution": Decimal("5"),
    "verification.run": Decimal("10"),
    "preview.verification": Decimal("8"),
    "plugin.invocation": Decimal("3"),
    "storage.mb_month": Decimal("2"),
}


def builtin_plans() -> list[dict[str, Any]]:
    return [
        {
            "plan_key": key,
            "currency": "USD",
            "stripe_price_ids": {},
            **value,
        }
        for key, value in PLAN_CATALOG.items()
    ]


def price_usage(metric: str, quantity: Decimal, explicit_price: Decimal | None = None) -> Decimal:
    if explicit_price is not None:
        return _money(explicit_price)
    return _money(USAGE_PRICE_CENTS.get(metric, Decimal("0")) * quantity)


def ensure_builtin_plans(db: Session) -> None:
    for plan in builtin_plans():
        existing = db.query(ArceusBillingPlan).filter(ArceusBillingPlan.plan_key == plan["plan_key"]).first()
        if existing:
            continue
        db.add(
            ArceusBillingPlan(
                plan_key=plan["plan_key"],
                display_name=plan["display_name"],
                billing_model=plan["billing_model"],
                monthly_price_cents=plan["monthly_price_cents"],
                annual_price_cents=plan["annual_price_cents"],
                currency=plan["currency"],
                included_credits_cents=plan["included_credits_cents"],
                feature_limits=plan["feature_limits"],
                stripe_price_ids=plan["stripe_price_ids"],
            )
        )


def create_or_update_subscription(db: Session, *, tenant_id: UUID, payload: SubscriptionRequest) -> ArceusBillingSubscription:
    provider_subscription_id = payload.provider_subscription_id or payload.idempotency_key or f"internal:{tenant_id}:{payload.organization_id or 'tenant'}"
    existing = (
        db.query(ArceusBillingSubscription)
        .filter(
            ArceusBillingSubscription.tenant_id == tenant_id,
            ArceusBillingSubscription.provider == payload.provider,
            ArceusBillingSubscription.provider_subscription_id == provider_subscription_id,
        )
        .first()
    )
    if existing:
        existing.plan_key = payload.plan_key
        existing.billing_cycle = payload.billing_cycle
        existing.seat_limit = payload.seat_limit
        existing.provider_customer_id = payload.provider_customer_id
        existing.status = "active"
        return existing
    item = ArceusBillingSubscription(
        tenant_id=tenant_id,
        organization_id=payload.organization_id,
        plan_key=payload.plan_key,
        status="active",
        billing_cycle=payload.billing_cycle,
        seat_limit=payload.seat_limit,
        provider=payload.provider,
        provider_customer_id=payload.provider_customer_id,
        provider_subscription_id=provider_subscription_id,
    )
    db.add(item)
    db.flush()
    plan = PLAN_CATALOG.get(payload.plan_key, PLAN_CATALOG["community"])
    for feature_key, limit in (plan.get("feature_limits") or {}).items():
        db.add(
            ArceusBillingEntitlement(
                tenant_id=tenant_id,
                subscription_id=item.id,
                feature_key=feature_key,
                limit_value=str(limit),
                current_usage=Decimal("0"),
                period="monthly",
            )
        )
    return item


def subscription_response(db: Session, item: ArceusBillingSubscription) -> SubscriptionResponse:
    entitlements = (
        db.query(ArceusBillingEntitlement)
        .filter(ArceusBillingEntitlement.tenant_id == item.tenant_id, ArceusBillingEntitlement.subscription_id == item.id)
        .all()
    )
    return SubscriptionResponse(
        id=item.id,
        organization_id=item.organization_id,
        plan_key=item.plan_key,
        status=item.status,
        billing_cycle=item.billing_cycle,
        seat_limit=item.seat_limit,
        assigned_seats=item.assigned_seats,
        provider=item.provider,
        provider_customer_id=item.provider_customer_id,
        provider_subscription_id=item.provider_subscription_id,
        renewal_at=item.renewal_at,
        entitlements=[
            {
                "feature_key": entitlement.feature_key,
                "limit": entitlement.limit_value,
                "current_usage": str(entitlement.current_usage),
                "period": entitlement.period,
            }
            for entitlement in entitlements
        ],
    )


def meter_usage(db: Session, *, tenant_id: UUID, payload: UsageMeterRequest) -> ArceusBillingUsageEvent:
    existing = db.query(ArceusBillingUsageEvent).filter(ArceusBillingUsageEvent.tenant_id == tenant_id, ArceusBillingUsageEvent.idempotency_key == payload.idempotency_key).first()
    if existing:
        return existing
    customer_price = price_usage(payload.metric, payload.quantity, payload.customer_price_cents)
    item = ArceusBillingUsageEvent(
        tenant_id=tenant_id,
        organization_id=payload.organization_id,
        workspace_id=payload.workspace_id,
        project_id=payload.project_id,
        mission_id=payload.mission_id,
        task_id=payload.task_id,
        execution_id=payload.execution_id,
        metric=payload.metric,
        quantity=payload.quantity,
        unit=payload.unit,
        provider_key=payload.provider_key,
        model_key=payload.model_key,
        provider_cost_cents=_money(payload.provider_cost_cents),
        customer_price_cents=customer_price,
        currency=payload.currency,
        idempotency_key=payload.idempotency_key,
        source=payload.source,
        metadata_json=payload.metadata,
    )
    db.add(item)
    db.flush()
    return item


def usage_response(item: ArceusBillingUsageEvent) -> UsageEventResponse:
    return UsageEventResponse(
        id=item.id,
        metric=item.metric,
        quantity=item.quantity,
        unit=item.unit,
        provider_cost_cents=item.provider_cost_cents,
        customer_price_cents=item.customer_price_cents,
        margin_cents=_money(Decimal(item.customer_price_cents or 0) - Decimal(item.provider_cost_cents or 0)),
        currency=item.currency,
        idempotency_key=item.idempotency_key,
        occurred_at=item.occurred_at,
    )


def upsert_budget_policy(db: Session, *, tenant_id: UUID, payload: BudgetPolicyRequest) -> ArceusBudget:
    existing = db.query(ArceusBudget).filter(ArceusBudget.tenant_id == tenant_id, ArceusBudget.scope_type == payload.scope_type, ArceusBudget.scope_id == payload.scope_id).first()
    if existing:
        existing.currency = payload.currency
        existing.limit_amount = _money(payload.limit_amount_cents)
        existing.warning_threshold_percent = payload.warning_threshold_percent
        existing.status = "active"
        return existing
    item = ArceusBudget(
        tenant_id=tenant_id,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        currency=payload.currency,
        limit_amount=_money(payload.limit_amount_cents),
        warning_threshold_percent=payload.warning_threshold_percent,
        status="active",
    )
    db.add(item)
    db.flush()
    return item


def evaluate_budget(db: Session, *, tenant_id: UUID, payload: BudgetEnforcementRequest) -> BudgetEnforcementResponse:
    budget = db.query(ArceusBudget).filter(ArceusBudget.tenant_id == tenant_id, ArceusBudget.scope_type == payload.scope_type, ArceusBudget.scope_id == payload.scope_id).first()
    if budget is None:
        return BudgetEnforcementResponse(
            allowed=True,
            action="allow",
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            limit_amount_cents=Decimal("0"),
            actual_amount_cents=Decimal("0"),
            reserved_amount_cents=Decimal("0"),
            estimated_amount_cents=payload.estimated_amount_cents,
            remaining_cents=Decimal("0"),
            utilization_percent=0.0,
            reason="No budget policy exists for this scope.",
        )
    used = _money(Decimal(budget.actual_amount or 0) + Decimal(budget.reserved_amount or 0))
    projected = _money(used + payload.estimated_amount_cents)
    remaining = _money(Decimal(budget.limit_amount or 0) - projected)
    utilization = float((projected / Decimal(budget.limit_amount or 1)) * 100) if Decimal(budget.limit_amount or 0) > 0 else 0.0
    if projected > Decimal(budget.limit_amount or 0):
        return BudgetEnforcementResponse(
            allowed=False,
            action="block",
            scope_type=payload.scope_type,
            scope_id=payload.scope_id,
            limit_amount_cents=budget.limit_amount,
            actual_amount_cents=budget.actual_amount,
            reserved_amount_cents=budget.reserved_amount,
            estimated_amount_cents=payload.estimated_amount_cents,
            remaining_cents=max(Decimal("0"), remaining),
            utilization_percent=round(utilization, 2),
            reason="Budget hard limit would be exceeded.",
        )
    if utilization >= int(budget.warning_threshold_percent or 80):
        action = "warn"
        reason = "Budget warning threshold would be reached."
    else:
        action = "allow"
        reason = "Budget permits this action."
    return BudgetEnforcementResponse(
        allowed=True,
        action=action,
        scope_type=payload.scope_type,
        scope_id=payload.scope_id,
        limit_amount_cents=budget.limit_amount,
        actual_amount_cents=budget.actual_amount,
        reserved_amount_cents=budget.reserved_amount,
        estimated_amount_cents=payload.estimated_amount_cents,
        remaining_cents=max(Decimal("0"), remaining),
        utilization_percent=round(utilization, 2),
        reason=reason,
    )


def apply_credit_transaction(db: Session, *, tenant_id: UUID, payload: CreditTransactionRequest) -> tuple[ArceusCreditWallet, ArceusCreditTransaction | None]:
    wallet = (
        db.query(ArceusCreditWallet)
        .filter(ArceusCreditWallet.tenant_id == tenant_id, ArceusCreditWallet.organization_id == payload.organization_id, ArceusCreditWallet.currency == payload.currency)
        .first()
    )
    if wallet is None:
        wallet = ArceusCreditWallet(tenant_id=tenant_id, organization_id=payload.organization_id, currency=payload.currency, balance_cents=Decimal("0"))
        db.add(wallet)
        db.flush()
    existing = db.query(ArceusCreditTransaction).filter(ArceusCreditTransaction.tenant_id == tenant_id, ArceusCreditTransaction.idempotency_key == payload.idempotency_key).first()
    if existing:
        return wallet, existing
    signed_amount = payload.amount_cents if payload.transaction_type in {"grant", "refund", "adjust"} else -payload.amount_cents
    next_balance = _money(Decimal(wallet.balance_cents or 0) + signed_amount)
    if next_balance < 0:
        raise ValueError("CREDIT_BALANCE_EXCEEDED")
    wallet.balance_cents = next_balance
    tx = ArceusCreditTransaction(
        tenant_id=tenant_id,
        wallet_id=wallet.id,
        transaction_type=payload.transaction_type,
        credit_type=payload.credit_type,
        amount_cents=_money(payload.amount_cents),
        balance_after_cents=next_balance,
        currency=payload.currency,
        idempotency_key=payload.idempotency_key,
        reference_type=payload.reference_type,
        reference_id=payload.reference_id,
        metadata_json=payload.metadata,
    )
    db.add(tx)
    db.flush()
    return wallet, tx


def wallet_response(wallet: ArceusCreditWallet, tx: ArceusCreditTransaction | None = None) -> CreditWalletResponse:
    return CreditWalletResponse(
        wallet_id=wallet.id,
        organization_id=wallet.organization_id,
        balance_cents=wallet.balance_cents,
        currency=wallet.currency,
        transaction_id=tx.id if tx else None,
        transaction_type=tx.transaction_type if tx else None,
        credit_type=tx.credit_type if tx else None,
    )


def draft_invoice(db: Session, *, tenant_id: UUID, payload: InvoiceDraftRequest) -> ArceusInvoice:
    subtotal = _money(sum((line.quantity * line.unit_amount_cents for line in payload.lines), Decimal("0")))
    total = _money(max(Decimal("0"), subtotal + payload.tax_cents - payload.credits_applied_cents))
    invoice = ArceusInvoice(
        tenant_id=tenant_id,
        organization_id=payload.organization_id,
        subscription_id=payload.subscription_id,
        invoice_number=payload.invoice_number or f"ARC-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}",
        status="open",
        subtotal_cents=subtotal,
        tax_cents=_money(payload.tax_cents),
        credits_applied_cents=_money(payload.credits_applied_cents),
        total_cents=total,
        currency=payload.currency,
    )
    db.add(invoice)
    db.flush()
    for line in payload.lines:
        db.add(
            ArceusInvoiceItem(
                tenant_id=tenant_id,
                invoice_id=invoice.id,
                usage_event_id=line.usage_event_id,
                item_type=line.item_type,
                description=line.description,
                quantity=line.quantity,
                unit_amount_cents=_money(line.unit_amount_cents),
                total_cents=_money(line.quantity * line.unit_amount_cents),
                metadata_json=line.metadata,
            )
        )
    db.flush()
    return invoice


def invoice_response(db: Session, item: ArceusInvoice) -> InvoiceResponse:
    rows = db.query(ArceusInvoiceItem).filter(ArceusInvoiceItem.tenant_id == item.tenant_id, ArceusInvoiceItem.invoice_id == item.id).all()
    return InvoiceResponse(
        id=item.id,
        invoice_number=item.invoice_number,
        status=item.status,
        subtotal_cents=item.subtotal_cents,
        tax_cents=item.tax_cents,
        credits_applied_cents=item.credits_applied_cents,
        total_cents=item.total_cents,
        currency=item.currency,
        items=[
            {
                "id": str(row.id),
                "item_type": row.item_type,
                "description": row.description,
                "quantity": str(row.quantity),
                "unit_amount_cents": str(row.unit_amount_cents),
                "total_cents": str(row.total_cents),
            }
            for row in rows
        ],
    )


def post_ledger_entries(db: Session, *, tenant_id: UUID, payload: LedgerPostingRequest) -> list[ArceusFinancialLedgerEntry]:
    debit_total = sum((entry.amount_cents for entry in payload.entries if entry.direction == "debit"), Decimal("0"))
    credit_total = sum((entry.amount_cents for entry in payload.entries if entry.direction == "credit"), Decimal("0"))
    if _money(debit_total) != _money(credit_total):
        raise ValueError("LEDGER_NOT_BALANCED")
    group_id = payload.entry_group_id or uuid.uuid4()
    rows: list[ArceusFinancialLedgerEntry] = []
    for entry in payload.entries:
        existing = (
            db.query(ArceusFinancialLedgerEntry)
            .filter(
                ArceusFinancialLedgerEntry.tenant_id == tenant_id,
                ArceusFinancialLedgerEntry.idempotency_key == entry.idempotency_key,
                ArceusFinancialLedgerEntry.account == entry.account,
                ArceusFinancialLedgerEntry.direction == entry.direction,
            )
            .first()
        )
        if existing:
            rows.append(existing)
            continue
        row = ArceusFinancialLedgerEntry(
            tenant_id=tenant_id,
            entry_group_id=group_id,
            account=entry.account,
            direction=entry.direction,
            amount_cents=_money(entry.amount_cents),
            currency=entry.currency,
            source_type=entry.source_type,
            source_id=entry.source_id,
            idempotency_key=entry.idempotency_key,
            metadata_json=entry.metadata,
        )
        db.add(row)
        rows.append(row)
    db.flush()
    return rows


def ledger_response(rows: list[ArceusFinancialLedgerEntry]) -> LedgerPostingResponse:
    debit_total = _money(sum((Decimal(row.amount_cents or 0) for row in rows if row.direction == "debit"), Decimal("0")))
    credit_total = _money(sum((Decimal(row.amount_cents or 0) for row in rows if row.direction == "credit"), Decimal("0")))
    group_id = rows[0].entry_group_id if rows else uuid.uuid4()
    return LedgerPostingResponse(
        entry_group_id=group_id,
        balanced=debit_total == credit_total,
        debit_total_cents=debit_total,
        credit_total_cents=credit_total,
        entries=[
            {
                "id": str(row.id),
                "account": row.account,
                "direction": row.direction,
                "amount_cents": str(row.amount_cents),
                "currency": row.currency,
                "source_type": row.source_type,
                "source_id": str(row.source_id) if row.source_id else None,
            }
            for row in rows
        ],
    )


def billing_summary(db: Session, *, tenant_id: UUID, currency: str = "USD") -> BillingSummaryResponse:
    usage_rows = db.query(ArceusBillingUsageEvent).filter(ArceusBillingUsageEvent.tenant_id == tenant_id, ArceusBillingUsageEvent.currency == currency).all()
    provider_cost = _money(sum((Decimal(row.provider_cost_cents or 0) for row in usage_rows), Decimal("0")))
    customer_price = _money(sum((Decimal(row.customer_price_cents or 0) for row in usage_rows), Decimal("0")))
    active_subscriptions = int(
        db.query(func.count(ArceusBillingSubscription.id))
        .filter(ArceusBillingSubscription.tenant_id == tenant_id, ArceusBillingSubscription.status.in_(["trial", "active"]))
        .scalar()
        or 0
    )
    open_invoices = int(db.query(func.count(ArceusInvoice.id)).filter(ArceusInvoice.tenant_id == tenant_id, ArceusInvoice.status == "open").scalar() or 0)
    credit_balance = _money(
        db.query(func.coalesce(func.sum(ArceusCreditWallet.balance_cents), 0))
        .filter(ArceusCreditWallet.tenant_id == tenant_id, ArceusCreditWallet.currency == currency)
        .scalar()
        or 0
    )
    budget_rows = db.query(ArceusBudget.status, func.count(ArceusBudget.id)).filter(ArceusBudget.tenant_id == tenant_id).group_by(ArceusBudget.status).all()
    return BillingSummaryResponse(
        tenant_id=tenant_id,
        currency=currency,
        usage_count=len(usage_rows),
        provider_cost_cents=provider_cost,
        customer_price_cents=customer_price,
        gross_margin_cents=_money(customer_price - provider_cost),
        active_subscriptions=active_subscriptions,
        open_invoices=open_invoices,
        credit_balance_cents=credit_balance,
        budget_statuses={str(status): int(count) for status, count in budget_rows},
    )


def _money(value: Any) -> Decimal:
    return Decimal(str(value or 0)).quantize(Decimal("0.000001"))

