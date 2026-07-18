"""Policy and approval gates for Arceus OS."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


ToolCategory = Literal[
    "READ_ONLY",
    "LOCAL_WRITE",
    "NETWORK_ACCESS",
    "EXTERNAL_COMMUNICATION",
    "INFRASTRUCTURE_CHANGE",
    "PRODUCTION_CHANGE",
    "FINANCIAL_ACTION",
    "DESTRUCTIVE_ACTION",
]
RiskLevel = Literal["low", "medium", "high", "critical"]


@dataclass(slots=True)
class AuthorityContext:
    actor_id: str
    tenant_id: str
    role: str
    environment: Literal["local", "development", "staging", "production"] = "development"
    approved: bool = False
    reviewer_ids: list[str] | None = None


@dataclass(slots=True)
class PolicyDecision:
    allowed: bool
    reason: str
    requires_human_approval: bool = False
    required_reviewers: int = 0


HIGH_RISK_TOOLS: set[ToolCategory] = {
    "NETWORK_ACCESS",
    "EXTERNAL_COMMUNICATION",
    "INFRASTRUCTURE_CHANGE",
    "PRODUCTION_CHANGE",
    "FINANCIAL_ACTION",
    "DESTRUCTIVE_ACTION",
}


def evaluate_tool_policy(context: AuthorityContext, category: ToolCategory, risk_level: RiskLevel, *, author_id: str | None = None) -> PolicyDecision:
    if category in HIGH_RISK_TOOLS or risk_level in {"high", "critical"} or context.environment == "production":
        reviewers = context.reviewer_ids or []
        if not context.approved:
            return PolicyDecision(False, "Human approval required before high-impact action.", True, 1)
        if author_id and author_id in reviewers and len(set(reviewers)) < 2:
            return PolicyDecision(False, "Author cannot be the only reviewer for high-risk work.", True, 2)
        return PolicyDecision(True, "Approved high-impact action.", False, 1)

    if context.role == "viewer":
        return PolicyDecision(False, "Viewer role cannot execute tools.")
    return PolicyDecision(True, "Low-risk action allowed.")

