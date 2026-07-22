from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from services.shared.arceus_core_models import (
    ArceusActivityEvent,
    ArceusCollaborationMilestone,
    ArceusCollaborationMessage,
    ArceusCollaborationMessageRecipient,
    ArceusCollaborationMessageTopic,
    ArceusCollaborationTask,
    ArceusCollaborationTeam,
    ArceusCollaborationTeamMember,
    ArceusComment,
    ArceusDecision,
    ArceusDiscussionThread,
    ArceusKnowledgePage,
    ArceusKnowledgeRevision,
    ArceusNotification,
    ArceusMemoryItem,
    ArceusParticipant,
    ArceusParticipantInboxItem,
    ArceusPresenceSession,
    ArceusProject,
    ArceusProjectMember,
    ArceusReview,
    ArceusReviewFinding,
    ArceusTask,
)

from ..application.errors import RuntimeStateConflict
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..compiler.utils import stable_hash


SECRET_PATTERN = re.compile(r"(sk-|Bearer\s+|password=|token=|secret=)[^\s]+", re.IGNORECASE)
HIGH_RISK_DECISIONS = {"security", "authentication", "authorization", "deployment", "data_migration", "budget", "risk_acceptance"}
MENTION_PATTERN = re.compile(r"@([A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+)*)")


class CollaborationService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    def create_team(self, *, tenant_id: UUID, organization_id: UUID | None, name: str, description: str | None, lead_user_id: UUID | None = None) -> ArceusCollaborationTeam:
        slug = self._unique_slug(ArceusCollaborationTeam, tenant_id=tenant_id, value=name)
        team = ArceusCollaborationTeam(
            tenant_id=tenant_id,
            organization_id=organization_id,
            name=name,
            slug=slug,
            description=description,
            lead_user_id=lead_user_id,
        )
        self.uow.db.add(team)
        self.uow.db.flush()
        self._activity(tenant_id=tenant_id, project_id=None, event_type="team.created", resource_type="team", resource_id=team.id, message=f"Team created: {name}")
        return team

    def add_team_member(self, *, tenant_id: UUID, team_id: UUID, user_id: UUID | None, participant_id: UUID | None, member_type: str, role_key: str) -> ArceusCollaborationTeamMember:
        if not user_id and not participant_id:
            raise RuntimeStateConflict("Team member requires either user_id or participant_id.")
        existing = (
            self.uow.db.query(ArceusCollaborationTeamMember)
            .filter(
                ArceusCollaborationTeamMember.tenant_id == tenant_id,
                ArceusCollaborationTeamMember.team_id == team_id,
                ArceusCollaborationTeamMember.user_id == user_id,
                ArceusCollaborationTeamMember.participant_id == participant_id,
            )
            .first()
        )
        if existing:
            existing.status = "active"
            existing.role_key = role_key
            return existing
        item = ArceusCollaborationTeamMember(
            tenant_id=tenant_id,
            team_id=team_id,
            user_id=user_id,
            participant_id=participant_id,
            member_type=member_type,
            role_key=role_key,
        )
        self.uow.db.add(item)
        self.uow.db.flush()
        return item

    def create_project_workspace(
        self,
        *,
        tenant_id: UUID,
        organization_id: UUID | None,
        name: str,
        description: str | None,
        created_by: UUID,
        team_ids: list[UUID] | None = None,
        settings: dict[str, Any] | None = None,
    ) -> ArceusProject:
        slug = self._unique_slug(ArceusProject, tenant_id=tenant_id, value=name)
        project = ArceusProject(
            tenant_id=tenant_id,
            name=name,
            slug=slug,
            description=description,
            status="active",
            created_by=created_by,
            settings={**(settings or {}), "organization_id": str(organization_id) if organization_id else None, "collaboration_enabled": True},
        )
        self.uow.db.add(project)
        self.uow.db.flush()
        for team_id in team_ids or []:
            self.add_project_member(tenant_id=tenant_id, project_id=project.id, team_id=team_id, user_id=None, participant_id=None, role_key="team")
        self._activity(tenant_id=tenant_id, project_id=project.id, event_type="project.created", resource_type="project", resource_id=project.id, message=f"Project workspace created: {name}")
        return project

    def add_project_member(self, *, tenant_id: UUID, project_id: UUID, user_id: UUID | None, participant_id: UUID | None, team_id: UUID | None, role_key: str, permissions: list[str] | None = None) -> ArceusProjectMember:
        if not any([user_id, participant_id, team_id]):
            raise RuntimeStateConflict("Project membership requires a user, participant, or team.")
        existing = (
            self.uow.db.query(ArceusProjectMember)
            .filter(
                ArceusProjectMember.tenant_id == tenant_id,
                ArceusProjectMember.project_id == project_id,
                ArceusProjectMember.user_id == user_id,
                ArceusProjectMember.participant_id == participant_id,
                ArceusProjectMember.team_id == team_id,
            )
            .first()
        )
        if existing:
            existing.status = "active"
            existing.role_key = role_key
            existing.permissions = permissions or existing.permissions or []
            return existing
        item = ArceusProjectMember(
            tenant_id=tenant_id,
            project_id=project_id,
            user_id=user_id,
            participant_id=participant_id,
            team_id=team_id,
            role_key=role_key,
            permissions=permissions or [],
        )
        self.uow.db.add(item)
        self.uow.db.flush()
        return item

    def create_milestone(self, *, tenant_id: UUID, project_id: UUID, title: str, objective: str | None = None, sort_order: int = 0, due_at=None) -> ArceusCollaborationMilestone:
        milestone = ArceusCollaborationMilestone(tenant_id=tenant_id, project_id=project_id, title=title, objective=objective, sort_order=sort_order, due_at=due_at)
        self.uow.db.add(milestone)
        self.uow.db.flush()
        self._activity(tenant_id=tenant_id, project_id=project_id, event_type="milestone.created", resource_type="milestone", resource_id=milestone.id, message=f"Milestone created: {title}")
        return milestone

    def create_workspace_task(self, *, tenant_id: UUID, project_id: UUID, title: str, **kwargs) -> ArceusCollaborationTask:
        task = ArceusCollaborationTask(
            tenant_id=tenant_id,
            project_id=project_id,
            title=title,
            status="backlog",
            dependencies=[str(item) for item in kwargs.pop("dependencies", [])],
            **kwargs,
        )
        self.uow.db.add(task)
        self.uow.db.flush()
        self._activity(tenant_id=tenant_id, project_id=project_id, mission_id=task.mission_id, event_type="task.created", resource_type="task", resource_id=task.id, message=f"Task created: {title}")
        if task.assignee_user_id or task.assignee_participant_id:
            self._notification(
                tenant_id=tenant_id,
                recipient_user_id=task.assignee_user_id,
                recipient_participant_id=task.assignee_participant_id,
                notification_type="assignment",
                title=f"Assigned: {title}",
                body=task.description or "A workspace task was assigned to you.",
                resource_type="task",
                resource_id=task.id,
            )
        return task

    def upsert_presence(self, *, tenant_id: UUID, **kwargs) -> ArceusPresenceSession:
        if not kwargs.get("user_id") and not kwargs.get("participant_id"):
            raise RuntimeStateConflict("Presence requires user_id or participant_id.")
        device_id = kwargs.get("device_id") or "default"
        existing = (
            self.uow.db.query(ArceusPresenceSession)
            .filter(
                ArceusPresenceSession.tenant_id == tenant_id,
                ArceusPresenceSession.user_id == kwargs.get("user_id"),
                ArceusPresenceSession.participant_id == kwargs.get("participant_id"),
                ArceusPresenceSession.device_id == device_id,
            )
            .first()
        )
        if existing:
            for key, value in kwargs.items():
                setattr(existing, key, value)
            existing.device_id = device_id
            existing.last_seen_at = datetime.now(timezone.utc)
            existing.version_number = int(existing.version_number or 1) + 1
            return existing
        item = ArceusPresenceSession(tenant_id=tenant_id, device_id=device_id, **kwargs)
        self.uow.db.add(item)
        self.uow.db.flush()
        return item

    def create_thread(self, *, tenant_id: UUID, **kwargs) -> ArceusDiscussionThread:
        thread = ArceusDiscussionThread(tenant_id=tenant_id, **kwargs)
        self.uow.db.add(thread)
        self.uow.db.flush()
        self._activity(tenant_id=tenant_id, project_id=thread.project_id, mission_id=thread.mission_id, event_type="discussion.created", resource_type="discussion", resource_id=thread.id, message=f"Discussion opened: {thread.title}")
        return thread

    def add_comment(self, *, tenant_id: UUID, body: str, **kwargs) -> ArceusComment:
        if SECRET_PATTERN.search(body):
            raise RuntimeStateConflict("Raw secrets cannot be posted in comments.")
        mentions = sorted(set(MENTION_PATTERN.findall(body)))
        comment = ArceusComment(tenant_id=tenant_id, body=body, mentions=mentions, body_hash=stable_hash({"body": body, "resource": kwargs.get("resource_id")}), **kwargs)
        self.uow.db.add(comment)
        self.uow.db.flush()
        self._activity(tenant_id=tenant_id, project_id=comment.project_id, mission_id=comment.mission_id, event_type="comment.added", resource_type=comment.resource_type, resource_id=comment.resource_id, message="Comment added")
        for mention in mentions:
            self._notification(
                tenant_id=tenant_id,
                recipient_user_id=None,
                recipient_participant_id=None,
                notification_type="mention",
                title=f"New mention: @{mention}",
                body=body[:500],
                resource_type="comment",
                resource_id=comment.id,
            )
        return comment

    def upsert_knowledge_page(self, *, tenant_id: UUID, project_id: UUID, title: str, markdown: str, change_summary: str | None = None, **kwargs) -> ArceusKnowledgePage:
        if SECRET_PATTERN.search(markdown):
            raise RuntimeStateConflict("Raw secrets cannot be stored in knowledge pages.")
        slug = self._slug(title)
        content_hash = stable_hash({"title": title, "markdown": markdown})
        page = self.uow.db.query(ArceusKnowledgePage).filter(ArceusKnowledgePage.tenant_id == tenant_id, ArceusKnowledgePage.project_id == project_id, ArceusKnowledgePage.slug == slug).first()
        if page:
            revision_number = int(page.version_number or 1) + 1
            page.title = title
            page.markdown = markdown
            page.content_hash = content_hash
            page.version_number = revision_number
        else:
            revision_number = 1
            page = ArceusKnowledgePage(tenant_id=tenant_id, project_id=project_id, title=title, slug=slug, markdown=markdown, content_hash=content_hash, **kwargs)
            self.uow.db.add(page)
            self.uow.db.flush()
        self.uow.db.add(
            ArceusKnowledgeRevision(
                tenant_id=tenant_id,
                page_id=page.id,
                revision_number=revision_number,
                markdown=markdown,
                content_hash=content_hash,
                author_user_id=kwargs.get("author_user_id"),
                change_summary=change_summary,
            )
        )
        self._activity(tenant_id=tenant_id, project_id=project_id, event_type="knowledge.updated", resource_type="knowledge_page", resource_id=page.id, message=f"Knowledge page updated: {title}")
        self.uow.db.flush()
        return page

    def workspace_health(self, *, tenant_id: UUID, project_id: UUID) -> dict[str, Any]:
        open_tasks = self.uow.db.query(ArceusCollaborationTask).filter(ArceusCollaborationTask.tenant_id == tenant_id, ArceusCollaborationTask.project_id == project_id, ArceusCollaborationTask.status.in_(["backlog", "planned", "in_progress", "review"])).count()
        blocked_tasks = self.uow.db.query(ArceusCollaborationTask).filter(ArceusCollaborationTask.tenant_id == tenant_id, ArceusCollaborationTask.project_id == project_id, ArceusCollaborationTask.status == "blocked").count()
        unresolved = self.uow.db.query(ArceusDiscussionThread).filter(ArceusDiscussionThread.tenant_id == tenant_id, ArceusDiscussionThread.project_id == project_id, ArceusDiscussionThread.status == "open").count()
        stale_docs = self.uow.db.query(ArceusKnowledgePage).filter(ArceusKnowledgePage.tenant_id == tenant_id, ArceusKnowledgePage.project_id == project_id, ArceusKnowledgePage.freshness_status == "stale").count()
        unread = self.uow.db.query(ArceusNotification).filter(ArceusNotification.tenant_id == tenant_id, ArceusNotification.status == "unread").count()
        recommendations = []
        if blocked_tasks:
            recommendations.append("Resolve blocked tasks before planning new implementation work.")
        if unresolved:
            recommendations.append("Summarize or resolve open discussions to reduce decision drift.")
        if stale_docs:
            recommendations.append("Refresh stale knowledge pages before using them as mission context.")
        health = "attention" if blocked_tasks or stale_docs else "review" if unresolved else "healthy"
        return {
            "project_id": project_id,
            "open_tasks": open_tasks,
            "blocked_tasks": blocked_tasks,
            "unresolved_discussions": unresolved,
            "stale_knowledge_pages": stale_docs,
            "unread_notifications": unread,
            "health": health,
            "recommendations": recommendations,
        }

    def register_participant(
        self,
        *,
        tenant_id: UUID,
        organization_id: UUID | None,
        display_name: str,
        participant_type: str,
        role_key: str | None = None,
        user_id: UUID | None = None,
        organization_member_id: UUID | None = None,
        specialist_profile_id: UUID | None = None,
        capabilities: list[str] | None = None,
        authorities: list[str] | None = None,
        active_mission_ids: list[UUID] | None = None,
    ) -> ArceusParticipant:
        participant = ArceusParticipant(
            tenant_id=tenant_id,
            organization_id=organization_id,
            user_id=user_id,
            organization_member_id=organization_member_id,
            participant_type=participant_type,
            display_name=display_name,
            role_key=role_key,
            specialist_profile_id=specialist_profile_id,
            capabilities=capabilities or [],
            authorities=authorities or [],
            active_mission_ids=[str(item) for item in (active_mission_ids or [])],
            status="available",
        )
        self.uow.db.add(participant)
        self.uow.db.flush()
        return participant

    def send_message(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID,
        sender_participant_id: UUID,
        message_type: str,
        subject: str,
        body: str,
        structured_payload: dict[str, Any],
        correlation_id: UUID,
        workflow_id: UUID | None = None,
        task_id: UUID | None = None,
        decision_id: UUID | None = None,
        recipient_participant_ids: list[UUID] | None = None,
        topic_keys: list[str] | None = None,
        priority: str = "normal",
        confidentiality: str = "mission",
        requires_acknowledgement: bool = False,
        response_required_by=None,
        causation_id: UUID | None = None,
    ) -> ArceusCollaborationMessage:
        self.uow.missions.get(tenant_id=tenant_id, mission_id=mission_id)
        sender = self._participant(tenant_id=tenant_id, participant_id=sender_participant_id)
        if sender.status in {"suspended", "revoked"}:
            raise RuntimeStateConflict("Suspended or revoked participants cannot send collaboration messages.")
        if SECRET_PATTERN.search(body) and confidentiality != "secret_reference_only":
            raise RuntimeStateConflict("Message body appears to contain a raw secret; send a secret reference instead.")
        if len(body) > 6_000:
            raise RuntimeStateConflict("Collaboration message body exceeds the maximum size.")
        message = ArceusCollaborationMessage(
            tenant_id=tenant_id,
            mission_id=mission_id,
            workflow_id=workflow_id,
            task_id=task_id,
            decision_id=decision_id,
            message_type=message_type,
            sender_participant_id=sender_participant_id,
            subject=subject,
            body=body,
            structured_payload=structured_payload or {},
            priority=priority,
            confidentiality=confidentiality,
            requires_acknowledgement=requires_acknowledgement,
            response_required_by=response_required_by,
            correlation_id=correlation_id,
            causation_id=causation_id,
            body_hash=stable_hash({"subject": subject, "body": body, "payload": structured_payload or {}}),
        )
        self.uow.db.add(message)
        self.uow.db.flush()
        recipients = self._resolve_recipients(
            tenant_id=tenant_id,
            mission_id=mission_id,
            explicit_recipient_ids=recipient_participant_ids or [],
            topic_keys=topic_keys or [],
            message_type=message_type,
            task_id=task_id,
        )
        for topic_key in sorted(set(topic_keys or [])):
            self.uow.db.add(ArceusCollaborationMessageTopic(tenant_id=tenant_id, message_id=message.id, topic_key=topic_key))
        for recipient, score in recipients:
            self.uow.db.add(
                ArceusCollaborationMessageRecipient(
                    tenant_id=tenant_id,
                    message_id=message.id,
                    participant_id=recipient.id,
                    relevance_score=score,
                    delivery_status="delivered",
                )
            )
            if score >= 0.35:
                self.uow.db.add(
                    ArceusParticipantInboxItem(
                        tenant_id=tenant_id,
                        participant_id=recipient.id,
                        message_id=message.id,
                        relevance_score=score,
                        delivery_status="unread",
                    )
                )
        self._event(
            tenant_id=tenant_id,
            aggregate_type="collaboration_message",
            aggregate_id=message.id,
            aggregate_version=message.version_number,
            event_type="MESSAGE_CREATED",
            actor_id=str(sender_participant_id),
            payload={"mission_id": str(mission_id), "message_type": message_type, "recipient_count": len(recipients)},
            correlation_id=correlation_id,
        )
        return message

    def acknowledge_inbox_item(self, *, tenant_id: UUID, item_id: UUID, participant_id: UUID) -> ArceusParticipantInboxItem:
        item = (
            self.uow.db.query(ArceusParticipantInboxItem)
            .filter(
                ArceusParticipantInboxItem.tenant_id == tenant_id,
                ArceusParticipantInboxItem.id == item_id,
                ArceusParticipantInboxItem.participant_id == participant_id,
            )
            .first()
        )
        if item is None:
            raise RuntimeStateConflict("Inbox item was not found for this participant.")
        item.delivery_status = "acknowledged"
        item.acknowledged_at = datetime.now(timezone.utc)
        item.version_number = int(item.version_number or 1) + 1
        self._event(
            tenant_id=tenant_id,
            aggregate_type="participant_inbox_item",
            aggregate_id=item.id,
            aggregate_version=item.version_number,
            event_type="MESSAGE_ACKNOWLEDGED",
            actor_id=str(participant_id),
            payload={"message_id": str(item.message_id)},
            correlation_id=item.message_id,
        )
        return item

    def create_decision(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID,
        proposer_participant_id: UUID,
        decision_key: str,
        decision_type: str,
        title: str,
        problem_statement: str,
        options: list[dict[str, Any]],
        evidence_ids: list[UUID] | None = None,
        affected_task_ids: list[UUID] | None = None,
        risk_level: str = "medium",
    ) -> ArceusDecision:
        proposer = self._participant(tenant_id=tenant_id, participant_id=proposer_participant_id)
        if proposer.status in {"suspended", "revoked"}:
            raise RuntimeStateConflict("Revoked participants cannot propose decisions.")
        scored_options = self._score_options(options)
        if len(scored_options) < 2 and decision_type not in {"policy_interpretation"}:
            raise RuntimeStateConflict("Important decisions require at least two meaningful options.")
        best = max(scored_options, key=lambda item: item["score"])
        decision = ArceusDecision(
            tenant_id=tenant_id,
            mission_id=mission_id,
            decision_key=decision_key,
            title=title,
            summary=problem_statement,
            selected_option={},
            alternatives=scored_options,
            rationale=f"Recommended option: {best['option_key']} with score {best['score']}.",
            status="proposed",
            decided_by_member_id=proposer.organization_member_id,
        )
        decision.alternatives = [
            {
                **item,
                "evidence_ids": [str(evidence_id) for evidence_id in item.get("evidence_ids", [])],
                "affected_task_ids": [str(task_id) for task_id in (affected_task_ids or [])],
                "risk_level": risk_level,
            }
            for item in decision.alternatives
        ]
        self.uow.db.add(decision)
        self.uow.db.flush()
        self._event(
            tenant_id=tenant_id,
            aggregate_type="decision",
            aggregate_id=decision.id,
            aggregate_version=decision.version_number,
            event_type="DECISION_OPENED",
            actor_id=str(proposer_participant_id),
            payload={"decision_key": decision_key, "decision_type": decision_type, "evidence_ids": [str(item) for item in (evidence_ids or [])]},
            correlation_id=mission_id,
        )
        return decision

    def resolve_decision(
        self,
        *,
        tenant_id: UUID,
        decision_id: UUID,
        selected_option_key: str,
        rationale: str,
        approver_participant_id: UUID,
        human_approved: bool,
    ) -> ArceusDecision:
        decision = self.uow.decisions.get(tenant_id=tenant_id, decision_id=decision_id)
        approver = self._participant(tenant_id=tenant_id, participant_id=approver_participant_id)
        risk_level = next((item.get("risk_level") for item in decision.alternatives if item.get("option_key") == selected_option_key), "medium")
        if (risk_level in {"high", "critical"} or "security" in decision.decision_key or "auth" in decision.decision_key) and not human_approved:
            raise RuntimeStateConflict("High-risk decisions require human approval.")
        option = next((item for item in decision.alternatives if item.get("option_key") == selected_option_key), None)
        if option is None:
            raise RuntimeStateConflict("Selected decision option was not found.")
        decision.selected_option = option
        decision.rationale = rationale
        decision.status = "approved"
        decision.decided_by_member_id = approver.organization_member_id
        decision.version_number = int(decision.version_number or 1) + 1
        self._event(
            tenant_id=tenant_id,
            aggregate_type="decision",
            aggregate_id=decision.id,
            aggregate_version=decision.version_number,
            event_type="DECISION_APPROVED",
            actor_id=str(approver_participant_id),
            payload={"selected_option_key": selected_option_key, "human_approved": human_approved},
            correlation_id=decision.mission_id,
        )
        return decision

    def request_review(self, *, tenant_id: UUID, mission_id: UUID, requester_participant_id: UUID, reviewer_participant_id: UUID, **kwargs) -> ArceusReview:
        if requester_participant_id == reviewer_participant_id:
            raise RuntimeStateConflict("Review requester and reviewer must be independent.")
        requester = self._participant(tenant_id=tenant_id, participant_id=requester_participant_id)
        reviewer = self._participant(tenant_id=tenant_id, participant_id=reviewer_participant_id)
        if requester.organization_member_id and requester.organization_member_id == reviewer.organization_member_id:
            raise RuntimeStateConflict("Artifact author cannot be assigned as independent reviewer.")
        review = ArceusReview(
            tenant_id=tenant_id,
            mission_id=mission_id,
            requester_participant_id=requester_participant_id,
            reviewer_participant_id=reviewer_participant_id,
            **kwargs,
        )
        self.uow.db.add(review)
        self.uow.db.flush()
        self._event(
            tenant_id=tenant_id,
            aggregate_type="review",
            aggregate_id=review.id,
            aggregate_version=review.version_number,
            event_type="REVIEW_REQUESTED",
            actor_id=str(requester_participant_id),
            payload={"reviewer_participant_id": str(reviewer_participant_id), "target_hash": review.target_hash},
            correlation_id=mission_id,
        )
        return review

    def complete_review(self, *, tenant_id: UUID, review_id: UUID, reviewer_participant_id: UUID, verdict: str, findings: list[dict[str, Any]]) -> ArceusReview:
        review = self.uow.db.query(ArceusReview).filter(ArceusReview.tenant_id == tenant_id, ArceusReview.id == review_id).first()
        if review is None:
            raise RuntimeStateConflict("Review was not found.")
        if review.reviewer_participant_id != reviewer_participant_id:
            raise RuntimeStateConflict("Only the assigned reviewer can complete this review.")
        for index, finding in enumerate(findings, start=1):
            self.uow.db.add(
                ArceusReviewFinding(
                    tenant_id=tenant_id,
                    review_id=review.id,
                    finding_key=str(finding.get("finding_key") or f"finding_{index}"),
                    severity=str(finding.get("severity") or "medium"),
                    statement=str(finding.get("statement") or ""),
                    evidence_ids=[str(item) for item in finding.get("evidence_ids", [])],
                    status="open",
                )
            )
        review.status = "completed"
        review.verdict = verdict
        review.completed_at = datetime.now(timezone.utc)
        review.version_number = int(review.version_number or 1) + 1
        self._event(
            tenant_id=tenant_id,
            aggregate_type="review",
            aggregate_id=review.id,
            aggregate_version=review.version_number,
            event_type="REVIEW_COMPLETED",
            actor_id=str(reviewer_participant_id),
            payload={"verdict": verdict, "finding_count": len(findings), "target_hash": review.target_hash},
            correlation_id=review.mission_id,
        )
        return review

    def propose_memory(self, *, tenant_id: UUID, **kwargs) -> ArceusMemoryItem:
        if SECRET_PATTERN.search(kwargs["content"]):
            raise RuntimeStateConflict("Raw secrets cannot be stored as memory.")
        content_hash = stable_hash(
            {
                "scope": kwargs["memory_scope"],
                "scope_reference_id": str(kwargs.get("scope_reference_id")),
                "title": kwargs["title"],
                "content": kwargs["content"],
            }
        )
        item = ArceusMemoryItem(
            tenant_id=tenant_id,
            content_hash=content_hash,
            lifecycle_status="proposed",
            trust_level="unverified",
            source_ids=[str(item) for item in kwargs.get("source_ids", [])],
            evidence_ids=[str(item) for item in kwargs.get("evidence_ids", [])],
            **{key: value for key, value in kwargs.items() if key not in {"source_ids", "evidence_ids"}},
        )
        self.uow.db.add(item)
        self.uow.db.flush()
        return item

    def approve_memory(self, *, tenant_id: UUID, memory_id: UUID) -> ArceusMemoryItem:
        item = self.uow.db.query(ArceusMemoryItem).filter(ArceusMemoryItem.tenant_id == tenant_id, ArceusMemoryItem.id == memory_id).first()
        if item is None:
            raise RuntimeStateConflict("Memory item was not found.")
        if item.trust_level == "unverified" and not item.evidence_ids:
            raise RuntimeStateConflict("Unverified memory requires evidence before approval.")
        item.lifecycle_status = "approved"
        item.trust_level = "authoritative"
        item.version_number = int(item.version_number or 1) + 1
        return item

    def _resolve_recipients(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID,
        explicit_recipient_ids: list[UUID],
        topic_keys: list[str],
        message_type: str,
        task_id: UUID | None,
    ) -> list[tuple[ArceusParticipant, float]]:
        candidates = self.uow.db.query(ArceusParticipant).filter(ArceusParticipant.tenant_id == tenant_id).all()
        resolved: dict[UUID, tuple[ArceusParticipant, float]] = {}
        for participant in candidates:
            score = self._relevance_score(
                participant=participant,
                mission_id=mission_id,
                explicit=participant.id in explicit_recipient_ids,
                topic_keys=topic_keys,
                message_type=message_type,
                task_id=task_id,
            )
            if score > 0:
                resolved[participant.id] = (participant, score)
        return list(resolved.values())

    def _relevance_score(self, *, participant: ArceusParticipant, mission_id: UUID, explicit: bool, topic_keys: list[str], message_type: str, task_id: UUID | None) -> float:
        score = 0.0
        active_missions = {str(item) for item in participant.active_mission_ids or []}
        if explicit:
            score += 0.7
        if str(mission_id) in active_missions:
            score += 0.25
        if participant.role_key and any(participant.role_key in topic for topic in topic_keys):
            score += 0.25
        if message_type in {"risk_alert", "review_request"} and participant.role_key and "reviewer" in participant.role_key:
            score += 0.25
        if task_id and participant.organization_member_id:
            task = self.uow.db.query(ArceusTask).filter(ArceusTask.tenant_id == participant.tenant_id, ArceusTask.id == task_id).first()
            if task is not None and task.owner_member_id == participant.organization_member_id:
                score += 0.3
        if participant.status in {"suspended", "revoked", "offline"}:
            score -= 1.0
        return round(max(0.0, min(1.0, score)), 4)

    def _score_options(self, options: list[dict[str, Any]]) -> list[dict[str, Any]]:
        scored = []
        for option in options:
            benefits = len(option.get("benefits") or [])
            drawbacks = len(option.get("drawbacks") or [])
            risks = len(option.get("risks") or [])
            reversibility = {"high": 0.2, "medium": 0.1, "low": -0.05}.get(str(option.get("reversibility") or "medium").lower(), 0.1)
            score = round(max(0.0, min(1.0, 0.55 + benefits * 0.06 - drawbacks * 0.04 - risks * 0.05 + reversibility)), 3)
            scored.append({**option, "score": score})
        return scored

    def _participant(self, *, tenant_id: UUID, participant_id: UUID) -> ArceusParticipant:
        participant = self.uow.db.query(ArceusParticipant).filter(ArceusParticipant.tenant_id == tenant_id, ArceusParticipant.id == participant_id).first()
        if participant is None:
            raise RuntimeStateConflict("Participant was not found.")
        return participant

    def _event(self, *, tenant_id: UUID, aggregate_type: str, aggregate_id: UUID, aggregate_version: int, event_type: str, actor_id: str, payload: dict[str, Any], correlation_id: UUID) -> None:
        self.uow.events.append(
            tenant_id=tenant_id,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            aggregate_version=aggregate_version,
            event_type=event_type,
            actor_type="participant",
            actor_id=actor_id,
            payload=payload,
            correlation_id=correlation_id,
            idempotency_key=f"{event_type}:{aggregate_id}:{aggregate_version}:{actor_id}",
        )

    def _activity(self, *, tenant_id: UUID, project_id: UUID | None, event_type: str, resource_type: str, resource_id: UUID | None, message: str, mission_id: UUID | None = None, payload: dict[str, Any] | None = None) -> None:
        self.uow.db.add(
            ArceusActivityEvent(
                tenant_id=tenant_id,
                project_id=project_id,
                mission_id=mission_id,
                event_type=event_type,
                resource_type=resource_type,
                resource_id=resource_id,
                message=message,
                payload=payload or {},
            )
        )

    def _notification(self, *, tenant_id: UUID, recipient_user_id: UUID | None, recipient_participant_id: UUID | None, notification_type: str, title: str, body: str, resource_type: str, resource_id: UUID | None) -> None:
        self.uow.db.add(
            ArceusNotification(
                tenant_id=tenant_id,
                recipient_user_id=recipient_user_id,
                recipient_participant_id=recipient_participant_id,
                notification_type=notification_type,
                title=title,
                body=body,
                channels=["desktop", "web"],
                status="unread",
                resource_type=resource_type,
                resource_id=resource_id,
            )
        )

    def _unique_slug(self, model, *, tenant_id: UUID, value: str) -> str:
        base = self._slug(value)
        slug = base
        index = 2
        while self.uow.db.query(model).filter(model.tenant_id == tenant_id, model.slug == slug).first():
            slug = f"{base}-{index}"
            index += 1
        return slug

    def _slug(self, value: str) -> str:
        cleaned = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return cleaned or "workspace"
