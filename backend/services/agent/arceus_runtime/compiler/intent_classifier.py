from __future__ import annotations


INTENT_KEYWORDS: dict[str, tuple[str, ...]] = {
    "authentication_change": ("auth", "login", "signin", "sign in", "oauth", "clerk", "session", "password", "passkey"),
    "authorization_change": ("permission", "role", "rbac", "policy", "access control", "authorize"),
    "security_change": ("security", "secret", "vulnerability", "csrf", "xss", "injection", "encrypt", "token"),
    "database_change": ("database", "postgres", "migration", "schema", "model", "sql", "query"),
    "infrastructure_change": ("docker", "redis", "celery", "railway", "deploy", "worker", "queue"),
    "performance_improvement": ("performance", "speed", "latency", "optimize", "cache", "slow"),
    "dependency_upgrade": ("upgrade", "dependency", "package", "npm install", "pip install"),
    "documentation": ("docs", "documentation", "readme", "guide", "runbook"),
    "testing_improvement": ("test", "pytest", "unit test", "e2e", "coverage", "verify"),
    "bug_fix": ("bug", "fix", "broken", "error", "crash", "failed", "not working"),
    "refactoring": ("refactor", "split", "cleanup", "simplify", "extract"),
    "repository_analysis": ("analyze", "inspect", "review repository", "understand codebase"),
    "feature_development": ("add", "create", "build", "implement", "support", "enable"),
}


CAPABILITY_HINTS: dict[str, tuple[str, ...]] = {
    "authentication_change": ("authentication_review", "authorization_review", "fastapi_development", "frontend_testing"),
    "authorization_change": ("authorization_review", "secure_code_review", "api_design"),
    "security_change": ("threat_modeling", "secrets_review", "secure_code_review"),
    "database_change": ("postgresql_design", "database_migration", "query_optimization"),
    "infrastructure_change": ("docker_configuration", "cloud_deployment", "observability"),
    "performance_improvement": ("frontend_performance", "query_optimization", "caching_strategy"),
    "dependency_upgrade": ("dependency_security", "build_verification", "regression_testing"),
    "documentation": ("release_management", "acceptance_criteria_definition"),
    "testing_improvement": ("unit_test_design", "integration_testing", "evidence_validation"),
    "bug_fix": ("build_verification", "regression_testing", "evidence_validation"),
    "refactoring": ("architecture_tradeoff_analysis", "regression_testing", "secure_code_review"),
    "repository_analysis": ("requirement_analysis", "system_architecture", "evidence_validation"),
    "feature_development": ("requirement_analysis", "acceptance_criteria_definition", "api_design"),
}


class IntentClassificationStage:
    stage_key = "intent_classification"

    def run(self, payload: dict) -> dict:
        normalized = payload["input_normalization"]["output"]["normalized"]
        text = " ".join(
            [
                normalized["objective"],
                *normalized.get("constraints", []),
                *normalized.get("desired_outcomes", []),
            ]
        ).casefold()
        matches: list[tuple[str, int]] = []
        for intent, keywords in INTENT_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in text)
            if score:
                matches.append((intent, score))
        matches.sort(key=lambda item: (-item[1], item[0]))
        primary_intent = matches[0][0] if matches else "unknown"
        secondary_intents = [intent for intent, _score in matches[1:5]]
        capability_hints = sorted(
            {
                capability
                for intent in [primary_intent, *secondary_intents]
                for capability in CAPABILITY_HINTS.get(intent, ())
            }
        )
        warning_codes = ["intent_unknown"] if primary_intent == "unknown" else []
        return {
            "status": "passed" if primary_intent != "unknown" else "needs_clarification",
            "primary_intent": primary_intent,
            "secondary_intents": secondary_intents,
            "required_capability_hints": capability_hints,
            "warning_codes": warning_codes,
            "cost_usd": 0.0,
        }

