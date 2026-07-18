from __future__ import annotations


class RequirementPlanningStage:
    stage_key = "requirement_planning"

    def run(self, payload: dict) -> dict:
        normalized = payload["input_normalization"]["output"]["normalized"]
        intent = payload["intent_classification"]["output"]
        objective = normalized["objective"]
        requirements = [objective, *normalized.get("desired_outcomes", [])]
        deduped: list[str] = []
        for item in requirements:
            if item not in deduped:
                deduped.append(item)
        functional = [
            {"requirement_key": f"FR-{index:03d}", "statement": item, "source": "mission_objective"}
            for index, item in enumerate(deduped[:12], start=1)
        ]
        nonfunctional = []
        if intent["primary_intent"] in {"security_change", "authentication_change", "authorization_change"}:
            nonfunctional.append({"requirement_key": "NFR-SEC-001", "statement": "Security behavior must be independently reviewed."})
        if intent["primary_intent"] in {"performance_improvement", "infrastructure_change"}:
            nonfunctional.append({"requirement_key": "NFR-OPS-001", "statement": "Operational impact must be measured with evidence."})
        return {
            "status": "passed",
            "requirements": functional,
            "nonfunctional_requirements": nonfunctional,
            "warning_codes": [] if functional else ["requirements_empty"],
            "cost_usd": 0.0001,
        }

