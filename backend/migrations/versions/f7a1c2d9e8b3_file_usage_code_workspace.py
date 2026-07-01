"""file usage code workspace

Revision ID: f7a1c2d9e8b3
Revises: 5d3e4fdd4bfe
Create Date: 2026-07-01 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f7a1c2d9e8b3"
down_revision = "5d3e4fdd4bfe"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "file_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("file_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("file_references.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("metadata_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("idx_file_chunks_file_index", "file_chunks", ["file_id", "chunk_index"])
    op.create_index("idx_file_chunks_user_file", "file_chunks", ["user_id", "file_id"])

    op.create_table(
        "usage_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("route", sa.String(length=255), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("provider", sa.String(length=100), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), nullable=True, server_default="0"),
        sa.Column("file_ids", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.CheckConstraint("total_tokens >= 0", name="ck_usage_total_tokens_non_negative"),
    )
    op.create_index("idx_usage_user_created", "usage_events", ["user_id", "created_at"])
    op.create_index("idx_usage_user_session", "usage_events", ["user_id", "session_id"])

    op.create_table(
        "code_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("file_ids", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True, server_default="active"),
        sa.Column("plan_text", sa.Text(), nullable=True),
        sa.Column("patch_text", sa.Text(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("idx_code_sessions_user_status", "code_sessions", ["user_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_code_sessions_user_status", table_name="code_sessions")
    op.drop_table("code_sessions")
    op.drop_index("idx_usage_user_session", table_name="usage_events")
    op.drop_index("idx_usage_user_created", table_name="usage_events")
    op.drop_table("usage_events")
    op.drop_index("idx_file_chunks_user_file", table_name="file_chunks")
    op.drop_index("idx_file_chunks_file_index", table_name="file_chunks")
    op.drop_table("file_chunks")
