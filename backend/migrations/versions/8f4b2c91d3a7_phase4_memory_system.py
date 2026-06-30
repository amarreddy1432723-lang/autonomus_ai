"""phase4_memory_system

Revision ID: 8f4b2c91d3a7
Revises: d6cb6eedf9b4
Create Date: 2026-06-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "8f4b2c91d3a7"
down_revision: Union[str, Sequence[str], None] = ("d6cb6eedf9b4", "5d3e4fdd4bfe")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "embedding_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("memory_id", sa.UUID(), nullable=True),
        sa.Column("provider", sa.String(length=100), nullable=True),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("operation", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=True),
        sa.Column("meta_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "memory_conflicts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("existing_memory_id", sa.UUID(), nullable=False),
        sa.Column("new_memory_id", sa.UUID(), nullable=True),
        sa.Column("incoming_content", sa.Text(), nullable=False),
        sa.Column("conflict_type", sa.String(length=100), nullable=True),
        sa.Column("similarity", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("resolution", sa.Text(), nullable=True),
        sa.Column("meta_data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["existing_memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["new_memory_id"], ["memories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("idx_memories_user_archived", "memories", ["user_id", "is_archived"], unique=False)
    op.create_index("idx_memories_user_type", "memories", ["user_id", "memory_type"], unique=False)
    op.create_index("idx_memories_user_importance", "memories", ["user_id", "importance"], unique=False)
    op.create_index("idx_embedding_jobs_user_status", "embedding_jobs", ["user_id", "status"], unique=False)
    op.create_index("idx_memory_conflicts_user_status", "memory_conflicts", ["user_id", "status"], unique=False)

    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memories_vector_hnsw "
        "ON memories USING hnsw (vector vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_memories_vector_hnsw")
    op.drop_index("idx_memory_conflicts_user_status", table_name="memory_conflicts")
    op.drop_index("idx_embedding_jobs_user_status", table_name="embedding_jobs")
    op.drop_index("idx_memories_user_importance", table_name="memories")
    op.drop_index("idx_memories_user_type", table_name="memories")
    op.drop_index("idx_memories_user_archived", table_name="memories")
    op.drop_table("memory_conflicts")
    op.drop_table("embedding_jobs")
