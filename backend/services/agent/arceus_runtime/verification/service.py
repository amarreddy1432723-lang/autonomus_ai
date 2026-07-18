from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from services.shared.arceus_core_models import (
    ArceusApproval,
    ArceusCompletionCertificate,
    ArceusEvidence,
    ArceusMission,
    ArceusMissionSuccessCriterion,
    ArceusQualityGate,
    ArceusReview,
    ArceusTrustScore,
    ArceusVerificationPlan,
)


TRUST_LEVELS = {
    "unverified": 0,
    "ai_reviewed": 1,
    "tool_verified": 2,
    "independent_review": 3,
    "human_approved": 4,
    "production_observed": 5,
}


def stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def evidence_content_hash(*, mission_id: UUID, evidence_type: str, summary: str, payload: dict[str, Any]) -> str:
    return stable_hash(
        {
            "mission_id": str(mission_id),
            "evidence_type": evidence_type,
            "summary": summary,
            "payload": payload,
        }
    )


def default_gate_key(method: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in method.lower()).strip("_")
    return normalized or "manual_review"


def build_default_quality_gate(*, plan: ArceusVerificationPlan, method: str, evidence_type: str) -> ArceusQualityGate:
    key = default_gate_key(method)
    category = {
        "build": "functional",
        "unit_tests": "functional",
        "integration_tests": "functional",
        "security_scan": "security",
        "accessibility": "accessibility",
        "performance": "performance",
        "human_acceptance": "approval",
        "manual_review": "review",
    }.get(key, "functional")
    return ArceusQualityGate(
        tenant_id=plan.tenant_id,
        mission_id=plan.mission_id,
        verification_plan_id=plan.id,
        gate_key=key,
        name=method.replace("_", " ").title(),
        category=category,
        gate_type="mandatory" if plan.blocking else "conditional",
        required=plan.blocking,
        verifier=method,
        timeout_seconds=min(int(plan.timeout_seconds or 300), 3600),
        status="pending",
        result={"required_evidence_type": evidence_type},
        evidence_ids=[],
    )


def _is_verified_evidence(item: ArceusEvidence) -> bool:
    return item.status in {"validated", "trusted", "verified"}


def _tool_evidence_type(tool_key: str, action_key: str) -> str:
    return f"tool_{tool_key}_{action_key}".replace("-", "_")


def _coerce_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _matching_evidence(*, evidence: list[ArceusEvidence], evidence_type: str, verification_method: str | None = None) -> list[ArceusEvidence]:
    return [
        item
        for item in evidence
        if _is_verified_evidence(item)
        and (item.evidence_type == evidence_type or (verification_method is not None and item.verification_method == verification_method))
    ]


def evaluate_tool_evidence_requirement(requirement: str | dict[str, Any], evidence: list[ArceusEvidence]) -> tuple[bool, dict[str, Any]]:
    if isinstance(requirement, str):
        evidence_type = requirement
        verification_method = None
        require_passing_checks = evidence_type == "tool_github_check_runs"
        allow_empty_checks = False
    else:
        tool_key = str(requirement.get("tool_key") or "").strip()
        action_key = str(requirement.get("action_key") or "").strip()
        evidence_type = str(requirement.get("evidence_type") or _tool_evidence_type(tool_key, action_key)).strip()
        verification_method = requirement.get("verification_method")
        require_passing_checks = bool(requirement.get("require_passing_checks", evidence_type == "tool_github_check_runs"))
        allow_empty_checks = bool(requirement.get("allow_empty_checks", False))

    matches = _matching_evidence(evidence=evidence, evidence_type=evidence_type, verification_method=verification_method)
    if not matches:
        return False, {
            "reason": "missing_tool_evidence",
            "required_evidence_type": evidence_type,
        }

    if not require_passing_checks:
        return True, {
            "reason": "matching_tool_evidence",
            "required_evidence_type": evidence_type,
            "matched_evidence_ids": [str(item.id) for item in matches],
        }

    latest_blocker: dict[str, Any] | None = None
    for item in matches:
        payload = item.payload or {}
        total = _coerce_int(payload.get("total"))
        failed = _coerce_int(payload.get("failed"))
        running = _coerce_int(payload.get("running"))
        passed = _coerce_int(payload.get("passed"))
        if total <= 0 and not allow_empty_checks:
            latest_blocker = {
                "reason": "github_checks_missing",
                "required_evidence_type": evidence_type,
                "matched_evidence_ids": [str(item.id)],
                "total": total,
                "passed": passed,
                "failed": failed,
                "running": running,
            }
            continue
        if failed > 0:
            latest_blocker = {
                "reason": "github_checks_failed",
                "required_evidence_type": evidence_type,
                "matched_evidence_ids": [str(item.id)],
                "total": total,
                "passed": passed,
                "failed": failed,
                "running": running,
            }
            continue
        if running > 0:
            latest_blocker = {
                "reason": "github_checks_running",
                "required_evidence_type": evidence_type,
                "matched_evidence_ids": [str(item.id)],
                "total": total,
                "passed": passed,
                "failed": failed,
                "running": running,
            }
            continue
        return True, {
            "reason": "github_checks_passing",
            "required_evidence_type": evidence_type,
            "matched_evidence_ids": [str(item.id)],
            "total": total,
            "passed": passed,
            "failed": failed,
            "running": running,
        }

    return False, latest_blocker or {
        "reason": "github_checks_not_passing",
        "required_evidence_type": evidence_type,
        "matched_evidence_ids": [str(item.id) for item in matches],
    }


def evaluate_tool_evidence_requirements(requirements: list[str | dict[str, Any]], evidence: list[ArceusEvidence]) -> tuple[bool, dict[str, Any]]:
    results: list[dict[str, Any]] = []
    matched_ids: list[str] = []
    for requirement in requirements:
        passed, result = evaluate_tool_evidence_requirement(requirement, evidence)
        results.append({"passed": passed, **result})
        matched_ids.extend(result.get("matched_evidence_ids") or [])

    blockers = [result for result in results if not result["passed"]]
    if blockers:
        return False, {
            "reason": "tool_evidence_requirements_blocked",
            "requirements": results,
            "matched_evidence_ids": sorted(set(matched_ids)),
        }
    return True, {
        "reason": "tool_evidence_requirements_met",
        "requirements": results,
        "matched_evidence_ids": sorted(set(matched_ids)),
    }


def gate_passes_with_evidence(gate: ArceusQualityGate, evidence: list[ArceusEvidence]) -> tuple[bool, dict[str, Any]]:
    tool_requirements = (gate.result or {}).get("required_tool_evidence") or (gate.result or {}).get("tool_evidence_required")
    if tool_requirements:
        if isinstance(tool_requirements, (str, dict)):
            tool_requirements = [tool_requirements]
        return evaluate_tool_evidence_requirements(list(tool_requirements), evidence)

    required_type = (gate.result or {}).get("required_evidence_type") or gate.verifier
    trusted_evidence = _matching_evidence(evidence=evidence, evidence_type=required_type, verification_method=gate.verifier)
    if trusted_evidence:
        return True, {
            "reason": "matching_trusted_evidence",
            "matched_evidence_ids": [str(item.id) for item in trusted_evidence],
        }
    return False, {
        "reason": "missing_matching_trusted_evidence",
        "required_evidence_type": required_type,
    }


def calculate_trust_score(
    *,
    mission_id: UUID,
    evidence: list[ArceusEvidence],
    gates: list[ArceusQualityGate],
    reviews: list[ArceusReview],
    approvals: list[ArceusApproval],
    target_type: str = "mission",
    target_id: UUID | None = None,
) -> ArceusTrustScore:
    verified_evidence = [item for item in evidence if item.status in {"validated", "trusted", "verified"}]
    required_gates = [gate for gate in gates if gate.required]
    passed_required_gates = [gate for gate in required_gates if gate.status == "passed"]
    completed_reviews = [review for review in reviews if review.status == "completed" and review.verdict in {"approved", "pass", "passed"}]
    human_approvals = [
        approval
        for approval in approvals
        if approval.status == "approved" and bool((approval.quorum_policy or {}).get("requires_human", False))
    ]
    production_observed = any(item.evidence_type == "production_observation" and item.status in {"trusted", "verified"} for item in evidence)

    evidence_score = 20.0 if verified_evidence else 0.0
    gate_score = 40.0 * (len(passed_required_gates) / len(required_gates)) if required_gates else 40.0
    review_score = 25.0 if completed_reviews or not reviews else 0.0
    approval_score = 10.0 if human_approvals else 0.0
    production_score = 5.0 if production_observed else 0.0
    score = round(evidence_score + gate_score + review_score + approval_score + production_score, 2)

    max_evidence_level = max([TRUST_LEVELS.get(item.trust_level, 0) for item in evidence] or [0])
    trust_level = max_evidence_level
    if completed_reviews:
        trust_level = max(trust_level, 3)
    if human_approvals:
        trust_level = max(trust_level, 4)
    if production_observed:
        trust_level = 5

    contributors = {
        "verified_evidence": len(verified_evidence),
        "required_gates": len(required_gates),
        "passed_required_gates": len(passed_required_gates),
        "completed_reviews": len(completed_reviews),
        "human_approvals": len(human_approvals),
        "production_observed": production_observed,
    }
    confidence = round(min(score / 100.0, 1.0), 4)
    return ArceusTrustScore(
        mission_id=mission_id,
        target_type=target_type,
        target_id=target_id or mission_id,
        trust_level=trust_level,
        score=score,
        confidence=confidence,
        contributors=contributors,
    )


@dataclass(frozen=True)
class CompletionEvaluation:
    status: str
    blockers: list[dict[str, Any]]
    completed_requirements: list[dict[str, Any]]
    evidence_ids: list[str]
    gate_ids: list[str]
    approval_ids: list[str]


def evaluate_completion(
    *,
    mission: ArceusMission,
    criteria: list[ArceusMissionSuccessCriterion],
    evidence: list[ArceusEvidence],
    gates: list[ArceusQualityGate],
    reviews: list[ArceusReview],
    approvals: list[ArceusApproval],
) -> CompletionEvaluation:
    blockers: list[dict[str, Any]] = []
    verified_evidence = [item for item in evidence if item.status in {"validated", "trusted", "verified"}]

    completed_requirements: list[dict[str, Any]] = []
    for criterion in criteria:
        matches = [
            item
            for item in verified_evidence
            if item.evidence_type == criterion.verification_method
            or item.verification_method == criterion.verification_method
            or criterion.criterion_key in ((item.payload or {}).get("criteria_keys") or [])
        ]
        if criterion.required and not matches:
            blockers.append(
                {
                    "type": "missing_evidence",
                    "criterion_key": criterion.criterion_key,
                    "message": f"Required criterion has no verified evidence: {criterion.statement}",
                }
            )
        elif matches:
            completed_requirements.append(
                {
                    "criterion_key": criterion.criterion_key,
                    "statement": criterion.statement,
                    "evidence_ids": [str(item.id) for item in matches],
                }
            )

    for gate in gates:
        if gate.required and gate.status != "passed":
            blockers.append(
                {
                    "type": "quality_gate",
                    "gate_key": gate.gate_key,
                    "status": gate.status,
                    "message": f"Required quality gate is not passing: {gate.name}",
                }
            )

    for review in reviews:
        if review.blocking and review.status != "completed":
            blockers.append(
                {
                    "type": "blocking_review",
                    "review_id": str(review.id),
                    "status": review.status,
                    "message": "Blocking review is still open.",
                }
            )
        elif review.blocking and review.verdict not in {"approved", "pass", "passed"}:
            blockers.append(
                {
                    "type": "review_verdict",
                    "review_id": str(review.id),
                    "verdict": review.verdict,
                    "message": "Blocking review did not approve the target.",
                }
            )

    high_risk = mission.risk_level in {"high", "critical"} or mission.status == "awaiting_completion_approval"
    human_approved = any(
        approval.status == "approved" and bool((approval.quorum_policy or {}).get("requires_human", False))
        for approval in approvals
    )
    if high_risk and not human_approved:
        blockers.append(
            {
                "type": "human_approval",
                "message": "High-risk or completion-gated mission requires human approval.",
            }
        )

    return CompletionEvaluation(
        status="certified" if not blockers else "blocked",
        blockers=blockers,
        completed_requirements=completed_requirements,
        evidence_ids=[str(item.id) for item in verified_evidence],
        gate_ids=[str(gate.id) for gate in gates if gate.status == "passed"],
        approval_ids=[str(approval.id) for approval in approvals if approval.status == "approved"],
    )


def build_completion_certificate(
    *,
    tenant_id: UUID,
    mission: ArceusMission,
    evaluation: CompletionEvaluation,
    trust_score: ArceusTrustScore,
    version: int = 1,
) -> ArceusCompletionCertificate:
    payload = {
        "mission_id": str(mission.id),
        "version": version,
        "status": evaluation.status,
        "completed_requirements": evaluation.completed_requirements,
        "evidence_ids": evaluation.evidence_ids,
        "gate_ids": evaluation.gate_ids,
        "approval_ids": evaluation.approval_ids,
        "trust_score": trust_score.score,
        "trust_level": trust_score.trust_level,
    }
    certificate_hash = stable_hash(payload)
    return ArceusCompletionCertificate(
        tenant_id=tenant_id,
        mission_id=mission.id,
        certificate_version=version,
        status=evaluation.status,
        completed_requirements=evaluation.completed_requirements,
        evidence_ids=evaluation.evidence_ids,
        gate_ids=evaluation.gate_ids,
        approval_ids=evaluation.approval_ids,
        trust_score_id=trust_score.id,
        blockers=evaluation.blockers,
        certificate_hash=certificate_hash,
        signature=stable_hash({"certificate_hash": certificate_hash, "signed_at": datetime.now(timezone.utc).isoformat()}),
        signed_at=datetime.now(timezone.utc) if evaluation.status == "certified" else None,
        immutable=True,
    )
