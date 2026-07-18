"""Generation 3 human-AI collaboration contracts.

Generation 3 makes humans and AI specialists first-class participants in the
same organization model while preserving separate execution semantics.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from .core import new_id, utc_now


ParticipantType = Literal["human", "ai_agent", "service", "external_reviewer"]
ParticipantStatus = Literal["active", "busy", "unavailable", "suspended", "removed"]
MembershipStatus = Literal["invited", "active", "suspended", "removed", "expired"]
RoleScope = Literal["organization", "project", "mission", "task", "approval", "environment", "repository"]
EnvironmentName = Literal["development", "staging", "production", "preview", "sandbox"]
RiskLevel = Literal["low", "medium", "high", "critical"]
Sensitivity = Literal["public", "internal", "confidential", "restricted"]
PermissionDecisionKind = Literal["allow", "deny", "require_approval"]
Authority = Literal[
    "VIEW",
    "COMMENT",
    "PROPOSE",
    "ASSIGN",
    "MODIFY",
    "EXECUTE_TOOL",
    "REVIEW",
    "VERIFY",
    "APPROVE",
    "DEPLOY",
    "MANAGE_MEMBERS",
    "MANAGE_POLICY",
    "MANAGE_BUDGET",
    "ACCESS_SECRET",
    "RESPOND_TO_INCIDENT",
    "DELETE",
    "EXPORT",
]


ROLE_AUTHORITY: dict[str, set[Authority]] = {
    "Product Owner": {"VIEW", "COMMENT", "PROPOSE", "ASSIGN", "APPROVE"},
    "Technical Lead": {"VIEW", "COMMENT", "PROPOSE", "ASSIGN", "MODIFY", "REVIEW", "VERIFY", "APPROVE", "DEPLOY"},
    "Human Backend Engineer": {"VIEW", "COMMENT", "PROPOSE", "MODIFY", "EXECUTE_TOOL"},
    "AI Authentication Specialist": {"VIEW", "COMMENT", "PROPOSE", "MODIFY", "EXECUTE_TOOL"},
    "Security Reviewer": {"VIEW", "COMMENT", "REVIEW", "VERIFY", "APPROVE"},
    "Production Operator": {"VIEW", "COMMENT", "DEPLOY", "RESPOND_TO_INCIDENT"},
    "Project Observer": {"VIEW", "COMMENT"},
}

ROLE_ENVIRONMENT_ALLOW: dict[str, set[EnvironmentName]] = {
    "Product Owner": {"development", "staging", "preview"},
    "Technical Lead": {"development", "staging", "preview"},
    "Human Backend Engineer": {"development", "preview"},
    "AI Authentication Specialist": {"development", "preview", "sandbox"},
    "Security Reviewer": {"development", "staging", "production", "preview"},
    "Production Operator": {"production", "staging"},
    "Project Observer": {"development", "preview"},
}

ROLE_PATH_PREFIX_ALLOW: dict[str, tuple[str, ...]] = {
    "Human Backend Engineer": ("backend/", "services/", "api/", "server/"),
    "AI Authentication Specialist": ("backend/services/auth", "backend/services/agent/auth", "frontend/src/app/auth", "frontend/src/app/sign-in", "frontend/src/app/sign-up"),
}


@dataclass(slots=True)
class Participant:
    tenant_id: str
    organization_id: str
    display_name: str
    participant_type: ParticipantType
    status: ParticipantStatus = "active"
    capabilities: list[str] = field(default_factory=list)
    authority_scope: dict[str, Any] = field(default_factory=dict)
    memory_scope: dict[str, Any] = field(default_factory=dict)
    tool_scope: dict[str, Any] = field(default_factory=dict)
    current_assignments: list[str] = field(default_factory=list)
    performance_reference: dict[str, Any] = field(default_factory=dict)
    participant_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    @property
    def is_human(self) -> bool:
        return self.participant_type == "human"

    def to_dict(self) -> dict[str, Any]:
        return {
            "participant_id": self.participant_id,
            "tenant_id": self.tenant_id,
            "organization_id": self.organization_id,
            "display_name": self.display_name,
            "participant_type": self.participant_type,
            "status": self.status,
            "capabilities": self.capabilities,
            "authority_scope": self.authority_scope,
            "memory_scope": self.memory_scope,
            "tool_scope": self.tool_scope,
            "current_assignments": self.current_assignments,
            "performance_reference": self.performance_reference,
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class HumanMember:
    tenant_id: str
    user_id: str
    organization_id: str
    display_name: str
    email: str
    status: MembershipStatus = "invited"
    organization_roles: list[str] = field(default_factory=list)
    department_memberships: list[str] = field(default_factory=list)
    project_memberships: list[str] = field(default_factory=list)
    capabilities: list[str] = field(default_factory=list)
    authority_bindings: list[str] = field(default_factory=list)
    availability: dict[str, Any] = field(default_factory=dict)
    working_hours: dict[str, Any] = field(default_factory=dict)
    notification_preferences: dict[str, Any] = field(default_factory=dict)
    member_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def activate(self) -> None:
        if self.status == "expired":
            raise ValueError("Expired invitations cannot be activated.")
        self.status = "active"
        self.updated_at = utc_now()


@dataclass(slots=True)
class RoleBinding:
    participant_id: str
    role_name: str
    scope: RoleScope
    tenant_id: str
    organization_id: str
    project_id: str | None = None
    mission_id: str | None = None
    task_id: str | None = None
    environment: EnvironmentName | None = None
    repository_id: str | None = None
    expires_at: str | None = None
    binding_id: str = field(default_factory=new_id)


@dataclass(slots=True)
class ProjectMembership:
    tenant_id: str
    project_id: str
    participant_id: str
    roles: list[str]
    capabilities: list[str] = field(default_factory=list)
    repository_access: list[str] = field(default_factory=list)
    environment_access: list[EnvironmentName] = field(default_factory=list)
    secret_access: list[str] = field(default_factory=list)
    mission_permissions: list[str] = field(default_factory=list)
    approval_authority: list[str] = field(default_factory=list)
    status: MembershipStatus = "active"
    added_by: str | None = None
    reason: str = ""
    membership_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class PermissionRequest:
    tenant_id: str
    organization_id: str
    project_id: str
    participant_id: str
    action: Authority
    resource_type: str
    resource_owner_id: str | None = None
    environment: EnvironmentName = "development"
    risk_level: RiskLevel = "low"
    data_sensitivity: Sensitivity = "internal"
    path: str | None = None
    requires_human_approval: bool = False
    author_participant_id: str | None = None
    artifact_id: str | None = None


@dataclass(slots=True)
class PermissionDecision:
    allowed: bool
    decision: PermissionDecisionKind
    reason_codes: list[str]
    matched_policies: list[str] = field(default_factory=list)
    required_approvers: list[str] = field(default_factory=list)
    conditions: list[str] = field(default_factory=list)
    expires_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "decision": self.decision,
            "reason_codes": self.reason_codes,
            "matched_policies": self.matched_policies,
            "required_approvers": self.required_approvers,
            "conditions": self.conditions,
            "expires_at": self.expires_at,
        }


class PermissionEvaluator:
    def __init__(self, participants: list[Participant], role_bindings: list[RoleBinding]) -> None:
        self.participants = {participant.participant_id: participant for participant in participants}
        self.role_bindings = role_bindings

    def evaluate(self, request: PermissionRequest) -> PermissionDecision:
        participant = self.participants.get(request.participant_id)
        if participant is None or participant.tenant_id != request.tenant_id:
            return self._deny("participant_not_found_or_cross_tenant")
        if participant.status not in {"active", "busy"}:
            return self._deny("participant_unavailable")

        roles = self._roles_for(request)
        if not roles:
            return self._deny("no_role_binding")
        if not any(request.action in ROLE_AUTHORITY.get(role, set()) for role in roles):
            return self._deny("missing_authority")

        environment_allowed = any(request.environment in ROLE_ENVIRONMENT_ALLOW.get(role, set()) for role in roles)
        if not environment_allowed:
            return self._deny("environment_not_authorized")

        if request.path and not self._path_allowed(roles, request.path):
            return self._deny("path_not_authorized")

        if participant.participant_type == "ai_agent" and request.action in {"APPROVE", "DEPLOY", "MANAGE_POLICY", "MANAGE_MEMBERS", "MANAGE_BUDGET", "ACCESS_SECRET"}:
            return self._deny("ai_participant_cannot_perform_human_authority_action")

        if participant.participant_type == "ai_agent" and request.environment == "production":
            return self._deny("ai_participant_cannot_access_production")

        if request.action == "ACCESS_SECRET" and request.environment == "production":
            return self._require_approval("production_secret_requires_brokered_human_approval", ["Security Reviewer", "Production Operator"])

        if request.action == "DEPLOY" and request.environment == "production":
            if "Production Operator" not in roles:
                return self._deny("production_deploy_requires_production_operator")
            return self._require_approval("production_deploy_requires_security_review", ["Security Reviewer"])

        if request.requires_human_approval and participant.participant_type != "human":
            return self._require_approval("human_approval_required", ["Technical Lead", "Product Owner"])

        if request.action == "APPROVE" and request.author_participant_id == request.participant_id and request.risk_level in {"high", "critical"}:
            return self._require_approval("author_cannot_solely_approve_high_risk_work", ["Technical Lead", "Security Reviewer"])

        return PermissionDecision(True, "allow", ["role_and_policy_allowed"], matched_policies=["generation3_default_policy"])

    def _roles_for(self, request: PermissionRequest) -> list[str]:
        roles: list[str] = []
        for binding in self.role_bindings:
            if binding.participant_id != request.participant_id:
                continue
            if binding.tenant_id != request.tenant_id or binding.organization_id != request.organization_id:
                continue
            if binding.scope == "project" and binding.project_id != request.project_id:
                continue
            if binding.scope == "environment" and binding.environment != request.environment:
                continue
            roles.append(binding.role_name)
        return list(dict.fromkeys(roles))

    def _path_allowed(self, roles: list[str], path: str) -> bool:
        normalized = path.replace("\\", "/").lstrip("/")
        scoped_roles = [role for role in roles if role in ROLE_PATH_PREFIX_ALLOW]
        if not scoped_roles:
            return True
        return any(normalized.startswith(prefix) for role in scoped_roles for prefix in ROLE_PATH_PREFIX_ALLOW[role])

    def _deny(self, reason: str) -> PermissionDecision:
        return PermissionDecision(False, "deny", [reason], matched_policies=["generation3_default_policy"])

    def _require_approval(self, reason: str, required_approvers: list[str]) -> PermissionDecision:
        return PermissionDecision(False, "require_approval", [reason], matched_policies=["generation3_default_policy"], required_approvers=required_approvers)


@dataclass(slots=True)
class ApprovalVote:
    participant_id: str
    participant_type: ParticipantType
    role_name: str
    verdict: Literal["approve", "reject", "abstain"]
    created_at: str = field(default_factory=utc_now)


@dataclass(slots=True)
class ApprovalQuorumPolicy:
    name: str
    required_roles: list[str]
    minimum_human_approvals: int = 1
    minimum_total_approvals: int = 1
    author_cannot_count: bool = True
    ai_cannot_count_as_human: bool = True
    veto_roles: list[str] = field(default_factory=list)


class ApprovalQuorumEvaluator:
    def evaluate(self, policy: ApprovalQuorumPolicy, votes: list[ApprovalVote], *, author_participant_id: str | None = None) -> PermissionDecision:
        if any(vote.verdict == "reject" and vote.role_name in policy.veto_roles for vote in votes):
            return PermissionDecision(False, "deny", ["veto_role_rejected"], matched_policies=[policy.name])

        approvals = [vote for vote in votes if vote.verdict == "approve"]
        if policy.author_cannot_count and author_participant_id:
            approvals = [vote for vote in approvals if vote.participant_id != author_participant_id]

        human_approvals = [vote for vote in approvals if vote.participant_type == "human"]
        approved_roles = {vote.role_name for vote in approvals}
        missing_roles = [role for role in policy.required_roles if role not in approved_roles]
        if missing_roles:
            return PermissionDecision(False, "require_approval", ["approval_roles_missing"], matched_policies=[policy.name], required_approvers=missing_roles)
        if len(approvals) < policy.minimum_total_approvals:
            return PermissionDecision(False, "require_approval", ["approval_count_not_met"], matched_policies=[policy.name])
        if len(human_approvals) < policy.minimum_human_approvals:
            return PermissionDecision(False, "require_approval", ["human_approval_count_not_met"], matched_policies=[policy.name])
        return PermissionDecision(True, "allow", ["approval_quorum_met"], matched_policies=[policy.name])


@dataclass(slots=True)
class Handoff:
    from_participant_id: str
    to_participant_id: str
    task_id: str
    reason: str
    completed_work: list[str]
    current_state: str
    open_questions: list[str]
    required_action: str
    relevant_context: list[str] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    expected_response: str = ""
    deadline: str | None = None
    acknowledged_at: str | None = None
    handoff_id: str = field(default_factory=new_id)
    created_at: str = field(default_factory=utc_now)

    @property
    def acknowledged(self) -> bool:
        return self.acknowledged_at is not None

    def acknowledge(self, participant_id: str) -> None:
        if participant_id != self.to_participant_id:
            raise ValueError("Only the receiving participant can acknowledge this handoff.")
        self.acknowledged_at = utc_now()


@dataclass(slots=True)
class ResponsibilityChain:
    artifact_id: str
    tenant_id: str
    project_id: str
    proposed_by: str | None = None
    authored_by: str | None = None
    contributors: list[str] = field(default_factory=list)
    reviewers: list[str] = field(default_factory=list)
    verifiers: list[str] = field(default_factory=list)
    approvers: list[str] = field(default_factory=list)
    model_ids: list[str] = field(default_factory=list)
    tool_ids: list[str] = field(default_factory=list)
    policy_decisions: list[dict[str, Any]] = field(default_factory=list)
    evidence_ids: list[str] = field(default_factory=list)
    mission_id: str | None = None
    task_id: str | None = None
    environment: EnvironmentName | None = None
    changes_after_approval: list[str] = field(default_factory=list)
    chain_id: str = field(default_factory=new_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "chain_id": self.chain_id,
            "artifact_id": self.artifact_id,
            "tenant_id": self.tenant_id,
            "project_id": self.project_id,
            "proposed_by": self.proposed_by,
            "authored_by": self.authored_by,
            "contributors": self.contributors,
            "reviewers": self.reviewers,
            "verifiers": self.verifiers,
            "approvers": self.approvers,
            "model_ids": self.model_ids,
            "tool_ids": self.tool_ids,
            "policy_decisions": self.policy_decisions,
            "evidence_ids": self.evidence_ids,
            "mission_id": self.mission_id,
            "task_id": self.task_id,
            "environment": self.environment,
            "changes_after_approval": self.changes_after_approval,
        }


def generation3_manifest() -> dict[str, Any]:
    return {
        "name": "Arceus Generation 3 Human-AI Organization Runtime",
        "objective": "Represent humans and AI specialists in one auditable organization model with scoped authority.",
        "vertical_slice": "Three-person human team collaborates with AI specialists on a production-ready authentication improvement.",
        "core_modules": [
            "participants",
            "memberships",
            "scoped_roles",
            "permission_evaluator",
            "approval_quorums",
            "handoffs",
            "responsibility_chains",
        ],
        "definition_of_done": [
            "Humans and AI specialists share one participant model.",
            "Server-side role and permission boundaries are enforced.",
            "AI participants never count as required human approval.",
            "Production authority is separate from development authority.",
            "Responsibility chains identify authors, reviewers, approvers, models, tools, policies, and evidence.",
        ],
    }

