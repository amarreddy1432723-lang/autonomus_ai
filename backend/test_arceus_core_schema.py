from services.shared.models import Base


EXPECTED_ARCEUS_TABLES = {
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
    "arceus_participants",
    "arceus_collaboration_messages",
    "arceus_collaboration_message_recipients",
    "arceus_collaboration_message_topics",
    "arceus_participant_inbox_items",
    "arceus_stream_summaries",
    "arceus_reviews",
    "arceus_review_findings",
    "arceus_conflicts",
    "arceus_memory_items",
    "arceus_lesson_proposals",
    "arceus_performance_observations",
    "arceus_tool_definitions",
    "arceus_tool_executions",
    "arceus_policy_evaluations",
    "arceus_events",
    "arceus_outbox_messages",
    "arceus_inbox_messages",
    "arceus_idempotency_records",
    "arceus_audit_events",
    "arceus_usage_records",
}


GLOBAL_TABLES = {
    "arceus_tenants",
    "arceus_users",
    "arceus_capabilities",
    "arceus_specialist_profiles",
    "arceus_specialist_capabilities",
    "arceus_tool_definitions",
}


def _constraint_names(table_name: str) -> set[str]:
    return {constraint.name for constraint in Base.metadata.tables[table_name].constraints if constraint.name}


def test_arceus_core_tables_registered_in_shared_metadata() -> None:
    missing = EXPECTED_ARCEUS_TABLES.difference(Base.metadata.tables)
    assert missing == set()


def test_tenant_owned_tables_have_tenant_id() -> None:
    for table_name in EXPECTED_ARCEUS_TABLES - GLOBAL_TABLES:
        assert "tenant_id" in Base.metadata.tables[table_name].columns, table_name


def test_mission_state_and_recovery_columns_exist() -> None:
    mission = Base.metadata.tables["arceus_missions"]
    for column in [
        "status",
        "risk_level",
        "maximum_budget_amount",
        "actual_cost_amount",
        "budget_currency",
        "current_version_id",
        "active_workflow_id",
        "paused_at",
        "completed_at",
        "failed_at",
        "failure_reason",
        "version_number",
    ]:
        assert column in mission.columns


def test_mission_versions_are_unique_and_content_addressed() -> None:
    constraints = _constraint_names("arceus_mission_versions")
    assert "uq_arceus_mission_versions_version" in constraints
    assert "uq_arceus_mission_versions_source_hash" in constraints


def test_compiler_runs_track_stage_results_and_outputs() -> None:
    compiler_runs = Base.metadata.tables["arceus_compiler_runs"]
    for column in [
        "mission_id",
        "source_mission_version",
        "status",
        "current_stage",
        "stage_results",
        "compiled_mission_version_id",
        "warning_codes",
        "error_code",
        "started_at",
        "completed_at",
    ]:
        assert column in compiler_runs.columns


def test_replay_and_retry_safety_constraints_exist() -> None:
    assert "uq_arceus_events_aggregate_version" in _constraint_names("arceus_events")
    assert "uq_arceus_idempotency_records_key" in _constraint_names("arceus_idempotency_records")
    assert "uq_arceus_tool_executions_idempotency" in _constraint_names("arceus_tool_executions")
    assert "uq_arceus_task_attempt_idempotency" in _constraint_names("arceus_task_attempts")


def test_outbox_schema_supports_claim_retry_and_dead_letter() -> None:
    outbox = Base.metadata.tables["arceus_outbox_messages"]
    for column in ["status", "attempts", "next_attempt_at", "locked_by", "locked_at", "last_error", "sent_at"]:
        assert column in outbox.columns


def test_runtime_execution_schema_supports_leases_and_checkpoints() -> None:
    leases = Base.metadata.tables["arceus_worker_leases"]
    checkpoints = Base.metadata.tables["arceus_runtime_checkpoints"]

    assert "heartbeat_at" in leases.columns
    for column in [
        "mission_id",
        "task_id",
        "workflow_id",
        "worker_lease_id",
        "checkpoint_key",
        "workflow_version",
        "execution_state",
        "artifacts",
        "model_calls",
        "tool_calls",
        "outputs",
        "progress_percent",
        "created_by_worker_id",
    ]:
        assert column in checkpoints.columns


def test_approval_votes_distinguish_human_authority() -> None:
    approval_votes = Base.metadata.tables["arceus_approval_votes"]
    assert "is_human_vote" in approval_votes.columns
    assert "voter_user_id" in approval_votes.columns
    assert "voter_member_id" in approval_votes.columns
