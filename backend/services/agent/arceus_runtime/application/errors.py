from __future__ import annotations

from typing import Any


class DomainError(Exception):
    code = "DOMAIN_ERROR"
    http_status = 400
    retryable = False

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class AuthenticationRequired(DomainError):
    code = "AUTHENTICATION_REQUIRED"
    http_status = 401


class PermissionDenied(DomainError):
    code = "PERMISSION_DENIED"
    http_status = 403


class ProjectNotFound(DomainError):
    code = "PROJECT_NOT_FOUND"
    http_status = 404


class MissionNotFound(DomainError):
    code = "MISSION_NOT_FOUND"
    http_status = 404


class MissionVersionConflict(DomainError):
    code = "MISSION_VERSION_CONFLICT"
    http_status = 409


class MissionStateConflict(DomainError):
    code = "MISSION_STATE_CONFLICT"
    http_status = 409


class CompilerRunNotFound(DomainError):
    code = "COMPILER_RUN_NOT_FOUND"
    http_status = 404


class CompilerRunStateConflict(DomainError):
    code = "COMPILER_RUN_STATE_CONFLICT"
    http_status = 409


class CompilerRunStale(DomainError):
    code = "COMPILER_RUN_STALE"
    http_status = 409


class CompilerBudgetExceeded(DomainError):
    code = "COMPILER_BUDGET_EXCEEDED"
    http_status = 402


class IdempotencyConflict(DomainError):
    code = "IDEMPOTENCY_CONFLICT"
    http_status = 409


class InvalidIdempotencyKey(DomainError):
    code = "INVALID_IDEMPOTENCY_KEY"
    http_status = 400


class RepositoryScopeInvalid(DomainError):
    code = "REPOSITORY_SCOPE_INVALID"
    http_status = 422


class ClarificationInvalid(DomainError):
    code = "MISSION_CLARIFICATION_INVALID"
    http_status = 422


class ApprovalNotFound(DomainError):
    code = "APPROVAL_NOT_FOUND"
    http_status = 404


class ArtifactNotFound(DomainError):
    code = "ARTIFACT_NOT_FOUND"
    http_status = 404


class EvidenceNotFound(DomainError):
    code = "EVIDENCE_NOT_FOUND"
    http_status = 404


class VerificationRunNotFound(DomainError):
    code = "VERIFICATION_RUN_NOT_FOUND"
    http_status = 404


class TaskNotFound(DomainError):
    code = "TASK_NOT_FOUND"
    http_status = 404


class TaskStateConflict(DomainError):
    code = "TASK_STATE_CONFLICT"
    http_status = 409


class WorkerLeaseNotFound(DomainError):
    code = "WORKER_LEASE_NOT_FOUND"
    http_status = 404


class RuntimeStateConflict(DomainError):
    code = "RUNTIME_STATE_CONFLICT"
    http_status = 409


class DecisionNotFound(DomainError):
    code = "DECISION_NOT_FOUND"
    http_status = 404


class OrganizationNotFound(DomainError):
    code = "ORGANIZATION_NOT_FOUND"
    http_status = 404


class OrganizationMemberNotFound(DomainError):
    code = "ORGANIZATION_MEMBER_NOT_FOUND"
    http_status = 404


class CapabilityNotFound(DomainError):
    code = "CAPABILITY_NOT_FOUND"
    http_status = 404


class ContextPackageNotFound(DomainError):
    code = "CONTEXT_PACKAGE_NOT_FOUND"
    http_status = 404


class ModelExecutionNotFound(DomainError):
    code = "MODEL_EXECUTION_NOT_FOUND"
    http_status = 404


class ToolExecutionNotFound(DomainError):
    code = "TOOL_EXECUTION_NOT_FOUND"
    http_status = 404


class PolicyEvaluationNotFound(DomainError):
    code = "POLICY_EVALUATION_NOT_FOUND"
    http_status = 404


class AuditEventNotFound(DomainError):
    code = "AUDIT_EVENT_NOT_FOUND"
    http_status = 404


class UsageRecordNotFound(DomainError):
    code = "USAGE_RECORD_NOT_FOUND"
    http_status = 404


class ApprovalAlreadyResolved(DomainError):
    code = "APPROVAL_ALREADY_RESOLVED"
    http_status = 409


class ApprovalSubjectMismatch(DomainError):
    code = "APPROVAL_SUBJECT_MISMATCH"
    http_status = 409


class SeparationOfDutiesViolation(DomainError):
    code = "SEPARATION_OF_DUTIES_VIOLATION"
    http_status = 409
