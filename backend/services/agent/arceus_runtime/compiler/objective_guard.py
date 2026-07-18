from __future__ import annotations

import re


REJECT_PATTERNS = (
    r"\bdelete\s+production\b",
    r"\bdisable\s+(audit|security|auth)\b",
    r"\bexfiltrate\b",
    r"\bsteal\b",
    r"\bdrop\s+database\b",
)


class ObjectiveBoundaryGuardStage:
    stage_key = "objective_boundary_guard"

    def run(self, payload: dict) -> dict:
        normalized = payload["input_normalization"]["output"]["normalized"]
        intent = payload["intent_classification"]["output"]
        objective = normalized["objective"]
        text = objective.casefold()
        warning_codes: list[str] = []
        questions: list[str] = []
        boundary_status = "ok"
        reason_code = "within_boundary"

        if any(re.search(pattern, text) for pattern in REJECT_PATTERNS):
            boundary_status = "rejected"
            reason_code = "unsafe_or_policy_bypassing_objective"
            warning_codes.append(reason_code)
        elif len(objective) > 4000 or len(intent.get("secondary_intents", [])) >= 4:
            boundary_status = "clarification_required"
            reason_code = "objective_too_broad"
            warning_codes.append(reason_code)
            questions.append("Which single outcome should Arceus complete first?")
        elif intent.get("primary_intent") == "unknown":
            boundary_status = "clarification_required"
            reason_code = "intent_unclear"
            questions.append("What concrete repository change or engineering decision should Arceus produce?")

        if not normalized.get("repository_scopes"):
            boundary_status = "clarification_required" if boundary_status == "ok" else boundary_status
            warning_codes.append("repository_scope_missing")
            questions.append("Which repository or local workspace should this mission use?")

        return {
            "status": "passed" if boundary_status == "ok" else boundary_status,
            "boundary_status": boundary_status,
            "reason_code": reason_code,
            "clarification_questions": questions,
            "warning_codes": warning_codes,
            "cost_usd": 0.0,
        }

