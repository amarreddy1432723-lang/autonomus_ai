"""Structured decision management for Generation 1."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .core import new_id, utc_now


DecisionState = Literal["PROPOSED", "UNDER_REVIEW", "NEEDS_INFORMATION", "APPROVED", "REJECTED", "SUPERSEDED"]
DecisionKind = Literal["architecture", "security", "deployment", "authentication", "authorization", "billing", "data_migration", "infrastructure", "implementation"]
ReviewVerdict = Literal["approve", "reject", "needs_information"]

HUMAN_APPROVAL_DECISIONS = {"architecture", "security", "deployment", "authentication", "authorization", "billing", "data_migration", "infrastructure"}


@dataclass(slots=True)
class DecisionOption:
    name: str
    advantages: list[str] = field(default_factory=list)
    disadvantages: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    estimated_cost: float = 0.0
    estimated_effort: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "advantages": self.advantages,
            "disadvantages": self.disadvantages,
            "risks": self.risks,
            "estimated_cost": self.estimated_cost,
            "estimated_effort": self.estimated_effort,
        }


@dataclass(slots=True)
class DecisionReview:
    reviewer_id: str
    reviewer_role: str
    verdict: ReviewVerdict
    findings: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewer_id": self.reviewer_id,
            "reviewer_role": self.reviewer_role,
            "verdict": self.verdict,
            "findings": self.findings,
            "evidence_ids": self.evidence_ids,
        }


@dataclass(slots=True)
class MissionDecision:
    tenant_id: str
    project_id: str
    mission_id: str
    problem: str
    decision_type: DecisionKind
    proposed_by: str
    options: list[DecisionOption]
    proposed_option: str
    evidence_ids: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)
    reviewers: list[str] = field(default_factory=list)
    reviews: list[DecisionReview] = field(default_factory=list)
    final_selection: str | None = None
    status: DecisionState = "PROPOSED"
    superseded_decision_id: str | None = None
    human_approval_required: bool = False
    human_approved: bool = False
    decision_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.human_approval_required = self.human_approval_required or self.decision_type in HUMAN_APPROVAL_DECISIONS

    def add_review(self, review: DecisionReview) -> None:
        if review.reviewer_id == self.proposed_by:
            raise ValueError("Decision proposer cannot be the only independent reviewer.")
        self.reviews.append(review)
        if review.verdict == "reject":
            self.status = "REJECTED"
        elif review.verdict == "needs_information":
            self.status = "NEEDS_INFORMATION"
        elif self.approval_count() >= 1:
            self.status = "UNDER_REVIEW" if self.human_approval_required and not self.human_approved else "APPROVED"

    def approval_count(self) -> int:
        return len({review.reviewer_id for review in self.reviews if review.verdict == "approve" and review.reviewer_id != self.proposed_by})

    def approve_human(self, user_id: str) -> None:
        if not user_id:
            raise ValueError("Human approval requires a user id.")
        self.human_approved = True
        if self.approval_count() >= 1:
            self.status = "APPROVED"

    def finalize(self, option: str) -> None:
        if self.status != "APPROVED":
            raise ValueError("Decision must be approved before final selection.")
        if option not in {item.name for item in self.options}:
            raise ValueError("Final selection must preserve one proposed option.")
        self.final_selection = option

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "mission_id": self.mission_id,
            "problem": self.problem,
            "decision_type": self.decision_type,
            "proposed_by": self.proposed_by,
            "options": [option.to_dict() for option in self.options],
            "proposed_option": self.proposed_option,
            "evidence_ids": self.evidence_ids,
            "assumptions": self.assumptions,
            "reviewers": self.reviewers,
            "reviews": [review.to_dict() for review in self.reviews],
            "final_selection": self.final_selection,
            "status": self.status,
            "superseded_decision_id": self.superseded_decision_id,
            "human_approval_required": self.human_approval_required,
            "human_approved": self.human_approved,
            "created_at": self.created_at,
        }

