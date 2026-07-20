from __future__ import annotations

from collections import defaultdict
from typing import Any
from uuid import UUID

from services.shared.arceus_core_models import ArceusEvidence, ArceusLessonProposal, ArceusPerformanceObservation


TRUSTED_EVIDENCE_STATUSES = {"validated", "trusted", "verified"}
TRUSTED_EVIDENCE_LEVELS = {"tool_verified", "independent_review", "human_approved", "production_observed"}
PROMOTION_THRESHOLDS = {
    "mission": 1,
    "project": 2,
    "organization": 3,
    "global": 5,
}


def trusted_evidence(evidence: list[ArceusEvidence]) -> list[ArceusEvidence]:
    return [
        item
        for item in evidence
        if item.status in TRUSTED_EVIDENCE_STATUSES or item.trust_level in TRUSTED_EVIDENCE_LEVELS
    ]


def evaluate_learning_record(*, evidence: list[ArceusEvidence], evidence_ids: list[UUID]) -> dict[str, Any]:
    trusted = trusted_evidence(evidence)
    missing_count = max(0, len(evidence_ids) - len(evidence))
    if missing_count:
        return {
            "status": "blocked_missing_evidence",
            "promotion_ready": False,
            "trusted_evidence_count": len(trusted),
            "reason": "Learning record references evidence that does not exist in this tenant or mission.",
        }
    if not evidence_ids:
        return {
            "status": "blocked_no_evidence",
            "promotion_ready": False,
            "trusted_evidence_count": 0,
            "reason": "Learning records require verified evidence before they can influence future work.",
        }
    if not trusted:
        return {
            "status": "blocked_unverified_evidence",
            "promotion_ready": False,
            "trusted_evidence_count": 0,
            "reason": "Evidence exists but is not trusted, validated, verified, or independently reviewed.",
        }
    return {
        "status": "proposed",
        "promotion_ready": True,
        "trusted_evidence_count": len(trusted),
        "reason": "Verified evidence is present; learning can enter governed review.",
    }


def pattern_key_for_lesson(lesson: ArceusLessonProposal) -> str:
    text = f"{lesson.title} {lesson.lesson}".lower()
    if any(word in text for word in ["test", "verification", "qa", "build"]):
        return "quality.verification"
    if any(word in text for word in ["security", "auth", "permission", "secret"]):
        return "security.governance"
    if any(word in text for word in ["plan", "scope", "requirement", "roadmap"]):
        return "planning.scope_control"
    if any(word in text for word in ["latency", "performance", "cache", "cost"]):
        return "operations.optimization"
    return "engineering.practice"


def discover_patterns(lessons: list[ArceusLessonProposal]) -> list[dict[str, Any]]:
    grouped: dict[str, list[ArceusLessonProposal]] = defaultdict(list)
    for lesson in lessons:
        grouped[pattern_key_for_lesson(lesson)].append(lesson)

    rows: list[dict[str, Any]] = []
    for key, items in grouped.items():
        support_count = len(items)
        evidence_ids = []
        approved_count = 0
        for item in items:
            evidence_ids.extend([UUID(str(evidence_id)) for evidence_id in item.evidence_ids])
            if item.status == "approved":
                approved_count += 1
        confidence = min(0.98, 0.35 + support_count * 0.15 + approved_count * 0.15)
        promotion_level = "candidate"
        if support_count >= PROMOTION_THRESHOLDS["organization"] and approved_count:
            promotion_level = "organization_candidate"
        elif support_count >= PROMOTION_THRESHOLDS["project"]:
            promotion_level = "project_candidate"
        rows.append(
            {
                "pattern_key": key,
                "title": key.replace(".", " ").title(),
                "category": key.split(".", 1)[0],
                "confidence": round(confidence, 3),
                "support_count": support_count,
                "promotion_level": promotion_level,
                "evidence_ids": sorted(set(evidence_ids), key=str),
                "status": "review_required" if confidence >= 0.65 else "collecting_evidence",
            }
        )
    return sorted(rows, key=lambda item: (-item["confidence"], item["pattern_key"]))


def scorecard_from_observations(*, subject_type: str, subject_id: UUID | None, observations: list[ArceusPerformanceObservation]) -> dict[str, Any]:
    metrics: dict[str, list[float]] = defaultdict(list)
    for observation in observations:
        if observation.subject_type == subject_type and (subject_id is None or observation.subject_id == subject_id):
            metrics[observation.metric_key].append(float(observation.metric_value))
    averaged = {key: round(sum(values) / len(values), 4) for key, values in metrics.items() if values}
    return scorecard_from_metrics(subject_type=subject_type, subject_id=subject_id, metrics=averaged)


def scorecard_from_metrics(*, subject_type: str, subject_id: UUID | None, metrics: dict[str, float]) -> dict[str, Any]:
    normalized: dict[str, float] = {}
    for key, value in metrics.items():
        normalized[key] = max(0.0, min(1.0, float(value)))
    score = round((sum(normalized.values()) / len(normalized)) * 100, 2) if normalized else 0.0
    strengths = [key for key, value in normalized.items() if value >= 0.85]
    improvement_areas = [key for key, value in normalized.items() if value < 0.7]
    if score >= 85:
        status = "strong"
    elif score >= 70:
        status = "stable"
    elif score > 0:
        status = "needs_improvement"
    else:
        status = "insufficient_data"
    return {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "score": score,
        "status": status,
        "metrics": normalized,
        "strengths": strengths,
        "improvement_areas": improvement_areas,
    }


def evaluate_promotion(*, lesson: ArceusLessonProposal, evidence: list[ArceusEvidence], target_scope: str, dry_run: bool) -> dict[str, Any]:
    trusted_count = len(trusted_evidence(evidence))
    required = PROMOTION_THRESHOLDS[target_scope]
    approvals = ["mission_lead", "human_reviewer"]
    if target_scope in {"organization", "global"}:
        approvals.extend(["organization_owner", "security_reviewer"])
    if trusted_count < required:
        return {
            "accepted": False,
            "status": "blocked",
            "reason": f"{target_scope} promotion requires at least {required} trusted evidence item(s).",
            "required_approvals": approvals,
            "reversible": True,
        }
    if target_scope in {"organization", "global"} and lesson.status != "approved":
        return {
            "accepted": False,
            "status": "review_required",
            "reason": "Organization/global learning requires approved lesson status before promotion.",
            "required_approvals": approvals,
            "reversible": True,
        }
    return {
        "accepted": bool(dry_run or target_scope == "mission"),
        "status": "dry_run_accepted" if dry_run else ("approved" if target_scope == "mission" else "review_required"),
        "reason": "Promotion is evidence-backed and remains reversible/auditable.",
        "required_approvals": approvals,
        "reversible": True,
    }
