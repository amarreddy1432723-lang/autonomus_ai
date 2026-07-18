from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RiskAssessment:
    task_type: str
    risk_level: str
    planning_depth: str
    risk_score: float
    reasons: list[str]


CRITICAL_TERMS = {
    "production",
    "deploy",
    "migration",
    "database",
    "billing",
    "stripe",
    "payment",
    "auth",
    "secret",
    "token",
    "delete",
    "remove",
    "rename",
}

HIGH_TERMS = {
    "github",
    "pr",
    "terminal",
    "command",
    "docker",
    "sandbox",
    "worker",
    "redis",
    "celery",
    "admin",
}


def classify_task_type(text: str) -> str:
    lowered = text.lower()
    if any(word in lowered for word in ("fix", "bug", "error", "crash", "failed", "failure")):
        return "fix"
    if any(word in lowered for word in ("design", "ui", "ux", "screen", "mockup")):
        return "design"
    if any(word in lowered for word in ("deploy", "release", "railway", "github", "production")):
        return "release"
    if any(word in lowered for word in ("research", "compare", "analyze")):
        return "research"
    if any(word in lowered for word in ("test", "verify", "qa", "check")):
        return "verification"
    return "build"


def assess_risk(text: str) -> RiskAssessment:
    lowered = text.lower()
    reasons: list[str] = []
    critical_hits = sorted(term for term in CRITICAL_TERMS if term in lowered)
    high_hits = sorted(term for term in HIGH_TERMS if term in lowered)

    if critical_hits:
        risk_level = "critical" if len(critical_hits) >= 3 else "high"
        reasons.append(f"Sensitive terms: {', '.join(critical_hits[:6])}")
    elif high_hits:
        risk_level = "medium"
        reasons.append(f"Operational terms: {', '.join(high_hits[:6])}")
    else:
        risk_level = "low"
        reasons.append("No destructive or production-sensitive intent detected.")

    score = {"low": 0.2, "medium": 0.45, "high": 0.75, "critical": 0.95}[risk_level]
    depth = "deep" if risk_level in {"high", "critical"} else "standard"
    if classify_task_type(text) in {"release", "verification"} and depth == "standard":
        depth = "deep"

    return RiskAssessment(
        task_type=classify_task_type(text),
        risk_level=risk_level,
        planning_depth=depth,
        risk_score=score,
        reasons=reasons,
    )

