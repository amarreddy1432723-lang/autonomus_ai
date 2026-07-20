"""arceus extension platform

Revision ID: n1c2d3e4f5a6
Revises: m0b1c2d3e4f5
Create Date: 2026-07-19 00:00:00.000000
"""

from alembic import op

from services.shared.database import Base
from services.shared import arceus_core_models  # noqa: F401


revision = "n1c2d3e4f5a6"
down_revision = "m0b1c2d3e4f5"
branch_labels = None
depends_on = None


EXTENSION_PLATFORM_TABLES = [
    "arceus_plugin_publishers",
    "arceus_plugins",
    "arceus_plugin_versions",
    "arceus_plugin_installations",
    "arceus_plugin_installation_permissions",
    "arceus_plugin_invocations",
    "arceus_plugin_security_findings",
    "arceus_plugin_usage_events",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in EXTENSION_PLATFORM_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(EXTENSION_PLATFORM_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
