"""code orgs job logs artifacts

Revision ID: d1e2f3a4b5c6
Revises: c9d2e3f4a5b6
Create Date: 2026-07-11 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d1e2f3a4b5c6"
down_revision = "c9d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=True, server_default="active"),
        sa.Column("settings_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("metadata_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_index("idx_orgs_owner_status", "organizations", ["owner_user_id", "status"])

    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=True, server_default="developer"),
        sa.Column("status", sa.String(length=50), nullable=True, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("organization_id", "user_id", name="uq_memberships_org_user"),
    )
    op.create_index("idx_memberships_org_status", "memberships", ["organization_id", "status"])
    op.create_index("idx_memberships_user_status", "memberships", ["user_id", "status"])

    op.create_table(
        "workspace_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("code_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("code_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=True, server_default="developer"),
        sa.Column("status", sa.String(length=50), nullable=True, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("code_session_id", "user_id", name="uq_workspace_members_session_user"),
    )
    op.create_index("idx_workspace_members_session_status", "workspace_members", ["code_session_id", "status"])

    op.create_table(
        "team_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=True, server_default="developer"),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=True, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.UniqueConstraint("token", name="uq_team_invites_token"),
    )
    op.create_index("idx_team_invites_org_status", "team_invites", ["organization_id", "status"])

    op.create_table(
        "org_billing",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("plan_type", sa.String(length=50), nullable=True, server_default="pro"),
        sa.Column("status", sa.String(length=50), nullable=True, server_default="active"),
        sa.Column("provider", sa.String(length=100), nullable=True, server_default="internal"),
        sa.Column("provider_customer_id", sa.String(length=255), nullable=True),
        sa.Column("provider_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("entitlements", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )

    op.create_table(
        "agent_job_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("code_sessions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("kind", sa.String(length=50), nullable=True, server_default="info"),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("idx_agent_job_logs_job_created", "agent_job_logs", ["job_id", "created_at"])
    op.create_index("idx_agent_job_logs_user_created", "agent_job_logs", ["user_id", "created_at"])

    op.create_table(
        "agent_job_artifacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code_session_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("code_sessions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("artifact_type", sa.String(length=100), nullable=True, server_default="file"),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("uri", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("metadata_json", postgresql.JSON(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
    )
    op.create_index("idx_agent_job_artifacts_job_created", "agent_job_artifacts", ["job_id", "created_at"])
    op.create_index("idx_agent_job_artifacts_session_created", "agent_job_artifacts", ["code_session_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_agent_job_artifacts_session_created", table_name="agent_job_artifacts")
    op.drop_index("idx_agent_job_artifacts_job_created", table_name="agent_job_artifacts")
    op.drop_table("agent_job_artifacts")
    op.drop_index("idx_agent_job_logs_user_created", table_name="agent_job_logs")
    op.drop_index("idx_agent_job_logs_job_created", table_name="agent_job_logs")
    op.drop_table("agent_job_logs")
    op.drop_table("org_billing")
    op.drop_index("idx_team_invites_org_status", table_name="team_invites")
    op.drop_table("team_invites")
    op.drop_index("idx_workspace_members_session_status", table_name="workspace_members")
    op.drop_table("workspace_members")
    op.drop_index("idx_memberships_user_status", table_name="memberships")
    op.drop_index("idx_memberships_org_status", table_name="memberships")
    op.drop_table("memberships")
    op.drop_index("idx_orgs_owner_status", table_name="organizations")
    op.drop_table("organizations")
