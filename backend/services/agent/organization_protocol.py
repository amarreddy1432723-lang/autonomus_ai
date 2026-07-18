"""Structured communication protocol for the Arceus AI organization.

The goal is to move specialist collaboration away from loose prose and toward
typed messages that can be stored, summarized, reviewed, and turned into
execution decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4


MessagePriority = Literal["low", "normal", "high", "critical"]
MessageStatus = Literal["draft", "needs_review", "accepted", "rejected", "resolved"]
ReviewLens = Literal[
    "architecture",
    "security",
    "performance",
    "accessibility",
    "compliance",
    "reliability",
    "cost",
    "scalability",
    "maintainability",
    "business",
    "ux",
    "future_evolution",
]


REVIEW_COUNCIL: tuple[ReviewLens, ...] = (
    "architecture",
    "security",
    "performance",
    "accessibility",
    "compliance",
    "reliability",
    "cost",
    "scalability",
    "maintainability",
    "business",
    "ux",
    "future_evolution",
)


GENERATION_ROADMAP: list[dict[str, Any]] = [
    {
        "generation": 1,
        "name": "Orchestrated Specialists",
        "capability": "Single orchestrator, five core specialists, shared memory, work receipts.",
    },
    {
        "generation": 2,
        "name": "Dynamic Organization",
        "capability": "Domain-based team creation, review council, knowledge graph, structured messages.",
    },
    {
        "generation": 3,
        "name": "Cross-Domain Organizations",
        "capability": "Software, AI, security, cloud, healthcare, finance and other domain teams.",
    },
    {
        "generation": 4,
        "name": "Autonomous Operations",
        "capability": "Planning, execution, monitoring, improvement, with human approvals for risk.",
    },
    {
        "generation": 5,
        "name": "Artificial Engineering Organization",
        "capability": "Hundreds of specialists, persistent organizational intelligence, adaptive structure.",
    },
]


@dataclass(slots=True)
class SpecialistMessage:
    from_specialist: str
    to_specialist: str
    topic: str
    finding: str
    recommendation: str
    priority: MessagePriority = "normal"
    evidence: list[str] = field(default_factory=list)
    confidence: float = 0.75
    status: MessageStatus = "needs_review"
    review_lens: ReviewLens | None = None
    message_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.message_id,
            "from": self.from_specialist,
            "to": self.to_specialist,
            "topic": self.topic,
            "priority": self.priority,
            "finding": self.finding,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "confidence": max(0.0, min(1.0, float(self.confidence))),
            "status": self.status,
            "review_lens": self.review_lens,
            "created_at": self.created_at,
        }


def create_specialist_message(
    *,
    from_specialist: str,
    to_specialist: str,
    topic: str,
    finding: str,
    recommendation: str,
    priority: MessagePriority = "normal",
    evidence: list[str] | None = None,
    confidence: float = 0.75,
    status: MessageStatus = "needs_review",
    review_lens: ReviewLens | None = None,
) -> dict[str, Any]:
    """Create a serializable specialist-to-specialist communication record."""

    return SpecialistMessage(
        from_specialist=from_specialist,
        to_specialist=to_specialist,
        topic=topic,
        finding=finding,
        recommendation=recommendation,
        priority=priority,
        evidence=evidence or [],
        confidence=confidence,
        status=status,
        review_lens=review_lens,
    ).to_dict()


def sample_review_messages() -> list[dict[str, Any]]:
    """Return canonical examples used by UI previews, tests, and seed data."""

    return [
        create_specialist_message(
            from_specialist="Security Engineer",
            to_specialist="Backend Engineer",
            topic="Authentication Review",
            priority="high",
            finding="Refresh tokens should rotate on every use.",
            evidence=["Current implementation reuses refresh tokens."],
            recommendation="Implement refresh token rotation and revoke previous tokens after successful refresh.",
            confidence=0.97,
            review_lens="security",
        ),
        create_specialist_message(
            from_specialist="Architect",
            to_specialist="Engineering Manager",
            topic="Service Boundary Decision",
            priority="normal",
            finding="The MVP should remain a modular monolith until team and load justify service extraction.",
            evidence=["Roadmap prioritizes speed to market.", "Operational budget is constrained."],
            recommendation="Keep modules isolated behind internal interfaces and record extraction criteria.",
            confidence=0.91,
            review_lens="architecture",
        ),
    ]


def summarize_message_bus(messages: list[dict[str, Any]]) -> dict[str, Any]:
    by_priority: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_lens: dict[str, int] = {}
    for message in messages:
        by_priority[message.get("priority", "normal")] = by_priority.get(message.get("priority", "normal"), 0) + 1
        by_status[message.get("status", "needs_review")] = by_status.get(message.get("status", "needs_review"), 0) + 1
        lens = message.get("review_lens") or "unassigned"
        by_lens[lens] = by_lens.get(lens, 0) + 1
    return {
        "total_messages": len(messages),
        "by_priority": by_priority,
        "by_status": by_status,
        "by_review_lens": by_lens,
        "open_critical": by_priority.get("critical", 0),
        "open_high": by_priority.get("high", 0),
    }
