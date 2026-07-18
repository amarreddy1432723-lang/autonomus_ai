"""arceus collaboration and memory schema

Revision ID: g4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-07-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

from services.shared.database import Base
from services.shared import arceus_core_models  # noqa: F401


revision = "g4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


COLLABORATION_TABLES = [
    "arceus_participants",
    "arceus_collaboration_messages",
    "arceus_collaboration_message_recipients",
    "arceus_collaboration_message_topics",
    "arceus_participant_inbox_items",
    "arceus_stream_summaries",
    "arceus_reviews",
    "arceus_review_findings",
    "arceus_conflicts",
    "arceus_memory_items",
    "arceus_lesson_proposals",
    "arceus_performance_observations",
]


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))

    for table_name in COLLABORATION_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(COLLABORATION_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
