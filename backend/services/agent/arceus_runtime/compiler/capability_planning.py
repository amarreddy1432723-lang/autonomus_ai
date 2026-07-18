from __future__ import annotations


class CapabilityPlanningStage:
    stage_key = "capability_planning"

    def run(self, payload: dict) -> dict:
        intent = payload["intent_classification"]["output"]
        requirements = payload["requirement_planning"]["output"].get("requirements", [])
        risk = payload["risk_planning"]["output"]["risk_profile"]
        capabilities = list(intent.get("required_capability_hints") or [])
        if requirements and "acceptance_criteria_definition" not in capabilities:
            capabilities.insert(0, "acceptance_criteria_definition")
        if "requirement_analysis" not in capabilities:
            capabilities.insert(0, "requirement_analysis")
        if risk.get("requires_security_review") and "secure_code_review" not in capabilities:
            capabilities.append("secure_code_review")
        if "build_verification" not in capabilities:
            capabilities.append("build_verification")
        deduped = []
        for capability in capabilities:
            if capability not in deduped:
                deduped.append(capability)
        return {
            "status": "passed",
            "required_capabilities": deduped,
            "capability_sources": {
                "intent": intent.get("primary_intent"),
                "risk_level": risk.get("level"),
                "requirement_count": len(requirements),
            },
            "warning_codes": [],
            "cost_usd": 0.0001,
        }

