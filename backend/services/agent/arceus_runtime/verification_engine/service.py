from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import subprocess
import time
from typing import Any

from ..compiler.utils import stable_hash
from .api_schemas import (
    ContractValidationError,
    DiscoveredTestCommand,
    EvidenceInput,
    EvidenceProducerRequest,
    EvidenceProducerResponse,
    OutputContractValidationRequest,
    OutputContractValidationResponse,
    PlannedVerificationCheck,
    QualityGateDefinition,
    QualityGateResult,
    ReleaseReadinessRequest,
    ReleaseReadinessResponse,
    ReviewFinding,
    ReviewRequest,
    ReviewResponse,
    ReviewVerdict,
    TestDiscoveryResponse,
    VerificationTestDiscoveryRequest,
    VerificationCheckDefinition,
    VerificationExecutionGroup,
    VerificationPlanRequest,
    VerificationPlanResponse,
    VerificationRunRequest,
    VerificationRunResponse,
    VerificationWorkerJobResponse,
)


DEFAULT_GATES = [
    QualityGateDefinition(gate_key="build", name="Build", category="build", evidence_type="build", required=True),
    QualityGateDefinition(gate_key="tests", name="Tests", category="test", evidence_type="test", required=True),
    QualityGateDefinition(gate_key="security", name="Security Review", category="security", evidence_type="security_scan", required=True),
    QualityGateDefinition(gate_key="review", name="Independent Review", category="review", evidence_type="code_review", required=True),
]

VERIFIED_STATUSES = {"validated", "trusted", "verified", "passed"}
TRUST_WEIGHTS = {
    "unverified": 0.2,
    "ai_reviewed": 0.55,
    "tool_verified": 0.78,
    "independent_review": 0.9,
    "human_approved": 0.96,
    "production_observed": 1.0,
}
SEVERITY_WEIGHTS = {"info": 0, "low": 3, "medium": 9, "moderate": 9, "high": 22, "critical": 40}
EVIDENCE_PRODUCERS = {
    "output_contract": "contract",
    "syntax": "build",
    "compile": "build",
    "type_check": "build",
    "lint": "lint",
    "unit_tests": "test",
    "integration_tests": "test",
    "secret_scan": "security",
    "dependency_scan": "security",
    "security_review": "review",
    "architecture_review": "review",
    "accessibility": "playwright",
    "independent_review": "review",
}
PRODUCER_EVIDENCE_TYPE = {
    "lint": "lint",
    "build": "build",
    "test": "test",
    "security": "security_scan",
    "playwright": "accessibility",
    "github_checks": "github_check",
    "contract": "contract_validation",
    "review": "code_review",
}

CHECK_REGISTRY = [
    VerificationCheckDefinition(
        check_id="output_contract",
        name="Output Contract Validation",
        category="schema",
        supported_subject_types=["source_change", "configuration", "migration", "api_contract", "ui_change", "deployment", "artifact", "plan", "release"],
        deterministic=True,
        default_timeout_seconds=30,
        produces_evidence_types=["contract_validation"],
    ),
    VerificationCheckDefinition(
        check_id="syntax",
        name="Syntax Validation",
        category="syntax",
        supported_subject_types=["source_change", "configuration", "migration", "api_contract", "ui_change"],
        deterministic=True,
        required_tools=["parser"],
        default_timeout_seconds=120,
        produces_evidence_types=["syntax"],
    ),
    VerificationCheckDefinition(
        check_id="compile",
        name="Compilation / Build",
        category="compile",
        supported_subject_types=["source_change", "configuration", "migration", "api_contract", "ui_change", "release"],
        deterministic=True,
        required_tools=["tool_runtime"],
        default_timeout_seconds=900,
        produces_evidence_types=["build"],
    ),
    VerificationCheckDefinition(
        check_id="type_check",
        name="Type Checking",
        category="type_check",
        supported_subject_types=["source_change", "api_contract", "ui_change"],
        deterministic=True,
        required_tools=["tool_runtime"],
        default_timeout_seconds=600,
        produces_evidence_types=["type_check"],
    ),
    VerificationCheckDefinition(
        check_id="lint",
        name="Linting",
        category="lint",
        supported_subject_types=["source_change", "configuration", "ui_change"],
        deterministic=True,
        required_tools=["tool_runtime"],
        default_timeout_seconds=600,
        produces_evidence_types=["lint"],
    ),
    VerificationCheckDefinition(
        check_id="unit_tests",
        name="Targeted Unit Tests",
        category="unit_test",
        supported_subject_types=["source_change", "migration", "api_contract", "ui_change"],
        deterministic=True,
        required_tools=["tool_runtime"],
        default_timeout_seconds=1200,
        produces_evidence_types=["test"],
    ),
    VerificationCheckDefinition(
        check_id="integration_tests",
        name="Affected Integration Tests",
        category="integration_test",
        supported_subject_types=["source_change", "migration", "api_contract", "deployment", "release"],
        deterministic=True,
        required_tools=["tool_runtime"],
        default_timeout_seconds=1800,
        produces_evidence_types=["test"],
    ),
    VerificationCheckDefinition(
        check_id="secret_scan",
        name="Secret Scan",
        category="secret_scan",
        supported_subject_types=["source_change", "configuration", "deployment", "release"],
        deterministic=True,
        required_tools=["secret_scanner"],
        default_timeout_seconds=300,
        produces_evidence_types=["security_scan"],
    ),
    VerificationCheckDefinition(
        check_id="dependency_scan",
        name="Dependency Risk Scan",
        category="dependency",
        supported_subject_types=["source_change", "configuration", "deployment", "release"],
        deterministic=True,
        required_tools=["dependency_scanner"],
        default_timeout_seconds=600,
        produces_evidence_types=["security_scan"],
    ),
    VerificationCheckDefinition(
        check_id="security_review",
        name="Security Reviewer",
        category="security",
        supported_subject_types=["source_change", "configuration", "migration", "api_contract", "deployment", "release"],
        deterministic=False,
        required_capabilities=["security_review"],
        default_timeout_seconds=900,
        produces_evidence_types=["security_review"],
    ),
    VerificationCheckDefinition(
        check_id="architecture_review",
        name="Architecture Conformance",
        category="architecture",
        supported_subject_types=["source_change", "api_contract", "deployment", "plan", "release"],
        deterministic=False,
        required_capabilities=["architecture_review"],
        default_timeout_seconds=900,
        produces_evidence_types=["architecture_review"],
    ),
    VerificationCheckDefinition(
        check_id="accessibility",
        name="Accessibility Review",
        category="accessibility",
        supported_subject_types=["ui_change", "release"],
        deterministic=True,
        required_tools=["browser", "accessibility_scanner"],
        default_timeout_seconds=900,
        produces_evidence_types=["accessibility"],
    ),
    VerificationCheckDefinition(
        check_id="independent_review",
        name="Independent Code Review",
        category="ai_review",
        supported_subject_types=["source_change", "configuration", "migration", "api_contract", "ui_change", "deployment", "artifact", "plan", "release"],
        deterministic=False,
        required_capabilities=["independent_review"],
        default_timeout_seconds=900,
        produces_evidence_types=["code_review"],
    ),
]

PROFILE_CHECKS = {
    "documentation_light": ["output_contract", "syntax", "independent_review"],
    "frontend_standard": ["output_contract", "syntax", "compile", "type_check", "lint", "unit_tests", "accessibility", "independent_review"],
    "backend_standard": ["output_contract", "syntax", "compile", "type_check", "lint", "unit_tests", "integration_tests", "secret_scan", "dependency_scan", "independent_review"],
    "security_sensitive": ["output_contract", "syntax", "compile", "type_check", "lint", "unit_tests", "integration_tests", "secret_scan", "dependency_scan", "security_review", "independent_review"],
    "database_migration": ["output_contract", "syntax", "compile", "unit_tests", "integration_tests", "secret_scan", "security_review", "architecture_review", "independent_review"],
    "infrastructure_change": ["output_contract", "syntax", "compile", "secret_scan", "dependency_scan", "security_review", "architecture_review", "independent_review"],
    "production_deployment": ["output_contract", "compile", "integration_tests", "secret_scan", "dependency_scan", "security_review", "architecture_review", "independent_review"],
    "release_candidate": ["output_contract", "compile", "type_check", "lint", "unit_tests", "integration_tests", "secret_scan", "dependency_scan", "security_review", "architecture_review", "accessibility", "independent_review"],
    "critical_system_change": ["output_contract", "syntax", "compile", "type_check", "lint", "unit_tests", "integration_tests", "secret_scan", "dependency_scan", "security_review", "architecture_review", "independent_review"],
}


def check_registry() -> list[VerificationCheckDefinition]:
    return CHECK_REGISTRY


def evidence_producer_for_check(check_definition_id: str) -> str:
    return EVIDENCE_PRODUCERS.get(check_definition_id, "build")


def worker_jobs_for_plan(plan: VerificationPlanResponse, task_id: Any | None = None) -> list[VerificationWorkerJobResponse]:
    jobs: list[VerificationWorkerJobResponse] = []
    for item in plan.checks:
        idempotency_key = stable_hash({"mission_id": str(plan.mission_id), "plan_id": plan.plan_id, "check_id": item.check_id})
        jobs.append(
            VerificationWorkerJobResponse(
                job_id="vjob_" + idempotency_key[:24],
                mission_id=plan.mission_id,
                task_id=task_id,
                plan_id=plan.plan_id,
                check_id=item.check_id,
                check_definition_id=item.check_definition_id,
                category=item.category,
                evidence_producer=evidence_producer_for_check(item.check_definition_id),
                mandatory=item.mandatory,
                blocking=item.blocking,
                status="queued",
                inputs=item.inputs,
                depends_on=item.depends_on,
                timeout_seconds=item.timeout_seconds,
                attempts=0,
            )
        )
    return jobs


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?[^'\"\s]{8,}"),
]


def execute_worker_job_payload(job: Any, *, workspace_root: str | None = None) -> EvidenceProducerRequest:
    inputs = getattr(job, "inputs", None) or {}
    producer_key = getattr(job, "evidence_producer", "build")
    started = time.monotonic()
    command = inputs.get("command") or inputs.get("verification_command")
    if command:
        result = _run_command(command, inputs=inputs, timeout_seconds=int(getattr(job, "timeout_seconds", 300) or 300), workspace_root=workspace_root)
        return EvidenceProducerRequest(
            mission_id=job.mission_id,
            task_id=getattr(job, "task_id", None),
            worker_job_id=job.id,
            producer_key=producer_key,
            check_id=job.check_id,
            status="succeeded" if result["exit_code"] == 0 else "failed",
            command=command,
            exit_code=result["exit_code"],
            duration_ms=result["duration_ms"],
            output=result["output"],
            artifacts=result["artifacts"],
            payload=result["payload"],
        )

    if producer_key == "security":
        payload = _run_secret_scan(inputs, workspace_root=workspace_root)
    elif producer_key == "github_checks":
        payload = _evaluate_github_checks(inputs)
    elif producer_key == "playwright":
        payload = _evaluate_playwright_report(inputs)
    elif producer_key == "contract":
        payload = _evaluate_contract_inputs(inputs)
    elif producer_key == "review":
        payload = _evaluate_review_inputs(inputs)
    else:
        payload = {
            "status": "passed",
            "note": "No command was configured; evidence generated from verification job metadata.",
            "check_definition_id": getattr(job, "check_definition_id", None),
        }
    failed = payload.get("status") == "failed"
    return EvidenceProducerRequest(
        mission_id=job.mission_id,
        task_id=getattr(job, "task_id", None),
        worker_job_id=job.id,
        producer_key=producer_key,
        check_id=job.check_id,
        status="failed" if failed else "succeeded",
        duration_ms=int((time.monotonic() - started) * 1000),
        output=str(payload.get("summary") or payload.get("note") or ""),
        payload=payload,
    )


def _run_command(command: str, *, inputs: dict[str, Any], timeout_seconds: int, workspace_root: str | None = None) -> dict[str, Any]:
    cwd = inputs.get("working_directory") or workspace_root or "."
    started = time.monotonic()
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            encoding="utf-8",
            errors="replace",
        )
        output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
        return {
            "exit_code": completed.returncode,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "output": output[:20_000],
            "artifacts": [],
            "payload": {
                "status": "passed" if completed.returncode == 0 else "failed",
                "exit_code": completed.returncode,
                "stdout_excerpt": completed.stdout[:4000],
                "stderr_excerpt": completed.stderr[:4000],
            },
        }
    except subprocess.TimeoutExpired as exc:
        output = "\n".join(part for part in [exc.stdout or "", exc.stderr or ""] if part)
        return {
            "exit_code": 124,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "output": output[:20_000] or "Verification command timed out.",
            "artifacts": [],
            "payload": {"status": "failed", "error": "timeout", "timeout_seconds": timeout_seconds},
        }
    except Exception as exc:
        return {
            "exit_code": 1,
            "duration_ms": int((time.monotonic() - started) * 1000),
            "output": str(exc),
            "artifacts": [],
            "payload": {"status": "failed", "error": str(exc)},
        }


def _run_secret_scan(inputs: dict[str, Any], *, workspace_root: str | None = None) -> dict[str, Any]:
    changed_files = inputs.get("changed_files") or []
    root = Path(inputs.get("working_directory") or workspace_root or ".").resolve()
    findings: list[dict[str, Any]] = []
    for item in changed_files[:200]:
        path = (root / str(item)).resolve()
        try:
            if not str(path).startswith(str(root)) or not path.exists() or not path.is_file() or path.stat().st_size > 512_000:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append({"file": str(item), "rule": "possible_secret"})
                break
    return {
        "status": "failed" if findings else "passed",
        "critical": 0,
        "high": len(findings),
        "findings": findings,
        "summary": f"Secret scan found {len(findings)} possible secret(s)." if findings else "Secret scan passed.",
    }


def _evaluate_github_checks(inputs: dict[str, Any]) -> dict[str, Any]:
    checks = inputs.get("github_checks") or inputs.get("checks") or []
    failed = [item for item in checks if str(item.get("conclusion") or item.get("status")).lower() in {"failure", "failed", "cancelled", "timed_out", "action_required"}]
    pending = [item for item in checks if str(item.get("status")).lower() not in {"completed", "success", "passed"} and not item.get("conclusion")]
    return {
        "status": "failed" if failed or pending else "passed",
        "total": len(checks),
        "failed": len(failed),
        "pending": len(pending),
        "checks": checks,
        "summary": "GitHub checks passed." if not failed and not pending else "GitHub checks are not passing.",
    }


def _evaluate_playwright_report(inputs: dict[str, Any]) -> dict[str, Any]:
    console_errors = inputs.get("console_errors") or []
    failed_requests = inputs.get("failed_requests") or []
    blank_page = bool(inputs.get("blank_page"))
    failed = blank_page or bool(console_errors) or bool(failed_requests)
    return {
        "status": "failed" if failed else "passed",
        "blank_page": blank_page,
        "console_errors": console_errors,
        "failed_requests": failed_requests,
        "summary": "Preview verification failed." if failed else "Preview verification passed.",
    }


def _evaluate_contract_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    output = inputs.get("output") or {}
    required = inputs.get("required_fields") or []
    missing = [field for field in required if field not in output]
    return {
        "status": "failed" if missing else "passed",
        "missing_fields": missing,
        "summary": "Contract validation failed." if missing else "Contract validation passed.",
    }


def _evaluate_review_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    findings = inputs.get("findings") or []
    blockers = [item for item in findings if item.get("blocks_release") or item.get("severity") in {"high", "critical"}]
    return {
        "status": "failed" if blockers else "passed",
        "findings": findings,
        "summary": "Independent review found blockers." if blockers else "Independent review passed.",
    }


def normalize_evidence_producer_output(payload: EvidenceProducerRequest) -> EvidenceProducerResponse:
    evidence_type = PRODUCER_EVIDENCE_TYPE[payload.producer_key]
    failed = payload.status == "failed" or (payload.exit_code is not None and payload.exit_code != 0)
    cancelled = payload.status == "cancelled"
    normalized_status = "cancelled" if cancelled else "failed" if failed else "validated"
    trust_level = "independent_review" if payload.producer_key == "review" and not failed else "tool_verified"
    summary = producer_summary(payload, failed=failed, cancelled=cancelled)
    evidence = EvidenceInput(
        evidence_id="evidence_" + stable_hash(payload.model_dump(mode="json"))[:12],
        evidence_type=evidence_type,
        status="collected" if cancelled else "validated",
        trust_level=trust_level,
        summary=summary,
        payload={
            **payload.payload,
            "status": "failed" if failed else "cancelled" if cancelled else "passed",
            "producer_key": payload.producer_key,
            "check_id": payload.check_id,
            "exit_code": payload.exit_code,
            "duration_ms": payload.duration_ms,
            "output_excerpt": (payload.output or "")[:4000],
            "artifacts": payload.artifacts,
        },
        verification_method=payload.producer_key,
    )
    return EvidenceProducerResponse(
        producer_run_id="producer_" + stable_hash({"mission_id": str(payload.mission_id), "producer": payload.producer_key, "payload": payload.model_dump(mode="json")})[:24],
        mission_id=payload.mission_id,
        producer_key=payload.producer_key,
        normalized_status=normalized_status,
        evidence=evidence,
        retryable=failed and payload.producer_key in {"lint", "build", "test", "playwright", "github_checks"},
        blocks_release=failed and payload.producer_key in {"build", "test", "security", "github_checks"},
        summary=summary,
    )


def producer_summary(payload: EvidenceProducerRequest, *, failed: bool, cancelled: bool) -> str:
    label = {
        "lint": "Lint",
        "build": "Build",
        "test": "Tests",
        "security": "Security scan",
        "playwright": "Preview verification",
        "github_checks": "GitHub checks",
        "contract": "Contract validation",
        "review": "Independent review",
    }[payload.producer_key]
    if cancelled:
        return f"{label} was cancelled."
    if failed:
        reason = payload.payload.get("error") or payload.payload.get("conclusion") or payload.output[:160] or "non-zero result"
        return f"{label} failed: {reason}"
    if payload.producer_key == "test":
        total = payload.payload.get("total")
        passed = payload.payload.get("passed")
        if total is not None:
            return f"Tests passed ({passed or total}/{total})."
    if payload.producer_key == "github_checks":
        return f"GitHub checks passed for {payload.payload.get('ref') or payload.check_id or 'current ref'}."
    return f"{label} passed."


def plan_verification(payload: VerificationPlanRequest) -> VerificationPlanResponse:
    profile = payload.required_gate_profile or infer_profile(payload)
    requested = payload.requested_checks or PROFILE_CHECKS.get(profile, PROFILE_CHECKS["backend_standard"])
    registry = {item.check_id: item for item in CHECK_REGISTRY if item.enabled}
    checks: list[PlannedVerificationCheck] = []
    warnings: list[str] = []
    previous_categories: list[str] = []
    for index, check_id in enumerate(requested):
        definition = registry.get(check_id)
        if definition is None:
            warnings.append(f"Unknown verification check requested: {check_id}")
            continue
        if payload.subject_type not in definition.supported_subject_types:
            warnings.append(f"Check {check_id} is not normally used for {payload.subject_type}.")
        mandatory = is_mandatory(check_id, payload.risk_level, profile)
        checks.append(
            PlannedVerificationCheck(
                check_id=f"chk_{index + 1:02d}_{check_id}",
                check_definition_id=definition.check_id,
                name=definition.name,
                category=definition.category,
                mandatory=mandatory,
                blocking=mandatory,
                inputs={
                    "subject_reference": payload.subject_reference,
                    "repository_id": payload.repository_id,
                    "base_revision": payload.base_revision,
                    "target_revision": payload.target_revision,
                    "changed_files": payload.changed_files,
                },
                timeout_seconds=definition.default_timeout_seconds,
                depends_on=dependencies_for_check(definition.category, previous_categories),
                success_threshold=80 if definition.category in {"performance", "accessibility"} else None,
                failure_severity="critical" if payload.risk_level == "critical" and mandatory else "high" if mandatory else "medium",
            )
        )
        previous_categories.append(definition.category)
    deterministic = [item.check_id for item in checks if registry[item.check_definition_id].deterministic]
    reviewers = [item.check_id for item in checks if not registry[item.check_definition_id].deterministic]
    groups = [
        VerificationExecutionGroup(group_key="deterministic", check_ids=deterministic, parallel=False),
        VerificationExecutionGroup(group_key="reviewers", check_ids=reviewers, run_after=deterministic, parallel=True),
    ]
    duration = sum(item.timeout_seconds for item in checks if item.blocking)
    return VerificationPlanResponse(
        plan_id="vplan_" + stable_hash(payload.model_dump(mode="json"))[:24],
        mission_id=payload.mission_id,
        status="planning",
        profile_id=profile,
        risk_level=payload.risk_level,
        checks=checks,
        execution_groups=[group for group in groups if group.check_ids],
        mandatory_check_ids=[item.check_id for item in checks if item.mandatory],
        advisory_check_ids=[item.check_id for item in checks if not item.mandatory],
        estimated_duration_seconds=duration,
        estimated_cost_usd=round(len(reviewers) * 0.06 + len(checks) * 0.005, 4),
        repair_policy={
            "allow_repair": payload.allow_repair,
            "maximum_repair_attempts": payload.maximum_repair_attempts,
            "invalidate_stale_evidence": True,
            "stop_on_repeated_failure": True,
        },
        warnings=warnings,
    )


def infer_profile(payload: VerificationPlanRequest) -> str:
    files = " ".join(payload.changed_files).lower()
    if payload.subject_type == "release":
        return "release_candidate"
    if payload.subject_type == "deployment":
        return "production_deployment"
    if payload.subject_type == "migration" or any(term in files for term in ["migration", "schema", "alembic"]):
        return "database_migration"
    if payload.risk_level == "critical":
        return "critical_system_change"
    if any(term in files for term in ["auth", "login", "token", "password", "secret", "payment", "billing"]):
        return "security_sensitive"
    if payload.subject_type == "ui_change" or any(file.endswith((".tsx", ".jsx", ".css")) for file in payload.changed_files):
        return "frontend_standard"
    if payload.subject_type == "configuration" or any(file.endswith((".yml", ".yaml", "Dockerfile", ".toml")) for file in payload.changed_files):
        return "infrastructure_change"
    if payload.subject_type == "artifact" and all(file.endswith((".md", ".txt")) for file in payload.changed_files):
        return "documentation_light"
    return "backend_standard"


def is_mandatory(check_id: str, risk_level: str, profile: str) -> bool:
    if check_id in {"output_contract", "compile", "unit_tests", "secret_scan", "independent_review"}:
        return True
    if risk_level in {"high", "critical"} and check_id in {"integration_tests", "security_review", "architecture_review", "dependency_scan"}:
        return True
    if profile in {"release_candidate", "critical_system_change", "production_deployment"}:
        return True
    return False


def dependencies_for_check(category: str, previous_categories: list[str]) -> list[str]:
    if category in {"ai_review", "security", "architecture"}:
        return []
    if category in {"unit_test", "integration_test", "lint", "type_check"} and "compile" in previous_categories:
        return []
    return []


def validate_output_contract(payload: OutputContractValidationRequest) -> OutputContractValidationResponse:
    errors: list[ContractValidationError] = []
    missing = [field for field in payload.required_fields if field not in payload.output]
    for field in missing:
        errors.append(ContractValidationError(field=field, message="Required field is missing."))
    unsupported = sorted(set(payload.output) - set(payload.allowed_fields)) if payload.allowed_fields else []
    for field in unsupported:
        errors.append(ContractValidationError(field=field, message="Field is not supported by this output contract."))
    for field, expected in payload.field_types.items():
        if field not in payload.output:
            continue
        if not type_matches(payload.output[field], expected):
            errors.append(ContractValidationError(field=field, message=f"Expected {expected}, received {type(payload.output[field]).__name__}."))
    return OutputContractValidationResponse(
        schema_valid=not errors,
        required_fields_present=not missing,
        unsupported_fields=unsupported,
        validation_errors=errors,
    )


def discover_tests(payload: VerificationTestDiscoveryRequest) -> TestDiscoveryResponse:
    files = payload.repository_files
    lower_files = [item.replace("\\", "/").lower() for item in files]
    commands: list[DiscoveredTestCommand] = []
    warnings: list[str] = []
    for script_name, command in payload.package_scripts.items():
        normalized = script_name.lower()
        if "test:e2e" in normalized or "e2e" in normalized:
            test_type = "e2e"
        elif "integration" in normalized:
            test_type = "integration"
        elif "smoke" in normalized:
            test_type = "smoke"
        else:
            test_type = "unit"
        if "test" in normalized or test_type != "unit":
            commands.append(
                DiscoveredTestCommand(
                    command_id=f"npm_{normalized.replace(':', '_')}",
                    command=f"npm run {script_name}",
                    test_type=test_type,
                    source="package_manifest",
                    confidence=0.92,
                )
            )
    if not commands:
        if any(item.endswith("pytest.ini") or item.endswith("pyproject.toml") for item in lower_files):
            commands.append(DiscoveredTestCommand(command_id="pytest", command="python -m pytest", test_type="unit", source="convention", confidence=0.78))
        elif any(item.endswith("package.json") for item in lower_files):
            commands.append(DiscoveredTestCommand(command_id="npm_test", command="npm test", test_type="unit", source="convention", confidence=0.7))
        else:
            warnings.append("No test command discovered from manifests or conventions.")
    unit_locations = sorted({item for item in files if any(marker in item.lower() for marker in ["test_", ".test.", ".spec.", "__tests__"])})
    integration_locations = sorted({item for item in files if "integration" in item.lower()})
    e2e_locations = sorted({item for item in files if "e2e" in item.lower() or "playwright" in item.lower() or "cypress" in item.lower()})
    framework = payload.framework or infer_test_framework(lower_files, payload.package_scripts)
    confidence = round(min(1.0, (0.45 if commands else 0.1) + len(unit_locations[:5]) * 0.05 + (0.2 if framework else 0)), 3)
    return TestDiscoveryResponse(
        framework=framework,
        commands=commands,
        unit_test_locations=unit_locations,
        integration_test_locations=integration_locations,
        end_to_end_test_locations=e2e_locations,
        coverage_available=any("coverage" in key.lower() or "coverage" in value.lower() for key, value in payload.package_scripts.items()),
        confidence=confidence,
        warnings=warnings,
    )


def infer_test_framework(files: list[str], scripts: dict[str, str]) -> str | None:
    joined = " ".join(files + list(scripts.values())).lower()
    if "playwright" in joined:
        return "Playwright"
    if "cypress" in joined:
        return "Cypress"
    if "vitest" in joined:
        return "Vitest"
    if "jest" in joined:
        return "Jest"
    if "pytest" in joined:
        return "Pytest"
    return None


def type_matches(value: Any, expected: str) -> bool:
    expected = expected.lower()
    if expected in {"str", "string"}:
        return isinstance(value, str)
    if expected in {"int", "integer"}:
        return isinstance(value, int) and not isinstance(value, bool)
    if expected in {"float", "number"}:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected in {"bool", "boolean"}:
        return isinstance(value, bool)
    if expected in {"list", "array"}:
        return isinstance(value, list)
    if expected in {"dict", "object"}:
        return isinstance(value, dict)
    return True


def run_verification(payload: VerificationRunRequest) -> VerificationRunResponse:
    gates = payload.gates or DEFAULT_GATES
    gate_results = [evaluate_quality_gate(gate, payload.evidence, payload.changed_files) for gate in gates]
    findings = _dedupe_findings([finding for gate in gate_results for finding in gate.findings] + semantic_findings(payload.changed_files, payload.evidence))
    evidence_score = score_evidence(payload.evidence)
    penalties = sum(SEVERITY_WEIGHTS[finding.severity] for finding in findings)
    gate_score = sum(result.score for result in gate_results) / len(gate_results) if gate_results else 100.0
    overall = round(max(0.0, min(100.0, gate_score * 0.65 + evidence_score * 0.35 - penalties)), 2)
    blockers = [finding for finding in findings if finding.blocks_release or finding.severity in {"critical", "high"}]
    failed_required = [result for result in gate_results if result.required and result.status in {"failed", "blocked"}]
    release_blockers = blockers + [finding for result in failed_required for finding in result.findings]
    status = "passed" if not release_blockers and not failed_required and overall >= 75 else "blocked" if release_blockers or failed_required else "warning"
    verdict = verdict_from_score_and_findings(overall, release_blockers, findings)
    actions = recommended_actions(gate_results, findings, payload.release_candidate)
    return VerificationRunResponse(
        run_id="ver_" + stable_hash(payload.model_dump(mode="json"))[:24],
        mission_id=payload.mission_id,
        target_type=payload.target_type,
        target_id=payload.target_id or payload.mission_id,
        status=status,
        overall_score=overall,
        verdict=verdict,
        gate_results=gate_results,
        findings=findings,
        evidence_score=evidence_score,
        release_blockers=release_blockers,
        recommended_actions=actions,
        repair_loop_required=verdict in {"changes_requested", "blocked"},
        events=["VERIFICATION_STARTED", "QUALITY_GATES_EVALUATED", "AUTONOMOUS_REVIEW_COMPLETED", "VERIFICATION_BLOCKED" if status == "blocked" else "VERIFICATION_PASSED"],
    )


def evaluate_quality_gate(gate: QualityGateDefinition, evidence: list[EvidenceInput], changed_files: list[str] | None = None) -> QualityGateResult:
    matches = [
        item
        for item in evidence
        if item.evidence_type == (gate.evidence_type or gate.gate_key)
        or item.verification_method == (gate.command_key or gate.evidence_type or gate.gate_key)
    ]
    trusted = [item for item in matches if item.status in VERIFIED_STATUSES]
    findings: list[ReviewFinding] = []
    score = 100.0
    if not trusted:
        severity = "high" if gate.required else "medium"
        findings.append(
            ReviewFinding(
                finding_key=f"{gate.gate_key}.missing_evidence",
                severity=severity,
                title=f"{gate.name} evidence is missing",
                detail=f"Required evidence type `{gate.evidence_type or gate.gate_key}` was not found.",
                recommendation=f"Run or attach evidence for {gate.name}.",
                blocks_release=gate.required,
            )
        )
        return QualityGateResult(gate_key=gate.gate_key, name=gate.name, category=gate.category, required=gate.required, status="blocked" if gate.required else "warning", score=0.0, findings=findings, reason="missing_evidence")

    latest = trusted[-1]
    payload = latest.payload or {}
    if _has_failed_command(payload):
        findings.append(
            ReviewFinding(
                finding_key=f"{gate.gate_key}.command_failed",
                severity="high" if gate.required else "medium",
                title=f"{gate.name} failed",
                detail=str(payload.get("error") or payload.get("stderr") or payload.get("summary") or "Command reported failure."),
                evidence_ids=[latest.evidence_id],
                recommendation="Fix the failure and rerun the gate.",
                blocks_release=gate.required,
            )
        )
        return QualityGateResult(gate_key=gate.gate_key, name=gate.name, category=gate.category, required=gate.required, status="failed", score=0.0, evidence_ids=[item.evidence_id for item in trusted], findings=findings, reason="command_failed")

    if gate.category == "test":
        failed = _int(payload.get("failed"))
        total = _int(payload.get("total"))
        if failed > 0:
            score = max(0.0, 100.0 - failed * 18)
            findings.append(
                ReviewFinding(
                    finding_key=f"{gate.gate_key}.tests_failed",
                    severity="high",
                    title="Tests are failing",
                    detail=f"{failed} test(s) failed out of {total or 'unknown'} total.",
                    evidence_ids=[latest.evidence_id],
                    recommendation="Repair failing tests before completion.",
                    blocks_release=gate.required,
                )
            )
    if gate.category == "security":
        critical = _int(payload.get("critical"))
        high = _int(payload.get("high"))
        if critical or high:
            score = max(0.0, 100.0 - critical * 40 - high * 20)
            findings.append(
                ReviewFinding(
                    finding_key=f"{gate.gate_key}.security_findings",
                    severity="critical" if critical else "high",
                    title="Security findings block release",
                    detail=f"Security scan found {critical} critical and {high} high issue(s).",
                    evidence_ids=[latest.evidence_id],
                    recommendation="Resolve high and critical security findings or obtain explicit security approval.",
                    blocks_release=True,
                )
            )
    if gate.minimum_score is not None and score < gate.minimum_score:
        findings.append(
            ReviewFinding(
                finding_key=f"{gate.gate_key}.score_below_minimum",
                severity="medium",
                title="Quality score below required minimum",
                detail=f"Gate score {score:.1f} is below required {gate.minimum_score:.1f}.",
                evidence_ids=[latest.evidence_id],
                recommendation="Improve the gate result and rerun verification.",
                blocks_release=gate.required,
            )
        )

    status = "passed" if not [item for item in findings if item.blocks_release] else "failed"
    return QualityGateResult(
        gate_key=gate.gate_key,
        name=gate.name,
        category=gate.category,
        required=gate.required,
        status=status,
        score=round(score, 2),
        evidence_ids=[item.evidence_id for item in trusted],
        findings=findings,
        reason="gate_passed" if status == "passed" else "gate_failed",
    )


def perform_autonomous_review(payload: ReviewRequest) -> ReviewResponse:
    findings = semantic_findings(payload.changed_files, payload.evidence, diff_summary=payload.diff_summary)
    score = round(max(0.0, 100.0 - sum(SEVERITY_WEIGHTS[item.severity] for item in findings)), 2)
    blockers = [item for item in findings if item.blocks_release or item.severity in {"critical", "high"}]
    verdict = verdict_from_score_and_findings(score, blockers, findings)
    return ReviewResponse(
        review_id="review_" + stable_hash(payload.model_dump(mode="json"))[:24],
        mission_id=payload.mission_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        reviewer_role=payload.reviewer_role,
        verdict=verdict,
        score=score,
        findings=findings,
        evidence_ids=[item.evidence_id for item in payload.evidence if item.status in VERIFIED_STATUSES],
        independent_review_required=bool(blockers) or payload.reviewer_role not in {"qa_reviewer", "security_reviewer", "architecture_reviewer"},
    )


def evaluate_release_readiness(payload: ReleaseReadinessRequest) -> ReleaseReadinessResponse:
    blockers: list[str] = []
    warnings: list[str] = []
    failed_required = [gate for gate in payload.gate_results if gate.required and gate.status in {"failed", "blocked"}]
    if failed_required:
        blockers.extend([f"Required gate not passing: {gate.name}" for gate in failed_required])
    blocking_findings = [finding for gate in payload.gate_results for finding in gate.findings if finding.blocks_release or finding.severity in {"critical", "high"}]
    blockers.extend([finding.title for finding in blocking_findings])
    completed_reviews = [review for review in payload.reviews if review.verdict in {"approved", "approved_with_warnings"}]
    if not completed_reviews:
        blockers.append("At least one independent review is required.")
    elif any(review.verdict == "approved_with_warnings" for review in completed_reviews):
        warnings.append("One or more reviews approved with warnings.")
    if payload.require_human_approval and not any(item.get("status") == "approved" and item.get("actor_type") == "human" for item in payload.approvals):
        blockers.append("Human approval is required before release.")
    gate_score = sum(gate.score for gate in payload.gate_results) / len(payload.gate_results) if payload.gate_results else 0.0
    review_score = sum(review.score for review in completed_reviews) / len(completed_reviews) if completed_reviews else 0.0
    score = round(gate_score * 0.65 + review_score * 0.35, 2)
    ready = not blockers and score >= 75
    return ReleaseReadinessResponse(
        ready=ready,
        status="ready" if ready else "blocked" if blockers else "review_required",
        score=score,
        blockers=blockers,
        warnings=warnings,
        required_actions=release_actions(blockers, warnings),
        evidence_summary={
            "gate_count": len(payload.gate_results),
            "passed_gates": len([gate for gate in payload.gate_results if gate.status == "passed"]),
            "review_count": len(payload.reviews),
            "approval_count": len(payload.approvals),
        },
    )


def score_evidence(evidence: list[EvidenceInput]) -> float:
    if not evidence:
        return 0.0
    scores = []
    for item in evidence:
        status_bonus = 1.0 if item.status in VERIFIED_STATUSES else 0.35
        trust = TRUST_WEIGHTS.get(item.trust_level, 0.2)
        scores.append(status_bonus * trust * 100.0)
    return round(sum(scores) / len(scores), 2)


def semantic_findings(changed_files: list[str], evidence: list[EvidenceInput], diff_summary: str = "") -> list[ReviewFinding]:
    findings: list[ReviewFinding] = []
    text = " ".join(changed_files + [diff_summary]).lower()
    evidence_types = {item.evidence_type for item in evidence if item.status in VERIFIED_STATUSES}
    if any(term in text for term in ["auth", "login", "token", "password", "secret"]) and "security_scan" not in evidence_types:
        findings.append(
            ReviewFinding(
                finding_key="semantic.security_evidence_missing",
                severity="high",
                title="Security-sensitive change lacks security evidence",
                detail="Authentication, token, password, or secret-related files changed without verified security scan evidence.",
                recommendation="Run security scan and request independent security review.",
                blocks_release=True,
            )
        )
    if any(term in text for term in ["migration", "schema", "alembic"]) and "migration_dry_run" not in evidence_types:
        findings.append(
            ReviewFinding(
                finding_key="semantic.migration_dry_run_missing",
                severity="high",
                title="Database migration lacks dry-run evidence",
                detail="Migration or schema files changed without a verified migration dry run.",
                recommendation="Run migration dry-run and rollback verification.",
                blocks_release=True,
            )
        )
    if any(file.endswith((".tsx", ".jsx", ".css")) for file in changed_files) and "accessibility" not in evidence_types:
        findings.append(
            ReviewFinding(
                finding_key="semantic.accessibility_evidence_missing",
                severity="medium",
                title="UI change lacks accessibility evidence",
                detail="Frontend UI files changed without accessibility verification evidence.",
                recommendation="Run accessibility smoke checks or attach reviewer evidence.",
                blocks_release=False,
            )
        )
    if changed_files and "test" not in evidence_types and not any("test" in file.lower() or "spec" in file.lower() for file in changed_files):
        findings.append(
            ReviewFinding(
                finding_key="semantic.test_evidence_missing",
                severity="medium",
                title="Change lacks test evidence",
                detail="No verified test evidence was attached for this change.",
                recommendation="Run relevant tests or document why tests are not applicable.",
                blocks_release=False,
            )
        )
    return findings


def verdict_from_score_and_findings(score: float, blockers: list[ReviewFinding], findings: list[ReviewFinding]) -> ReviewVerdict:
    if blockers or any(item.severity == "critical" for item in findings):
        return "blocked"
    if any(item.severity == "high" for item in findings) or score < 65:
        return "changes_requested"
    if findings or score < 85:
        return "approved_with_warnings"
    return "approved"


def recommended_actions(gates: list[QualityGateResult], findings: list[ReviewFinding], release_candidate: bool) -> list[str]:
    actions: list[str] = []
    for gate in gates:
        if gate.status in {"failed", "blocked"}:
            actions.append(f"rerun_{gate.gate_key}_after_fix")
    severities = Counter(finding.severity for finding in findings)
    if severities["critical"] or severities["high"]:
        actions.append("start_repair_loop")
        actions.append("request_independent_review")
    if release_candidate:
        actions.append("block_release_until_required_gates_pass")
    if not actions:
        actions.append("promote_verification_evidence")
    return list(dict.fromkeys(actions))


def release_actions(blockers: list[str], warnings: list[str]) -> list[str]:
    if blockers:
        return ["resolve_release_blockers", "rerun_quality_gates", "request_human_approval"]
    if warnings:
        return ["review_warnings_before_release"]
    return ["release_candidate_ready"]


def _has_failed_command(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or payload.get("conclusion") or "").lower()
    exit_code = payload.get("exit_code")
    failed = payload.get("failed")
    if status in {"failed", "failure", "error"}:
        return True
    if exit_code is not None and _int(exit_code) != 0:
        return True
    return failed is not None and _int(failed) > 0 and "total" not in payload


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _dedupe_findings(findings: list[ReviewFinding]) -> list[ReviewFinding]:
    deduped: dict[str, ReviewFinding] = {}
    for finding in findings:
        deduped[finding.finding_key] = finding
    return list(deduped.values())
