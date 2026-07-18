from __future__ import annotations


class UnknownPlanningStage:
    stage_key = "unknown_planning"

    def run(self, payload: dict) -> dict:
        normalized = payload["input_normalization"]["output"]["normalized"]
        intent = payload["intent_classification"]["output"]
        guard = payload["objective_boundary_guard"]["output"]
        unknowns = [
            {"question": question, "risk_if_unanswered": guard.get("reason_code", "Mission boundary is unclear.")}
            for question in guard.get("clarification_questions", [])
        ]
        if intent["primary_intent"] == "dependency_upgrade":
            unknowns.append({"question": "Which dependency versions are allowed?", "risk_if_unanswered": "Upgrade may introduce incompatible or unsafe packages."})
        if "production" in normalized["objective"].casefold():
            unknowns.append({"question": "Which production environment is in scope?", "risk_if_unanswered": "Production changes require explicit environment approval."})
        return {
            "status": "needs_clarification" if unknowns and guard.get("boundary_status") != "ok" else "passed",
            "unknowns": unknowns,
            "warning_codes": ["material_unknowns_present"] if unknowns else [],
            "cost_usd": 0.0001,
        }

