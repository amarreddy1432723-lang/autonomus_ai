"""arceus data platform

Revision ID: s6b7c8d9e0f1
Revises: r5a6b7c8d9e0
Create Date: 2026-07-22 00:00:00.000000
"""

from alembic import op

from services.shared.database import Base
from services.shared import arceus_core_models  # noqa: F401


revision = "s6b7c8d9e0f1"
down_revision = "r5a6b7c8d9e0"
branch_labels = None
depends_on = None


DATA_PLATFORM_TABLES = [
    "arceus_data_event_contracts",
    "arceus_data_outbox_records",
    "arceus_processed_data_events",
    "arceus_dead_letter_data_events",
    "arceus_datasets",
    "arceus_metric_definitions",
    "arceus_metric_snapshots",
    "arceus_data_quality_rules",
    "arceus_data_quality_runs",
    "arceus_data_lineage_edges",
    "arceus_analytics_experiments",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in DATA_PLATFORM_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(DATA_PLATFORM_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
