"""arceus parallel task runtime

Revision ID: v9e0f1g2h3i4
Revises: u8d9e0f1g2h3
Create Date: 2026-07-22 00:00:00.000000
"""

from alembic import op

from services.shared import arceus_core_models  # noqa: F401
from services.shared.database import Base


revision = "v9e0f1g2h3i4"
down_revision = "u8d9e0f1g2h3"
branch_labels = None
depends_on = None


PARALLEL_RUNTIME_TABLES = [
    "arceus_agent_runtime_workers",
    "arceus_mission_task_assignments",
    "arceus_mission_path_reservations",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in PARALLEL_RUNTIME_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(PARALLEL_RUNTIME_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
