"""arceus verification engine production persistence

Revision ID: l9a0b1c2d3e4
Revises: k8f9a0b1c2d3
Create Date: 2026-07-19 00:00:00.000000
"""

from alembic import op

from services.shared.database import Base
from services.shared import arceus_core_models  # noqa: F401


revision = "l9a0b1c2d3e4"
down_revision = "k8f9a0b1c2d3"
branch_labels = None
depends_on = None


VERIFICATION_ENGINE_TABLES = [
    "arceus_verification_findings",
    "arceus_verification_worker_jobs",
    "arceus_evidence_producer_runs",
    "arceus_release_readiness_gates",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in VERIFICATION_ENGINE_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(VERIFICATION_ENGINE_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
