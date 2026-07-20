"""arceus identity governance persistence

Revision ID: j7e8f9a0b1c2
Revises: i6d7e8f9a0b1
Create Date: 2026-07-19 00:00:00.000000
"""

from alembic import op

from services.shared.database import Base
from services.shared import arceus_core_models  # noqa: F401


revision = "j7e8f9a0b1c2"
down_revision = "i6d7e8f9a0b1"
branch_labels = None
depends_on = None


IDENTITY_TABLES = [
    "arceus_role_permissions",
    "arceus_user_sessions",
    "arceus_api_tokens",
    "arceus_service_accounts",
    "arceus_agent_identities",
    "arceus_authorization_decisions",
    "arceus_identity_providers",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in IDENTITY_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(IDENTITY_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
