from __future__ import annotations


CAPABILITY_CATALOG: dict[str, dict] = {
    "requirement_analysis": {"domain": "Product", "name": "Requirement Analysis", "verification_methods": ["product_review"]},
    "acceptance_criteria_definition": {"domain": "Product", "name": "Acceptance Criteria Definition", "verification_methods": ["criteria_review"]},
    "system_architecture": {"domain": "Architecture", "name": "System Architecture", "verification_methods": ["architecture_review"]},
    "architecture_tradeoff_analysis": {"domain": "Architecture", "name": "Architecture Tradeoff Analysis", "verification_methods": ["architecture_review"]},
    "api_design": {"domain": "Backend", "name": "API Design", "verification_methods": ["api_contract_review"]},
    "fastapi_development": {"domain": "Backend", "name": "FastAPI Development", "verification_methods": ["backend_tests"]},
    "python_backend_development": {"domain": "Backend", "name": "Python Backend Development", "verification_methods": ["backend_tests"]},
    "postgresql_design": {"domain": "Database", "name": "PostgreSQL Design", "verification_methods": ["migration_dry_run"]},
    "database_migration": {"domain": "Database", "name": "Database Migration", "verification_methods": ["migration_dry_run", "rollback_dry_run"]},
    "react_development": {"domain": "Frontend", "name": "React Development", "verification_methods": ["frontend_build"]},
    "nextjs_development": {"domain": "Frontend", "name": "Next.js Development", "verification_methods": ["frontend_build"]},
    "responsive_ui": {"domain": "Frontend", "name": "Responsive UI", "verification_methods": ["viewport_smoke"]},
    "accessibility_review": {"domain": "Frontend", "name": "Accessibility Review", "verification_methods": ["accessibility_review"]},
    "frontend_testing": {"domain": "Quality", "name": "Frontend Testing", "verification_methods": ["frontend_tests"]},
    "unit_test_design": {"domain": "Quality", "name": "Unit Test Design", "verification_methods": ["test_review"]},
    "integration_testing": {"domain": "Quality", "name": "Integration Testing", "verification_methods": ["integration_tests"]},
    "build_verification": {"domain": "Quality", "name": "Build Verification", "verification_methods": ["build"]},
    "evidence_validation": {"domain": "Quality", "name": "Evidence Validation", "verification_methods": ["evidence_review"]},
    "authentication_review": {"domain": "Security", "name": "Authentication Review", "verification_methods": ["security_review"]},
    "authorization_review": {"domain": "Security", "name": "Authorization Review", "verification_methods": ["security_review"]},
    "secure_code_review": {"domain": "Security", "name": "Secure Code Review", "verification_methods": ["security_review"]},
    "secrets_review": {"domain": "Security", "name": "Secrets Review", "verification_methods": ["secret_scan"]},
    "dependency_security": {"domain": "Security", "name": "Dependency Security", "verification_methods": ["dependency_scan"]},
    "docker_configuration": {"domain": "Operations", "name": "Docker Configuration", "verification_methods": ["container_smoke"]},
    "cloud_deployment": {"domain": "Operations", "name": "Cloud Deployment", "verification_methods": ["deployment_smoke"]},
    "observability": {"domain": "Operations", "name": "Observability", "verification_methods": ["metrics_check"]},
    "release_management": {"domain": "Operations", "name": "Release Management", "verification_methods": ["release_gate"]},
}


SPECIALIST_REGISTRY: dict[str, dict] = {
    "mission_lead": {
        "display_name": "Mission Lead",
        "type": "ai",
        "capabilities": ("requirement_analysis", "acceptance_criteria_definition"),
        "authority": {"can_coordinate": True, "can_change_plan": True},
    },
    "product_analyst": {
        "display_name": "Product Analyst",
        "type": "ai",
        "capabilities": ("requirement_analysis", "acceptance_criteria_definition"),
        "authority": {"can_read_requirements": True},
    },
    "solution_architect": {
        "display_name": "Solution Architect",
        "type": "ai",
        "capabilities": ("system_architecture", "architecture_tradeoff_analysis", "api_design"),
        "authority": {"can_propose_architecture": True},
    },
    "backend_engineer": {
        "display_name": "Backend Engineer",
        "type": "ai",
        "capabilities": ("python_backend_development", "fastapi_development", "api_design", "postgresql_design", "database_migration"),
        "authority": {"can_read_repository": True, "can_write_backend_paths": True, "can_run_tests": True},
    },
    "frontend_engineer": {
        "display_name": "Frontend Engineer",
        "type": "ai",
        "capabilities": ("react_development", "nextjs_development", "responsive_ui", "frontend_testing"),
        "authority": {"can_read_repository": True, "can_write_frontend_paths": True, "can_run_tests": True},
    },
    "qa_reviewer": {
        "display_name": "QA Reviewer",
        "type": "ai",
        "capabilities": ("unit_test_design", "integration_testing", "build_verification", "evidence_validation"),
        "authority": {"can_review_tests": True, "can_validate_evidence": True},
    },
    "security_reviewer": {
        "display_name": "Security Reviewer",
        "type": "ai",
        "capabilities": ("authentication_review", "authorization_review", "secure_code_review", "secrets_review", "dependency_security"),
        "authority": {"can_veto_unsafe_changes": True, "can_review_security": True},
    },
    "devops_reviewer": {
        "display_name": "DevOps Reviewer",
        "type": "ai",
        "capabilities": ("docker_configuration", "cloud_deployment", "observability", "release_management"),
        "authority": {"can_review_deployment": True, "can_validate_release_gate": True},
    },
    "human_approver": {
        "display_name": "Human Approver",
        "type": "human",
        "capabilities": ("acceptance_criteria_definition",),
        "authority": {"can_approve_plan": True, "can_govern_execution": True},
    },
}

