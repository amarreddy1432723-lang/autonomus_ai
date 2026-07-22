"""arceus enterprise collaboration

Revision ID: p3e4f5a6b7c8
Revises: o2d3e4f5a6b7
Create Date: 2026-07-22 00:00:00.000000
"""

from alembic import op

from services.shared.database import Base
from services.shared import arceus_core_models  # noqa: F401


revision = "p3e4f5a6b7c8"
down_revision = "o2d3e4f5a6b7"
branch_labels = None
depends_on = None


ENTERPRISE_COLLABORATION_TABLES = [
    "arceus_collaboration_teams",
    "arceus_collaboration_team_members",
    "arceus_project_members",
    "arceus_collaboration_milestones",
    "arceus_collaboration_tasks",
    "arceus_presence_sessions",
    "arceus_discussion_threads",
    "arceus_comments",
    "arceus_knowledge_pages",
    "arceus_knowledge_revisions",
    "arceus_activity_events",
    "arceus_notifications",
    "arceus_collaboration_review_requests",
    "arceus_meeting_notes",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in ENTERPRISE_COLLABORATION_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(ENTERPRISE_COLLABORATION_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)

