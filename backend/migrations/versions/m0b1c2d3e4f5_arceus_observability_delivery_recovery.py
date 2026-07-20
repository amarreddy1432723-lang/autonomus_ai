"""arceus observability delivery recovery

Revision ID: m0b1c2d3e4f5
Revises: l9a0b1c2d3e4
Create Date: 2026-07-19 00:00:00.000000
"""

from alembic import op

from services.shared.database import Base
from services.shared import arceus_core_models  # noqa: F401


revision = "m0b1c2d3e4f5"
down_revision = "l9a0b1c2d3e4"
branch_labels = None
depends_on = None


OBSERVABILITY_DELIVERY_TABLES = [
    "arceus_telemetry_exporter_configs",
    "arceus_alert_delivery_channels",
    "arceus_alert_delivery_attempts",
    "arceus_recovery_actions",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in OBSERVABILITY_DELIVERY_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(OBSERVABILITY_DELIVERY_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
