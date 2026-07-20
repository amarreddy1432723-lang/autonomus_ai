# Mission Runtime Implementation

Part 35 adds a runtime facade that turns the existing mission, planning, task, checkpoint, evidence, approval, and context services into one UI-ready execution surface.

## Runtime APIs

- `POST /api/v1/mission-runtime/plans/validate`
  Validates task DAGs, detects cycles, reports ready nodes, topological order, and critical path.
- `GET /api/v1/mission-runtime/{mission_id}/snapshot`
  Returns current mission status, progress, task buckets, critical path, latest events, evidence, artifacts, approvals, and budget usage.
- `GET /api/v1/mission-runtime/{mission_id}/report`
  Produces an executive mission report with completed work, blockers, remaining risks, warnings, and next actions.
- `POST /api/v1/mission-runtime/{mission_id}/run-next`
  Runs the next ready task through the existing deterministic scheduler/executor.
- `POST /api/v1/mission-runtime/tasks/{task_id}/context`
  Builds a model-specific context package for one task using the Context Engine.

## Design Boundaries

The module does not replace the existing durable runtime. It connects:

- mission state from `missions`
- planned task DAGs from `planning`
- worker leases and checkpoints from `execution`
- context packages from `context_engine`
- artifacts, evidence, approvals, and events from the shared runtime tables

This keeps the runtime inspectable from Mission Control without duplicating task execution logic.
