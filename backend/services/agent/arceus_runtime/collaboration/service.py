from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from services.shared.arceus_core_models import (
    ArceusCollaborationMessage,
    ArceusCollaborationMessageRecipient,
    ArceusCollaborationMessageTopic,
    ArceusDecision,
    ArceusMemoryItem,
    ArceusParticipant,
    ArceusParticipantInboxItem,
    ArceusReview,
    ArceusReviewFinding,
    ArceusTask,
)

from ..application.errors import RuntimeStateConflict
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..compiler.utils import stable_hash


SECRET_PATTERN = re.compile(r"(sk-|Bearer\s+|password=|token=|secret=)[^\s]+", re.IGNORECASE)
HIGH_RISK_DECISIONS = {"security", "authentication", "authorization", "deployment", "data_migration", "budget", "risk_acceptance"}


class CollaborationService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

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
