import uuid

from services.agent.arceus_runtime.verification.service import (
    build_completion_certificate,
    calculate_trust_score,
    evaluate_completion,
    evaluate_tool_evidence_requirement,
    evaluate_tool_evidence_requirements,
    evidence_content_hash,
    gate_passes_with_evidence,
)
from services.shared.arceus_core_models import (
    ArceusApproval,
    ArceusEvidence,
    ArceusMission,
    ArceusMissionSuccessCriterion,
    ArceusQualityGate,
    ArceusReview,
)


def _mission(risk_level: str = "medium") -> ArceusMission:
    return ArceusMission(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        project_id=uuid.uuid4(),
        created_by=uuid.uuid4(),
        title="Implement Google Login",
        objective="Add Google OAuth sign-in with protected session handling.",
        status="verifying",
        risk_level=risk_level,
        version_number=3,
    )


def _criterion(mission: ArceusMission, method: str = "backend_tests") -> ArceusMissionSuccessCriterion:
    return ArceusMissionSuccessCriterion(
        id=uuid.uuid4(),
        tenant_id=mission.tenant_id,
        mission_id=mission.id,
        criterion_key="auth.backend",
        statement="Protected endpoints accept the issued session.",
        verification_method=method,
        required=True,
    )


def _evidence(mission: ArceusMission, evidence_type: str = "backend_tests", trust_level: str = "tool_verified") -> ArceusEvidence:
    payload = {"status": "passed", "criteria_keys": ["auth.backend"]}
    return ArceusEvidence(
        id=uuid.uuid4(),
        tenant_id=mission.tenant_id,
        mission_id=mission.id,
        evidence_type=evidence_type,
        status="validated",
        summary="Backend auth tests passed.",
        payload=payload,
        verification_method=evidence_type,
        content_hash=evidence_content_hash(
            mission_id=mission.id,
            evidence_type=evidence_type,
            summary="Backend auth tests passed.",
            payload=payload,
        ),
        trust_level=trust_level,
        immutable=True,
    )


def _tool_evidence(mission: ArceusMission, evidence_type: str, payload: dict) -> ArceusEvidence:
    return ArceusEvidence(
        id=uuid.uuid4(),
        tenant_id=mission.tenant_id,
        mission_id=mission.id,
        evidence_type=evidence_type,
        status="validated",
        summary=f"Tool evidence collected: {evidence_type}.",
        payload=payload,
        verification_method=evidence_type.replace("tool_", "gateway_tool:", 1).replace("_", "."),
        content_hash=evidence_content_hash(
            mission_id=mission.id,
            evidence_type=evidence_type,
            summary=f"Tool evidence collected: {evidence_type}.",
            payload=payload,
        ),
        trust_level="tool_verified",
        immutable=True,
    )


def _gate(mission: ArceusMission, status: str = "passed") -> ArceusQualityGate:
    return ArceusQualityGate(
        id=uuid.uuid4(),
        tenant_id=mission.tenant_id,
        mission_id=mission.id,
        gate_key="backend_tests",
        name="Backend Tests",
        category="functional",
        gate_type="mandatory",
        required=True,
        verifier="backend_tests",
        timeout_seconds=300,
        status=status,
        result={"required_evidence_type": "backend_tests"},
        evidence_ids=[],
    )


def test_missing_evidence_blocks_completion() -> None:
    mission = _mission()
    evaluation = evaluate_completion(
        mission=mission,
        criteria=[_criterion(mission)],
        evidence=[],
        gates=[_gate(mission)],
        reviews=[],
        approvals=[],
    )

    assert evaluation.status == "blocked"
    assert evaluation.blockers[0]["type"] == "missing_evidence"


def test_failed_quality_gate_blocks_completion_even_with_evidence() -> None:
    mission = _mission()
    evaluation = evaluate_completion(
        mission=mission,
        criteria=[_criterion(mission)],
        evidence=[_evidence(mission)],
        gates=[_gate(mission, status="failed")],
        reviews=[],
        approvals=[],
    )

    assert evaluation.status == "blocked"
    assert any(blocker["type"] == "quality_gate" for blocker in evaluation.blockers)


def test_gate_passes_only_with_matching_validated_evidence() -> None:
    mission = _mission()
    passed, result = gate_passes_with_evidence(_gate(mission, status="pending"), [_evidence(mission)])

    assert passed is True
    assert result["reason"] == "matching_trusted_evidence"


def test_tool_evidence_requirement_accepts_pull_request_artifact() -> None:
    mission = _mission()
    evidence = _tool_evidence(
        mission,
        "tool_github_open_pull_request",
        {"pull_request_url": "https://github.com/acme/platform/pull/42", "pull_request_number": 42},
    )

    passed, result = evaluate_tool_evidence_requirement(
        {"tool_key": "github", "action_key": "open_pull_request"},
        [evidence],
    )

    assert passed is True
    assert result["reason"] == "matching_tool_evidence"
    assert result["matched_evidence_ids"] == [str(evidence.id)]


def test_tool_evidence_requirement_blocks_failed_github_checks() -> None:
    mission = _mission()
    evidence = _tool_evidence(
        mission,
        "tool_github_check_runs",
        {"total": 3, "passed": 2, "failed": 1, "running": 0},
    )

    passed, result = evaluate_tool_evidence_requirement(
        {"tool_key": "github", "action_key": "check_runs", "require_passing_checks": True},
        [evidence],
    )

    assert passed is False
    assert result["reason"] == "github_checks_failed"
    assert result["failed"] == 1


def test_tool_evidence_requirement_blocks_running_github_checks() -> None:
    mission = _mission()
    evidence = _tool_evidence(
        mission,
        "tool_github_check_runs",
        {"total": 3, "passed": 2, "failed": 0, "running": 1},
    )

    passed, result = evaluate_tool_evidence_requirement("tool_github_check_runs", [evidence])

    assert passed is False
    assert result["reason"] == "github_checks_running"
    assert result["running"] == 1


def test_tool_evidence_requirements_pass_with_pr_and_green_checks() -> None:
    mission = _mission()
    pr_evidence = _tool_evidence(
        mission,
        "tool_github_open_pull_request",
        {"pull_request_url": "https://github.com/acme/platform/pull/42", "pull_request_number": 42},
    )
    check_evidence = _tool_evidence(
        mission,
        "tool_github_check_runs",
        {"total": 3, "passed": 3, "failed": 0, "running": 0},
    )

    passed, result = evaluate_tool_evidence_requirements(
        [
            {"tool_key": "github", "action_key": "open_pull_request"},
            {"tool_key": "github", "action_key": "check_runs", "require_passing_checks": True},
        ],
        [pr_evidence, check_evidence],
    )

    assert passed is True
    assert result["reason"] == "tool_evidence_requirements_met"
    assert sorted(result["matched_evidence_ids"]) == sorted([str(pr_evidence.id), str(check_evidence.id)])


def test_tool_evidence_quality_gate_blocks_missing_pull_request() -> None:
    mission = _mission()
    gate = ArceusQualityGate(
        id=uuid.uuid4(),
        tenant_id=mission.tenant_id,
        mission_id=mission.id,
        gate_key="github_release",
        name="GitHub Release Evidence",
        category="release",
        gate_type="mandatory",
        required=True,
        verifier="gateway_tool",
        timeout_seconds=300,
        status="pending",
        result={
            "required_tool_evidence": [
                {"tool_key": "github", "action_key": "open_pull_request"},
                {"tool_key": "github", "action_key": "check_runs", "require_passing_checks": True},
            ]
        },
        evidence_ids=[],
    )
    checks = _tool_evidence(mission, "tool_github_check_runs", {"total": 2, "passed": 2, "failed": 0, "running": 0})

    passed, result = gate_passes_with_evidence(gate, [checks])

    assert passed is False
    assert result["reason"] == "tool_evidence_requirements_blocked"
    assert result["requirements"][0]["reason"] == "missing_tool_evidence"


def test_trust_score_is_derived_from_evidence_gates_reviews_and_human_approval() -> None:
    mission = _mission(risk_level="high")
    review = ArceusReview(
        id=uuid.uuid4(),
        tenant_id=mission.tenant_id,
        mission_id=mission.id,
        review_type="security",
        target_type="mission",
        target_id=mission.id,
        target_hash="sha256:target",
        requester_participant_id=uuid.uuid4(),
        reviewer_participant_id=uuid.uuid4(),
        required=True,
        blocking=True,
        status="completed",
        verdict="approved",
    )
    approval = ArceusApproval(
        id=uuid.uuid4(),
        tenant_id=mission.tenant_id,
        mission_id=mission.id,
        approval_type="completion",
        subject_type="mission",
        subject_hash="sha256:mission",
        status="approved",
        quorum_policy={"requires_human": True, "required_human_votes": 1},
    )

    score = calculate_trust_score(
        mission_id=mission.id,
        evidence=[_evidence(mission)],
        gates=[_gate(mission)],
        reviews=[review],
        approvals=[approval],
    )

    assert score.trust_level == 4
    assert score.score == 95.0
    assert score.contributors["human_approvals"] == 1


def test_completion_certificate_is_blocked_or_signed_from_evaluation() -> None:
    mission = _mission()
    evidence = _evidence(mission)
    gate = _gate(mission)
    trust_score = calculate_trust_score(mission_id=mission.id, evidence=[evidence], gates=[gate], reviews=[], approvals=[])
    trust_score.id = uuid.uuid4()
    evaluation = evaluate_completion(
        mission=mission,
        criteria=[_criterion(mission)],
        evidence=[evidence],
        gates=[gate],
        reviews=[],
        approvals=[],
    )

    certificate = build_completion_certificate(
        tenant_id=mission.tenant_id,
        mission=mission,
        evaluation=evaluation,
        trust_score=trust_score,
    )

    assert certificate.status == "certified"
    assert certificate.signed_at is not None
    assert certificate.certificate_hash.startswith("sha256:")
    assert certificate.signature.startswith("sha256:")
