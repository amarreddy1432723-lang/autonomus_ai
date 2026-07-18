"""arceus model tool gateway routing and costs

Revision ID: i6d7e8f9a0b1
Revises: h5c6d7e8f9a0
Create Date: 2026-07-18 00:00:00.000000
"""

from alembic import op

from services.shared.database import Base
from services.shared import arceus_core_models  # noqa: F401


revision = "i6d7e8f9a0b1"
down_revision = "h5c6d7e8f9a0"
branch_labels = None
depends_on = None


GATEWAY_TABLES = [
    "arceus_provider_profiles",
    "arceus_model_profiles",
    "arceus_tool_profiles",
    "arceus_routing_decisions",
    "arceus_budgets",
    "arceus_cost_reservations",
    "arceus_ai_execution_ledger",
    "arceus_execution_evaluations",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in GATEWAY_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(GATEWAY_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
