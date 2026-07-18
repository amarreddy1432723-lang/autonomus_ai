from services.agent.os_kernel.generation3 import (
    ApprovalQuorumEvaluator,
    ApprovalQuorumPolicy,
    ApprovalVote,
    Handoff,
    Participant,
    PermissionEvaluator,
    PermissionRequest,
    ProjectMembership,
    ResponsibilityChain,
    RoleBinding,
    generation3_manifest,
)


TENANT = "tenant-a"
ORG = "org-a"
PROJECT = "project-a"


def participant(name: str, participant_type: str = "human") -> Participant:
    return Participant(
        tenant_id=TENANT,
        organization_id=ORG,
        display_name=name,
        participant_type=participant_type,  # type: ignore[arg-type]
    )


def binding(who: Participant, role: str, *, environment: str | None = None) -> RoleBinding:
    return RoleBinding(
        participant_id=who.participant_id,
        role_name=role,
        scope="environment" if environment else "project",
        tenant_id=TENANT,
        organization_id=ORG,
        project_id=PROJECT,
        environment=environment,  # type: ignore[arg-type]
    )


def evaluator_with(*items: tuple[Participant, str] | tuple[Participant, str, str]) -> tuple[PermissionEvaluator, dict[str, Participant]]:
    participants = [item[0] for item in items]
    bindings = [
        binding(item[0], item[1], environment=item[2] if len(item) == 3 else None)
        for item in items
    ]
    return PermissionEvaluator(participants, bindings), {p.display_name: p for p in participants}


def request(who: Participant, action: str, *, environment: str = "development", path: str | None = None, risk: str = "low", author: Participant | None = None, requires_human: bool = False) -> PermissionRequest:
    return PermissionRequest(
        tenant_id=TENANT,
        organization_id=ORG,
        project_id=PROJECT,
        participant_id=who.participant_id,
        action=action,  # type: ignore[arg-type]
        resource_type="artifact",
        environment=environment,  # type: ignore[arg-type]
        path=path,
        risk_level=risk,  # type: ignore[arg-type]
        author_participant_id=author.participant_id if author else None,
        requires_human_approval=requires_human,
    )


def test_generation3_participants_unify_humans_and_ai_without_identity_confusion():
    human = participant("Human Backend Engineer")
    ai = participant("AI Authentication Specialist", "ai_agent")

    assert human.participant_type == "human"
    assert ai.participant_type == "ai_agent"
    assert human.is_human is True
    assert ai.is_human is False
    assert human.to_dict()["participant_type"] != ai.to_dict()["participant_type"]


def test_product_owner_can_create_missions_and_approve_scope_but_cannot_deploy_production():
    evaluator, people = evaluator_with((participant("Product Owner"), "Product Owner"))
    owner = people["Product Owner"]

    assert evaluator.evaluate(request(owner, "PROPOSE")).allowed is True
    assert evaluator.evaluate(request(owner, "APPROVE", risk="medium")).allowed is True

    deploy = evaluator.evaluate(request(owner, "DEPLOY", environment="production"))

    assert deploy.allowed is False
    assert "missing_authority" in deploy.reason_codes


def test_technical_lead_can_approve_architecture_and_staging_but_not_own_critical_work_alone():
    lead = participant("Technical Lead")
    evaluator = PermissionEvaluator(
        [lead],
        [
            binding(lead, "Technical Lead"),
            binding(lead, "Technical Lead", environment="staging"),
        ],
    )

    assert evaluator.evaluate(request(lead, "APPROVE", risk="medium")).allowed is True
    assert evaluator.evaluate(request(lead, "DEPLOY", environment="staging")).allowed is True

    self_approval = evaluator.evaluate(request(lead, "APPROVE", risk="critical", author=lead))

    assert self_approval.decision == "require_approval"
    assert "author_cannot_solely_approve_high_risk_work" in self_approval.reason_codes


def test_human_backend_engineer_can_modify_backend_paths_and_run_dev_tools_but_not_self_approve():
    evaluator, people = evaluator_with((participant("Human Backend Engineer"), "Human Backend Engineer"))
    engineer = people["Human Backend Engineer"]

    allowed = evaluator.evaluate(request(engineer, "MODIFY", path="backend/services/auth/main.py"))
    forbidden_path = evaluator.evaluate(request(engineer, "MODIFY", path="frontend/src/app/page.tsx"))
    approval = evaluator.evaluate(request(engineer, "APPROVE", risk="high", author=engineer))

    assert allowed.allowed is True
    assert forbidden_path.allowed is False
    assert "path_not_authorized" in forbidden_path.reason_codes
    assert approval.allowed is False
    assert "missing_authority" in approval.reason_codes


def test_ai_auth_specialist_is_scoped_and_cannot_access_production_secrets_or_human_approval():
    evaluator, people = evaluator_with((participant("AI Authentication Specialist", "ai_agent"), "AI Authentication Specialist"))
    ai = people["AI Authentication Specialist"]

    scoped_modify = evaluator.evaluate(request(ai, "MODIFY", path="backend/services/auth/session.py"))
    bad_path = evaluator.evaluate(request(ai, "MODIFY", path="backend/services/billing.py"))
    secret = evaluator.evaluate(request(ai, "ACCESS_SECRET", environment="production"))
    approval = evaluator.evaluate(request(ai, "APPROVE", requires_human=True))

    assert scoped_modify.allowed is True
    assert bad_path.allowed is False
    assert "path_not_authorized" in bad_path.reason_codes
    assert secret.allowed is False
    assert "missing_authority" in secret.reason_codes or "ai_participant_cannot_perform_human_authority_action" in secret.reason_codes
    assert approval.allowed is False
    assert "ai_participant_cannot_perform_human_authority_action" in approval.reason_codes or "missing_authority" in approval.reason_codes


def test_security_reviewer_can_review_and_veto_but_path_policy_blocks_direct_modification():
    evaluator, people = evaluator_with((participant("Security Reviewer"), "Security Reviewer"))
    reviewer = people["Security Reviewer"]

    review = evaluator.evaluate(request(reviewer, "REVIEW", risk="high"))
    modify = evaluator.evaluate(request(reviewer, "MODIFY", path="backend/services/auth/main.py"))

    assert review.allowed is True
    assert modify.allowed is False
    assert "missing_authority" in modify.reason_codes


def test_production_operator_can_deploy_only_after_security_review_requirement_is_satisfied():
    evaluator, people = evaluator_with((participant("Production Operator"), "Production Operator", "production"))
    operator = people["Production Operator"]

    deploy = evaluator.evaluate(request(operator, "DEPLOY", environment="production"))

    assert deploy.decision == "require_approval"
    assert "production_deploy_requires_security_review" in deploy.reason_codes
    assert deploy.required_approvers == ["Security Reviewer"]


def test_ai_vote_never_counts_as_required_human_approval():
    policy = ApprovalQuorumPolicy(
        name="staging-auth-release",
        required_roles=["Technical Lead", "Security Reviewer"],
        minimum_human_approvals=2,
        minimum_total_approvals=2,
        veto_roles=["Security Reviewer"],
    )
    lead = participant("Technical Lead")
    ai_security = participant("AI Security Reviewer", "ai_agent")
    votes = [
        ApprovalVote(lead.participant_id, "human", "Technical Lead", "approve"),
        ApprovalVote(ai_security.participant_id, "ai_agent", "Security Reviewer", "approve"),
    ]

    decision = ApprovalQuorumEvaluator().evaluate(policy, votes)

    assert decision.decision == "require_approval"
    assert "human_approval_count_not_met" in decision.reason_codes


def test_bidirectional_handoff_requires_receiver_acknowledgement():
    human = participant("Human Backend Engineer")
    ai = participant("AI Authentication Specialist", "ai_agent")
    handoff = Handoff(
        from_participant_id=ai.participant_id,
        to_participant_id=human.participant_id,
        task_id="task-auth-1",
        reason="Domain decision is required before changing session policy.",
        completed_work=["Analyzed existing auth routes"],
        current_state="Implementation blocked on product rule",
        open_questions=["Should expired sessions be revoked immediately?"],
        required_action="Choose session revocation behavior",
    )

    assert handoff.acknowledged is False
    handoff.acknowledge(human.participant_id)
    assert handoff.acknowledged is True


def test_project_membership_supports_distinct_repository_environment_and_secret_access():
    member = ProjectMembership(
        tenant_id=TENANT,
        project_id=PROJECT,
        participant_id="participant-backend",
        roles=["Human Backend Engineer"],
        repository_access=["repo-api"],
        environment_access=["development"],
        secret_access=[],
        approval_authority=[],
    )

    assert member.environment_access == ["development"]
    assert "production" not in member.environment_access
    assert member.secret_access == []


def test_responsibility_chain_exposes_author_review_approval_policy_model_tool_and_evidence():
    chain = ResponsibilityChain(
        artifact_id="artifact-auth-change",
        tenant_id=TENANT,
        project_id=PROJECT,
        proposed_by="product-owner",
        authored_by="ai-auth-specialist",
        reviewers=["security-reviewer"],
        verifiers=["qa-reviewer"],
        approvers=["technical-lead"],
        model_ids=["gpt-5-codex"],
        tool_ids=["scoped_file_writer"],
        policy_decisions=[{"decision": "allow", "reason_codes": ["role_and_policy_allowed"]}],
        evidence_ids=["test-auth-1"],
        mission_id="mission-auth",
        task_id="task-auth-1",
        environment="staging",
    )

    payload = chain.to_dict()

    assert payload["authored_by"] == "ai-auth-specialist"
    assert payload["reviewers"] == ["security-reviewer"]
    assert payload["approvers"] == ["technical-lead"]
    assert payload["policy_decisions"][0]["decision"] == "allow"


def test_generation3_manifest_exposes_human_ai_collaboration_scope():
    manifest = generation3_manifest()

    assert "participants" in manifest["core_modules"]
    assert "approval_quorums" in manifest["core_modules"]
    assert "Three-person human team" in manifest["vertical_slice"]
