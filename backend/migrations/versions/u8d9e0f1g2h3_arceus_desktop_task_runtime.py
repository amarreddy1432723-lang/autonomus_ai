"""arceus desktop task runtime

Revision ID: u8d9e0f1g2h3
Revises: t7c8d9e0f1g2
Create Date: 2026-07-22 00:00:00.000000
"""

from alembic import op

from services.shared import arceus_core_models  # noqa: F401
from services.shared.database import Base


revision = "u8d9e0f1g2h3"
down_revision = "t7c8d9e0f1g2"
branch_labels = None
depends_on = None


DESKTOP_RUNTIME_TABLES = [
    "arceus_desktop_sessions",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in DESKTOP_RUNTIME_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(DESKTOP_RUNTIME_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
