from __future__ import annotations

from typing import Any

from services.shared.arceus_core_models import (
    ArceusApproval,
    ArceusArtifact,
    ArceusArtifactVersion,
    ArceusCapability,
    ArceusMissionOrganization,
    ArceusMissionRequiredCapability,
    ArceusOrganizationMember,
    ArceusSpecialistCapability,
    ArceusSpecialistProfile,
    ArceusTask,
    ArceusTaskDependency,
    ArceusWorkflowDefinition,
    ArceusWorkflowEdge,
    ArceusWorkflowNode,
)

from ..application.errors import MissionStateConflict
from ..application.unit_of_work import SqlAlchemyUnitOfWork
from ..compiler.utils import stable_hash
from .builder import build_organization_proposals, plan_metrics, validate_plan
from .contracts import PlanBuildResult, PlanMissionCommand, PlannedMember, PlannedTask
from .registry import CAPABILITY_CATALOG, SPECIALIST_REGISTRY


class PlanMissionService:
    def __init__(self, uow: SqlAlchemyUnitOfWork) -> None:
        self.uow = uow

    def plan(self, command: PlanMissionCommand) -> PlanBuildResult:
        existing = self.uow.idempotency.get(
            tenant_id=command.tenant_id,
            scope="mission.plan",
            idempotency_key=command.idempotency_key,
        )
        if existing is not None:
            return PlanBuildResult(**self.uow.idempotency.resolve_existing(existing, command.request_hash))

        mission = self.uow.missions.get(tenant_id=command.tenant_id, mission_id=command.mission_id)
        self.uow.missions.require_version(mission, command.expected_version)
        if mission.status != "compiled":
            raise MissionStateConflict(
                "Mission planning can only run after compilation has completed.",
                details={"current_state": mission.status},
            )
        if mission.current_version_id is None:
            raise MissionStateConflict("Compiled mission does not have a current mission version.")
        from services.shared.arceus_core_models import ArceusMissionVersion

        mission_version = self.uow.db.query(ArceusMissionVersion).filter(
            ArceusMissionVersion.tenant_id == command.tenant_id,
            ArceusMissionVersion.id == mission.current_version_id,
        ).first()
        if mission_version is None:
            raise MissionStateConflict("Compiled mission version was not found.")

        contract = mission_version.mission_contract or {}
        required_capabilities = self._required_capabilities(contract)
        requirements = self._requirements(contract, mission.objective)
        performance_history = self._performance_history()
        proposals = build_organization_proposals(
            requirements,
            required_capabilities,
            mission.risk_level,
            performance_history=performance_history,
        )
        selected_proposal = proposals[0]
        members = list(selected_proposal.members)
        tasks = list(selected_proposal.tasks)
        capability_gaps = list(selected_proposal.capability_gaps)
        validation = validate_plan(members, tasks, requirements)
        if not validation["valid"]:
            raise MissionStateConflict("Generated plan failed validation.", details={"errors": validation["errors"]})

        capability_by_key = self._ensure_registry(required_capabilities, members)
        self._ensure_mission_required_capabilities(command, mission, required_capabilities, capability_by_key)
        previous_workflow = self.uow.workflows.get_for_mission(tenant_id=command.tenant_id, mission_id=mission.id)
        workflow_version = int((previous_workflow.metadata_json or {}).get("workflow_version", 0)) + 1 if previous_workflow else 1
        if previous_workflow is not None and previous_workflow.status in {"draft", "approved"}:
            previous_workflow.status = "superseded"
        organization = self._create_organization(command, mission, members, capability_gaps)
        member_by_role = self._create_members(command, organization, members)

        graph_payload = self._graph_payload(
            mission,
            mission_version,
            members,
            tasks,
            validation,
            capability_gaps,
            selected_proposal=selected_proposal,
            proposals=proposals,
            workflow_version=workflow_version,
            supersedes_workflow_id=str(previous_workflow.id) if previous_workflow is not None else None,
        )
        graph_hash = stable_hash(graph_payload)
        workflow = ArceusWorkflowDefinition(
            tenant_id=command.tenant_id,
            mission_id=mission.id,
            mission_version_id=mission_version.id,
            status="draft",
            graph_hash=graph_hash,
            metadata_json={
                "workflow_version": workflow_version,
                "selected_proposal": selected_proposal.proposal_key,
                "proposal_count": len(proposals),
                "supersedes_workflow_id": str(previous_workflow.id) if previous_workflow is not None else None,
                "critical_path": validation["critical_path"],
                "capability_gaps": capability_gaps,
                "metrics": plan_metrics(members, tasks, validation, capability_gaps),
            },
        )
        self.uow.workflows.add(workflow)
        self.uow.db.flush()
        node_by_task = self._create_workflow_nodes_and_tasks(command, mission, workflow, tasks, member_by_role)
        self._create_workflow_edges(command, workflow, tasks, node_by_task)
        self._create_task_dependencies(command, tasks)

        plan_artifact, plan_version = self._create_plan_artifact(
            command,
            mission,
            workflow,
            graph_payload,
            graph_hash,
        )
        approval = self._create_plan_approval(command, mission, graph_hash)

        previous_status = mission.status
        mission.status = "awaiting_plan_approval"
        mission.active_workflow_id = workflow.id
        mission.version_number = int(mission.version_number) + 1

        event = self.uow.events.append(
            tenant_id=command.tenant_id,
            aggregate_type="mission",
            aggregate_id=mission.id,
            aggregate_version=mission.version_number,
            event_type="PLAN_REVIEW_REQUESTED",
            actor_type="system",
            actor_id="organization-builder",
            payload={
                "mission_id": str(mission.id),
                "previous_status": previous_status,
                "status": mission.status,
                "organization_id": str(organization.id),
                "workflow_id": str(workflow.id),
                "plan_artifact_id": str(plan_artifact.id),
                "plan_artifact_version_id": str(plan_version.id),
                "approval_id": str(approval.id),
                "graph_hash": graph_hash,
                "workflow_version": workflow_version,
                "selected_proposal": selected_proposal.proposal_key,
            },
            correlation_id=command.correlation_id,
            idempotency_key=command.idempotency_key,
        )
        self.uow.outbox.add_from_event(event, topic="arceus.mission.plan.review.requested")

        result = PlanBuildResult(
            mission_id=mission.id,
            organization_id=organization.id,
            workflow_id=workflow.id,
            plan_artifact_id=plan_artifact.id,
            approval_id=approval.id,
            status=mission.status,
            organization_size=len(members),
            task_count=len(tasks),
            graph_hash=graph_hash,
            critical_path=tuple(validation["critical_path"]),
            capability_gaps=tuple(capability_gaps),
            metrics=workflow.metadata_json["metrics"],
        )
        response_payload = {
            **result.__dict__,
            "mission_id": str(result.mission_id),
            "organization_id": str(result.organization_id),
            "workflow_id": str(result.workflow_id),
            "plan_artifact_id": str(result.plan_artifact_id),
            "approval_id": str(result.approval_id),
            "critical_path": list(result.critical_path),
            "capability_gaps": list(result.capability_gaps),
        }
        self.uow.idempotency.complete(
            tenant_id=command.tenant_id,
            scope="mission.plan",
            idempotency_key=command.idempotency_key,
            request_hash=command.request_hash,
            response_payload=response_payload,
        )
        self.uow.audit.record(
            tenant_id=command.tenant_id,
            actor_id=command.actor_id,
            action="mission.plan",
            resource_type="mission",
            resource_id=mission.id,
            result="success",
            metadata={"workflow_id": str(workflow.id), "approval_id": str(approval.id), "graph_hash": graph_hash},
        )
        self.uow.commit()
        return result

    def _required_capabilities(self, contract: dict[str, Any]) -> list[str]:
        required = contract.get("capabilities", {}).get("required") or contract.get("required_capabilities") or []
        normalized = []
        for capability in required:
            key = str(capability).strip()
            if key and key not in normalized:
                normalized.append(key)
        return normalized or ["requirement_analysis", "acceptance_criteria_definition", "build_verification"]

    def _requirements(self, contract: dict[str, Any], fallback: str) -> list[str]:
        requirements = contract.get("requirements") or contract.get("objective", {}).get("outcomes") or []
        if isinstance(requirements, dict):
            requirements = list(requirements.values())
        cleaned = [str(item).strip() for item in requirements if str(item).strip()]
        return cleaned or [fallback]

    def _ensure_registry(self, required_capabilities: list[str], members: list[PlannedMember]) -> dict[str, ArceusCapability]:
        capabilities = set(required_capabilities)
        for member in members:
            capabilities.update(member.assigned_capabilities)
        capability_by_key: dict[str, ArceusCapability] = {}
        for capability_key in sorted(capabilities):
            catalog_item = CAPABILITY_CATALOG.get(
                capability_key,
                {"domain": "Unmapped", "name": capability_key.replace("_", " ").title(), "verification_methods": ["manual_review"]},
            )
            capability = self.uow.db.query(ArceusCapability).filter(ArceusCapability.capability_key == capability_key).first()
            if capability is None:
                capability = ArceusCapability(
                    capability_key=capability_key,
                    domain=catalog_item["domain"],
                    name=catalog_item["name"],
                    description=f"Capability required for Arceus planning: {catalog_item['name']}.",
                    verification_methods=catalog_item["verification_methods"],
                    active=True,
                )
                self.uow.db.add(capability)
                self.uow.db.flush()
            capability_by_key[capability_key] = capability

        for member in members:
            profile = self.uow.db.query(ArceusSpecialistProfile).filter(ArceusSpecialistProfile.specialist_key == member.specialist_key).first()
            if profile is None:
                profile = ArceusSpecialistProfile(
                    specialist_key=member.specialist_key,
                    display_name=member.display_name,
                    specialist_type=member.specialist_type,
                    authority_profile=member.authority,
                    default_model_policy={"routing": "auto", "allowed_provider_classes": ["cloud", "local"]},
                    active=True,
                )
                self.uow.db.add(profile)
                self.uow.db.flush()
            for capability_key in member.assigned_capabilities:
                capability = capability_by_key.get(capability_key)
                if capability is None:
                    continue
                existing = self.uow.db.query(ArceusSpecialistCapability).filter(
                    ArceusSpecialistCapability.specialist_profile_id == profile.id,
                    ArceusSpecialistCapability.capability_id == capability.id,
                ).first()
                if existing is None:
                    self.uow.db.add(
                        ArceusSpecialistCapability(
                            specialist_profile_id=profile.id,
                            capability_id=capability.id,
                            proficiency=0.82 if member.specialist_type == "ai" else 1.0,
                            evidence={"source": "built_in_registry"},
                        )
                    )
        return capability_by_key

    def _ensure_mission_required_capabilities(
        self,
        command: PlanMissionCommand,
        mission,
        required_capabilities: list[str],
        capability_by_key: dict[str, ArceusCapability],
    ) -> None:
        for capability_key in required_capabilities:
            capability = capability_by_key.get(capability_key)
            if capability is None:
                continue
            existing = self.uow.db.query(ArceusMissionRequiredCapability).filter(
                ArceusMissionRequiredCapability.tenant_id == command.tenant_id,
                ArceusMissionRequiredCapability.mission_id == mission.id,
                ArceusMissionRequiredCapability.capability_id == capability.id,
            ).first()
            if existing is None:
                self.uow.db.add(
                    ArceusMissionRequiredCapability(
                        tenant_id=command.tenant_id,
                        mission_id=mission.id,
                        capability_id=capability.id,
                        reason="Required by compiled mission contract and organization planner.",
                        required_level="standard",
                    )
                )

    def _create_organization(self, command: PlanMissionCommand, mission, members: list[PlannedMember], capability_gaps: list[str]) -> ArceusMissionOrganization:
        organization = ArceusMissionOrganization(
            tenant_id=command.tenant_id,
            mission_id=mission.id,
            organization_name=f"{mission.title} Engineering Organization",
            status="draft",
            rationale="Built from compiled mission capabilities, risk level, and required separation of duties.",
            budget_policy={
                "currency": mission.budget_currency,
                "maximum_amount": str(mission.maximum_budget_amount) if mission.maximum_budget_amount is not None else None,
                "capability_gaps": capability_gaps,
                "organization_size": len(members),
            },
        )
        self.uow.db.add(organization)
        self.uow.db.flush()
        return organization

    def _create_members(self, command: PlanMissionCommand, organization: ArceusMissionOrganization, members: list[PlannedMember]) -> dict[str, ArceusOrganizationMember]:
        result: dict[str, ArceusOrganizationMember] = {}
        for member in members:
            profile = self.uow.db.query(ArceusSpecialistProfile).filter(ArceusSpecialistProfile.specialist_key == member.specialist_key).first()
            organization_member = ArceusOrganizationMember(
                tenant_id=command.tenant_id,
                organization_id=organization.id,
                specialist_profile_id=profile.id,
                participant_user_id=command.actor_id if member.specialist_type == "human" else None,
                role_key=member.role_key,
                responsibility=member.responsibility,
                authority={**member.authority, "assigned_capabilities": list(member.assigned_capabilities)},
                can_implement=member.can_implement,
                can_review=member.can_review,
                can_approve=member.can_approve,
                status="active",
            )
            self.uow.db.add(organization_member)
            self.uow.db.flush()
            result[member.role_key] = organization_member
        return result

    def _graph_payload(
        self,
        mission,
        mission_version,
        members: list[PlannedMember],
        tasks: list[PlannedTask],
        validation: dict[str, Any],
        capability_gaps: list[str],
        *,
        selected_proposal,
        proposals,
        workflow_version: int,
        supersedes_workflow_id: str | None,
    ) -> dict[str, Any]:
        return {
            "mission": {"id": str(mission.id), "title": mission.title, "risk_level": mission.risk_level},
            "mission_version_id": str(mission_version.id),
            "workflow_version": workflow_version,
            "supersedes_workflow_id": supersedes_workflow_id,
            "selected_proposal": selected_proposal.proposal_key,
            "organization_proposals": [
                {
                    "proposal_key": proposal.proposal_key,
                    "name": proposal.name,
                    "rationale": proposal.rationale,
                    "organization_size": len(proposal.members),
                    "task_count": len(proposal.tasks),
                    "capability_gaps": list(proposal.capability_gaps),
                    "metrics": proposal.metrics,
                }
                for proposal in proposals
            ],
            "organization": [
                {
                    "role_key": member.role_key,
                    "specialist_key": member.specialist_key,
                    "capabilities": list(member.assigned_capabilities),
                    "can_implement": member.can_implement,
                    "can_review": member.can_review,
                    "can_approve": member.can_approve,
                    "score": member.score,
                    "score_reason": member.score_reason,
                }
                for member in members
            ],
            "tasks": [
                {
                    "task_key": task.task_key,
                    "title": task.title,
                    "category": task.category,
                    "owner_role_key": task.owner_role_key,
                    "dependencies": list(task.dependencies),
                    "outputs": list(task.outputs),
                    "acceptance_criteria": list(task.acceptance_criteria),
                    "verification_methods": list(task.verification_methods),
                    "risk_level": task.risk_level,
                    "estimated_hours": task.estimated_hours,
                    "estimated_cost_usd": task.estimated_cost_usd,
                    "estimated_tokens": task.estimated_tokens,
                }
                for task in tasks
            ],
            "validation": validation,
            "capability_gaps": capability_gaps,
        }

    def _create_workflow_nodes_and_tasks(self, command: PlanMissionCommand, mission, workflow, tasks: list[PlannedTask], member_by_role: dict[str, ArceusOrganizationMember]) -> dict[str, tuple[ArceusWorkflowNode, ArceusTask]]:
        result = {}
        for task in tasks:
            owner = member_by_role[task.owner_role_key]
            node = ArceusWorkflowNode(
                tenant_id=command.tenant_id,
                workflow_id=workflow.id,
                node_key=task.task_key,
                node_type=task.category.lower(),
                title=task.title,
                config={
                    "owner_role_key": task.owner_role_key,
                    "dependencies": list(task.dependencies),
                    "outputs": list(task.outputs),
                    "estimated_hours": task.estimated_hours,
                    "retry_policy": {"max_attempts": 3, "backoff_seconds": 5},
                    "timeout_minutes": 60,
                    "risk_level": task.risk_level,
                    "estimates": {
                        "hours": task.estimated_hours,
                        "cost_usd": task.estimated_cost_usd,
                        "tokens": task.estimated_tokens,
                    },
                },
            )
            self.uow.workflows.add_node(node)
            self.uow.db.flush()
            arceus_task = ArceusTask(
                tenant_id=command.tenant_id,
                mission_id=mission.id,
                workflow_node_id=node.id,
                task_key=task.task_key,
                title=task.title,
                task_type=task.category.lower(),
                status="pending" if task.dependencies else "ready",
                owner_member_id=owner.id,
                input_contract={"description": task.description, "required_capabilities": list(task.required_capabilities)},
                output_contract={"outputs": list(task.outputs), "verification_methods": list(task.verification_methods)},
                acceptance_criteria=list(task.acceptance_criteria),
            )
            self.uow.db.add(arceus_task)
            self.uow.db.flush()
            result[task.task_key] = (node, arceus_task)
        return result

    def _create_workflow_edges(self, command: PlanMissionCommand, workflow, tasks: list[PlannedTask], node_by_task: dict[str, tuple[ArceusWorkflowNode, ArceusTask]]) -> None:
        for task in tasks:
            target_node = node_by_task[task.task_key][0]
            for dependency in task.dependencies:
                source_node = node_by_task[dependency][0]
                self.uow.workflows.add_edge(
                    ArceusWorkflowEdge(
                        tenant_id=command.tenant_id,
                        workflow_id=workflow.id,
                        source_node_id=source_node.id,
                        target_node_id=target_node.id,
                        condition={"type": "hard", "reason": "planner_dependency"},
                    )
                )

    def _create_task_dependencies(self, command: PlanMissionCommand, tasks: list[PlannedTask]) -> None:
        task_rows = {
            task.task_key: self.uow.db.query(ArceusTask)
            .filter(
                ArceusTask.tenant_id == command.tenant_id,
                ArceusTask.mission_id == command.mission_id,
                ArceusTask.task_key == task.task_key,
            )
            .order_by(ArceusTask.created_at.desc())
            .first()
            for task in tasks
        }
        for task in tasks:
            row = task_rows[task.task_key]
            for dependency in task.dependencies:
                self.uow.db.add(
                    ArceusTaskDependency(
                        tenant_id=command.tenant_id,
                        task_id=row.id,
                        depends_on_task_id=task_rows[dependency].id,
                        dependency_type="hard",
                    )
                )

    def _create_plan_artifact(self, command: PlanMissionCommand, mission, workflow, graph_payload: dict[str, Any], graph_hash: str) -> tuple[ArceusArtifact, ArceusArtifactVersion]:
        artifact = ArceusArtifact(
            tenant_id=command.tenant_id,
            mission_id=mission.id,
            artifact_key="execution_plan",
            artifact_type="plan",
            title="Execution Plan",
            trust_status="unverified",
            metadata_json={"workflow_id": str(workflow.id), "graph_hash": graph_hash},
        )
        self.uow.db.add(artifact)
        self.uow.db.flush()
        version = ArceusArtifactVersion(
            tenant_id=command.tenant_id,
            artifact_id=artifact.id,
            version=1,
            content=graph_payload,
            content_hash=graph_hash,
            provenance={"source": "organization_builder", "mission_id": str(mission.id)},
        )
        self.uow.db.add(version)
        self.uow.db.flush()
        artifact.current_version_id = version.id
        return artifact, version

    def _create_plan_approval(self, command: PlanMissionCommand, mission, graph_hash: str) -> ArceusApproval:
        approval = ArceusApproval(
            tenant_id=command.tenant_id,
            mission_id=mission.id,
            approval_type="mission_plan",
            subject_type="execution_plan",
            subject_hash=graph_hash,
            proposed_action="Approve generated organization and workflow plan before implementation.",
            risk_level=mission.risk_level,
            status="pending",
            quorum_policy={"requires_human": True, "required_human_votes": 1, "ai_votes_allowed": False},
        )
        self.uow.db.add(approval)
        self.uow.db.flush()
        return approval

    def _performance_history(self) -> dict[str, dict[str, float]]:
        rows = self.uow.db.query(ArceusSpecialistCapability).all()
        history: dict[str, dict[str, float]] = {}
        for row in rows:
            profile = self.uow.db.query(ArceusSpecialistProfile).filter(ArceusSpecialistProfile.id == row.specialist_profile_id).first()
            if profile is None:
                continue
            evidence = row.evidence or {}
            current = history.setdefault(
                profile.specialist_key,
                {"quality": 0.82, "speed": 0.75, "cost_efficiency": 0.75},
            )
            current["quality"] = max(current["quality"], float(row.proficiency or 0.0))
            if "speed" in evidence:
                current["speed"] = max(current["speed"], float(evidence["speed"]))
            if "cost_efficiency" in evidence:
                current["cost_efficiency"] = max(current["cost_efficiency"], float(evidence["cost_efficiency"]))
        return history
