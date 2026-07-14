"""code orchestration phase1

Revision ID: e2f4a6b8c9d0
Revises: d1e2f3a4b5c6
Create Date: 2026-07-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e2f4a6b8c9d0"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "code_project_orchestrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("code_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage", sa.String(length=80), nullable=True, server_default="intake"),
        sa.Column("original_problem", sa.Text(), nullable=True),
        sa.Column("clarified_problem", sa.Text(), nullable=True),
        sa.Column("business_goal", sa.Text(), nullable=True),
        sa.Column("target_users", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("constraints", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("acceptance_criteria", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("selected_proposal_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("architecture_document", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("implementation_plan", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("tasks", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("review_findings", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("test_results", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("decisions", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("budget_used_usd", sa.Float(), nullable=True, server_default="0"),
        sa.Column("token_usage", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("metadata_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("idx_code_orchestration_project", "code_project_orchestrations", ["project_id", "user_id"])

    op.create_table(
        "code_solution_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("orchestration_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("code_project_orchestrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("code_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("perspective", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("architecture", sa.Text(), nullable=True),
        sa.Column("advantages", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("disadvantages", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("estimated_cost", sa.String(length=100), nullable=True),
        sa.Column("estimated_complexity", sa.String(length=100), nullable=True),
        sa.Column("risks", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("recommended_for", sa.Text(), nullable=True),
        sa.Column("score", sa.Integer(), nullable=True, server_default="0"),
        sa.Column("judge_summary", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("idx_code_proposals_project", "code_solution_proposals", ["project_id", "user_id"])

    op.create_table(
        "code_project_decisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("orchestration_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("code_project_orchestrations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("code_projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("decision_type", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("selected_option_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("payload", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("idx_code_decisions_project", "code_project_decisions", ["project_id", "user_id"])


def downgrade() -> None:
    op.drop_index("idx_code_decisions_project", table_name="code_project_decisions")
    op.drop_table("code_project_decisions")
    op.drop_index("idx_code_proposals_project", table_name="code_solution_proposals")
    op.drop_table("code_solution_proposals")
    op.drop_index("idx_code_orchestration_project", table_name="code_project_orchestrations")
    op.drop_table("code_project_orchestrations")
