from __future__ import annotations

import copy
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

from services.shared.arceus_core_models import ArceusPolicyEvaluation, ArceusToolDefinition, ArceusToolExecution

from ..compiler.utils import stable_hash
from .api_schemas import (
    SideEffectClass,
    ToolAuthorizationRequest,
    ToolAuthorizationResponse,
    ToolDecision,
    ToolExecutionReceipt,
    ToolExecutionRequest,
    ToolRuntimeProfile,
)


SECRET_PATTERNS = (
    re.compile(r"(?i)(Bearer\s+)[^\s'\"`]+"),
    re.compile(r"(?i)((?:password|token|secret|api_key|access_key)=)[^\s'\"`]+"),
    re.compile(r"(?i)\bsk-[A-Za-z0-9_\-]{12,}\b"),
)

DESTRUCTIVE_ACTION_TERMS = ("delete", "remove", "destroy", "drop", "truncate", "reset", "wipe", "purge")
EXTERNAL_ACTION_TERMS = ("deploy", "publish", "send", "charge", "refund", "merge", "release", "pr", "email")
MUTATION_ACTION_TERMS = ("write", "create", "modify", "update", "patch", "install", "run")


CATALOG: dict[str, ToolRuntimeProfile] = {
    "echo.message": ToolRuntimeProfile(
        tool_key="echo.message",
        display_name="Echo Message",
        category="custom",
        capabilities=["receipt_test", "audit_test"],
        supported_actions=["echo"],
        risk_level="low",
        side_effect_class="READ_ONLY",
        supports_dry_run=True,
        required_authorities=[],
    ),
    "repository.search": ToolRuntimeProfile(
        tool_key="repository.search",
        display_name="Repository Search",
        category="git",
        capabilities=["search", "repository_inspection"],
        supported_actions=["search", "list"],
        risk_level="low",
        side_effect_class="READ_ONLY",
        supports_dry_run=True,
        required_authorities=["repository.search"],
    ),
    "filesystem.write": ToolRuntimeProfile(
        tool_key="filesystem.write",
        display_name="Filesystem Write",
        category="filesystem",
        capabilities=["file_create", "file_modify"],
        supported_actions=["create_file", "modify_file", "mkdir"],
        risk_level="high",
        side_effect_class="LOCAL_MUTATION",
        supports_dry_run=True,
        supports_rollback=True,
        required_authorities=["tool.execute"],
    ),
    "terminal.run": ToolRuntimeProfile(
        tool_key="terminal.run",
        display_name="Terminal Command",
        category="terminal",
        capabilities=["command_execution"],
        supported_actions=["run_command"],
        risk_level="critical",
        side_effect_class="EXTERNAL_IRREVERSIBLE",
        supports_dry_run=True,
        required_authorities=["tool.execute"],
    ),
    "deployment.release": ToolRuntimeProfile(
        tool_key="deployment.release",
        display_name="Production Release",
        category="deployment",
        capabilities=["deploy", "release"],
        supported_actions=["deploy", "rollback"],
        risk_level="critical",
        side_effect_class="PRODUCTION_CHANGE",
        supports_dry_run=True,
        required_authorities=["production.deploy"],
        allowed_environments=["staging", "production"],
    ),
}


def redact_tool_payload(value: Any) -> Any:
    if isinstance(value, str):
        redacted = value
        for pattern in SECRET_PATTERNS:
            redacted = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]" if match.lastindex else "[REDACTED]", redacted)
        return redacted
    if isinstance(value, list):
        return [redact_tool_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_tool_payload(item) for item in value]
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if re.search(r"(?i)(password|token|secret|api[_-]?key|credential)", key_text):
                sanitized[key_text] = "[REDACTED]"
            else:
                sanitized[key_text] = redact_tool_payload(item)
        return sanitized
    return value


def contains_secret(value: Any) -> bool:
    redacted = redact_tool_payload(value)
    return redacted != value


def idempotency_fingerprint(payload: ToolAuthorizationRequest | ToolExecutionRequest) -> str:
    return stable_hash(
        {
            "mission_id": str(payload.mission_id) if payload.mission_id else None,
            "task_id": str(payload.task_id) if payload.task_id else None,
            "tool_key": payload.tool_key,
            "action_key": payload.action_key,
            "environment": payload.environment,
            "dry_run": payload.dry_run,
            "arguments": redact_tool_payload(payload.arguments),
        }
    )


def builtin_profile(tool_key: str, override: ToolRuntimeProfile | None = None) -> ToolRuntimeProfile:
    if override is not None:
        return override
    if tool_key in CATALOG:
        return CATALOG[tool_key]
    return ToolRuntimeProfile(
        tool_key=tool_key,
        display_name=tool_key.replace(".", " ").title(),
        category=tool_key.split(".", 1)[0] if "." in tool_key else "custom",
        supported_actions=[],
        risk_level="high",
        side_effect_class="EXTERNAL_IRREVERSIBLE",
        supports_dry_run=True,
        required_authorities=["tool.execute"],
        enabled=False,
    )


def _action_contains(action_key: str, terms: tuple[str, ...]) -> bool:
    action = action_key.lower()
    return any(term in action for term in terms)


def classify_tool_action(profile: ToolRuntimeProfile, action_key: str, arguments: dict[str, Any], environment: str) -> tuple[ToolDecision, list[str], list[str]]:
    reasons: list[str] = []
    approvals: list[str] = []
    decision: ToolDecision = "allow"

    if not profile.enabled:
        return "deny", ["Tool is disabled or unregistered."], ["tool_owner"]

    if profile.supported_actions and action_key not in profile.supported_actions:
        return "deny", [f"Action '{action_key}' is not supported by {profile.tool_key}."], ["tool_owner"]

    if profile.allowed_environments and environment not in profile.allowed_environments:
        return "deny", [f"Environment '{environment}' is not allowed for this tool."], ["environment_owner"]

    if contains_secret(arguments) and profile.side_effect_class != "SECRET_ACCESS":
        decision = "require_review"
        reasons.append("Arguments contain secret-like values; use secret references instead of raw secrets.")
        approvals.append("security_reviewer")

    side_effect = profile.side_effect_class
    if side_effect in {"EXTERNAL_IRREVERSIBLE", "PRODUCTION_CHANGE", "FINANCIAL_ACTION", "SECRET_ACCESS"}:
        decision = "require_review"
        reasons.append(f"Side effect class {side_effect} requires explicit approval.")
        approvals.append("human_operator")

    if side_effect in {"LOCAL_MUTATION", "REPOSITORY_MUTATION", "EXTERNAL_REVERSIBLE"}:
        decision = "require_review"
        reasons.append(f"Tool changes external state: {side_effect}.")
        approvals.append("reviewer")

    if profile.risk_level in {"high", "critical"}:
        decision = "require_review"
        reasons.append(f"Risk level is {profile.risk_level}.")
        approvals.append("risk_owner")

    if _action_contains(action_key, DESTRUCTIVE_ACTION_TERMS):
        decision = "require_review"
        reasons.append("Action name indicates destructive behavior.")
        approvals.append("safety_reviewer")
    elif _action_contains(action_key, EXTERNAL_ACTION_TERMS):
        decision = "require_review"
        reasons.append("Action name indicates external side effects.")
        approvals.append("external_action_approver")
    elif _action_contains(action_key, MUTATION_ACTION_TERMS) and side_effect == "READ_ONLY":
        decision = "deny"
        reasons.append("Mutation-like action cannot run through a read-only tool profile.")
        approvals.append("tool_owner")

    if not reasons:
        reasons.append("Read-only or explicitly low-risk action is allowed.")

    return decision, reasons, sorted(set(approvals))


def authorize_tool_request(payload: ToolAuthorizationRequest | ToolExecutionRequest) -> ToolAuthorizationResponse:
    profile = builtin_profile(payload.tool_key, payload.profile)
    decision, reasons, approvals = classify_tool_action(profile, payload.action_key, payload.arguments, payload.environment)
    missing_authorities = sorted(set(profile.required_authorities or []) - set(payload.requester_authorities or []))
    if missing_authorities and decision == "allow":
        decision = "deny"
        reasons.append(f"Missing required authorities: {', '.join(missing_authorities)}.")
    elif missing_authorities:
        reasons.append(f"Missing required authorities: {', '.join(missing_authorities)}.")

    if payload.dry_run and profile.supports_dry_run and decision == "require_review":
        if profile.side_effect_class not in {"SECRET_ACCESS", "FINANCIAL_ACTION", "PRODUCTION_CHANGE"}:
            reasons.append("Dry-run may proceed without mutating external state.")
            decision = "allow"

    return ToolAuthorizationResponse(
        decision=decision,
        tool_key=payload.tool_key,
        action_key=payload.action_key,
        risk_level=profile.risk_level,
        side_effect_class=profile.side_effect_class,
        reasons=reasons,
        required_approvals=approvals,
        required_authorities=profile.required_authorities or [],
        execution_boundary={
            "environment": payload.environment,
            "sandbox_required": profile.requires_sandbox,
            "timeout_seconds": profile.maximum_runtime_seconds,
            "dry_run": payload.dry_run,
            "rollback_supported": profile.supports_rollback,
        },
        idempotency_fingerprint=idempotency_fingerprint(payload),
        sanitized_arguments=redact_tool_payload(payload.arguments),
    )


def verify_tool_receipt(receipt: ToolExecutionReceipt) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if receipt.status == "succeeded" and receipt.decision != "allow":
        reasons.append("Succeeded receipts must have an allow decision.")
    if receipt.status == "blocked" and receipt.decision == "allow":
        reasons.append("Blocked receipts should not have an allow decision.")
    if receipt.status == "succeeded" and not receipt.output_hash:
        reasons.append("Succeeded receipts require an output hash.")
    if receipt.rollback_available and receipt.dry_run:
        reasons.append("Dry-run receipts cannot advertise rollback availability.")
    return not reasons, reasons or ["Receipt is internally consistent."]


class ToolRuntimeService:
    def __init__(self, db: Session, *, tenant_id: UUID, actor_id: UUID, correlation_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.actor_id = actor_id
        self.correlation_id = correlation_id

    def authorize(self, payload: ToolAuthorizationRequest | ToolExecutionRequest) -> ToolAuthorizationResponse:
        response = authorize_tool_request(payload)
        self._record_policy(payload=payload, response=response)
        if payload.mission_id:
            self._append_event(payload.mission_id, "TOOL_AUTHORIZATION_EVALUATED", response.model_dump(mode="json"))
        return response

    def execute(self, payload: ToolExecutionRequest) -> ToolExecutionReceipt:
        idempotency_key = payload.idempotency_key or idempotency_fingerprint(payload)
        existing = self._existing_execution(idempotency_key)
        if existing is not None:
            return self._receipt_from_execution(existing, replayed=True)

        authorization = self.authorize(payload)
        profile = builtin_profile(payload.tool_key, payload.profile)
        definition = self._ensure_definition(profile)
        execution = ArceusToolExecution(
            tenant_id=self.tenant_id,
            mission_id=payload.mission_id,
            task_id=payload.task_id,
            member_id=payload.member_id,
            tool_definition_id=definition.id,
            idempotency_key=idempotency_key,
            action=payload.action_key,
            target=str(payload.arguments.get("path") or payload.arguments.get("target") or ""),
            status="running",
            input_payload={
                "tool_key": payload.tool_key,
                "action_key": payload.action_key,
                "arguments": authorization.sanitized_arguments,
                "environment": payload.environment,
                "dry_run": payload.dry_run,
                "input_hash": idempotency_fingerprint(payload),
                "authorization": authorization.model_dump(mode="json"),
            },
        )
        self.db.add(execution)
        self.db.flush()

        if payload.mission_id:
            self._append_event(payload.mission_id, "TOOL_EXECUTION_STARTED", {"execution_id": str(execution.id), "tool_key": payload.tool_key, "action_key": payload.action_key})

        if authorization.decision != "allow":
            execution.status = "blocked"
            execution.error = {"decision": authorization.decision, "reasons": authorization.reasons, "required_approvals": authorization.required_approvals}
            execution.finished_at = datetime.now(timezone.utc)
            if payload.mission_id:
                self._append_event(payload.mission_id, "TOOL_EXECUTION_BLOCKED", {"execution_id": str(execution.id), "reasons": authorization.reasons})
            self.db.flush()
            return self._receipt_from_execution(execution)

        try:
            output = self._execute_builtin(profile, payload)
            redacted_output = redact_tool_payload(output)
            execution.status = "succeeded"
            execution.output_payload = redacted_output
            execution.finished_at = datetime.now(timezone.utc)
            if payload.mission_id:
                self._append_event(payload.mission_id, "TOOL_EXECUTION_COMPLETED", {"execution_id": str(execution.id), "output_hash": stable_hash(redacted_output)})
        except Exception as exc:  # noqa: BLE001 - runtime receipts need durable failure causes
            execution.status = "failed"
            execution.error = {"message": str(exc), "error_class": exc.__class__.__name__}
            execution.finished_at = datetime.now(timezone.utc)
            if payload.mission_id:
                self._append_event(payload.mission_id, "TOOL_EXECUTION_FAILED", {"execution_id": str(execution.id), "error": execution.error})
        self.db.flush()
        return self._receipt_from_execution(execution)

    def execution(self, execution_id: UUID) -> ToolExecutionReceipt | None:
        item = (
            self.db.query(ArceusToolExecution)
            .filter(ArceusToolExecution.tenant_id == self.tenant_id, ArceusToolExecution.id == execution_id)
            .first()
        )
        return self._receipt_from_execution(item) if item else None

    def executions(self, *, mission_id: UUID | None = None, status: str | None = None, limit: int = 50) -> list[ToolExecutionReceipt]:
        query = self.db.query(ArceusToolExecution).filter(ArceusToolExecution.tenant_id == self.tenant_id)
        if mission_id:
            query = query.filter(ArceusToolExecution.mission_id == mission_id)
        if status:
            query = query.filter(ArceusToolExecution.status == status)
        rows = query.order_by(ArceusToolExecution.created_at.desc(), ArceusToolExecution.id.desc()).limit(min(limit, 100)).all()
        return [self._receipt_from_execution(item) for item in rows]

    def _existing_execution(self, idempotency_key: str) -> ArceusToolExecution | None:
        return (
            self.db.query(ArceusToolExecution)
            .filter(ArceusToolExecution.tenant_id == self.tenant_id, ArceusToolExecution.idempotency_key == idempotency_key)
            .first()
        )

    def _ensure_definition(self, profile: ToolRuntimeProfile) -> ArceusToolDefinition:
        item = self.db.query(ArceusToolDefinition).filter(ArceusToolDefinition.tool_key == profile.tool_key).first()
        if item is None:
            item = ArceusToolDefinition(
                tool_key=profile.tool_key,
                display_name=profile.display_name,
                tool_type=profile.category,
                permission_requirements={"authorities": profile.required_authorities, "side_effect_class": profile.side_effect_class},
                active=profile.enabled,
            )
            self.db.add(item)
            self.db.flush()
        return item

    def _record_policy(self, *, payload: ToolAuthorizationRequest | ToolExecutionRequest, response: ToolAuthorizationResponse) -> None:
        if not payload.mission_id:
            return
        item = ArceusPolicyEvaluation(
            tenant_id=self.tenant_id,
            mission_id=payload.mission_id,
            task_id=payload.task_id,
            policy_key="tool_runtime.authorization",
            subject={"actor_id": str(self.actor_id), "member_id": str(payload.member_id) if payload.member_id else None},
            action=f"{payload.tool_key}.{payload.action_key}",
            resource={"tool_key": payload.tool_key, "environment": payload.environment},
            decision="needs_approval" if response.decision == "require_review" else response.decision,
            reason="; ".join(response.reasons),
        )
        self.db.add(item)

    def _append_event(self, mission_id: UUID, event_type: str, payload: dict[str, Any]) -> None:
        from services.shared.arceus_core_models import ArceusEvent

        latest = (
            self.db.query(ArceusEvent.aggregate_version)
            .filter(ArceusEvent.tenant_id == self.tenant_id, ArceusEvent.aggregate_type == "mission", ArceusEvent.aggregate_id == mission_id)
            .order_by(ArceusEvent.aggregate_version.desc())
            .first()
        )
        version = int(latest[0]) + 1 if latest else 1
        self.db.add(
            ArceusEvent(
                tenant_id=self.tenant_id,
                aggregate_type="mission",
                aggregate_id=mission_id,
                aggregate_version=version,
                event_type=event_type,
                actor_type="user",
                actor_id=str(self.actor_id),
                payload=payload,
                metadata_json={"correlation_id": str(self.correlation_id), "source": "tool_runtime"},
            )
        )

    def _execute_builtin(self, profile: ToolRuntimeProfile, payload: ToolExecutionRequest) -> dict[str, Any]:
        if payload.dry_run:
            return {
                "dry_run": True,
                "would_execute": f"{payload.tool_key}.{payload.action_key}",
                "arguments": redact_tool_payload(payload.arguments),
                "expected_outputs": redact_tool_payload(payload.expected_outputs),
            }
        if profile.tool_key == "echo.message" and payload.action_key == "echo":
            return {"message": redact_tool_payload(payload.arguments.get("message", "")), "echoed": True}
        if profile.side_effect_class == "READ_ONLY":
            return {"status": "completed", "tool_key": profile.tool_key, "action_key": payload.action_key, "arguments": redact_tool_payload(payload.arguments)}
        raise ValueError("Only dry-run or read-only built-in execution is enabled in the secure runtime facade.")

    def _receipt_from_execution(self, execution: ArceusToolExecution, *, replayed: bool = False) -> ToolExecutionReceipt:
        input_payload = copy.deepcopy(execution.input_payload or {})
        authorization = input_payload.get("authorization") or {}
        decision = authorization.get("decision") or ("allow" if execution.status == "succeeded" else "deny")
        output = redact_tool_payload(execution.output_payload or {})
        input_hash = input_payload.get("input_hash") or stable_hash(input_payload)
        return ToolExecutionReceipt(
            execution_id=execution.id,
            status=execution.status,
            decision=decision,
            tool_key=input_payload.get("tool_key") or "unknown",
            action_key=execution.action,
            dry_run=bool(input_payload.get("dry_run")),
            replayed=replayed,
            input_hash=input_hash,
            output_hash=stable_hash(output) if output else None,
            redacted_input=redact_tool_payload(input_payload),
            redacted_output=output,
            error=redact_tool_payload(execution.error or {}),
            evidence={
                "idempotency_key": execution.idempotency_key,
                "tool_definition_id": str(execution.tool_definition_id),
                "audit_status": "recorded",
            },
            rollback_available=bool((authorization.get("execution_boundary") or {}).get("rollback_supported")) and execution.status == "succeeded" and not bool(input_payload.get("dry_run")),
            started_at=execution.started_at,
            finished_at=execution.finished_at,
        )
