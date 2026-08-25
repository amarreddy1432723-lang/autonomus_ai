"""desktop auth one-time exchange codes

Revision ID: w0f1g2h3i4j5
Revises: v9e0f1g2h3i4
Create Date: 2026-07-26 00:00:00.000000
"""

from alembic import op

from services.shared.database import Base
from services.shared import models  # noqa: F401


revision = "w0f1g2h3i4j5"
down_revision = "v9e0f1g2h3i4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["desktop_auth_codes"].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    Base.metadata.tables["desktop_auth_codes"].drop(bind, checkfirst=True)
