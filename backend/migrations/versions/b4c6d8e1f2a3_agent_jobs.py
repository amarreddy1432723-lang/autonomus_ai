"""agent jobs

Revision ID: b4c6d8e1f2a3
Revises: a2b7c8d9e0f1
Create Date: 2026-07-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b4c6d8e1f2a3"
down_revision = "a2b7c8d9e0f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("code_sessions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("mode", sa.String(length=100), nullable=True, server_default="code"),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True, server_default="queued"),
        sa.Column("approval_state", sa.String(length=50), nullable=True, server_default="none"),
        sa.Column("logs", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("files_touched", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("commands_run", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("result", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("idx_agent_jobs_user_created", "agent_jobs", ["user_id", "created_at"])
    op.create_index("idx_agent_jobs_session_created", "agent_jobs", ["code_session_id", "created_at"])
    op.create_index("idx_agent_jobs_user_status", "agent_jobs", ["user_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_agent_jobs_user_status", table_name="agent_jobs")
    op.drop_index("idx_agent_jobs_session_created", table_name="agent_jobs")
    op.drop_index("idx_agent_jobs_user_created", table_name="agent_jobs")
    op.drop_table("agent_jobs")
