from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


class CreateTeamRequest(BaseModel):
    organization_id: UUID | None = None
    name: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=2000)
    lead_user_id: UUID | None = None


class TeamResponse(BaseModel):
    id: UUID
    organization_id: UUID | None
    name: str
    slug: str
    description: str | None
    lead_user_id: UUID | None
    status: str
    member_count: int = 0
    created_at: datetime


class AddTeamMemberRequest(BaseModel):
    user_id: UUID | None = None
    participant_id: UUID | None = None
    member_type: str = Field(default="human", max_length=60)
    role_key: str = Field(default="member", max_length=120)


class CreateCollaborativeProjectRequest(BaseModel):
    organization_id: UUID | None = None
    name: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=3000)
    created_by: UUID | None = None
    team_ids: list[UUID] = Field(default_factory=list)
    settings: dict[str, Any] = Field(default_factory=dict)


class ProjectWorkspaceResponse(BaseModel):
    id: UUID
    organization_id: UUID | None
    name: str
    slug: str
    description: str | None
    status: str
    team_count: int = 0
    member_count: int = 0
    open_task_count: int = 0
    knowledge_page_count: int = 0
    unresolved_discussion_count: int = 0
    created_at: datetime


class ProjectMemberRequest(BaseModel):
    user_id: UUID | None = None
    participant_id: UUID | None = None
    team_id: UUID | None = None
    role_key: str = Field(default="observer", max_length=120)
    permissions: list[str] = Field(default_factory=list)


class CreateMilestoneRequest(BaseModel):
    project_id: UUID
    title: str = Field(min_length=1, max_length=240)
    objective: str | None = Field(default=None, max_length=2000)
    sort_order: int = 0
    due_at: datetime | None = None


class CreateWorkspaceTaskRequest(BaseModel):
    project_id: UUID
    milestone_id: UUID | None = None
    mission_id: UUID | None = None
    source_type: str = Field(default="user", max_length=80)
    source_id: UUID | None = None
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=4000)
    assignee_user_id: UUID | None = None
    assignee_participant_id: UUID | None = None
    priority: str = Field(default="medium", max_length=40)
    dependencies: list[UUID] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    due_at: datetime | None = None


class WorkspaceTaskResponse(BaseModel):
    id: UUID
    project_id: UUID
    milestone_id: UUID | None
    mission_id: UUID | None
    title: str
    description: str | None
    assignee_user_id: UUID | None
    assignee_participant_id: UUID | None
    priority: str
    status: str
    dependencies: list[Any]
    acceptance_criteria: list[str]
    created_at: datetime


class UpsertPresenceRequest(BaseModel):
    user_id: UUID | None = None
    participant_id: UUID | None = None
    project_id: UUID | None = None
    mission_id: UUID | None = None
    resource_type: str | None = Field(default=None, max_length=120)
    resource_id: UUID | None = None
    status: str = Field(default="online", max_length=60)
    activity: str = Field(default="viewing", max_length=160)
    device_id: str | None = Field(default=None, max_length=180)
    cursor_payload: dict[str, Any] = Field(default_factory=dict)


class PresenceResponse(BaseModel):
    id: UUID
    user_id: UUID | None
    participant_id: UUID | None
    project_id: UUID | None
    mission_id: UUID | None
    status: str
    activity: str
    resource_type: str | None
    resource_id: UUID | None
    last_seen_at: datetime


class CreateDiscussionThreadRequest(BaseModel):
    project_id: UUID | None = None
    mission_id: UUID | None = None
    resource_type: str = Field(default="project", max_length=120)
    resource_id: UUID | None = None
    title: str = Field(min_length=1, max_length=240)
    created_by_user_id: UUID | None = None
    created_by_participant_id: UUID | None = None


class CreateCommentRequest(BaseModel):
    thread_id: UUID | None = None
    project_id: UUID | None = None
    mission_id: UUID | None = None
    resource_type: str = Field(default="project", max_length=120)
    resource_id: UUID | None = None
    parent_comment_id: UUID | None = None
    author_user_id: UUID | None = None
    author_participant_id: UUID | None = None
    body: str = Field(min_length=1, max_length=6000)


class CommentResponse(BaseModel):
    id: UUID
    thread_id: UUID | None
    project_id: UUID | None
    mission_id: UUID | None
    resource_type: str
    resource_id: UUID | None
    author_user_id: UUID | None
    author_participant_id: UUID | None
    body: str
    mentions: list[str]
    body_hash: str
    status: str
    created_at: datetime


class UpsertKnowledgePageRequest(BaseModel):
    project_id: UUID
    parent_page_id: UUID | None = None
    title: str = Field(min_length=1, max_length=240)
    page_type: str = Field(default="doc", max_length=80)
    markdown: str = Field(min_length=1, max_length=30000)
    author_user_id: UUID | None = None
    author_participant_id: UUID | None = None
    source_ids: list[UUID] = Field(default_factory=list)
    change_summary: str | None = Field(default=None, max_length=1000)


class KnowledgePageResponse(BaseModel):
    id: UUID
    project_id: UUID
    title: str
    slug: str
    page_type: str
    markdown: str
    status: str
    freshness_status: str
    content_hash: str
    created_at: datetime


class NotificationResponse(BaseModel):
    id: UUID
    recipient_user_id: UUID | None
    recipient_participant_id: UUID | None
    notification_type: str
    title: str
    body: str
    channels: list[str]
    status: str
    resource_type: str | None
    resource_id: UUID | None
    created_at: datetime


class WorkspaceHealthResponse(BaseModel):
    project_id: UUID
    open_tasks: int
    blocked_tasks: int
    unresolved_discussions: int
    stale_knowledge_pages: int
    unread_notifications: int
    health: str
    recommendations: list[str]


class SendCollaborationMessageRequest(BaseModel):
    message_type: str = Field(min_length=1, max_length=80)
    sender_participant_id: UUID
    recipient_participant_ids: list[UUID] = Field(default_factory=list)
    topic_keys: list[str] = Field(default_factory=list)
    workflow_id: UUID | None = None
    task_id: UUID | None = None
    decision_id: UUID | None = None
    subject: str = Field(min_length=1, max_length=300)
    body: str = Field(min_length=1, max_length=6000)
    structured_payload: dict[str, Any] = Field(default_factory=dict)
    priority: str = Field(default="normal", max_length=40)
    confidentiality: str = Field(default="mission", max_length=60)
    requires_acknowledgement: bool = False
    response_required_by: datetime | None = None
    causation_id: UUID | None = None


class CollaborationMessageResponse(BaseModel):
    id: UUID
    mission_id: UUID
    task_id: UUID | None
    decision_id: UUID | None
    message_type: str
    sender_participant_id: UUID
    subject: str
    body: str
    structured_payload: dict[str, Any]
    priority: str
    confidentiality: str
    requires_acknowledgement: bool
    body_hash: str
    created_at: datetime
    version_number: int


class InboxItemResponse(BaseModel):
    id: UUID
    participant_id: UUID
    message_id: UUID
    delivery_status: str
    relevance_score: float
    delivered_at: datetime
    acknowledged_at: datetime | None


class DecisionOptionRequest(BaseModel):
    option_key: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(min_length=1, max_length=2000)
    benefits: list[str] = Field(default_factory=list)
    drawbacks: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    reversibility: str = Field(default="medium", max_length=80)
    estimated_effort: str | None = Field(default=None, max_length=120)
    estimated_cost: str | None = Field(default=None, max_length=120)
    evidence_ids: list[UUID] = Field(default_factory=list)


class CreateDecisionRequest(BaseModel):
    proposer_participant_id: UUID
    decision_key: str = Field(min_length=1, max_length=160)
    decision_type: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=240)
    problem_statement: str = Field(min_length=1, max_length=2000)
    options: list[DecisionOptionRequest] = Field(min_length=1)
    affected_task_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    risk_level: str = Field(default="medium", max_length=40)


class ResolveDecisionRequest(BaseModel):
    selected_option_key: str = Field(min_length=1, max_length=120)
    rationale: str = Field(min_length=1, max_length=2000)
    approver_participant_id: UUID
    human_approved: bool = False


class CollaborationDecisionResponse(BaseModel):
    id: UUID
    mission_id: UUID
    decision_key: str
    title: str
    summary: str
    selected_option: dict[str, Any]
    alternatives: list[dict[str, Any]]
    rationale: str
    status: str
    version_number: int


class CreateReviewRequest(BaseModel):
    mission_id: UUID
    requester_participant_id: UUID
    reviewer_participant_id: UUID
    task_id: UUID | None = None
    review_type: str = Field(min_length=1, max_length=100)
    target_type: str = Field(min_length=1, max_length=100)
    target_id: UUID
    target_hash: str = Field(min_length=8, max_length=128)
    required: bool = True
    blocking: bool = True


class CompleteReviewRequest(BaseModel):
    reviewer_participant_id: UUID
    verdict: str = Field(min_length=1, max_length=60)
    findings: list[dict[str, Any]] = Field(default_factory=list)


class ReviewResponse(BaseModel):
    id: UUID
    mission_id: UUID
    task_id: UUID | None
    review_type: str
    target_type: str
    target_id: UUID
    target_hash: str
    requester_participant_id: UUID
    reviewer_participant_id: UUID
    status: str
    verdict: str | None


class MemoryProposalRequest(BaseModel):
    memory_scope: str = Field(max_length=80)
    scope_reference_id: UUID | None = None
    title: str = Field(min_length=1, max_length=240)
    content: str = Field(min_length=1, max_length=4000)
    content_type: str = Field(default="fact", max_length=80)
    source_type: str = Field(default="decision", max_length=80)
    source_ids: list[UUID] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    sensitivity: str = Field(default="mission", max_length=80)
    confidence: float | None = Field(default=None, ge=0, le=1)


class MemoryItemResponse(BaseModel):
    id: UUID
    memory_scope: str
    scope_reference_id: UUID | None
    title: str
    content: str
    lifecycle_status: str
    trust_level: str
    confidence: float | None
    content_hash: str
    created_at: datetime
