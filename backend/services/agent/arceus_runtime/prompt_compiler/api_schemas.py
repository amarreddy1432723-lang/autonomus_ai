from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from ..context_engine.api_schemas import ContextPackage


PromptBlockType = Literal[
    "system_policy",
    "organization_policy",
    "agent_role",
    "mission_objective",
    "task_instruction",
    "execution_state",
    "context",
    "memory",
    "tool_definition",
    "output_contract",
    "verification",
    "untrusted_data",
]


class PromptBudget(BaseModel):
    maximum_input_tokens: int = Field(default=32_000, ge=1_000, le=2_000_000)
    reserved_output_tokens: int = Field(default=4_000, ge=500, le=200_000)
    maximum_tool_definitions_tokens: int = Field(default=4_000, ge=0, le=100_000)
    maximum_context_tokens: int = Field(default=20_000, ge=0, le=1_500_000)
    maximum_memory_tokens: int = Field(default=2_000, ge=0, le=100_000)


class RuntimePromptState(BaseModel):
    mission_status: str = "draft"
    task_status: str = "pending"
    attempt_number: int = Field(default=1, ge=1)
    completed_dependency_ids: list[str] = Field(default_factory=list, max_length=200)
    failed_dependency_ids: list[str] = Field(default_factory=list, max_length=200)
    pending_approval_ids: list[str] = Field(default_factory=list, max_length=200)
    previous_errors: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    active_branch: str | None = Field(default=None, max_length=240)
    current_commit_sha: str | None = Field(default=None, max_length=80)
    remaining_mission_budget: dict[str, Any] = Field(default_factory=dict)


class RoleInstructionBlock(BaseModel):
    role_id: str
    role_version: str = "1.0.0"
    name: str
    purpose: str
    responsibilities: list[str]
    prohibited_actions: list[str]
    operating_principles: list[str]
    expected_behaviors: list[str]
    escalation_rules: list[str]


class CognitiveExecutionStage(BaseModel):
    id: str
    title: str
    purpose: str
    allowed_actions: list[str]
    expected_outputs: list[str]
    tool_preferences: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)


class CognitivePlanBlock(BaseModel):
    task_interpretation: str
    goals: list[str]
    non_goals: list[str]
    execution_stages: list[CognitiveExecutionStage]
    required_evidence: list[str]
    uncertainty_triggers: list[str]
    escalation_conditions: list[str]
    completion_criteria: list[str]


class PromptBlock(BaseModel):
    id: str
    type: PromptBlockType
    authority: int = Field(ge=1, le=9)
    title: str | None = None
    content: str
    trusted: bool
    source_type: str
    source_id: str | None = None
    estimated_tokens: int
    mandatory: bool
    priority: int = Field(default=50, ge=0, le=100)
    content_hash: str


class ToolDefinitionBlock(BaseModel):
    tool_id: str
    name: str
    description: str
    allowed_actions: list[str] = Field(default_factory=list)
    risk_level: str = "low"
    input_schema: dict[str, Any] = Field(default_factory=dict)


class OutputContract(BaseModel):
    contract_id: str = "arceus.output.default"
    output_mode: Literal["json", "text"] = "json"
    json_schema: dict[str, Any] = Field(default_factory=dict)
    required_fields: list[str] = Field(default_factory=list)
    repair_attempts: int = Field(default=1, ge=0, le=5)


class PromptInjectionAssessment(BaseModel):
    detected: bool
    severity: Literal["none", "low", "moderate", "high", "critical"]
    patterns: list[str] = Field(default_factory=list)
    affected_block_ids: list[str] = Field(default_factory=list)
    recommended_action: Literal["allow", "sanitize", "exclude", "require_review", "block"] = "allow"


class PromptIRMetadata(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    compiler_version: str
    model_profile: str
    planning_mode: str
    warnings: list[str] = Field(default_factory=list)
    suppressed_blocks: list[dict[str, Any]] = Field(default_factory=list)
    prompt_injection: PromptInjectionAssessment
    estimated_tokens: int
    cache_key: str
    generated_at: datetime


class PromptIR(BaseModel):
    id: str
    compiler_version: str
    mission_id: str
    task_id: str | None = None
    agent_id: str | None = None
    role: RoleInstructionBlock
    objective: PromptBlock
    plan: CognitivePlanBlock
    blocks: list[PromptBlock]
    tools: list[ToolDefinitionBlock]
    output_contract: OutputContract
    metadata: PromptIRMetadata


class ProviderPrompt(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    provider: str
    model_profile: str
    system: str
    user: str
    messages: list[dict[str, Any]]
    tools: list[dict[str, Any]]
    response_format: dict[str, Any] | None = None
    prompt_hash: str
    estimated_tokens: int


class PromptCompilationRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    mission_id: UUID | str
    task_id: UUID | str | None = None
    agent_id: UUID | str | None = None
    agent_role: str = Field(default="backend_engineer", max_length=120)
    objective: str = Field(min_length=1, max_length=20_000)
    task_type: str = Field(default="implementation", max_length=120)
    planning_mode: Literal["fast", "balanced", "deep", "verification_only", "recovery"] = "balanced"
    model_profile: str = Field(default="openai", max_length=120)
    provider: Literal["openai", "anthropic", "gemini", "groq", "local"] = "openai"
    context_package: ContextPackage | None = None
    runtime_state: RuntimePromptState = Field(default_factory=RuntimePromptState)
    budget: PromptBudget = Field(default_factory=PromptBudget)
    policies: list[str] = Field(default_factory=list, max_length=50)
    tool_definitions: list[ToolDefinitionBlock] = Field(default_factory=list, max_length=50)
    output_contract: OutputContract = Field(default_factory=OutputContract)
    allowed_paths: list[str] = Field(default_factory=list, max_length=100)
    force_rebuild: bool = False


class PromptCompilationResponse(BaseModel):
    ir: PromptIR
    provider_prompt: ProviderPrompt
    valid: bool
    validation_errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    cache_hit: bool = False


class PromptValidationRequest(BaseModel):
    ir: PromptIR


class PromptValidationResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class PromptTemplateResponse(BaseModel):
    template_id: str
    version: str
    type: str
    compatible_roles: list[str]
    required_capabilities: list[str]
