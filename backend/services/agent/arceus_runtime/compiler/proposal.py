from __future__ import annotations


VERIFICATION_BY_INTENT = {
    "authentication_change": ["auth route smoke test", "permission regression test", "manual login verification"],
    "authorization_change": ["role matrix test", "negative permission test", "audit event check"],
    "security_change": ["security review", "dependency scan", "secret redaction check"],
    "database_change": ["migration dry run", "rollback dry run", "query smoke test"],
    "infrastructure_change": ["service readiness check", "worker queue check", "rollback notes"],
    "performance_improvement": ["before/after latency evidence", "build verification", "regression test"],
    "dependency_upgrade": ["lockfile diff review", "build verification", "dependency vulnerability scan"],
    "documentation": ["documentation review", "link check"],
    "testing_improvement": ["new test fails before fix", "test suite passes after fix"],
    "bug_fix": ["reproduction evidence", "targeted regression test", "build verification"],
    "refactoring": ["build verification", "regression suite", "public behavior unchanged check"],
    "repository_analysis": ["files inspected receipt", "findings review"],
    "feature_development": ["acceptance criteria test", "build verification", "manual UX smoke test"],
}


class DeterministicProposalStage:
    stage_key = "deterministic_proposal"

    def run(self, payload: dict) -> dict:
        normalized = payload["input_normalization"]["output"]["normalized"]
        intent = payload["intent_classification"]["output"]
        guard = payload["objective_boundary_guard"]["output"]
        requirements = payload.get("requirement_planning", {}).get("output", {})
        risk = payload.get("risk_planning", {}).get("output", {})
        capabilities = payload.get("capability_planning", {}).get("output", {})
        verification = payload.get("verification_planning", {}).get("output", {})
        approvals = payload.get("approval_planning", {}).get("output", {})
        primary_intent = intent["primary_intent"]
        capability_hints = capabilities.get("required_capabilities") or intent.get("required_capability_hints") or []
        if guard["boundary_status"] != "ok":
            return {
                "status": guard["boundary_status"],
                "proposal": {
                    "objective": normalized["objective"],
                    "primary_intent": primary_intent,
                    "blocked_by": guard["reason_code"],
                    "clarification_questions": guard.get("clarification_questions", []),
                },
                "warning_codes": guard.get("warning_codes", []),
                "cost_usd": 0.0,
            }

        proposal = {
            "objective": normalized["objective"],
            "primary_intent": primary_intent,
            "secondary_intents": intent.get("secondary_intents", []),
            "requirements": [
                item["statement"] for item in requirements.get("requirements", [])
            ] or [normalized["objective"], *normalized.get("desired_outcomes", [])][:12],
            "nonfunctional_requirements": requirements.get("nonfunctional_requirements", []),
            "constraints": normalized.get("constraints", []),
            "required_capabilities": capability_hints,
            "expected_artifacts": ["mission_contract", "implementation_plan", "verification_plan", "work_receipt"],
            "verification_plan": verification.get("verification_methods") or VERIFICATION_BY_INTENT.get(primary_intent, ["build verification", "manual review"]),
            "approval_gates": approvals.get("approval_gates") or [{"approval_key": "human_plan_approval", "requires_human": True}],
            "risk_profile": risk.get("risk_profile") or {
                "level": "high" if primary_intent in {"security_change", "database_change", "infrastructure_change"} else "medium",
                "drivers": [primary_intent, *intent.get("secondary_intents", [])][:4],
            },
        }
        return {"status": "passed", "proposal": proposal, "warning_codes": [], "cost_usd": 0.0}
