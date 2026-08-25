from uuid import UUID

from services.agent.arceus_runtime.learning.service import (
    build_agent_skill_matrix,
    build_organization_brain,
    discover_patterns,
    evaluate_learning_record,
    evaluate_promotion,
    model_performance_matrix,
    rank_agents_for_capabilities,
    scorecard_from_metrics,
    synthesize_mission_reflection,
)
from services.shared.arceus_core_models import ArceusEvidence, ArceusLessonProposal, ArceusMission, ArceusParticipant, ArceusPerformanceObservation


MISSION_ID = UUID("11111111-1111-1111-1111-111111111111")
PROJECT_ID = UUID("99999999-9999-9999-9999-999999999999")


def _evidence(evidence_id: str, *, status: str = "verified", trust_level: str = "tool_verified"):
    return ArceusEvidence(
        id=UUID(evidence_id),
        tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
        mission_id=MISSION_ID,
        evidence_type="test_run",
        status=status,
        summary="Verification passed.",
        payload={"passed": True},
        verification_method="pytest",
        content_hash=evidence_id.replace("-", ""),
        trust_level=trust_level,
    )


def _lesson(*, status: str = "proposed", evidence_ids: list[str] | None = None):
    return ArceusLessonProposal(
        id=UUID("22222222-2222-2222-2222-222222222222"),
        tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
        mission_id=MISSION_ID,
        title="Always run verification before completion",
        lesson="Require deterministic test evidence before marking implementation work complete.",
        evidence_ids=evidence_ids or [],
        status=status,
        impact="high",
    )


def _mission(mission_id: UUID = MISSION_ID, *, status: str = "completed"):
    return ArceusMission(
        id=mission_id,
        tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
        project_id=PROJECT_ID,
        created_by=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        title="Implement OAuth",
        objective="Add OAuth login with tests and review.",
        status=status,
        risk_level="medium",
        priority=3,
    )


def test_learning_record_requires_verified_evidence():
    no_evidence = evaluate_learning_record(evidence=[], evidence_ids=[])
    assert no_evidence["promotion_ready"] is False
    assert no_evidence["status"] == "blocked_no_evidence"

    untrusted_id = UUID("33333333-3333-3333-3333-333333333333")
    untrusted = evaluate_learning_record(
        evidence=[_evidence(str(untrusted_id), status="collected", trust_level="unverified")],
        evidence_ids=[untrusted_id],
    )
    assert untrusted["promotion_ready"] is False
    assert untrusted["status"] == "blocked_unverified_evidence"

    trusted = evaluate_learning_record(evidence=[_evidence(str(untrusted_id))], evidence_ids=[untrusted_id])
    assert trusted["promotion_ready"] is True
    assert trusted["status"] == "proposed"


def test_pattern_discovery_groups_lessons_and_requires_review():
    lessons = [
        _lesson(status="approved", evidence_ids=["33333333-3333-3333-3333-333333333333"]),
        ArceusLessonProposal(
            id=UUID("44444444-4444-4444-4444-444444444444"),
            tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
            mission_id=MISSION_ID,
            title="Verification gates protect releases",
            lesson="Build and test evidence should block completion on failure.",
            evidence_ids=["55555555-5555-5555-5555-555555555555"],
            status="proposed",
            impact="medium",
        ),
    ]

    patterns = discover_patterns(lessons)

    assert patterns[0]["pattern_key"] == "quality.verification"
    assert patterns[0]["support_count"] == 2
    assert patterns[0]["status"] == "review_required"


def test_scorecard_turns_operational_metrics_into_assignment_signal():
    scorecard = scorecard_from_metrics(
        subject_type="specialist",
        subject_id=UUID("66666666-6666-6666-6666-666666666666"),
        metrics={"quality": 0.92, "speed": 0.74, "cost_efficiency": 0.61},
    )

    assert scorecard["status"] == "stable"
    assert scorecard["score"] == 75.67
    assert "quality" in scorecard["strengths"]
    assert "cost_efficiency" in scorecard["improvement_areas"]


def test_promotion_is_thresholded_reversible_and_governed():
    lesson = _lesson(status="proposed", evidence_ids=["33333333-3333-3333-3333-333333333333"])
    one_evidence = [_evidence("33333333-3333-3333-3333-333333333333")]

    mission_promotion = evaluate_promotion(lesson=lesson, evidence=one_evidence, target_scope="mission", dry_run=False)
    assert mission_promotion["accepted"] is True
    assert mission_promotion["reversible"] is True

    org_promotion = evaluate_promotion(lesson=lesson, evidence=one_evidence, target_scope="organization", dry_run=True)
    assert org_promotion["accepted"] is False
    assert org_promotion["status"] == "blocked"
    assert "organization_owner" in org_promotion["required_approvals"]


def test_collective_intelligence_reflection_separates_verified_lessons_from_hints():
    evidence_id = UUID("33333333-3333-3333-3333-333333333333")
    lesson = _lesson(status="proposed", evidence_ids=[str(evidence_id)])
    observations = [
        ArceusPerformanceObservation(
            tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
            mission_id=MISSION_ID,
            subject_type="mission",
            subject_id=MISSION_ID,
            metric_key="planning_accuracy",
            metric_value=0.93,
        ),
        ArceusPerformanceObservation(
            tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
            mission_id=MISSION_ID,
            subject_type="mission",
            subject_id=MISSION_ID,
            metric_key="execution_retry_rate",
            metric_value=0.48,
        ),
    ]

    reflection = synthesize_mission_reflection(
        mission_id=MISSION_ID,
        lessons=[lesson],
        evidence=[_evidence(str(evidence_id))],
        observations=observations,
    )

    assert reflection["reflection_status"] == "ready_for_review"
    assert "planning_accuracy" in reflection["what_worked"]
    assert "execution_retry_rate" in reflection["what_failed"]
    assert reflection["organization_memory_updates"][0]["requires_review"] is True
    assert reflection["future_context"][2] == "Do not let unverified lessons become organization standards."


def _participant(participant_id: str, name: str, capabilities: list[dict], *, status: str = "available"):
    return ArceusParticipant(
        id=UUID(participant_id),
        tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
        participant_type="ai_specialist",
        display_name=name,
        role_key=name.lower().replace(" ", "_"),
        capabilities=capabilities,
        status=status,
    )


def test_skill_matrix_and_dynamic_selection_use_learned_agent_strengths():
    frontend = _participant(
        "77777777-7777-7777-7777-777777777777",
        "Frontend Engineer",
        [{"capability_key": "react_development", "confidence": 0.76}],
    )
    backend = _participant(
        "88888888-8888-8888-8888-888888888888",
        "Backend Engineer",
        [{"capability_key": "fastapi_development", "confidence": 0.88}],
    )
    observations = [
        ArceusPerformanceObservation(
            tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
            participant_id=frontend.id,
            subject_type="agent",
            subject_id=frontend.id,
            metric_key="skill.react_development",
            metric_value=0.94,
        ),
        ArceusPerformanceObservation(
            tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
            participant_id=backend.id,
            subject_type="agent",
            subject_id=backend.id,
            metric_key="skill.react_development",
            metric_value=0.42,
        ),
    ]

    matrix = build_agent_skill_matrix(participants=[backend, frontend], observations=observations)
    selected = rank_agents_for_capabilities(required_capabilities=["react_development"], skill_matrix=matrix)

    assert matrix[0]["name"] == "Frontend Engineer"
    assert "react_development" in matrix[0]["strengths"]
    assert selected[0]["agent_id"] == frontend.id
    assert selected[0]["matched_capabilities"] == ["react_development"]


def test_model_performance_matrix_produces_routing_hints_from_history():
    observations = [
        ArceusPerformanceObservation(
            tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
            subject_type="model",
            subject_id=None,
            metric_key="model.quality",
            metric_value=0.96,
            evidence_ids=["33333333-3333-3333-3333-333333333333"],
            attribution={"model_key": "gpt-best", "task_type": "code_review"},
        ),
        ArceusPerformanceObservation(
            tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
            subject_type="model",
            subject_id=None,
            metric_key="model.reliability",
            metric_value=0.94,
            evidence_ids=["33333333-3333-3333-3333-333333333333"],
            attribution={"model_key": "gpt-best", "task_type": "code_review"},
        ),
        ArceusPerformanceObservation(
            tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
            subject_type="model",
            subject_id=None,
            metric_key="model.quality",
            metric_value=0.62,
            attribution={"model_key": "cheap-local", "task_type": "code_review"},
        ),
    ]

    matrix = model_performance_matrix(observations)

    assert matrix[0]["task_type"] == "code_review"
    assert matrix[0]["model_key"] == "gpt-best"
    assert matrix[0]["routing_hint"] == "preferred"
    assert matrix[0]["evidence_count"] == 1


def test_organization_brain_promotes_validated_knowledge_and_guides_scheduling():
    lessons: list[ArceusLessonProposal] = []
    evidence: list[ArceusEvidence] = []
    for index in range(26):
        evidence_id = UUID(f"33333333-3333-3333-3333-{index + 1:012d}")
        lesson = ArceusLessonProposal(
            id=UUID(f"44444444-4444-4444-4444-{index + 1:012d}"),
            tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
            mission_id=MISSION_ID,
            title="Authentication verification gates protect releases",
            lesson="Authentication changes should include deterministic integration verification before completion.",
            evidence_ids=[str(evidence_id)],
            status="approved",
            impact="high",
        )
        lessons.append(lesson)
        evidence.append(_evidence(str(evidence_id)))

    security = _participant(
        "77777777-7777-7777-7777-777777777777",
        "Security Reviewer",
        [{"capability_key": "authentication_review", "confidence": 0.91}],
    )
    observations = [
        ArceusPerformanceObservation(
            tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
            mission_id=MISSION_ID,
            participant_id=security.id,
            subject_type="agent",
            subject_id=security.id,
            metric_key="skill.authentication_review",
            metric_value=0.96,
        ),
        ArceusPerformanceObservation(
            tenant_id=UUID("00000000-0000-0000-0000-000000000000"),
            mission_id=MISSION_ID,
            subject_type="mission",
            subject_id=MISSION_ID,
            metric_key="execution_retry_rate",
            metric_value=0.45,
        ),
    ]

    brain = build_organization_brain(
        missions=[_mission()],
        lessons=lessons,
        evidence=evidence,
        observations=observations,
        participants=[security],
        project_id=PROJECT_ID,
    )

    assert brain["brain_status"] == "learning"
    assert brain["knowledge_candidates"][0]["validation_level"] == "validated"
    assert brain["knowledge_candidates"][0]["trusted_evidence_count"] == 26
    assert brain["engineering_standards"][0]["status"] == "validated"
    assert brain["repository_memory"]["previous_missions"] == 1
    assert brain["repository_memory"]["known_risks"] == ["quality"]
    assert brain["dynamic_scheduling"]["top_agents"][0]["name"] == "Security Reviewer"
    assert brain["cross_agent_review"]["rule"] == "Knowledge cannot become permanent until evidence and independent review agree."
    assert brain["ceo_agent"]["recommendations"][0]["type"] == "bottleneck"
