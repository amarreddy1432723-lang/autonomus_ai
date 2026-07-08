"""vault life graph model registry

Revision ID: a2b7c8d9e0f1
Revises: f7a1c2d9e8b3
Create Date: 2026-07-08 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import pgvector


revision = "a2b7c8d9e0f1"
down_revision = "f7a1c2d9e8b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_vaults",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("salt", sa.String(length=64), nullable=False),
        sa.Column("recovery_hash", sa.String(length=128), nullable=True),
        sa.Column("vault_version", sa.Integer(), nullable=True, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=True, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "life_graph_nodes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("label_encrypted", sa.Text(), nullable=False),
        sa.Column("label_blind_index", sa.String(length=64), nullable=False),
        sa.Column("node_type", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("strength", sa.Float(), nullable=True, server_default="0.5"),
        sa.Column("last_activity", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_encrypted", sa.Text(), nullable=True),
        sa.Column("vector", pgvector.sqlalchemy.vector.VECTOR(dim=1536), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("ix_life_graph_nodes_label_blind_index", "life_graph_nodes", ["label_blind_index"])
    op.create_index("idx_life_graph_nodes_user_type", "life_graph_nodes", ["user_id", "node_type"])

    op.create_table(
        "life_graph_edges",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("life_graph_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("target_node_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("life_graph_nodes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("relationship", sa.String(length=100), nullable=False),
        sa.Column("weight", sa.Float(), nullable=True, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("idx_life_graph_edges_user_source", "life_graph_edges", ["user_id", "source_node_id"])

    op.create_table(
        "weekly_reflections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("week_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("week_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content_encrypted", sa.Text(), nullable=False),
        sa.Column("tasks_completed", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("tasks_overdue", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("idx_weekly_reflections_user_week", "weekly_reflections", ["user_id", "week_start"])

    op.create_table(
        "model_performance_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("model_key", sa.String(length=100), nullable=False),
        sa.Column("provider", sa.String(length=100), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=False),
        sa.Column("task_type", sa.String(length=100), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error_type", sa.String(length=100), nullable=True),
        sa.Column("user_satisfaction", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("idx_model_performance_task_time", "model_performance_logs", ["task_type", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_model_performance_task_time", table_name="model_performance_logs")
    op.drop_table("model_performance_logs")
    op.drop_index("idx_weekly_reflections_user_week", table_name="weekly_reflections")
    op.drop_table("weekly_reflections")
    op.drop_index("idx_life_graph_edges_user_source", table_name="life_graph_edges")
    op.drop_table("life_graph_edges")
    op.drop_index("idx_life_graph_nodes_user_type", table_name="life_graph_nodes")
    op.drop_index("ix_life_graph_nodes_label_blind_index", table_name="life_graph_nodes")
    op.drop_table("life_graph_nodes")
    op.drop_table("user_vaults")
