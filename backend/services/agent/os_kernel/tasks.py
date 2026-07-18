"""Generation 1 task lifecycle and completion gates."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .core import new_id, utc_now


TaskState = Literal[
    "BACKLOG",
    "READY",
    "ASSIGNED",
    "IN_PROGRESS",
    "BLOCKED",
    "SUBMITTED",
    "UNDER_REVIEW",
    "CHANGES_REQUESTED",
    "APPROVED",
    "VERIFYING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
]
TaskType = Literal["requirements", "architecture", "implementation", "security_review", "qa_review", "verification", "approval", "learning"]
RiskLevel = Literal["low", "medium", "high", "critical"]
ReviewVerdict = Literal["approved", "changes_requested", "rejected"]


TASK_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    "BACKLOG": {"READY", "CANCELLED"},
    "READY": {"ASSIGNED", "BLOCKED", "CANCELLED"},
    "ASSIGNED": {"IN_PROGRESS", "BLOCKED", "CANCELLED"},
    "IN_PROGRESS": {"SUBMITTED", "BLOCKED", "FAILED", "CANCELLED"},
    "BLOCKED": {"READY", "IN_PROGRESS", "FAILED", "CANCELLED"},
    "SUBMITTED": {"UNDER_REVIEW", "CHANGES_REQUESTED", "FAILED"},
    "UNDER_REVIEW": {"APPROVED", "CHANGES_REQUESTED", "FAILED"},
    "CHANGES_REQUESTED": {"IN_PROGRESS", "CANCELLED"},
    "APPROVED": {"VERIFYING", "COMPLETED"},
    "VERIFYING": {"COMPLETED", "FAILED", "CHANGES_REQUESTED"},
    "COMPLETED": set(),
    "FAILED": {"READY", "CANCELLED"},
    "CANCELLED": set(),
}


@dataclass(slots=True)
class TaskReview:
    reviewer_id: str
    reviewer_role: str
    verdict: ReviewVerdict
    findings: list[str] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "reviewer_id": self.reviewer_id,
            "reviewer_role": self.reviewer_role,
            "verdict": self.verdict,
            "findings": self.findings,
            "evidence_ids": self.evidence_ids,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class MissionTask:
    tenant_id: str
    project_id: str
    mission_id: str
    title: str
    description: str
    task_type: TaskType
    owner_id: str
    reviewer_ids: list[str]
    dependencies: list[str] = field(default_factory=list)
    inputs: list[str] = field(default_factory=list)
    expected_outputs: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    risk_level: RiskLevel = "medium"
    tool_permissions: list[str] = field(default_factory=list)
    required_evidence: list[str] = field(default_factory=list)
    maximum_attempts: int = 3
    current_attempt: int = 0
    status: TaskState = "BACKLOG"
    evidence_ids: list[str] = field(default_factory=list)
    reviews: list[TaskReview] = field(default_factory=list)
    verification_passed: bool = False
    task_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def transition(self, new_state: TaskState) -> None:
        if new_state not in TASK_TRANSITIONS[self.status]:
            raise ValueError(f"Invalid task transition {self.status} -> {new_state}")
        self.status = new_state
        self.updated_at = utc_now()

    def submit(self, evidence_ids: list[str]) -> None:
        if not evidence_ids:
            raise ValueError("Task submission requires evidence.")
        if self.status != "IN_PROGRESS":
            raise ValueError("Only in-progress tasks can be submitted.")
        self.evidence_ids.extend(evidence_ids)
        self.transition("SUBMITTED")

    def add_review(self, review: TaskReview) -> None:
        if review.reviewer_id == self.owner_id:
            raise ValueError("Task owner cannot independently review their own work.")
        self.reviews.append(review)
        if review.verdict == "changes_requested":
            self.status = "CHANGES_REQUESTED"
        elif review.verdict == "rejected":
            self.status = "FAILED"
        elif self.independent_approval_count() >= self.required_reviewer_count():
            self.status = "APPROVED"
        self.updated_at = utc_now()

    def required_reviewer_count(self) -> int:
        return 2 if self.risk_level in {"medium", "high", "critical"} else 1

    def independent_approval_count(self) -> int:
        return len({review.reviewer_id for review in self.reviews if review.verdict == "approved" and review.reviewer_id != self.owner_id})

    def can_complete(self) -> bool:
        required_evidence_ok = set(self.required_evidence).issubset(set(self.evidence_ids)) if self.required_evidence else bool(self.evidence_ids)
        return (
            self.status in {"APPROVED", "VERIFYING"}
            and required_evidence_ok
            and self.independent_approval_count() >= self.required_reviewer_count()
            and self.verification_passed
        )

    def complete(self) -> None:
        if not self.can_complete():
            raise ValueError("Task completion requires owner submission, independent review, required evidence, and verification.")
        self.status = "COMPLETED"
        self.updated_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "mission_id": self.mission_id,
            "title": self.title,
            "description": self.description,
            "task_type": self.task_type,
            "owner_id": self.owner_id,
            "reviewer_ids": self.reviewer_ids,
            "dependencies": self.dependencies,
            "inputs": self.inputs,
            "expected_outputs": self.expected_outputs,
            "acceptance_criteria": self.acceptance_criteria,
            "risk_level": self.risk_level,
            "tool_permissions": self.tool_permissions,
            "required_evidence": self.required_evidence,
            "maximum_attempts": self.maximum_attempts,
            "current_attempt": self.current_attempt,
            "status": self.status,
            "evidence_ids": self.evidence_ids,
            "reviews": [review.to_dict() for review in self.reviews],
            "verification_passed": self.verification_passed,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
