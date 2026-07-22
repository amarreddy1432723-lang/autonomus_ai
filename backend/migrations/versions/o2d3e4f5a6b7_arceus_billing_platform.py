"""arceus billing platform

Revision ID: o2d3e4f5a6b7
Revises: n1c2d3e4f5a6
Create Date: 2026-07-22 00:00:00.000000
"""

from alembic import op

from services.shared.database import Base
from services.shared import arceus_core_models  # noqa: F401


revision = "o2d3e4f5a6b7"
down_revision = "n1c2d3e4f5a6"
branch_labels = None
depends_on = None


BILLING_PLATFORM_TABLES = [
    "arceus_billing_plans",
    "arceus_billing_subscriptions",
    "arceus_billing_entitlements",
    "arceus_billing_usage_events",
    "arceus_credit_wallets",
    "arceus_credit_transactions",
    "arceus_invoices",
    "arceus_invoice_items",
    "arceus_financial_ledger_entries",
    "arceus_marketplace_orders",
    "arceus_publisher_payouts",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in BILLING_PLATFORM_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(BILLING_PLATFORM_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)

