from __future__ import annotations

from fastapi import FastAPI

from .approvals.routes import router as approvals_router
from .artifacts.routes import router as artifacts_router
from .audit.routes import router as audit_router
from .automation.routes import router as automation_router
from .api.responses import handle_domain_error
from .application.errors import DomainError
from .capabilities.routes import router as capabilities_router
from .compiler.routes import router as compiler_router
from .collaboration.routes import router as collaboration_router
from .constitution.routes import router as constitution_router
from .decisions.routes import router as decisions_router
from .evidence.routes import router as evidence_router
from .events.routes import router as events_router
from .execution.routes import router as execution_router
from .execution_traces.routes import router as execution_traces_router
from .experience.routes import router as experience_router
from .gateway.routes import router as gateway_router
from .health.routes import router as health_router
from .knowledge.routes import router as knowledge_router
from .missions.routes import router as missions_router
from .organizations.routes import router as organizations_router
from .operations.routes import router as operations_router
from .planning.routes import router as planning_router
from .product.routes import router as product_router
from .runtime_kernel.routes import router as runtime_kernel_router
from .security.routes import router as security_router
from .tasks.routes import router as tasks_router
from .usage.routes import router as usage_router
from .verification.routes import router as verification_governance_router
from .workspaces.routes import router as workspaces_router


def install_arceus_runtime(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, handle_domain_error)
    app.include_router(missions_router)
    app.include_router(automation_router)
    app.include_router(experience_router)
    app.include_router(runtime_kernel_router)
    app.include_router(events_router)
    app.include_router(execution_router)
    app.include_router(approvals_router)
    app.include_router(artifacts_router)
    app.include_router(evidence_router)
    app.include_router(tasks_router)
    app.include_router(decisions_router)
    app.include_router(organizations_router)
    app.include_router(planning_router)
    app.include_router(capabilities_router)
    app.include_router(compiler_router)
    app.include_router(collaboration_router)
    app.include_router(execution_traces_router)
    app.include_router(gateway_router)
    app.include_router(audit_router)
    app.include_router(usage_router)
    app.include_router(health_router)
    app.include_router(verification_governance_router)
    app.include_router(security_router)
    app.include_router(workspaces_router)
    app.include_router(operations_router)
    app.include_router(constitution_router)
    app.include_router(knowledge_router)
    app.include_router(product_router)
