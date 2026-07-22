"""arceus security operations

Revision ID: r5a6b7c8d9e0
Revises: q4f5a6b7c8d9
Create Date: 2026-07-22 00:00:00.000000
"""

from alembic import op

from services.shared.database import Base
from services.shared import arceus_core_models  # noqa: F401


revision = "r5a6b7c8d9e0"
down_revision = "q4f5a6b7c8d9"
branch_labels = None
depends_on = None


SECURITY_OPERATIONS_TABLES = [
    "arceus_security_assets",
    "arceus_security_findings",
    "arceus_security_risk_scores",
    "arceus_threat_models",
    "arceus_security_incidents",
    "arceus_security_response_actions",
    "arceus_security_exceptions",
    "arceus_security_evidence",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in SECURITY_OPERATIONS_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(SECURITY_OPERATIONS_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
