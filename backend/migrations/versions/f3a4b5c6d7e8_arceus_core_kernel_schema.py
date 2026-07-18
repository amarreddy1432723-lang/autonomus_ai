"""arceus core kernel schema

Revision ID: f3a4b5c6d7e8
Revises: e2f4a6b8c9d0
Create Date: 2026-07-18 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

from services.shared.database import Base
from services.shared import arceus_core_models  # noqa: F401


revision = "f3a4b5c6d7e8"
down_revision = "e2f4a6b8c9d0"
branch_labels = None
depends_on = None


ARCEUS_TABLES = [
    "arceus_tenants",
    "arceus_users",
    "arceus_tenant_memberships",
    "arceus_projects",
    "arceus_project_repositories",
    "arceus_missions",
    "arceus_mission_versions",
    "arceus_compiler_runs",
    "arceus_mission_repository_scopes",
    "arceus_mission_requirements",
    "arceus_mission_constraints",
    "arceus_mission_unknowns",
    "arceus_mission_success_criteria",
    "arceus_capabilities",
    "arceus_mission_required_capabilities",
    "arceus_specialist_profiles",
    "arceus_specialist_capabilities",
    "arceus_mission_organizations",
    "arceus_organization_members",
    "arceus_workflow_definitions",
    "arceus_workflow_nodes",
    "arceus_workflow_edges",
    "arceus_tasks",
    "arceus_task_dependencies",
    "arceus_task_attempts",
    "arceus_worker_leases",
    "arceus_runtime_checkpoints",
    "arceus_decisions",
    "arceus_approvals",
    "arceus_approval_votes",
    "arceus_artifacts",
    "arceus_artifact_versions",
    "arceus_evidence",
    "arceus_verification_runs",
    "arceus_context_packages",
    "arceus_model_executions",
    "arceus_tool_definitions",
    "arceus_tool_executions",
    "arceus_policy_evaluations",
    "arceus_events",
    "arceus_outbox_messages",
    "arceus_inbox_messages",
    "arceus_idempotency_records",
    "arceus_audit_events",
    "arceus_usage_records",
]


POST_CREATE_FOREIGN_KEYS = [
    (
        "fk_arceus_missions_current_version",
        "arceus_missions",
        "arceus_mission_versions",
        ["current_version_id"],
        ["id"],
    ),
    (
        "fk_arceus_missions_active_workflow",
        "arceus_missions",
        "arceus_workflow_definitions",
        ["active_workflow_id"],
        ["id"],
    ),
    (
        "fk_arceus_artifacts_current_version",
        "arceus_artifacts",
        "arceus_artifact_versions",
        ["current_version_id"],
        ["id"],
    ),
]


def upgrade() -> None:
    bind = op.get_bind()
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS citext"))
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS vector"))

    for table_name in ARCEUS_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)

    for name, source, referent, local_cols, remote_cols in POST_CREATE_FOREIGN_KEYS:
        op.create_foreign_key(name, source, referent, local_cols, remote_cols)


def downgrade() -> None:
    for name, source, *_ in reversed(POST_CREATE_FOREIGN_KEYS):
        op.drop_constraint(name, source, type_="foreignkey")

    bind = op.get_bind()
    for table_name in reversed(ARCEUS_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
