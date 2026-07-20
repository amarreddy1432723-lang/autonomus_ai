# Arceus Execution Engine

Book II Part 42 adds a mission DAG execution facade over the existing durable mission runtime tables.

## API Surface

- `POST /api/v1/execution-engine/workflows/compile`
- `POST /api/v1/execution-engine/workflows/validate`
- `POST /api/v1/execution-engine/schedule`
- `POST /api/v1/execution-engine/transitions/validate`
- `POST /api/v1/execution-engine/leases/plan`
- `POST /api/v1/execution-engine/effects/reserve`

## What It Provides

- Explicit mission state-machine validation.
- Executable workflow and node schemas for agent tasks, tools, models, approvals, verification, checkpoints, conditions, fan-in/fan-out, compensation, and finalization.
- DAG validation for duplicate nodes, missing references, cycles, unreachable nodes, terminal reachability, compensation references, and unsafe side effects without approval predecessors.
- Dependency-aware ready-node scheduling with priority scoring, budget pressure, capacity limits, resource-lock awareness, queue selection, and idempotency keys.
- Lease planning with stable idempotency keys, fencing tokens, expiry, and worker safety rules.
- Execution-effect reservation to prevent duplicate side effects.
- Weighted mission progress for Mission Control.

## Relationship To Existing Runtime

The repository already contains durable SQLAlchemy models for missions, workflow definitions, nodes, edges, tasks, worker leases, checkpoints, events, outbox/inbox, and idempotency records. This module does not create a duplicate database runtime. It defines the deterministic execution contract that can be used by the existing `mission_runtime`, `runtime_kernel`, workers, and future queue-backed dispatchers.

## Next Production Steps

- Persist compiled `ExecutableWorkflowResponse` into `arceus_workflow_definitions`, `arceus_workflow_nodes`, and `arceus_workflow_edges`.
- Connect scheduler output to the outbox publisher and worker queues.
- Add database-backed active resource locks and partial unique indexes for active leases.
- Add crash-recovery workers that expire stale leases and redispatch ready nodes.
- Connect verification gates from Part 43 before final mission completion.
