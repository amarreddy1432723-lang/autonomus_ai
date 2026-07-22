from __future__ import annotations

from fastapi import FastAPI

from .approvals.routes import router as approvals_router
from .artifacts.routes import router as artifacts_router
from .audit.routes import router as audit_router
from .automation.routes import router as automation_router
from .billing.routes import router as billing_router
from .api.responses import handle_domain_error
from .application.errors import DomainError
from .capabilities.routes import router as capabilities_router
from .civilization.routes import router as civilization_router
from .compiler.routes import router as compiler_router
from .collaboration.routes import router as collaboration_router
from .compute.routes import router as compute_router
from .constitution.routes import router as constitution_router
from .context_engine.routes import router as context_engine_router
from .data_platform.routes import router as data_platform_router
from .decisions.routes import router as decisions_router
from .deployment.routes import router as deployment_router
from .enterprise_admin.routes import router as enterprise_admin_router
from .evidence.routes import router as evidence_router
from .events.routes import router as events_router
from .execution.routes import router as execution_router
from .execution_engine.routes import router as execution_engine_router
from .execution_traces.routes import router as execution_traces_router
from .experience.routes import router as experience_router
from .extensions.routes import router as extensions_router
from .federation.routes import router as federation_router
from .gateway.routes import router as gateway_router
from .graph.routes import router as graph_router
from .governance.routes import router as governance_router
from .health.routes import router as health_router
from .identity.routes import router as identity_router
from .knowledge.routes import router as knowledge_router
from .learning.routes import router as learning_router
from .memory_fabric.routes import router as memory_fabric_router
from .metakernel.routes import router as metakernel_router
from .model_gateway.routes import router as model_gateway_router
from .mission_runtime.routes import router as mission_runtime_router
from .missions.routes import router as missions_router
from .multi_agent.routes import router as multi_agent_router
from .organizations.routes import router as organizations_router
from .operations.routes import router as operations_router
from .platform.routes import router as platform_router
from .planning.routes import router as planning_router
from .planning_intelligence.routes import router as planning_intelligence_router
from .product.routes import router as product_router
from .prompt_compiler.routes import router as prompt_compiler_router
from .research.routes import router as research_router
from .repository.routes import router as repository_router
from .runtime_kernel.routes import router as runtime_kernel_router
from .security.routes import router as security_router
from .strategy.routes import router as strategy_router
from .tasks.routes import router as tasks_router
from .telemetry.routes import router as telemetry_router
from .tool_runtime.routes import router as tool_runtime_router
from .usage.routes import router as usage_router
from .verification_engine.routes import router as verification_engine_router
from .verification.routes import router as verification_governance_router
from .workspaces.routes import router as workspaces_router


def install_arceus_runtime(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, handle_domain_error)
    app.include_router(missions_router)
    app.include_router(automation_router)
    app.include_router(billing_router)
    app.include_router(experience_router)
    app.include_router(runtime_kernel_router)
    app.include_router(mission_runtime_router)
    app.include_router(multi_agent_router)
    app.include_router(events_router)
    app.include_router(execution_router)
    app.include_router(execution_engine_router)
    app.include_router(approvals_router)
    app.include_router(artifacts_router)
    app.include_router(evidence_router)
    app.include_router(tasks_router)
    app.include_router(telemetry_router)
    app.include_router(data_platform_router)
    app.include_router(decisions_router)
    app.include_router(deployment_router)
    app.include_router(enterprise_admin_router)
    app.include_router(organizations_router)
    app.include_router(planning_router)
    app.include_router(planning_intelligence_router)
    app.include_router(prompt_compiler_router)
    app.include_router(capabilities_router)
    app.include_router(compiler_router)
    app.include_router(context_engine_router)
    app.include_router(collaboration_router)
    app.include_router(execution_traces_router)
    app.include_router(extensions_router)
    app.include_router(gateway_router)
    app.include_router(tool_runtime_router)
    app.include_router(audit_router)
    app.include_router(usage_router)
    app.include_router(health_router)
    app.include_router(identity_router)
    app.include_router(verification_governance_router)
    app.include_router(verification_engine_router)
    app.include_router(security_router)
    app.include_router(workspaces_router)
    app.include_router(operations_router)
    app.include_router(platform_router)
    app.include_router(constitution_router)
    app.include_router(knowledge_router)
    app.include_router(repository_router)
    app.include_router(learning_router)
    app.include_router(product_router)
    app.include_router(strategy_router)
    app.include_router(metakernel_router)
    app.include_router(model_gateway_router)
    app.include_router(compute_router)
    app.include_router(graph_router)
    app.include_router(governance_router)
    app.include_router(memory_fabric_router)
    app.include_router(research_router)
    app.include_router(federation_router)
    app.include_router(civilization_router)
