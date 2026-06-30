"""phase6_database_completion

Revision ID: 3c9a0b8f2d6e
Revises: 8f4b2c91d3a7
Create Date: 2026-06-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3c9a0b8f2d6e"
down_revision: Union[str, Sequence[str], None] = "8f4b2c91d3a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _add_check_constraint_once(table: str, name: str, expression: str) -> None:
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = '{name}' AND conrelid = '{table}'::regclass
            ) THEN
                ALTER TABLE {table}
                ADD CONSTRAINT {name} CHECK ({expression}) NOT VALID;
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("device_info", sa.JSON(), nullable=True),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash", name="uq_user_sessions_token_hash"),
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("plan_type", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("billing_cycle", sa.String(length=50), nullable=True),
        sa.Column("provider", sa.String(length=100), nullable=True),
        sa.Column("provider_customer_id", sa.String(length=255), nullable=True),
        sa.Column("provider_subscription_id", sa.String(length=255), nullable=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("current_period_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_billing_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entitlements", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_subscription_id", name="uq_subscriptions_provider_subscription"),
    )
    op.create_table(
        "file_references",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("owner_type", sa.String(length=50), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=True),
        sa.Column("storage_provider", sa.String(length=100), nullable=True),
        sa.Column("bucket", sa.String(length=255), nullable=True),
        sa.Column("object_key", sa.Text(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=255), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    _add_check_constraint_once("goals", "ck_goals_priority_range", "priority BETWEEN 1 AND 5")
    _add_check_constraint_once("goals", "ck_goals_progress_pct_range", "progress_pct BETWEEN 0.0 AND 1.0")
    _add_check_constraint_once("projects", "ck_projects_progress_pct_range", "progress_pct BETWEEN 0.0 AND 1.0")
    _add_check_constraint_once("tasks", "ck_tasks_priority_score_range", "priority_score BETWEEN 0.0 AND 1.0")
    _add_check_constraint_once("tasks", "ck_tasks_quality_score_range", "quality_score IS NULL OR quality_score BETWEEN 0.0 AND 1.0")
    _add_check_constraint_once("tasks", "ck_tasks_retry_count_non_negative", "retry_count >= 0")
    _add_check_constraint_once("tasks", "ck_tasks_max_retries_non_negative", "max_retries >= 0")
    _add_check_constraint_once("memories", "ck_memories_confidence_range", "confidence BETWEEN 0.0 AND 1.0")
    _add_check_constraint_once("memories", "ck_memories_importance_range", "importance BETWEEN 1 AND 10")
    _add_check_constraint_once("notifications", "ck_notifications_priority_range", "priority BETWEEN 0 AND 3")

    op.execute("CREATE INDEX IF NOT EXISTS idx_users_last_active ON users(last_active_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_users_auth ON users(auth_provider, auth_provider_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_user_active ON user_sessions(user_id, is_active)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_user_sessions_expires ON user_sessions(expires_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user_status ON subscriptions(user_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_next_billing ON subscriptions(next_billing_at)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_file_references_user_owner ON file_references(user_id, owner_type, owner_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_file_references_user_status ON file_references(user_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_file_references_checksum ON file_references(checksum_sha256)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_goals_user_status ON goals(user_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_goals_user_deadline_active ON goals(user_id, deadline) WHERE status = 'active'")
    op.execute("CREATE INDEX IF NOT EXISTS idx_goals_user_priority_active ON goals(user_id, priority DESC) WHERE status = 'active'")
    op.execute("CREATE INDEX IF NOT EXISTS idx_goals_parent ON goals(parent_goal_id) WHERE parent_goal_id IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_projects_goal_id ON projects(goal_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_projects_user_status ON projects(user_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_id ON tasks(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_status ON tasks(user_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_critical ON tasks(user_id, is_critical_path) WHERE is_critical_path = true")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_tasks_user_priority_active "
        "ON tasks(user_id, priority_score DESC) "
        "WHERE status IN ('queued', 'in_progress', 'blocked', 'waiting_approval')"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_tasks_user_due_active ON tasks(user_id, due_date) WHERE due_date IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_exec_task_id ON task_executions(task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_exec_user_id ON task_executions(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_exec_started ON task_executions(started_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_task_exec_status ON task_executions(user_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_memories_user_id ON memories(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_memories_accessed ON memories(user_id, last_accessed_at DESC)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_memories_active "
        "ON memories(user_id, memory_type, importance DESC) WHERE is_archived = false"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_approvals_user_status ON approvals(user_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_approvals_pending ON approvals(user_id, requested_at DESC) WHERE status = 'pending'")
    op.execute("CREATE INDEX IF NOT EXISTS idx_approvals_task_id ON approvals(task_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_schedules_next_run ON schedules(next_run_at) WHERE is_active = true")
    op.execute("CREATE INDEX IF NOT EXISTS idx_schedules_user_active ON schedules(user_id, is_active)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_notifications_user_status ON notifications(user_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_notifications_unread ON notifications(user_id, created_at DESC) WHERE read_at IS NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_notifications_priority ON notifications(user_id, priority, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_integrations_user_id ON integrations(user_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_integrations_expiry ON integrations(token_expires_at) WHERE token_expires_at IS NOT NULL")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_integrations_user_provider_account "
        "ON integrations(user_id, provider, provider_user_id) WHERE provider_user_id IS NOT NULL"
    )
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_user_time ON audit_logs(user_id, occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_event_type ON audit_logs(event_type, occurred_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_audit_entity ON audit_logs(entity_type, entity_id)")

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs are append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        DROP TRIGGER IF EXISTS trg_prevent_audit_log_update ON audit_logs;
        CREATE TRIGGER trg_prevent_audit_log_update
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_prevent_audit_log_update ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_mutation()")
    op.execute("DROP INDEX IF EXISTS idx_audit_entity")
    op.execute("DROP INDEX IF EXISTS idx_audit_event_type")
    op.execute("DROP INDEX IF EXISTS idx_audit_user_time")
    op.execute("DROP INDEX IF EXISTS uq_integrations_user_provider_account")
    op.execute("DROP INDEX IF EXISTS idx_integrations_expiry")
    op.execute("DROP INDEX IF EXISTS idx_integrations_user_id")
    op.execute("DROP INDEX IF EXISTS idx_notifications_priority")
    op.execute("DROP INDEX IF EXISTS idx_notifications_unread")
    op.execute("DROP INDEX IF EXISTS idx_notifications_user_status")
    op.execute("DROP INDEX IF EXISTS idx_schedules_user_active")
    op.execute("DROP INDEX IF EXISTS idx_schedules_next_run")
    op.execute("DROP INDEX IF EXISTS idx_approvals_task_id")
    op.execute("DROP INDEX IF EXISTS idx_approvals_pending")
    op.execute("DROP INDEX IF EXISTS idx_approvals_user_status")
    op.execute("DROP INDEX IF EXISTS idx_memories_active")
    op.execute("DROP INDEX IF EXISTS idx_memories_accessed")
    op.execute("DROP INDEX IF EXISTS idx_memories_user_id")
    op.execute("DROP INDEX IF EXISTS idx_task_exec_status")
    op.execute("DROP INDEX IF EXISTS idx_task_exec_started")
    op.execute("DROP INDEX IF EXISTS idx_task_exec_user_id")
    op.execute("DROP INDEX IF EXISTS idx_task_exec_task_id")
    op.execute("DROP INDEX IF EXISTS idx_tasks_user_due_active")
    op.execute("DROP INDEX IF EXISTS idx_tasks_user_priority_active")
    op.execute("DROP INDEX IF EXISTS idx_tasks_user_critical")
    op.execute("DROP INDEX IF EXISTS idx_tasks_user_status")
    op.execute("DROP INDEX IF EXISTS idx_tasks_user_id")
    op.execute("DROP INDEX IF EXISTS idx_tasks_project_id")
    op.execute("DROP INDEX IF EXISTS idx_projects_user_status")
    op.execute("DROP INDEX IF EXISTS idx_projects_user_id")
    op.execute("DROP INDEX IF EXISTS idx_projects_goal_id")
    op.execute("DROP INDEX IF EXISTS idx_goals_parent")
    op.execute("DROP INDEX IF EXISTS idx_goals_user_priority_active")
    op.execute("DROP INDEX IF EXISTS idx_goals_user_deadline_active")
    op.execute("DROP INDEX IF EXISTS idx_goals_user_status")
    op.execute("DROP INDEX IF EXISTS idx_file_references_checksum")
    op.execute("DROP INDEX IF EXISTS idx_file_references_user_status")
    op.execute("DROP INDEX IF EXISTS idx_file_references_user_owner")
    op.execute("DROP INDEX IF EXISTS idx_subscriptions_next_billing")
    op.execute("DROP INDEX IF EXISTS idx_subscriptions_user_status")
    op.execute("DROP INDEX IF EXISTS idx_user_sessions_expires")
    op.execute("DROP INDEX IF EXISTS idx_user_sessions_user_active")
    op.execute("DROP INDEX IF EXISTS idx_users_auth")
    op.execute("DROP INDEX IF EXISTS idx_users_last_active")

    op.drop_table("file_references")
    op.drop_table("subscriptions")
    op.drop_table("user_sessions")
