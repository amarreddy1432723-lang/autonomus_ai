from __future__ import annotations


HIGH_RISK_INTENTS = {"security_change", "authentication_change", "authorization_change", "database_change", "infrastructure_change", "dependency_upgrade"}


class RiskPlanningStage:
    stage_key = "risk_planning"

    def run(self, payload: dict) -> dict:
        intent = payload["intent_classification"]["output"]
        normalized = payload["input_normalization"]["output"]["normalized"]
        drivers = [intent["primary_intent"], *intent.get("secondary_intents", [])]
        text = " ".join([normalized["objective"], *normalized.get("constraints", [])]).casefold()
        level = "high" if any(item in HIGH_RISK_INTENTS for item in drivers) else "medium"
        if any(token in text for token in ("delete", "production", "secret", "payment", "migration")):
            level = "high"
        if "readme" in text or intent["primary_intent"] == "documentation":
            level = "low"
        return {
            "status": "passed",
            "risk_profile": {
                "level": level,
                "drivers": drivers[:5],
                "requires_security_review": level == "high" or any("auth" in item for item in drivers),
                "requires_human_approval": True,
            },
            "warning_codes": ["high_risk_mission"] if level == "high" else [],
            "cost_usd": 0.0001,
        }

