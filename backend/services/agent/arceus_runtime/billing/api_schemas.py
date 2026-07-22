from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


BillingCycle = Literal["monthly", "annual", "contract", "usage"]
SubscriptionStatus = Literal["trial", "active", "past_due", "cancelled", "expired", "suspended"]


class BillingPlanResponse(BaseModel):
    plan_key: str
    display_name: str
    billing_model: str
    monthly_price_cents: int
    annual_price_cents: int
    currency: str = "USD"
    included_credits_cents: int = 0
    feature_limits: dict[str, Any] = Field(default_factory=dict)
    stripe_price_ids: dict[str, str] = Field(default_factory=dict)


class SubscriptionRequest(BaseModel):
    organization_id: UUID | None = None
    plan_key: str = "community"
    billing_cycle: BillingCycle = "monthly"
    seat_limit: int = Field(default=1, ge=1)
    provider: str = "internal"
    provider_customer_id: str | None = None
    provider_subscription_id: str | None = None
    idempotency_key: str | None = None


class SubscriptionResponse(BaseModel):
    id: UUID
    organization_id: UUID | None = None
    plan_key: str
    status: SubscriptionStatus
    billing_cycle: BillingCycle
    seat_limit: int
    assigned_seats: int
    provider: str
    provider_customer_id: str | None = None
    provider_subscription_id: str | None = None
    renewal_at: datetime | None = None
    entitlements: list[dict[str, Any]] = Field(default_factory=list)


class UsageMeterRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    organization_id: UUID | None = None
    workspace_id: UUID | None = None
    project_id: UUID | None = None
    mission_id: UUID | None = None
    task_id: UUID | None = None
    execution_id: UUID | None = None
    metric: str
    quantity: Decimal = Field(gt=0)
    unit: str = "unit"
    provider_key: str | None = None
    model_key: str | None = None
    provider_cost_cents: Decimal = Decimal("0")
    customer_price_cents: Decimal | None = None
    currency: str = "USD"
    source: str = "runtime"
    idempotency_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("metric", "unit", "currency", "source", "idempotency_key")
    @classmethod
    def require_non_blank(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be blank")
        return cleaned


class UsageEventResponse(BaseModel):
    id: UUID
    metric: str
    quantity: Decimal
    unit: str
    provider_cost_cents: Decimal
    customer_price_cents: Decimal
    margin_cents: Decimal
    currency: str
    idempotency_key: str
    occurred_at: datetime


class BudgetPolicyRequest(BaseModel):
    scope_type: str
    scope_id: UUID
    currency: str = "USD"
    limit_amount_cents: Decimal = Field(gt=0)
    warning_threshold_percent: int = Field(default=80, ge=1, le=100)
    hard_limit: bool = True


class BudgetEnforcementRequest(BaseModel):
    scope_type: str
    scope_id: UUID
    estimated_amount_cents: Decimal = Field(ge=0)
    currency: str = "USD"


class BudgetEnforcementResponse(BaseModel):
    allowed: bool
    action: Literal["allow", "warn", "block", "approval_required", "switch_cheaper_model"]
    scope_type: str
    scope_id: UUID
    limit_amount_cents: Decimal
    actual_amount_cents: Decimal
    reserved_amount_cents: Decimal
    estimated_amount_cents: Decimal
    remaining_cents: Decimal
    utilization_percent: float
    reason: str


class CreditTransactionRequest(BaseModel):
    organization_id: UUID | None = None
    amount_cents: Decimal
    currency: str = "USD"
    credit_type: str = "purchased"
    transaction_type: Literal["grant", "consume", "refund", "expire", "adjust"] = "grant"
    idempotency_key: str
    reference_type: str | None = None
    reference_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CreditWalletResponse(BaseModel):
    wallet_id: UUID
    organization_id: UUID | None = None
    balance_cents: Decimal
    currency: str
    transaction_id: UUID | None = None
    transaction_type: str | None = None
    credit_type: str | None = None


class InvoiceLineInput(BaseModel):
    item_type: str
    description: str
    quantity: Decimal = Field(default=Decimal("1"), gt=0)
    unit_amount_cents: Decimal = Field(ge=0)
    usage_event_id: UUID | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InvoiceDraftRequest(BaseModel):
    organization_id: UUID | None = None
    subscription_id: UUID | None = None
    currency: str = "USD"
    tax_cents: Decimal = Decimal("0")
    credits_applied_cents: Decimal = Decimal("0")
    lines: list[InvoiceLineInput] = Field(default_factory=list)
    invoice_number: str | None = None


class InvoiceResponse(BaseModel):
    id: UUID
    invoice_number: str
    status: str
    subtotal_cents: Decimal
    tax_cents: Decimal
    credits_applied_cents: Decimal
    total_cents: Decimal
    currency: str
    items: list[dict[str, Any]] = Field(default_factory=list)


class LedgerEntryInput(BaseModel):
    account: str
    direction: Literal["debit", "credit"]
    amount_cents: Decimal = Field(gt=0)
    currency: str = "USD"
    source_type: str
    source_id: UUID | None = None
    idempotency_key: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class LedgerPostingRequest(BaseModel):
    entries: list[LedgerEntryInput] = Field(min_length=2)
    entry_group_id: UUID | None = None


class LedgerPostingResponse(BaseModel):
    entry_group_id: UUID
    balanced: bool
    debit_total_cents: Decimal
    credit_total_cents: Decimal
    entries: list[dict[str, Any]]


class BillingSummaryResponse(BaseModel):
    tenant_id: UUID
    currency: str
    usage_count: int
    provider_cost_cents: Decimal
    customer_price_cents: Decimal
    gross_margin_cents: Decimal
    active_subscriptions: int
    open_invoices: int
    credit_balance_cents: Decimal
    budget_statuses: dict[str, int]
