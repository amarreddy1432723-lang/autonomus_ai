from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


AutomationDomain = Literal[
    "engineering",
    "devops",
    "it_operations",
    "customer_support",
    "sales",
    "marketing",
    "finance",
    "legal",
    "human_resources",
    "compliance",
    "cybersecurity",
    "data_engineering",
    "business_intelligence",
    "operations",
    "procurement",
]
TriggerType = Literal["event", "schedule", "condition", "human_request"]
AutonomyLevel = Literal["L0", "L1", "L2", "L3", "L4"]
RiskLevel = Literal["low", "medium", "high", "critical"]


class AutomationTriggerRequest(BaseModel):
    trigger_type: TriggerType
    source: str = Field(min_length=1, max_length=160)
    condition: str = Field(min_length=1, max_length=500)
    payload: dict[str, Any] = Field(default_factory=dict)
    domain: AutomationDomain
    mission_template: str = Field(min_length=1, max_length=160)
    autonomy_level: AutonomyLevel = "L2"
    dry_run: bool = True


class AutomationTriggerResponse(BaseModel):
    trigger_id: str
    trigger_type: TriggerType
    source: str
    condition: str
    domain: AutomationDomain
    mission_template: str
    risk_level: RiskLevel
    accepted: bool
    status: str
    policy_decision: dict[str, Any]
    generated_mission: dict[str, Any]
    events: list[str]
    created_at: datetime


class AutomationTemplateRequest(BaseModel):
    template_key: str = Field(min_length=1, max_length=160)
    name: str = Field(min_length=3, max_length=240)
    domain: AutomationDomain
    objectives: list[str] = Field(min_length=1, max_length=20)
    required_specialists: list[str] = Field(min_length=1, max_length=20)
    tasks: list[str] = Field(min_length=1, max_length=50)
    approval_gates: list[str] = Field(default_factory=list, max_length=20)
    rollback_required: bool = True


class AutomationTemplateResponse(BaseModel):
    template_key: str
    name: str
    domain: AutomationDomain
    objectives: list[str]
    required_specialists: list[str]
    tasks: list[str]
    approval_gates: list[str]
    rollback_required: bool
    version: int = 1


class AutomationExecuteRequest(BaseModel):
    objective: str = Field(min_length=3, max_length=2_000)
    domain: AutomationDomain
    template_key: str = Field(min_length=1, max_length=160)
    autonomy_level: AutonomyLevel = "L2"
    risk_level: RiskLevel = "medium"
    dry_run: bool = True
    connector_keys: list[str] = Field(default_factory=list, max_length=20)


class AutomationExecuteResponse(BaseModel):
    execution_id: str
    accepted: bool
    status: str
    autonomy_level: AutonomyLevel
    risk_level: RiskLevel
    policy_decision: dict[str, Any]
    workflow: dict[str, Any]
    connector_plan: list[dict[str, Any]]
    required_approvals: list[str]
    audit_events: list[str]
    created_at: datetime


class AutomationMissionResponse(BaseModel):
    mission_id: str
    title: str
    domain: AutomationDomain
    status: str
    autonomy_level: AutonomyLevel
    risk_level: RiskLevel
    owner_organization: str
    generated_from: str
    workflow_steps: list[str]


class AutomationOrganizationResponse(BaseModel):
    organization_key: str
    domain: AutomationDomain
    specialists: list[str]
    policies: list[str]
    connectors: list[str]
    autonomy_ceiling: AutonomyLevel


class AutomationDashboardResponse(BaseModel):
    generated_at: datetime
    automation_coverage: float
    human_intervention_rate: float
    sla_compliance: float
    success_rate: float
    cost_reduction: float
    error_reduction: float
    active_missions: int
    policy_violations: int
    organizations: list[AutomationOrganizationResponse]
    recommendations: list[str]


class ConnectorResponse(BaseModel):
    connector_id: str
    provider: str
    capabilities: list[str]
    authentication: str
    scopes: list[str]
    rate_limits: dict[str, Any]
    health: str
