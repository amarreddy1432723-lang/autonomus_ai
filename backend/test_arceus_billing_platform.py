from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest

from backend.services.agent.arceus_runtime.billing.api_schemas import (
    BudgetEnforcementRequest,
    InvoiceDraftRequest,
    InvoiceLineInput,
    LedgerEntryInput,
    LedgerPostingRequest,
)
from backend.services.agent.arceus_runtime.billing.service import (
    builtin_plans,
    draft_invoice,
    evaluate_budget,
    ledger_response,
    post_ledger_entries,
    price_usage,
)


def test_builtin_plans_include_entitlements_and_enterprise_controls() -> None:
    plans = {plan["plan_key"]: plan for plan in builtin_plans()}

    assert {"community", "pro", "team", "enterprise"}.issubset(plans)
    assert plans["team"]["feature_limits"]["private_marketplace"] is True
    assert plans["enterprise"]["feature_limits"]["sso"] is True


def test_usage_pricing_tracks_ai_tokens_and_provider_margin() -> None:
    customer_price = price_usage("model.output_tokens", Decimal("1000"))
    provider_cost = Decimal("0.650000")

    assert customer_price == Decimal("1.000000")
    assert customer_price - provider_cost == Decimal("0.350000")


def test_budget_check_blocks_when_projected_spend_exceeds_limit() -> None:
    scope_id = uuid4()
    budget = SimpleNamespace(
        limit_amount=Decimal("100.000000"),
        actual_amount=Decimal("80.000000"),
        reserved_amount=Decimal("10.000000"),
        warning_threshold_percent=80,
    )
    db = _FakeDb(budget=budget)

    response = evaluate_budget(
        db,
        tenant_id=uuid4(),
        payload=BudgetEnforcementRequest(scope_type="mission", scope_id=scope_id, estimated_amount_cents=Decimal("20")),
    )

    assert response.allowed is False
    assert response.action == "block"
    assert response.remaining_cents == Decimal("0")
    assert response.reason == "Budget hard limit would be exceeded."


def test_unbalanced_ledger_posting_is_rejected_before_persistence() -> None:
    payload = LedgerPostingRequest(
        entries=[
            LedgerEntryInput(account="accounts_receivable", direction="debit", amount_cents=Decimal("5000"), source_type="invoice", idempotency_key="ledger-1-dr"),
            LedgerEntryInput(account="revenue", direction="credit", amount_cents=Decimal("4900"), source_type="invoice", idempotency_key="ledger-1-cr"),
        ]
    )

    with pytest.raises(ValueError, match="LEDGER_NOT_BALANCED"):
        post_ledger_entries(_NeverUsedDb(), tenant_id=uuid4(), payload=payload)


def test_ledger_response_reports_balanced_double_entry_rows() -> None:
    group_id = uuid4()
    rows = [
        SimpleNamespace(id=uuid4(), entry_group_id=group_id, account="accounts_receivable", direction="debit", amount_cents=Decimal("5000"), currency="USD", source_type="invoice", source_id=None),
        SimpleNamespace(id=uuid4(), entry_group_id=group_id, account="revenue", direction="credit", amount_cents=Decimal("5000"), currency="USD", source_type="invoice", source_id=None),
    ]

    response = ledger_response(rows)

    assert response.balanced is True
    assert response.debit_total_cents == response.credit_total_cents == Decimal("5000.000000")


def test_invoice_total_accounts_for_tax_and_credits() -> None:
    db = _InvoiceDb()
    payload = InvoiceDraftRequest(
        currency="USD",
        tax_cents=Decimal("100"),
        credits_applied_cents=Decimal("250"),
        lines=[
            InvoiceLineInput(item_type="subscription", description="Pro plan", quantity=Decimal("1"), unit_amount_cents=Decimal("2900")),
            InvoiceLineInput(item_type="usage", description="AI usage", quantity=Decimal("2"), unit_amount_cents=Decimal("125")),
        ],
        invoice_number="ARC-TEST-1",
    )

    invoice = draft_invoice(db, tenant_id=uuid4(), payload=payload)

    assert invoice.subtotal_cents == Decimal("3150.000000")
    assert invoice.tax_cents == Decimal("100.000000")
    assert invoice.credits_applied_cents == Decimal("250.000000")
    assert invoice.total_cents == Decimal("3000.000000")
    assert len(db.added) == 3


class _FakeQuery:
    def __init__(self, value):
        self.value = value

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self.value


class _FakeDb:
    def __init__(self, *, budget):
        self.budget = budget

    def query(self, *args, **kwargs):
        return _FakeQuery(self.budget)


class _NeverUsedDb:
    def query(self, *args, **kwargs):
        raise AssertionError("database should not be queried for unbalanced ledger postings")


class _InvoiceDb:
    def __init__(self) -> None:
        self.added = []

    def add(self, item) -> None:
        if getattr(item, "id", None) is None:
            item.id = uuid4()
        self.added.append(item)

    def flush(self) -> None:
        return None

