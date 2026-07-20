from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from statistics import mean
from typing import Any
from uuid import UUID

from services.shared.arceus_core_models import ArceusParticipant, ArceusPerformanceObservation, ArceusTask

from ..application.errors import RuntimeStateConflict
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..collaboration.service import CollaborationService
from .api_schemas import AgentCandidateScore, AgentCapability, AgentResponse


AVAILABLE_STATUSES = {"available", "waiting"}
BLOCKED_STATUSES = {"paused", "offline", "suspended", "revoked", "degraded"}
STATUS_SCORE = {
    "available": 0.25,
    "waiting": 0.18,
    "busy": 0.02,
    "degraded": -0.12,
    "paused": -0.4,
    "offline": -0.5,
    "suspended": -1.0,
    "revoked": -1.0,
}


def normalize_capability_keys(capabilities: list[str | dict[str, Any] | AgentCapability]) -> set[str]:
    normalized: set[str] = set()
    for capability in capabilities:
        if isinstance(capability, AgentCapability):
            value = capability.capability_key
        elif isinstance(capability, dict):
            value = str(capability.get("capability_key") or capability.get("key") or capability.get("id") or "")
        else:
            value = str(capability)
        if value.strip():
            normalized.add(value.strip().lower().replace(" ", "_"))
    return normalized


def score_agent_candidate(
    *,
    agent_capabilities: list[str | dict[str, Any] | AgentCapability],
    required_capabilities: list[str],
    status: str,
    performance_score: float = 0.75,
    cost_score: float = 0.75,
    active_task_count: int = 0,
) -> dict[str, Any]:
    required = normalize_capability_keys(required_capabilities)
    available = normalize_capability_keys(agent_capabilities)
    matched = sorted(required & available)
    missing = sorted(required - available)
    capability_score = 1.0 if not required else len(matched) / len(required)
    workload_penalty = min(0.25, active_task_count * 0.05)
    score = (
        capability_score * 0.5
        + STATUS_SCORE.get(status, 0.0)
        + max(0.0, min(1.0, performance_score)) * 0.18
        + max(0.0, min(1.0, cost_score)) * 0.07
        - workload_penalty
    )
    reasons = []
    if matched:
        reasons.append("matches " + ", ".join(matched))
    if missing:
        reasons.append("missing " + ", ".join(missing))
    if status not in AVAILABLE_STATUSES:
        reasons.append(f"status is {status}")
    if active_task_count:
        reasons.append(f"{active_task_count} active task(s)")
    return {
        "score": round(max(0.0, min(1.0, score)), 4),
        "matched_capabilities": matched,
        "missing_capabilities": missing,
        "reasons": reasons or ["generalist fallback"],
    }


def select_best_agent(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    viable = [candidate for candidate in candidates if candidate.get("score", 0) > 0 and candidate.get("status") not in BLOCKED_STATUSES]
    if not viable:
        return None
    return max(viable, key=lambda item: (float(item.get("score", 0)), -int(item.get("active_task_count", 0)), str(item.get("name", ""))))


class MultiAgentRuntimeService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    def register_agent(
        self,
        *,
        tenant_id: UUID,
        name: str,
        role: str,
        participant_type: str,
        organization_id: UUID | None,
        organization_member_id: UUID | None,
        specialist_profile_id: UUID | None,
        capabilities: list[AgentCapability],
        model_profile: str,
        version: str,
        authorities: list[str],
        active_mission_ids: list[UUID],
        actor_id: str,
    ) -> ArceusParticipant:
        if participant_type not in {"ai_specialist", "service", "verifier", "integration", "policy_authority", "human"}:
            raise RuntimeStateConflict("Unsupported agent participant type.", details={"participant_type": participant_type})
        capability_payload = [capability.model_dump(mode="json") for capability in capabilities]
        participant = CollaborationService(self.uow).register_participant(
            tenant_id=tenant_id,
            organization_id=organization_id,
            display_name=name,
            participant_type=participant_type,
            role_key=role,
            organization_member_id=organization_member_id,
            specialist_profile_id=specialist_profile_id,
            capabilities=capability_payload,
            authorities=[*authorities, f"model_profile:{model_profile}", f"version:{version}"],
            active_mission_ids=active_mission_ids,
        )
        self._event(
            tenant_id=tenant_id,
            aggregate_id=participant.id,
            event_type="AGENT_REGISTERED",
            actor_id=actor_id,
            payload={"name": name, "role": role, "model_profile": model_profile, "capabilities": [item.capability_key for item in capabilities]},
        )
        return participant

    def list_agents(
        self,
        *,
        tenant_id: UUID,
        status: str | None = None,
        capability: str | None = None,
        organization_id: UUID | None = None,
        limit: int = 100,
    ) -> list[ArceusParticipant]:
        query = self.uow.db.query(ArceusParticipant).filter(ArceusParticipant.tenant_id == tenant_id)
        if status:
            query = query.filter(ArceusParticipant.status == status)
        if organization_id:
            query = query.filter(ArceusParticipant.organization_id == organization_id)
        rows = query.order_by(ArceusParticipant.updated_at.desc(), ArceusParticipant.id.desc()).limit(min(limit, 250)).all()
        if capability:
            required = normalize_capability_keys([capability])
            rows = [row for row in rows if required & normalize_capability_keys(row.capabilities or [])]
        return rows

    def get_agent(self, *, tenant_id: UUID, agent_id: UUID) -> ArceusParticipant:
        participant = self.uow.db.query(ArceusParticipant).filter(ArceusParticipant.tenant_id == tenant_id, ArceusParticipant.id == agent_id).first()
        if participant is None:
            raise RuntimeStateConflict("Agent was not found.")
        return participant

    def set_status(self, *, tenant_id: UUID, agent_id: UUID, status: str, actor_id: str) -> ArceusParticipant:
        mapped_status = {"disabled": "suspended", "retired": "revoked"}.get(status, status)
        if mapped_status not in {"available", "busy", "waiting", "paused", "offline", "degraded", "suspended", "revoked"}:
            raise RuntimeStateConflict("Unsupported agent status.", details={"status": status})
        participant = self.get_agent(tenant_id=tenant_id, agent_id=agent_id)
        participant.status = mapped_status
        participant.version_number = int(participant.version_number or 1) + 1
        self._event(
            tenant_id=tenant_id,
            aggregate_id=participant.id,
            event_type="AGENT_DISABLED" if mapped_status in {"suspended", "revoked"} else "AGENT_STATUS_CHANGED",
            actor_id=actor_id,
            payload={"status": mapped_status},
        )
        return participant

    def heartbeat(
        self,
        *,
        tenant_id: UUID,
        agent_id: UUID,
        status: str,
        cpu: float | None,
        memory: float | None,
        tasks_running: int,
        latency_ms: float | None,
        health_payload: dict[str, Any],
    ) -> ArceusParticipant:
        participant = self.set_status(tenant_id=tenant_id, agent_id=agent_id, status=status, actor_id=str(agent_id))
        metrics = {"cpu": cpu, "memory": memory, "tasks_running": float(tasks_running), "latency_ms": latency_ms}
        for key, value in metrics.items():
            if value is None:
                continue
            self._record_metric(tenant_id=tenant_id, participant_id=agent_id, metric_key=f"agent_health.{key}", metric_value=float(value), attribution=health_payload)
        self._event(
            tenant_id=tenant_id,
            aggregate_id=agent_id,
            event_type="AGENT_PROGRESS",
            actor_id=str(agent_id),
            payload={"status": participant.status, "tasks_running": tasks_running, "health": health_payload},
        )
        return participant

    def assign_task(
        self,
        *,
        tenant_id: UUID,
        task_id: UUID,
        required_capabilities: list[str],
        excluded_agent_ids: list[UUID],
        prefer_same_organization: bool,
        assign: bool,
        actor_id: str,
    ) -> tuple[AgentCandidateScore | None, list[AgentCandidateScore], bool]:
        task = self.uow.tasks.get(tenant_id=tenant_id, task_id=task_id)
        required = required_capabilities or self._capabilities_for_task(task)
        active_counts = self._active_task_counts(tenant_id=tenant_id)
        performance = self._performance_scores(tenant_id=tenant_id)
        candidates: list[AgentCandidateScore] = []
        for participant in self.list_agents(tenant_id=tenant_id, organization_id=None, limit=250):
            if participant.id in excluded_agent_ids:
                continue
            if prefer_same_organization and task.owner_member_id and participant.organization_member_id == task.owner_member_id:
                continue
            score_payload = score_agent_candidate(
                agent_capabilities=participant.capabilities or [],
                required_capabilities=required,
                status=participant.status,
                performance_score=performance.get(participant.id, 0.75),
                cost_score=self._cost_score(participant),
                active_task_count=active_counts.get(participant.id, 0),
            )
            candidates.append(
                AgentCandidateScore(
                    agent_id=participant.id,
                    name=participant.display_name,
                    role=participant.role_key,
                    status=participant.status,
                    active_task_count=active_counts.get(participant.id, 0),
                    **score_payload,
                )
            )
        selected_raw = select_best_agent([candidate.model_dump() for candidate in candidates])
        selected = AgentCandidateScore(**selected_raw) if selected_raw else None
        assigned = False
        if assign and selected is not None:
            participant = self.get_agent(tenant_id=tenant_id, agent_id=selected.agent_id)
            if participant.organization_member_id:
                task.owner_member_id = participant.organization_member_id
            task.status = "ready" if task.status == "pending" else task.status
            task.version_number = int(task.version_number or 1) + 1
            missions = set(str(item) for item in (participant.active_mission_ids or []))
            missions.add(str(task.mission_id))
            participant.active_mission_ids = sorted(missions)
            participant.status = "busy"
            participant.version_number = int(participant.version_number or 1) + 1
            self._event(
                tenant_id=tenant_id,
                aggregate_id=task.id,
                event_type="AGENT_ASSIGNED",
                actor_id=actor_id,
                payload={"agent_id": str(participant.id), "task_id": str(task.id), "score": selected.score, "capabilities": required},
                correlation_id=task.mission_id,
            )
            assigned = True
        return selected, sorted(candidates, key=lambda item: item.score, reverse=True), assigned

    def send_agent_message(
        self,
        *,
        tenant_id: UUID,
        mission_id: UUID,
        sender_agent_id: UUID,
        receiver_agent_ids: list[UUID],
        message_type: str,
        subject: str,
        body: str,
        structured_payload: dict[str, Any],
        task_id: UUID | None,
        topic_keys: list[str],
        priority: str,
        confidentiality: str,
        correlation_id: UUID,
    ):
        message = CollaborationService(self.uow).send_message(
            tenant_id=tenant_id,
            mission_id=mission_id,
            sender_participant_id=sender_agent_id,
            message_type=message_type,
            subject=subject,
            body=body,
            structured_payload=structured_payload,
            recipient_participant_ids=receiver_agent_ids,
            topic_keys=topic_keys,
            task_id=task_id,
            priority=priority,
            confidentiality=confidentiality,
            correlation_id=correlation_id,
        )
        self._event(
            tenant_id=tenant_id,
            aggregate_id=message.id,
            event_type="AGENT_MESSAGE_SENT",
            actor_id=str(sender_agent_id),
            payload={"receiver_agent_ids": [str(item) for item in receiver_agent_ids], "message_type": message_type},
            correlation_id=mission_id,
        )
        return message

    def metrics(self, *, tenant_id: UUID, agent_id: UUID) -> tuple[dict[str, float], int, float]:
        self.get_agent(tenant_id=tenant_id, agent_id=agent_id)
        rows = (
            self.uow.db.query(ArceusPerformanceObservation)
            .filter(ArceusPerformanceObservation.tenant_id == tenant_id, ArceusPerformanceObservation.participant_id == agent_id)
            .order_by(ArceusPerformanceObservation.created_at.desc())
            .limit(500)
            .all()
        )
        buckets: dict[str, list[float]] = defaultdict(list)
        for row in rows:
            buckets[row.metric_key].append(float(row.metric_value))
        metrics = {key: round(mean(values), 4) for key, values in buckets.items() if values}
        success = metrics.get("agent.task_success", 0.75)
        review = metrics.get("agent.review_score", 0.75)
        latency = metrics.get("agent_health.latency_ms", 1_000)
        latency_score = max(0.0, min(1.0, 1.0 - latency / 10_000))
        reputation = round(success * 0.5 + review * 0.3 + latency_score * 0.2, 4)
        return metrics, len(rows), reputation

    def response(self, participant: ArceusParticipant) -> AgentResponse:
        model_profile = "balanced"
        version = "1.0.0"
        authorities = []
        for item in participant.authorities or []:
            if str(item).startswith("model_profile:"):
                model_profile = str(item).split(":", 1)[1]
            elif str(item).startswith("version:"):
                version = str(item).split(":", 1)[1]
            else:
                authorities.append(str(item))
        return AgentResponse(
            id=participant.id,
            organization_id=participant.organization_id,
            organization_member_id=participant.organization_member_id,
            specialist_profile_id=participant.specialist_profile_id,
            name=participant.display_name,
            role=participant.role_key,
            participant_type=participant.participant_type,
            capabilities=participant.capabilities or [],
            model_profile=model_profile,
            version=version,
            status=participant.status,
            authorities=authorities,
            active_mission_ids=[str(item) for item in (participant.active_mission_ids or [])],
            created_at=participant.created_at,
            updated_at=participant.updated_at,
            version_number=int(participant.version_number or 1),
        )

    def _capabilities_for_task(self, task: ArceusTask) -> list[str]:
        text = " ".join([task.task_type, task.title, str(task.input_contract or {}), str(task.output_contract or {})]).lower()
        capabilities: list[str] = []
        if "frontend" in text or "react" in text or "ui" in text:
            capabilities.extend(["react_development", "responsive_ui"])
        if "backend" in text or "api" in text or "fastapi" in text:
            capabilities.extend(["fastapi_development", "api_design"])
        if "test" in text or "qa" in text or task.task_type == "verification":
            capabilities.extend(["unit_test_design", "evidence_validation"])
        if "security" in text or "auth" in text or "secret" in text:
            capabilities.extend(["security_review", "authentication_review"])
        if "database" in text or "postgres" in text or "migration" in text:
            capabilities.extend(["postgresql_design", "database_migration"])
        return sorted(set(capabilities or [task.task_type or "general_engineering"]))

    def _active_task_counts(self, *, tenant_id: UUID) -> dict[UUID, int]:
        rows = self.uow.db.query(ArceusTask).filter(ArceusTask.tenant_id == tenant_id, ArceusTask.status.in_(["ready", "running", "reviewing", "verifying"])).all()
        member_counts: dict[UUID, int] = defaultdict(int)
        for row in rows:
            if row.owner_member_id:
                member_counts[row.owner_member_id] += 1
        participants = self.uow.db.query(ArceusParticipant).filter(ArceusParticipant.tenant_id == tenant_id).all()
        return {participant.id: member_counts.get(participant.organization_member_id, 0) if participant.organization_member_id else 0 for participant in participants}

    def _performance_scores(self, *, tenant_id: UUID) -> dict[UUID, float]:
        rows = (
            self.uow.db.query(ArceusPerformanceObservation)
            .filter(ArceusPerformanceObservation.tenant_id == tenant_id, ArceusPerformanceObservation.metric_key.in_(["agent.task_success", "agent.review_score"]))
            .all()
        )
        buckets: dict[UUID, list[float]] = defaultdict(list)
        for row in rows:
            if row.participant_id:
                buckets[row.participant_id].append(float(row.metric_value))
        return {participant_id: max(0.0, min(1.0, mean(values))) for participant_id, values in buckets.items() if values}

    def _cost_score(self, participant: ArceusParticipant) -> float:
        for authority in participant.authorities or []:
            if str(authority).startswith("cost_score:"):
                try:
                    return max(0.0, min(1.0, float(str(authority).split(":", 1)[1])))
                except ValueError:
                    return 0.75
        return 0.75

    def _record_metric(self, *, tenant_id: UUID, participant_id: UUID, metric_key: str, metric_value: float, attribution: dict[str, Any]) -> None:
        self.uow.db.add(
            ArceusPerformanceObservation(
                tenant_id=tenant_id,
                participant_id=participant_id,
                subject_type="agent",
                subject_id=participant_id,
                metric_key=metric_key,
                metric_value=metric_value,
                attribution=attribution,
            )
        )

    def _event(
        self,
        *,
        tenant_id: UUID,
        aggregate_id: UUID,
        event_type: str,
        actor_id: str,
        payload: dict[str, Any],
        correlation_id: UUID | None = None,
    ) -> None:
        self.uow.events.append(
            tenant_id=tenant_id,
            aggregate_type="agent",
            aggregate_id=aggregate_id,
            aggregate_version=1,
            event_type=event_type,
            actor_type="agent_runtime",
            actor_id=actor_id,
            payload=payload,
            correlation_id=correlation_id or aggregate_id,
            idempotency_key=f"{event_type}:{aggregate_id}:{actor_id}:{datetime.now(timezone.utc).timestamp()}",
        )
