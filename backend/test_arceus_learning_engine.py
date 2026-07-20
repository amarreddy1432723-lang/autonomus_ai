from uuid import UUID

from services.agent.arceus_runtime.learning.service import (
    discover_patterns,
    evaluate_learning_record,
    evaluate_promotion,
    scorecard_from_metrics,
)
from services.shared.arceus_core_models import ArceusEvidence, ArceusLessonProposal


MISSION_ID = UUID("11111111-1111-1111-1111-111111111111")


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
