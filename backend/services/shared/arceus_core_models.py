import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.sql import func

from .database import Base


MISSION_STATUS_VALUES = (
    "draft",
    "compiling",
    "clarification_required",
    "compiled",
    "organizing",
    "plan_pending",
    "awaiting_plan_approval",
    "ready",
    "running",
    "paused",
    "blocked",
    "reviewing",
    "verifying",
    "awaiting_completion_approval",
    "completed",
    "failed",
    "cancelled",
    "archived",
)


def _uuid_pk() -> Column:
    return Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid())


def _tenant_fk(nullable: bool = False) -> Column:
    return Column(UUID(as_uuid=True), ForeignKey("arceus_tenants.id"), nullable=nullable)


class KernelMutableMixin:
    id = _uuid_pk()
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    version_number = Column(BigInteger, default=1, nullable=False)


class KernelTenantMixin(KernelMutableMixin):
    tenant_id = _tenant_fk()


class ArceusTenant(KernelMutableMixin, Base):
    __tablename__ = "arceus_tenants"

    name = Column(Text, nullable=False)
    slug = Column(String(255), nullable=False)
    status = Column(String(40), default="active", nullable=False)
    plan_key = Column(String(80), default="free", nullable=False)
    settings = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'suspended', 'closed')", name="ck_arceus_tenants_status"),
        UniqueConstraint("slug", name="uq_arceus_tenants_slug"),
        Index("ix_arceus_tenants_status", "status"),
    )


class ArceusUser(KernelMutableMixin, Base):
    __tablename__ = "arceus_users"

    external_identity_id = Column(Text, nullable=False)
    email = Column(String(320), nullable=False)
    display_name = Column(Text)
    avatar_url = Column(Text)
    status = Column(String(40), default="active", nullable=False)
    preferences = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled')", name="ck_arceus_users_status"),
        UniqueConstraint("external_identity_id", name="uq_arceus_users_external_identity"),
        UniqueConstraint("email", name="uq_arceus_users_email"),
    )


class ArceusTenantMembership(KernelTenantMixin, Base):
    __tablename__ = "arceus_tenant_memberships"

    user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    role_key = Column(String(120), nullable=False)
    status = Column(String(40), default="active", nullable=False)
    joined_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('invited', 'active', 'suspended', 'removed')", name="ck_arceus_tenant_memberships_status"),
        UniqueConstraint("tenant_id", "user_id", name="uq_arceus_tenant_membership"),
        Index("ix_arceus_tenant_memberships_user", "user_id", "status"),
        Index("ix_arceus_tenant_memberships_tenant_role", "tenant_id", "role_key", "status"),
    )


class ArceusProject(KernelTenantMixin, Base):
    __tablename__ = "arceus_projects"

    name = Column(Text, nullable=False)
    slug = Column(String(255), nullable=False)
    description = Column(Text)
    status = Column(String(40), default="active", nullable=False)
    settings = Column(JSON, default=dict, nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    archived_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('active', 'paused', 'archived')", name="ck_arceus_projects_status"),
        UniqueConstraint("tenant_id", "slug", name="uq_arceus_projects_tenant_slug"),
        Index("ix_arceus_projects_tenant_status", "tenant_id", "status"),
    )


class ArceusProjectRepository(KernelTenantMixin, Base):
    __tablename__ = "arceus_project_repositories"

    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"), nullable=False)
    provider = Column(String(40), nullable=False)
    external_repository_id = Column(Text)
    repository_url = Column(Text, nullable=False)
    default_branch = Column(Text, default="main", nullable=False)
    local_workspace_path = Column(Text)
    status = Column(String(40), default="active", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("provider IN ('github', 'gitlab', 'bitbucket', 'local')", name="ck_arceus_project_repositories_provider"),
        CheckConstraint("status IN ('active', 'disconnected', 'archived')", name="ck_arceus_project_repositories_status"),
        UniqueConstraint("tenant_id", "project_id", "repository_url", name="uq_arceus_project_repository_url"),
        Index("ix_arceus_project_repositories_project", "tenant_id", "project_id", "status"),
    )


class ArceusMission(KernelTenantMixin, Base):
    __tablename__ = "arceus_missions"

    project_id = Column(UUID(as_uuid=True), ForeignKey("arceus_projects.id"), nullable=False)
    created_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"), nullable=False)
    title = Column(Text, nullable=False)
    objective = Column(Text, nullable=False)
    status = Column(String(80), default="draft", nullable=False)
    risk_level = Column(String(40), default="medium", nullable=False)
    priority = Column(Integer, default=3, nullable=False)
    maximum_budget_amount = Column(Numeric(14, 4))
    actual_cost_amount = Column(Numeric(14, 4), default=0, nullable=False)
    budget_currency = Column(String(3), default="USD", nullable=False)
    current_version_id = Column(UUID(as_uuid=True))
    active_workflow_id = Column(UUID(as_uuid=True))
    paused_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    failed_at = Column(DateTime(timezone=True))
    failure_reason = Column(Text)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint(f"status IN {MISSION_STATUS_VALUES}", name="ck_arceus_missions_status"),
        CheckConstraint("priority >= 0 AND priority <= 5", name="ck_arceus_missions_priority"),
        Index("ix_arceus_missions_project_status", "tenant_id", "project_id", "status"),
        Index("ix_arceus_missions_created_by", "tenant_id", "created_by", "created_at"),
    )


class ArceusMissionVersion(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_versions"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    version = Column(Integer, nullable=False)
    compiled_by = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    objective_snapshot = Column(Text, nullable=False)
    mission_contract = Column(JSON, default=dict, nullable=False)
    intent_frame = Column(JSON, default=dict, nullable=False)
    risk_profile = Column(JSON, default=dict, nullable=False)
    execution_graph = Column(JSON, default=dict, nullable=False)
    source_hash = Column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "version", name="uq_arceus_mission_versions_version"),
        UniqueConstraint("mission_id", "source_hash", name="uq_arceus_mission_versions_source_hash"),
        Index("ix_arceus_mission_versions_mission", "tenant_id", "mission_id", "version"),
    )


class ArceusCompilerRun(KernelTenantMixin, Base):
    __tablename__ = "arceus_compiler_runs"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    source_mission_version = Column(BigInteger, nullable=False)
    status = Column(String(60), default="queued", nullable=False)
    current_stage = Column(String(120))
    stage_results = Column(JSON, default=dict, nullable=False)
    source_manifest_id = Column(UUID(as_uuid=True))
    compiled_mission_version_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_versions.id"))
    model_execution_ids = Column(JSON, default=list, nullable=False)
    warning_codes = Column(JSON, default=list, nullable=False)
    error_code = Column(String(160))
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'clarification_required', 'compiled', 'rejected', 'failed', 'stale', 'cancelled')",
            name="ck_arceus_compiler_runs_status",
        ),
        Index("ix_arceus_compiler_runs_mission_status", "tenant_id", "mission_id", "status"),
        Index("ix_arceus_compiler_runs_status_stage", "tenant_id", "status", "current_stage"),
    )


class ArceusMissionRepositoryScope(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_repository_scopes"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    repository_id = Column(UUID(as_uuid=True), ForeignKey("arceus_project_repositories.id"), nullable=False)
    base_ref = Column(Text)
    working_ref = Column(Text)
    allowed_paths = Column(ARRAY(Text), default=list, nullable=False)
    denied_paths = Column(ARRAY(Text), default=list, nullable=False)
    scope_reason = Column(Text)

    __table_args__ = (
        UniqueConstraint("mission_id", "repository_id", name="uq_arceus_mission_repository_scope"),
        Index("ix_arceus_mission_repository_scopes_mission", "tenant_id", "mission_id"),
    )


class ArceusMissionRequirement(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_requirements"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    requirement_key = Column(String(120), nullable=False)
    statement = Column(Text, nullable=False)
    source = Column(String(120), default="user", nullable=False)
    priority = Column(Integer, default=3, nullable=False)
    verified = Column(Boolean, default=False, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "requirement_key", name="uq_arceus_mission_requirement_key"),
        Index("ix_arceus_mission_requirements_mission", "tenant_id", "mission_id"),
    )


class ArceusMissionConstraint(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_constraints"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    constraint_key = Column(String(120), nullable=False)
    statement = Column(Text, nullable=False)
    severity = Column(String(40), default="required", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "constraint_key", name="uq_arceus_mission_constraint_key"),
        Index("ix_arceus_mission_constraints_mission", "tenant_id", "mission_id"),
    )


class ArceusMissionUnknown(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_unknowns"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    question = Column(Text, nullable=False)
    risk_if_unanswered = Column(Text)
    status = Column(String(40), default="open", nullable=False)
    answer = Column(Text)

    __table_args__ = (
        CheckConstraint("status IN ('open', 'answered', 'deferred')", name="ck_arceus_mission_unknowns_status"),
        Index("ix_arceus_mission_unknowns_mission", "tenant_id", "mission_id", "status"),
    )


class ArceusMissionSuccessCriterion(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_success_criteria"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    criterion_key = Column(String(120), nullable=False)
    statement = Column(Text, nullable=False)
    verification_method = Column(String(120), nullable=False)
    required = Column(Boolean, default=True, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "criterion_key", name="uq_arceus_mission_success_criterion_key"),
        Index("ix_arceus_mission_success_criteria_mission", "tenant_id", "mission_id"),
    )


class ArceusCapability(KernelMutableMixin, Base):
    __tablename__ = "arceus_capabilities"

    capability_key = Column(String(160), nullable=False)
    domain = Column(String(120), nullable=False)
    name = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    verification_methods = Column(JSON, default=list, nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("capability_key", name="uq_arceus_capabilities_key"),
        Index("ix_arceus_capabilities_domain", "domain", "active"),
    )


class ArceusMissionRequiredCapability(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_required_capabilities"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    capability_id = Column(UUID(as_uuid=True), ForeignKey("arceus_capabilities.id"), nullable=False)
    reason = Column(Text, nullable=False)
    required_level = Column(String(60), default="standard", nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "capability_id", name="uq_arceus_mission_required_capability"),
        Index("ix_arceus_mission_required_capabilities_mission", "tenant_id", "mission_id"),
    )


class ArceusSpecialistProfile(KernelMutableMixin, Base):
    __tablename__ = "arceus_specialist_profiles"

    specialist_key = Column(String(160), nullable=False)
    display_name = Column(Text, nullable=False)
    specialist_type = Column(String(80), nullable=False)
    authority_profile = Column(JSON, default=dict, nullable=False)
    default_model_policy = Column(JSON, default=dict, nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (
        CheckConstraint("specialist_type IN ('human', 'ai', 'system')", name="ck_arceus_specialist_profiles_type"),
        UniqueConstraint("specialist_key", name="uq_arceus_specialist_profiles_key"),
    )


class ArceusSpecialistCapability(KernelMutableMixin, Base):
    __tablename__ = "arceus_specialist_capabilities"

    specialist_profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_specialist_profiles.id"), nullable=False)
    capability_id = Column(UUID(as_uuid=True), ForeignKey("arceus_capabilities.id"), nullable=False)
    proficiency = Column(Float, default=0.75, nullable=False)
    evidence = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("specialist_profile_id", "capability_id", name="uq_arceus_specialist_capability"),
    )


class ArceusMissionOrganization(KernelTenantMixin, Base):
    __tablename__ = "arceus_mission_organizations"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    organization_name = Column(Text, nullable=False)
    status = Column(String(60), default="draft", nullable=False)
    rationale = Column(Text, nullable=False)
    budget_policy = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('draft', 'active', 'paused', 'retired')", name="ck_arceus_mission_organizations_status"),
        UniqueConstraint("mission_id", name="uq_arceus_mission_organizations_mission"),
        Index("ix_arceus_mission_organizations_mission", "tenant_id", "mission_id"),
    )


class ArceusOrganizationMember(KernelTenantMixin, Base):
    __tablename__ = "arceus_organization_members"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_organizations.id"), nullable=False)
    specialist_profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_specialist_profiles.id"), nullable=False)
    participant_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    role_key = Column(String(120), nullable=False)
    responsibility = Column(Text, nullable=False)
    authority = Column(JSON, default=dict, nullable=False)
    can_implement = Column(Boolean, default=False, nullable=False)
    can_review = Column(Boolean, default=False, nullable=False)
    can_approve = Column(Boolean, default=False, nullable=False)
    status = Column(String(60), default="active", nullable=False)

    __table_args__ = (
        UniqueConstraint("organization_id", "role_key", name="uq_arceus_organization_member_role"),
        Index("ix_arceus_organization_members_org", "tenant_id", "organization_id", "status"),
    )


class ArceusWorkflowDefinition(KernelTenantMixin, Base):
    __tablename__ = "arceus_workflow_definitions"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    mission_version_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_versions.id"), nullable=False)
    status = Column(String(60), default="draft", nullable=False)
    graph_hash = Column(String(128), nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "graph_hash", name="uq_arceus_workflow_definitions_graph_hash"),
        Index("ix_arceus_workflow_definitions_mission", "tenant_id", "mission_id", "status"),
    )


class ArceusWorkflowNode(KernelTenantMixin, Base):
    __tablename__ = "arceus_workflow_nodes"

    workflow_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_definitions.id"), nullable=False)
    node_key = Column(String(160), nullable=False)
    node_type = Column(String(80), nullable=False)
    title = Column(Text, nullable=False)
    config = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("workflow_id", "node_key", name="uq_arceus_workflow_nodes_key"),
        Index("ix_arceus_workflow_nodes_workflow", "tenant_id", "workflow_id"),
    )


class ArceusWorkflowEdge(KernelTenantMixin, Base):
    __tablename__ = "arceus_workflow_edges"

    workflow_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_definitions.id"), nullable=False)
    source_node_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_nodes.id"), nullable=False)
    target_node_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_nodes.id"), nullable=False)
    condition = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("workflow_id", "source_node_id", "target_node_id", name="uq_arceus_workflow_edges_pair"),
        Index("ix_arceus_workflow_edges_workflow", "tenant_id", "workflow_id"),
    )


class ArceusTask(KernelTenantMixin, Base):
    __tablename__ = "arceus_tasks"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    workflow_node_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_nodes.id"))
    task_key = Column(String(160), nullable=False)
    title = Column(Text, nullable=False)
    task_type = Column(String(80), nullable=False)
    status = Column(String(60), default="pending", nullable=False)
    owner_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    input_contract = Column(JSON, default=dict, nullable=False)
    output_contract = Column(JSON, default=dict, nullable=False)
    acceptance_criteria = Column(JSON, default=list, nullable=False)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    failure_reason = Column(Text)

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'ready', 'running', 'blocked', 'reviewing', 'verifying', 'completed', 'failed', 'cancelled')", name="ck_arceus_tasks_status"),
        UniqueConstraint("mission_id", "task_key", name="uq_arceus_tasks_key"),
        Index("ix_arceus_tasks_mission_status", "tenant_id", "mission_id", "status"),
        Index("ix_arceus_tasks_owner_status", "tenant_id", "owner_member_id", "status"),
    )


class ArceusTaskDependency(KernelTenantMixin, Base):
    __tablename__ = "arceus_task_dependencies"

    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"), nullable=False)
    depends_on_task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"), nullable=False)
    dependency_type = Column(String(60), default="blocks", nullable=False)

    __table_args__ = (
        UniqueConstraint("task_id", "depends_on_task_id", name="uq_arceus_task_dependency"),
        Index("ix_arceus_task_dependencies_task", "tenant_id", "task_id"),
    )


class ArceusTaskAttempt(KernelTenantMixin, Base):
    __tablename__ = "arceus_task_attempts"

    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    status = Column(String(60), default="running", nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True))
    worker_id = Column(String(160))
    idempotency_key = Column(String(255), nullable=False)
    result = Column(JSON, default=dict, nullable=False)
    error = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed', 'cancelled')", name="ck_arceus_task_attempts_status"),
        UniqueConstraint("task_id", "attempt_number", name="uq_arceus_task_attempt_number"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_arceus_task_attempt_idempotency"),
        Index("ix_arceus_task_attempts_task", "tenant_id", "task_id", "started_at"),
    )


class ArceusWorkerLease(KernelTenantMixin, Base):
    __tablename__ = "arceus_worker_leases"

    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"), nullable=False)
    worker_id = Column(String(160), nullable=False)
    lease_token = Column(String(255), nullable=False)
    status = Column(String(60), default="active", nullable=False)
    heartbeat_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('active', 'released', 'expired')", name="ck_arceus_worker_leases_status"),
        UniqueConstraint("task_id", "lease_token", name="uq_arceus_worker_lease_token"),
        Index("ix_arceus_worker_leases_active", "tenant_id", "status", "expires_at"),
    )


class ArceusRuntimeCheckpoint(KernelTenantMixin, Base):
    __tablename__ = "arceus_runtime_checkpoints"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"), nullable=False)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_definitions.id"))
    worker_lease_id = Column(UUID(as_uuid=True), ForeignKey("arceus_worker_leases.id"))
    checkpoint_key = Column(String(160), nullable=False)
    workflow_version = Column(BigInteger, nullable=False)
    execution_state = Column(JSON, default=dict, nullable=False)
    artifacts = Column(JSON, default=list, nullable=False)
    model_calls = Column(JSON, default=list, nullable=False)
    tool_calls = Column(JSON, default=list, nullable=False)
    outputs = Column(JSON, default=dict, nullable=False)
    progress_percent = Column(Integer, default=0, nullable=False)
    created_by_worker_id = Column(String(160), nullable=False)

    __table_args__ = (
        UniqueConstraint("task_id", "checkpoint_key", name="uq_arceus_runtime_checkpoints_task_key"),
        Index("ix_arceus_runtime_checkpoints_mission", "tenant_id", "mission_id", "created_at"),
        Index("ix_arceus_runtime_checkpoints_task", "tenant_id", "task_id", "created_at"),
    )


class ArceusDecision(KernelTenantMixin, Base):
    __tablename__ = "arceus_decisions"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    decision_key = Column(String(160), nullable=False)
    title = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    selected_option = Column(JSON, default=dict, nullable=False)
    alternatives = Column(JSON, default=list, nullable=False)
    rationale = Column(Text, nullable=False)
    status = Column(String(60), default="proposed", nullable=False)
    decided_by_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))

    __table_args__ = (
        CheckConstraint("status IN ('proposed', 'approved', 'rejected', 'superseded')", name="ck_arceus_decisions_status"),
        UniqueConstraint("mission_id", "decision_key", name="uq_arceus_decisions_key"),
        Index("ix_arceus_decisions_mission", "tenant_id", "mission_id", "status"),
    )


class ArceusApproval(KernelTenantMixin, Base):
    __tablename__ = "arceus_approvals"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    decision_id = Column(UUID(as_uuid=True), ForeignKey("arceus_decisions.id"))
    approval_type = Column(String(100), nullable=False)
    subject_type = Column(String(100), default="mission_plan", nullable=False)
    subject_hash = Column(String(128), nullable=False)
    proposed_action = Column(Text, default="", nullable=False)
    risk_level = Column(String(40), default="medium", nullable=False)
    status = Column(String(60), default="pending", nullable=False)
    quorum_policy = Column(JSON, default=dict, nullable=False)
    requested_by_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    expires_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'approved', 'rejected', 'cancelled')", name="ck_arceus_approvals_status"),
        Index("ix_arceus_approvals_mission_status", "tenant_id", "mission_id", "status"),
    )


class ArceusApprovalVote(KernelTenantMixin, Base):
    __tablename__ = "arceus_approval_votes"

    approval_id = Column(UUID(as_uuid=True), ForeignKey("arceus_approvals.id"), nullable=False)
    voter_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    voter_user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    vote = Column(String(40), nullable=False)
    comment = Column(Text)
    is_human_vote = Column(Boolean, default=False, nullable=False)

    __table_args__ = (
        CheckConstraint("vote IN ('approve', 'reject', 'abstain')", name="ck_arceus_approval_votes_vote"),
        UniqueConstraint("approval_id", "voter_member_id", "voter_user_id", name="uq_arceus_approval_vote_voter"),
        Index("ix_arceus_approval_votes_approval", "tenant_id", "approval_id"),
    )


class ArceusArtifact(KernelTenantMixin, Base):
    __tablename__ = "arceus_artifacts"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    artifact_key = Column(String(160), nullable=False)
    artifact_type = Column(String(100), nullable=False)
    title = Column(Text, nullable=False)
    current_version_id = Column(UUID(as_uuid=True))
    trust_status = Column(String(60), default="unverified", nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("trust_status IN ('unverified', 'verified', 'superseded', 'rejected')", name="ck_arceus_artifacts_trust_status"),
        UniqueConstraint("mission_id", "artifact_key", name="uq_arceus_artifacts_key"),
        Index("ix_arceus_artifacts_mission", "tenant_id", "mission_id", "artifact_type"),
    )


class ArceusArtifactVersion(KernelTenantMixin, Base):
    __tablename__ = "arceus_artifact_versions"

    artifact_id = Column(UUID(as_uuid=True), ForeignKey("arceus_artifacts.id"), nullable=False)
    version = Column(Integer, nullable=False)
    content = Column(JSON, default=dict, nullable=False)
    content_hash = Column(String(128), nullable=False)
    produced_by_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    provenance = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        UniqueConstraint("artifact_id", "version", name="uq_arceus_artifact_versions_version"),
        UniqueConstraint("artifact_id", "content_hash", name="uq_arceus_artifact_versions_content_hash"),
    )


class ArceusEvidence(KernelTenantMixin, Base):
    __tablename__ = "arceus_evidence"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    artifact_id = Column(UUID(as_uuid=True), ForeignKey("arceus_artifacts.id"))
    evidence_type = Column(String(100), nullable=False)
    status = Column(String(60), default="collected", nullable=False)
    summary = Column(Text, nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    collected_by_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))

    __table_args__ = (
        CheckConstraint("status IN ('collected', 'verified', 'failed')", name="ck_arceus_evidence_status"),
        Index("ix_arceus_evidence_mission", "tenant_id", "mission_id", "evidence_type"),
    )


class ArceusVerificationRun(KernelTenantMixin, Base):
    __tablename__ = "arceus_verification_runs"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    verification_type = Column(String(100), nullable=False)
    status = Column(String(60), nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True))
    command = Column(Text)
    result = Column(JSON, default=dict, nullable=False)
    evidence_id = Column(UUID(as_uuid=True), ForeignKey("arceus_evidence.id"))

    __table_args__ = (
        CheckConstraint("status IN ('running', 'passed', 'failed', 'cancelled')", name="ck_arceus_verification_runs_status"),
        Index("ix_arceus_verification_runs_mission", "tenant_id", "mission_id", "status"),
    )


class ArceusContextPackage(KernelTenantMixin, Base):
    __tablename__ = "arceus_context_packages"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    recipient_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    purpose = Column(Text, nullable=False)
    selected_items = Column(JSON, default=list, nullable=False)
    excluded_items = Column(JSON, default=list, nullable=False)
    token_budget = Column(Integer, default=0, nullable=False)
    content_hash = Column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "task_id", "recipient_member_id", "content_hash", name="uq_arceus_context_packages_hash"),
    )


class ArceusModelExecution(KernelTenantMixin, Base):
    __tablename__ = "arceus_model_executions"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    provider = Column(String(100), nullable=False)
    model = Column(String(160), nullable=False)
    purpose = Column(String(160), nullable=False)
    prompt_hash = Column(String(128), nullable=False)
    input_tokens = Column(Integer, default=0, nullable=False)
    output_tokens = Column(Integer, default=0, nullable=False)
    cost_usd = Column(Numeric(12, 6), default=0, nullable=False)
    latency_ms = Column(Integer)
    status = Column(String(60), nullable=False)
    error = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('succeeded', 'failed', 'cancelled')", name="ck_arceus_model_executions_status"),
        Index("ix_arceus_model_executions_mission", "tenant_id", "mission_id", "created_at"),
    )


class ArceusParticipant(KernelTenantMixin, Base):
    __tablename__ = "arceus_participants"

    organization_id = Column(UUID(as_uuid=True), ForeignKey("arceus_mission_organizations.id"))
    user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    organization_member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    participant_type = Column(String(80), nullable=False)
    display_name = Column(Text, nullable=False)
    role_key = Column(String(120))
    specialist_profile_id = Column(UUID(as_uuid=True), ForeignKey("arceus_specialist_profiles.id"))
    capabilities = Column(JSON, default=list, nullable=False)
    authorities = Column(JSON, default=list, nullable=False)
    active_mission_ids = Column(JSON, default=list, nullable=False)
    status = Column(String(60), default="available", nullable=False)

    __table_args__ = (
        CheckConstraint(
            "participant_type IN ('human', 'ai_specialist', 'service', 'verifier', 'integration', 'policy_authority')",
            name="ck_arceus_participants_type",
        ),
        CheckConstraint(
            "status IN ('available', 'busy', 'waiting', 'paused', 'offline', 'degraded', 'suspended', 'revoked')",
            name="ck_arceus_participants_status",
        ),
        Index("ix_arceus_participants_org_status", "tenant_id", "organization_id", "status"),
    )


class ArceusCollaborationMessage(KernelTenantMixin, Base):
    __tablename__ = "arceus_collaboration_messages"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("arceus_workflow_definitions.id"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    decision_id = Column(UUID(as_uuid=True), ForeignKey("arceus_decisions.id"))
    review_id = Column(UUID(as_uuid=True))
    message_type = Column(String(80), nullable=False)
    sender_participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"), nullable=False)
    subject = Column(Text, nullable=False)
    body = Column(Text, nullable=False)
    structured_payload = Column(JSON, default=dict, nullable=False)
    priority = Column(String(40), default="normal", nullable=False)
    confidentiality = Column(String(60), default="mission", nullable=False)
    requires_acknowledgement = Column(Boolean, default=False, nullable=False)
    response_required_by = Column(DateTime(timezone=True))
    correlation_id = Column(UUID(as_uuid=True), nullable=False)
    causation_id = Column(UUID(as_uuid=True))
    body_hash = Column(String(128), nullable=False)
    deleted_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "message_type IN ('command', 'question', 'answer', 'finding', 'proposal', 'review_request', 'review_result', 'decision_request', 'decision_result', 'handoff', 'status_update', 'risk_alert', 'incident', 'approval_request', 'approval_result', 'knowledge_proposal', 'system_notice')",
            name="ck_arceus_collaboration_messages_type",
        ),
        CheckConstraint("priority IN ('low', 'normal', 'high', 'urgent')", name="ck_arceus_collaboration_messages_priority"),
        CheckConstraint(
            "confidentiality IN ('public', 'tenant', 'project', 'mission', 'task', 'restricted', 'secret_reference_only')",
            name="ck_arceus_collaboration_messages_confidentiality",
        ),
        Index("ix_arceus_collaboration_messages_mission_created", "tenant_id", "mission_id", "created_at"),
        Index("ix_arceus_collaboration_messages_task_created", "tenant_id", "task_id", "created_at"),
    )


class ArceusCollaborationMessageRecipient(KernelTenantMixin, Base):
    __tablename__ = "arceus_collaboration_message_recipients"

    message_id = Column(UUID(as_uuid=True), ForeignKey("arceus_collaboration_messages.id"), nullable=False)
    participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"), nullable=False)
    delivery_status = Column(String(60), default="delivered", nullable=False)
    relevance_score = Column(Float, default=0.0, nullable=False)
    delivered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("participant_id", "message_id", name="uq_arceus_collaboration_recipient_message"),
        Index("ix_arceus_collaboration_recipients_participant", "tenant_id", "participant_id", "delivery_status"),
    )


class ArceusCollaborationMessageTopic(KernelTenantMixin, Base):
    __tablename__ = "arceus_collaboration_message_topics"

    message_id = Column(UUID(as_uuid=True), ForeignKey("arceus_collaboration_messages.id"), nullable=False)
    topic_key = Column(String(240), nullable=False)

    __table_args__ = (
        UniqueConstraint("message_id", "topic_key", name="uq_arceus_collaboration_message_topic"),
        Index("ix_arceus_collaboration_topics_key", "tenant_id", "topic_key"),
    )


class ArceusParticipantInboxItem(KernelTenantMixin, Base):
    __tablename__ = "arceus_participant_inbox_items"

    participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"), nullable=False)
    message_id = Column(UUID(as_uuid=True), ForeignKey("arceus_collaboration_messages.id"), nullable=False)
    delivery_status = Column(String(60), default="unread", nullable=False)
    relevance_score = Column(Float, default=0.0, nullable=False)
    delivered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    read_at = Column(DateTime(timezone=True))
    acknowledged_at = Column(DateTime(timezone=True))
    responded_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "delivery_status IN ('unread', 'read', 'acknowledged', 'responded', 'expired', 'dismissed', 'escalated')",
            name="ck_arceus_participant_inbox_status",
        ),
        UniqueConstraint("participant_id", "message_id", name="uq_arceus_participant_inbox_message"),
        Index("ix_arceus_participant_inbox", "tenant_id", "participant_id", "delivery_status", "delivered_at"),
    )


class ArceusStreamSummary(KernelTenantMixin, Base):
    __tablename__ = "arceus_stream_summaries"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    stream_key = Column(String(240), nullable=False)
    source_message_ids = Column(JSON, default=list, nullable=False)
    summary_payload = Column(JSON, default=dict, nullable=False)
    summary_version = Column(Integer, default=1, nullable=False)
    content_hash = Column(String(128), nullable=False)

    __table_args__ = (
        UniqueConstraint("mission_id", "stream_key", "summary_version", name="uq_arceus_stream_summary_version"),
        Index("ix_arceus_stream_summaries_stream", "tenant_id", "mission_id", "stream_key"),
    )


class ArceusReview(KernelTenantMixin, Base):
    __tablename__ = "arceus_reviews"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    review_type = Column(String(100), nullable=False)
    target_type = Column(String(100), nullable=False)
    target_id = Column(UUID(as_uuid=True), nullable=False)
    target_hash = Column(String(128), nullable=False)
    requester_participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"), nullable=False)
    reviewer_participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"), nullable=False)
    required = Column(Boolean, default=True, nullable=False)
    blocking = Column(Boolean, default=True, nullable=False)
    status = Column(String(60), default="requested", nullable=False)
    verdict = Column(String(60))
    due_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('requested', 'assigned', 'completed', 'rejected', 'expired')", name="ck_arceus_reviews_status"),
        Index("ix_arceus_reviews_mission_status", "tenant_id", "mission_id", "status"),
    )


class ArceusReviewFinding(KernelTenantMixin, Base):
    __tablename__ = "arceus_review_findings"

    review_id = Column(UUID(as_uuid=True), ForeignKey("arceus_reviews.id"), nullable=False)
    finding_key = Column(String(160), nullable=False)
    severity = Column(String(60), default="medium", nullable=False)
    statement = Column(Text, nullable=False)
    evidence_ids = Column(JSON, default=list, nullable=False)
    status = Column(String(60), default="open", nullable=False)

    __table_args__ = (
        UniqueConstraint("review_id", "finding_key", name="uq_arceus_review_finding_key"),
        Index("ix_arceus_review_findings_review", "tenant_id", "review_id", "severity"),
    )


class ArceusConflict(KernelTenantMixin, Base):
    __tablename__ = "arceus_conflicts"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    conflict_type = Column(String(100), nullable=False)
    title = Column(Text, nullable=False)
    status = Column(String(60), default="open", nullable=False)
    severity = Column(String(60), default="medium", nullable=False)
    resolution = Column(JSON, default=dict, nullable=False)
    escalated_at = Column(DateTime(timezone=True))
    resolved_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('open', 'escalated', 'resolved', 'cancelled')", name="ck_arceus_conflicts_status"),
        Index("ix_arceus_conflicts_mission_status", "tenant_id", "mission_id", "status"),
    )


class ArceusMemoryItem(KernelTenantMixin, Base):
    __tablename__ = "arceus_memory_items"

    memory_scope = Column(String(80), nullable=False)
    scope_reference_id = Column(UUID(as_uuid=True))
    title = Column(Text, nullable=False)
    content = Column(Text, nullable=False)
    content_type = Column(String(80), default="fact", nullable=False)
    source_type = Column(String(80), nullable=False)
    source_ids = Column(JSON, default=list, nullable=False)
    evidence_ids = Column(JSON, default=list, nullable=False)
    lifecycle_status = Column(String(60), default="proposed", nullable=False)
    trust_level = Column(String(60), default="unverified", nullable=False)
    confidence = Column(Float)
    sensitivity = Column(String(80), default="mission", nullable=False)
    content_hash = Column(String(128), nullable=False)
    valid_from = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    valid_until = Column(DateTime(timezone=True))
    supersedes_memory_id = Column(UUID(as_uuid=True), ForeignKey("arceus_memory_items.id"))

    __table_args__ = (
        CheckConstraint("memory_scope IN ('working', 'task', 'mission', 'project', 'organization', 'global')", name="ck_arceus_memory_items_scope"),
        CheckConstraint(
            "lifecycle_status IN ('proposed', 'verified', 'approved', 'disputed', 'superseded', 'archived')",
            name="ck_arceus_memory_items_lifecycle",
        ),
        UniqueConstraint("tenant_id", "memory_scope", "scope_reference_id", "content_hash", name="uq_arceus_memory_items_hash"),
        Index("ix_arceus_memory_items_scope", "tenant_id", "memory_scope", "scope_reference_id", "lifecycle_status"),
    )


class ArceusLessonProposal(KernelTenantMixin, Base):
    __tablename__ = "arceus_lesson_proposals"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"), nullable=False)
    title = Column(Text, nullable=False)
    lesson = Column(Text, nullable=False)
    evidence_ids = Column(JSON, default=list, nullable=False)
    status = Column(String(60), default="proposed", nullable=False)
    impact = Column(String(60), default="medium", nullable=False)

    __table_args__ = (
        CheckConstraint("status IN ('proposed', 'approved', 'rejected')", name="ck_arceus_lesson_proposals_status"),
        Index("ix_arceus_lesson_proposals_mission", "tenant_id", "mission_id", "status"),
    )


class ArceusPerformanceObservation(KernelTenantMixin, Base):
    __tablename__ = "arceus_performance_observations"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    participant_id = Column(UUID(as_uuid=True), ForeignKey("arceus_participants.id"))
    subject_type = Column(String(80), nullable=False)
    subject_id = Column(UUID(as_uuid=True))
    metric_key = Column(String(120), nullable=False)
    metric_value = Column(Float, nullable=False)
    evidence_ids = Column(JSON, default=list, nullable=False)
    attribution = Column(JSON, default=dict, nullable=False)

    __table_args__ = (
        Index("ix_arceus_performance_observations_subject", "tenant_id", "subject_type", "subject_id", "metric_key"),
    )


class ArceusToolDefinition(KernelMutableMixin, Base):
    __tablename__ = "arceus_tool_definitions"

    tool_key = Column(String(160), nullable=False)
    display_name = Column(Text, nullable=False)
    tool_type = Column(String(100), nullable=False)
    permission_requirements = Column(JSON, default=dict, nullable=False)
    active = Column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("tool_key", name="uq_arceus_tool_definitions_key"),)


class ArceusToolExecution(KernelTenantMixin, Base):
    __tablename__ = "arceus_tool_executions"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    member_id = Column(UUID(as_uuid=True), ForeignKey("arceus_organization_members.id"))
    tool_definition_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tool_definitions.id"), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    action = Column(String(160), nullable=False)
    target = Column(Text)
    status = Column(String(60), nullable=False)
    input_payload = Column(JSON, default=dict, nullable=False)
    output_payload = Column(JSON, default=dict, nullable=False)
    error = Column(JSON, default=dict, nullable=False)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('running', 'succeeded', 'failed', 'cancelled', 'blocked')", name="ck_arceus_tool_executions_status"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_arceus_tool_executions_idempotency"),
        Index("ix_arceus_tool_executions_mission", "tenant_id", "mission_id", "created_at"),
    )


class ArceusPolicyEvaluation(KernelTenantMixin, Base):
    __tablename__ = "arceus_policy_evaluations"

    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    task_id = Column(UUID(as_uuid=True), ForeignKey("arceus_tasks.id"))
    policy_key = Column(String(160), nullable=False)
    subject = Column(JSON, default=dict, nullable=False)
    action = Column(String(160), nullable=False)
    resource = Column(JSON, default=dict, nullable=False)
    decision = Column(String(60), nullable=False)
    reason = Column(Text, nullable=False)

    __table_args__ = (
        CheckConstraint("decision IN ('allow', 'deny', 'needs_approval')", name="ck_arceus_policy_evaluations_decision"),
        Index("ix_arceus_policy_evaluations_mission", "tenant_id", "mission_id", "created_at"),
    )


class ArceusEvent(Base):
    __tablename__ = "arceus_events"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    aggregate_type = Column(String(120), nullable=False)
    aggregate_id = Column(UUID(as_uuid=True), nullable=False)
    aggregate_version = Column(BigInteger, nullable=False)
    event_type = Column(String(160), nullable=False)
    actor_type = Column(String(80), nullable=False)
    actor_id = Column(String(160))
    payload = Column(JSON, default=dict, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("aggregate_type", "aggregate_id", "aggregate_version", name="uq_arceus_events_aggregate_version"),
        Index("ix_arceus_events_aggregate", "aggregate_type", "aggregate_id", "aggregate_version"),
        Index("ix_arceus_events_tenant_time", "tenant_id", "occurred_at"),
    )


class ArceusOutboxMessage(Base):
    __tablename__ = "arceus_outbox_messages"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    event_id = Column(UUID(as_uuid=True), ForeignKey("arceus_events.id"), nullable=False)
    topic = Column(String(160), nullable=False)
    payload = Column(JSON, default=dict, nullable=False)
    status = Column(String(60), default="pending", nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    next_attempt_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    locked_by = Column(String(160))
    locked_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    sent_at = Column(DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint("status IN ('pending', 'processing', 'sent', 'failed', 'dead_letter')", name="ck_arceus_outbox_messages_status"),
        Index("ix_arceus_outbox_messages_pending", "status", "next_attempt_at"),
        Index("ix_arceus_outbox_messages_locked", "locked_by", "locked_at"),
    )


class ArceusInboxMessage(Base):
    __tablename__ = "arceus_inbox_messages"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    source = Column(String(160), nullable=False)
    external_message_id = Column(String(255), nullable=False)
    status = Column(String(60), default="processed", nullable=False)
    payload_hash = Column(String(128), nullable=False)
    processed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "source", "external_message_id", name="uq_arceus_inbox_messages_external"),
    )


class ArceusIdempotencyRecord(Base):
    __tablename__ = "arceus_idempotency_records"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    scope = Column(String(160), nullable=False)
    idempotency_key = Column(String(255), nullable=False)
    request_hash = Column(String(128), nullable=False)
    response_payload = Column(JSON, default=dict, nullable=False)
    status = Column(String(60), default="completed", nullable=False)
    expires_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        UniqueConstraint("tenant_id", "scope", "idempotency_key", name="uq_arceus_idempotency_records_key"),
        Index("ix_arceus_idempotency_records_expiry", "expires_at"),
    )


class ArceusAuditEvent(Base):
    __tablename__ = "arceus_audit_events"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    actor_type = Column(String(80), nullable=False)
    actor_id = Column(String(160))
    action = Column(String(160), nullable=False)
    resource_type = Column(String(120), nullable=False)
    resource_id = Column(String(160))
    result = Column(String(60), nullable=False)
    ip_address = Column(String(80))
    user_agent = Column(Text)
    metadata_json = Column(JSON, default=dict, nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_arceus_audit_events_resource", "tenant_id", "resource_type", "resource_id", "occurred_at"),
        Index("ix_arceus_audit_events_actor", "tenant_id", "actor_type", "actor_id", "occurred_at"),
    )


class ArceusUsageRecord(Base):
    __tablename__ = "arceus_usage_records"

    id = _uuid_pk()
    tenant_id = _tenant_fk()
    user_id = Column(UUID(as_uuid=True), ForeignKey("arceus_users.id"))
    mission_id = Column(UUID(as_uuid=True), ForeignKey("arceus_missions.id"))
    usage_type = Column(String(120), nullable=False)
    quantity = Column(Numeric(14, 4), nullable=False)
    unit = Column(String(80), nullable=False)
    cost_usd = Column(Numeric(12, 6), default=0, nullable=False)
    metadata_json = Column(JSON, default=dict, nullable=False)
    occurred_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        Index("ix_arceus_usage_records_tenant_time", "tenant_id", "occurred_at"),
        Index("ix_arceus_usage_records_mission", "tenant_id", "mission_id", "occurred_at"),
    )
