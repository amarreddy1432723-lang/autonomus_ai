"""arceus observability aiops persistence

Revision ID: k8f9a0b1c2d3
Revises: j7e8f9a0b1c2
Create Date: 2026-07-19 00:00:00.000000
"""

from alembic import op

from services.shared.database import Base
from services.shared import arceus_core_models  # noqa: F401


revision = "k8f9a0b1c2d3"
down_revision = "j7e8f9a0b1c2"
branch_labels = None
depends_on = None


OBSERVABILITY_TABLES = [
    "arceus_telemetry_logs",
    "arceus_metric_samples",
    "arceus_traces",
    "arceus_spans",
    "arceus_alerts",
    "arceus_incidents",
    "arceus_provider_health",
    "arceus_mission_statistics",
    "arceus_cost_statistics",
    "arceus_dashboard_configs",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in OBSERVABILITY_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(OBSERVABILITY_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
