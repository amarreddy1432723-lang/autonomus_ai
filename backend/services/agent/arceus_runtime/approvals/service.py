from __future__ import annotations

from datetime import datetime, timezone

from services.shared.arceus_core_models import ArceusApproval, ArceusApprovalVote, ArceusMission

from ..application.errors import ApprovalAlreadyResolved, ApprovalSubjectMismatch, MissionStateConflict


def approval_requires_human(approval: ArceusApproval) -> bool:
    policy = approval.quorum_policy or {}
    return bool(policy.get("requires_human", True))


def required_human_votes(approval: ArceusApproval) -> int:
    policy = approval.quorum_policy or {}
    return max(int(policy.get("required_human_votes", 1)), 1 if approval_requires_human(approval) else 0)


def subject_hash_for(approval: ArceusApproval) -> str:
    return approval.subject_hash or (approval.quorum_policy or {}).get("subject_hash", "")


def validate_vote_preconditions(approval: ArceusApproval, *, subject_hash: str) -> None:
    if approval.status != "pending":
        raise ApprovalAlreadyResolved("Approval has already been resolved.", details={"status": approval.status})
    expected_hash = subject_hash_for(approval)
    if expected_hash and expected_hash != subject_hash:
        raise ApprovalSubjectMismatch("Approval subject changed after it was reviewed.")
    if approval.expires_at and approval.expires_at <= datetime.now(timezone.utc):
        raise ApprovalAlreadyResolved("Approval has expired.", details={"expired_at": approval.expires_at.isoformat()})


def quorum_satisfied(approval: ArceusApproval, votes: list[ArceusApprovalVote]) -> bool:
    approving_human_votes = [vote for vote in votes if vote.vote == "approve" and vote.is_human_vote]
    if approval_requires_human(approval) and len(approving_human_votes) < required_human_votes(approval):
        return False
    if any(vote.vote == "reject" for vote in votes):
        return False
    return any(vote.vote == "approve" for vote in votes)


def resolve_approval_if_ready(approval: ArceusApproval, mission: ArceusMission, votes: list[ArceusApprovalVote]) -> str:
    if any(vote.vote == "reject" for vote in votes):
        approval.status = "rejected"
        approval.resolved_at = datetime.now(timezone.utc)
        return "rejected"
    if quorum_satisfied(approval, votes):
        approval.status = "approved"
        approval.resolved_at = datetime.now(timezone.utc)
        if approval.approval_type == "mission_plan":
            if mission.status != "awaiting_plan_approval":
                raise MissionStateConflict(
                    "Mission plan approval can only resolve while the mission awaits plan approval.",
                    details={"current_state": mission.status},
                )
            mission.status = "ready"
            mission.version_number = int(mission.version_number) + 1
        return "approved"
    return "pending"
