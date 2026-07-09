"""code projects

Revision ID: c9d2e3f4a5b6
Revises: b4c6d8e1f2a3
Create Date: 2026-07-09 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c9d2e3f4a5b6"
down_revision = "b4c6d8e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "code_projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("repo_url", sa.Text(), nullable=True),
        sa.Column("default_branch", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True, server_default="active"),
        sa.Column("file_ids", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("settings_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("last_opened_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("idx_code_projects_user_status", "code_projects", ["user_id", "status"])
    op.create_index("idx_code_projects_user_opened", "code_projects", ["user_id", "last_opened_at"])

    op.add_column("code_sessions", sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_code_sessions_project_id",
        "code_sessions",
        "code_projects",
        ["project_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("idx_code_sessions_project_updated", "code_sessions", ["project_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("idx_code_sessions_project_updated", table_name="code_sessions")
    op.drop_constraint("fk_code_sessions_project_id", "code_sessions", type_="foreignkey")
    op.drop_column("code_sessions", "project_id")
    op.drop_index("idx_code_projects_user_opened", table_name="code_projects")
    op.drop_index("idx_code_projects_user_status", table_name="code_projects")
    op.drop_table("code_projects")
