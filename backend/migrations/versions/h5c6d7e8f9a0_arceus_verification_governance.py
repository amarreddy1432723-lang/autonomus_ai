"""arceus verification and completion governance

Revision ID: h5c6d7e8f9a0
Revises: g4b5c6d7e8f9
Create Date: 2026-07-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

from services.shared.database import Base
from services.shared import arceus_core_models  # noqa: F401


revision = "h5c6d7e8f9a0"
down_revision = "g4b5c6d7e8f9"
branch_labels = None
depends_on = None


GOVERNANCE_TABLES = [
    "arceus_verification_plans",
    "arceus_quality_gates",
    "arceus_trust_scores",
    "arceus_completion_certificates",
]


def _add_column_if_missing(bind, table_name: str, column_name: str, column: sa.Column) -> None:
    inspector = sa.inspect(bind)
    columns = {item["name"] for item in inspector.get_columns(table_name)}
    if column_name not in columns:
        op.add_column(table_name, column)


def upgrade() -> None:
    bind = op.get_bind()
    _add_column_if_missing(bind, "arceus_evidence", "workflow_id", sa.Column("workflow_id", sa.UUID(), nullable=True))
    _add_column_if_missing(bind, "arceus_evidence", "verification_method", sa.Column("verification_method", sa.String(length=120), nullable=False, server_default="manual"))
    _add_column_if_missing(bind, "arceus_evidence", "content_hash", sa.Column("content_hash", sa.String(length=128), nullable=False, server_default="sha256:legacy"))
    _add_column_if_missing(bind, "arceus_evidence", "trust_level", sa.Column("trust_level", sa.String(length=60), nullable=False, server_default="unverified"))
    _add_column_if_missing(bind, "arceus_evidence", "immutable", sa.Column("immutable", sa.Boolean(), nullable=False, server_default=sa.text("true")))

    for table_name in GOVERNANCE_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(GOVERNANCE_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
    for column_name in reversed(["workflow_id", "verification_method", "content_hash", "trust_level", "immutable"]):
        try:
            op.drop_column("arceus_evidence", column_name)
        except Exception:
            pass
