from __future__ import annotations

from uuid import uuid4

from backend.services.agent.arceus_runtime.verification_engine.api_schemas import (
    EvidenceInput,
    EvidenceProducerRequest,
    MissionControlReleaseGateResponse,
    OutputContractValidationRequest,
    QualityGateDefinition,
    ReleaseReadinessRequest,
    ReviewRequest,
    VerificationPlanRequest,
    VerificationRunRequest,
    VerificationTestDiscoveryRequest,
)
from backend.services.agent.arceus_runtime.verification_engine.service import (
    discover_tests,
    evaluate_quality_gate,
    evaluate_release_readiness,
    execute_worker_job_payload,
    normalize_evidence_producer_output,
    perform_autonomous_review,
    plan_verification,
    run_verification,
    score_evidence,
    validate_output_contract,
    worker_jobs_for_plan,
)


def _evidence(evidence_type: str, payload: dict | None = None, *, trust: str = "tool_verified", status: str = "validated") -> EvidenceInput:
    return EvidenceInput(evidence_type=evidence_type, payload=payload or {"status": "passed"}, trust_level=trust, status=status)


class _FakeWorkerJob:
    def __init__(self, *, evidence_producer: str, inputs: dict, check_id: str = "check_1") -> None:
        self.id = uuid4()
        self.mission_id = uuid4()
        self.task_id = None
        self.worker_job_id = self.id
        self.evidence_producer = evidence_producer
        self.check_id = check_id
        self.check_definition_id = check_id
        self.timeout_seconds = 30
        self.inputs = inputs


def test_quality_gate_passes_with_verified_matching_evidence() -> None:
    gate = QualityGateDefinition(gate_key="build", name="Build", category="build", evidence_type="build")

    result = evaluate_quality_gate(gate, [_evidence("build", {"exit_code": 0})])

    assert result.status == "passed"
    assert result.score == 100


def test_quality_gate_fails_failed_tests() -> None:
    gate = QualityGateDefinition(gate_key="tests", name="Tests", category="test", evidence_type="test")

    result = evaluate_quality_gate(gate, [_evidence("test", {"total": 12, "failed": 2})])

    assert result.status == "failed"
    assert result.findings[0].finding_key == "tests.tests_failed"
    assert result.findings[0].blocks_release is True


def test_autonomous_review_blocks_auth_change_without_security_evidence() -> None:
    response = perform_autonomous_review(
        ReviewRequest(
            changed_files=["backend/services/auth/login.py"],
            diff_summary="Changed token validation logic",
            evidence=[_evidence("test")],
        )
    )

    assert response.verdict == "blocked"
    assert any(finding.finding_key == "semantic.security_evidence_missing" for finding in response.findings)


def test_verification_run_combines_gates_and_semantic_findings() -> None:
    response = run_verification(
        VerificationRunRequest(
            changed_files=["frontend/src/Login.tsx"],
            evidence=[_evidence("build"), _evidence("test"), _evidence("security_scan"), _evidence("code_review", trust="independent_review")],
            release_candidate=True,
        )
    )

    assert response.status in {"passed", "warning"}
    assert response.verdict in {"approved", "approved_with_warnings"}
    assert any(finding.finding_key == "semantic.accessibility_evidence_missing" for finding in response.findings)


def test_release_readiness_requires_human_approval() -> None:
    run = run_verification(
        VerificationRunRequest(
            evidence=[_evidence("build"), _evidence("test"), _evidence("security_scan"), _evidence("code_review", trust="independent_review")],
        )
    )
    review = perform_autonomous_review(ReviewRequest(evidence=[_evidence("test")]))

    readiness = evaluate_release_readiness(ReleaseReadinessRequest(gate_results=run.gate_results, reviews=[review], approvals=[]))

    assert readiness.ready is False
    assert "Human approval is required before release." in readiness.blockers


def test_release_readiness_passes_with_gates_review_and_human_approval() -> None:
    run = run_verification(
        VerificationRunRequest(
            evidence=[_evidence("build"), _evidence("test"), _evidence("security_scan"), _evidence("code_review", trust="independent_review")],
        )
    )
    review = perform_autonomous_review(ReviewRequest(evidence=[_evidence("test")]))

    readiness = evaluate_release_readiness(
        ReleaseReadinessRequest(
            gate_results=run.gate_results,
            reviews=[review],
            approvals=[{"status": "approved", "actor_type": "human"}],
        )
    )

    assert readiness.ready is True
    assert readiness.status == "ready"


def test_evidence_scoring_rewards_higher_trust() -> None:
    low = score_evidence([_evidence("build", trust="unverified", status="collected")])
    high = score_evidence([_evidence("build", trust="production_observed", status="verified")])

    assert high > low
    assert high == 100


def test_security_gate_blocks_high_findings() -> None:
    gate = QualityGateDefinition(gate_key="security", name="Security", category="security", evidence_type="security_scan")

    result = evaluate_quality_gate(gate, [_evidence("security_scan", {"critical": 0, "high": 1})])

    assert result.status == "failed"
    assert result.findings[0].severity == "high"


def test_run_id_is_deterministic_for_same_payload() -> None:
    mission_id = uuid4()
    payload = VerificationRunRequest(mission_id=mission_id, evidence=[_evidence("build")])

    assert run_verification(payload).run_id == run_verification(payload).run_id


def test_planner_selects_security_profile_for_auth_changes() -> None:
    plan = plan_verification(
        VerificationPlanRequest(
            subject_type="source_change",
            risk_level="high",
            changed_files=["backend/services/auth/session_tokens.py"],
            subject_reference="patch-1",
        )
    )

    assert plan.profile_id == "security_sensitive"
    assert any(item.check_definition_id == "security_review" and item.mandatory for item in plan.checks)
    assert "reviewers" in [group.group_key for group in plan.execution_groups]


def test_planner_selects_database_migration_profile() -> None:
    plan = plan_verification(
        VerificationPlanRequest(
            subject_type="migration",
            risk_level="critical",
            changed_files=["backend/migrations/versions/001_add_users.py"],
        )
    )

    assert plan.profile_id == "database_migration"
    assert any(item.check_definition_id == "architecture_review" for item in plan.checks)


def test_output_contract_validation_reports_missing_and_unsupported_fields() -> None:
    result = validate_output_contract(
        OutputContractValidationRequest(
            output={"files_changed": "src/app.ts", "extra": True},
            required_fields=["files_changed", "work_receipt"],
            allowed_fields=["files_changed", "work_receipt"],
            field_types={"files_changed": "list", "work_receipt": "dict"},
        )
    )

    assert result.schema_valid is False
    assert result.required_fields_present is False
    assert result.unsupported_fields == ["extra"]
    assert {error.field for error in result.validation_errors} == {"files_changed", "work_receipt", "extra"}


def test_test_discovery_prefers_package_scripts_and_detects_framework() -> None:
    result = discover_tests(
        VerificationTestDiscoveryRequest(
            repository_files=["package.json", "src/app.test.ts", "e2e/login.spec.ts", "playwright.config.ts"],
            package_scripts={"test": "vitest run", "test:e2e": "playwright test", "coverage": "vitest run --coverage"},
            changed_files=["src/app.ts"],
        )
    )

    assert result.framework == "Playwright"
    assert [command.command_id for command in result.commands] == ["npm_test", "npm_test_e2e"]
    assert result.coverage_available is True
    assert "src/app.test.ts" in result.unit_test_locations


def test_test_discovery_falls_back_to_pytest_convention() -> None:
    result = discover_tests(VerificationTestDiscoveryRequest(repository_files=["pyproject.toml", "backend/test_api.py"]))

    assert result.commands[0].command == "python -m pytest"
    assert result.commands[0].source == "convention"


def test_worker_jobs_are_created_from_planned_checks() -> None:
    plan = plan_verification(VerificationPlanRequest(required_gate_profile="frontend_standard", changed_files=["frontend/src/app/page.tsx"]))

    jobs = worker_jobs_for_plan(plan)

    assert len(jobs) == len(plan.checks)
    assert any(job.evidence_producer == "lint" for job in jobs)
    assert any(job.evidence_producer == "playwright" for job in jobs)
    assert all(job.status == "queued" for job in jobs)


def test_failed_build_producer_creates_blocking_validated_evidence() -> None:
    produced = normalize_evidence_producer_output(
        EvidenceProducerRequest(
            producer_key="build",
            status="failed",
            exit_code=1,
            output="npm run build failed",
            payload={"error": "TypeScript compile failed"},
        )
    )
    gate = QualityGateDefinition(gate_key="build", name="Build", category="build", evidence_type="build")

    result = evaluate_quality_gate(gate, [produced.evidence])

    assert produced.normalized_status == "failed"
    assert produced.blocks_release is True
    assert produced.evidence.status == "validated"
    assert result.status == "failed"
    assert result.findings[0].finding_key == "build.command_failed"


def test_github_checks_evidence_blocks_release_when_failed() -> None:
    produced = normalize_evidence_producer_output(
        EvidenceProducerRequest(
            producer_key="github_checks",
            status="failed",
            payload={"conclusion": "failure", "ref": "feature/arceus"},
        )
    )

    assert produced.evidence.evidence_type == "github_check"
    assert produced.retryable is True
    assert produced.blocks_release is True


def test_mission_control_release_gate_response_blocks_missing_readiness() -> None:
    response = MissionControlReleaseGateResponse(
        allowed=False,
        subject_type="pull_request",
        subject_id="pr-42",
        readiness_status="missing",
        score=0,
        blockers=["Release readiness has not been evaluated for this subject."],
        warnings=[],
        required_actions=["run_release_readiness"],
    )

    assert response.allowed is False
    assert response.readiness_status == "missing"


def test_worker_handler_executes_configured_command() -> None:
    job = _FakeWorkerJob(evidence_producer="build", inputs={"command": "python --version"})

    payload = execute_worker_job_payload(job)

    assert payload.producer_key == "build"
    assert payload.status == "succeeded"
    assert payload.exit_code == 0
    assert "Python" in payload.output


def test_worker_handler_secret_scan_reads_changed_files(tmp_path) -> None:
    source = tmp_path / "settings.py"
    source.write_text("API_KEY='token=supersecretvalue'\n", encoding="utf-8")
    job = _FakeWorkerJob(evidence_producer="security", inputs={"working_directory": str(tmp_path), "changed_files": ["settings.py"]})

    payload = execute_worker_job_payload(job)

    assert payload.status == "failed"
    assert payload.payload["high"] == 1


def test_worker_handler_github_checks_and_playwright_reports_block_failures() -> None:
    github = execute_worker_job_payload(
        _FakeWorkerJob(evidence_producer="github_checks", inputs={"github_checks": [{"name": "ci", "conclusion": "failure", "status": "completed"}]})
    )
    preview = execute_worker_job_payload(
        _FakeWorkerJob(evidence_producer="playwright", inputs={"blank_page": True, "console_errors": [{"text": "boom"}]})
    )

    assert github.status == "failed"
    assert github.payload["failed"] == 1
    assert preview.status == "failed"
    assert preview.payload["blank_page"] is True
