"""arceus enterprise administration

Revision ID: t7c8d9e0f1g2
Revises: s6b7c8d9e0f1
Create Date: 2026-07-22 00:00:00.000000
"""

from alembic import op

from services.shared import arceus_core_models  # noqa: F401
from services.shared.database import Base


revision = "t7c8d9e0f1g2"
down_revision = "s6b7c8d9e0f1"
branch_labels = None
depends_on = None


ENTERPRISE_ADMIN_TABLES = [
    "arceus_admin_organization_profiles",
    "arceus_admin_org_units",
    "arceus_admin_domain_verifications",
    "arceus_admin_sso_configurations",
    "arceus_admin_scim_configurations",
    "arceus_admin_seat_assignments",
    "arceus_admin_access_reviews",
    "arceus_admin_audit_exports",
    "arceus_admin_support_access_grants",
    "arceus_admin_policy_bundles",
    "arceus_admin_tenant_operations",
]


def upgrade() -> None:
    bind = op.get_bind()
    for table_name in ENTERPRISE_ADMIN_TABLES:
        Base.metadata.tables[table_name].create(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()
    for table_name in reversed(ENTERPRISE_ADMIN_TABLES):
        Base.metadata.tables[table_name].drop(bind, checkfirst=True)
