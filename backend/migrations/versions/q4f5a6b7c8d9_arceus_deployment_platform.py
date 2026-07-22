"""arceus deployment platform

Revision ID: q4f5a6b7c8d9
Revises: p3e4f5a6b7c8
Create Date: 2026-07-22 00:00:00.000000
"""

from alembic import op

from services.shared.database import Base
from services.shared import arceus_core_models  # noqa: F401


revision = "q4f5a6b7c8d9"
down_revision = "p3e4f5a6b7c8"
branch_labels = None
depends_on = None


DEPLOYMENT_PLATFORM_TABLES = [
    "arceus_deployment_targets",
    "arceus_runtime_profiles",
    "arceus_deployment_applications",
    "arceus_deployment_environments",
    "arceus_deployment_releases",
    "arceus_deployment_artifacts",
    "arceus_deployment_requests",
    "arceus_deployment_plans",
    "arceus_deployment_health_checks",
    "arceus_deployment_rollbacks",
    "arceus_deployment_backups",
    "arceus_deployment_drift_reports",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in DEPLOYMENT_PLATFORM_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(DEPLOYMENT_PLATFORM_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
