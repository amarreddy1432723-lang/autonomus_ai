from __future__ import annotations

from .proposal import VERIFICATION_BY_INTENT


class VerificationPlanningStage:
    stage_key = "verification_planning"

    def run(self, payload: dict) -> dict:
        intent = payload["intent_classification"]["output"]
        requirements = payload["requirement_planning"]["output"].get("requirements", [])
        risk = payload["risk_planning"]["output"]["risk_profile"]
        methods = list(VERIFICATION_BY_INTENT.get(intent["primary_intent"], ["build verification", "manual review"]))
        if risk.get("requires_security_review") and "security review" not in methods:
            methods.append("security review")
        verification_plan = [
            {
                "requirement_key": requirement["requirement_key"],
                "methods": methods,
                "evidence_required": ["command_output", "work_receipt", "review_result"],
            }
            for requirement in requirements
        ]
        return {
            "status": "passed",
            "verification_methods": methods,
            "verification_plan": verification_plan,
            "warning_codes": [] if verification_plan else ["verification_plan_empty"],
            "cost_usd": 0.0001,
        }

