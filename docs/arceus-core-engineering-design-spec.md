# Arceus Core Engineering Design Specification

Status: Draft for review  
Scope: Arceus Kernel and Engineering OS MVP  
Decision: stop adding new conceptual generations until this kernel is implemented and proven.

## 1. Product Direction

Arceus Core is the intelligence kernel that every future Arceus product depends on. It is not an IDE shell, not a chat page, and not a loose collection of agents. It is a durable mission compiler and runtime for human-AI engineering work.

Primary loop:

```text
User objective
  -> Intent understanding
  -> Mission compiler
  -> Capability detection
  -> Organization builder
  -> Execution graph
  -> Context compiler
  -> Runtime scheduler
  -> Tools and models
  -> Evidence
  -> Review and approval
  -> Persistent state
  -> Learning
```

The first implementation target is still the Desktop Code MVP:

```text
Download Arceus Code
  -> sign in
  -> open folder
  -> create mission
  -> compile mission
  -> form organization
  -> execute safe scoped work
  -> show receipt and evidence
  -> review or undo
  -> run checks
  -> create PR
```

## 2. Kernel Principles

- Missions compile before execution.
- Agents may reason, but tools act only through policy gates.
- Every action emits an event.
- Every artifact has evidence and a responsibility chain.
- Humans and AI specialists share one participant model.
- Context is compiled, not dumped.
- State survives restart.
- Reviews and approvals are scoped and auditable.
- Knowledge has provenance, trust, scope, and freshness.
- Plugins extend the kernel through contracts, not direct coupling.

## 3. Core Modules

### Intent Understanding

Responsibility:

- Parse raw user requests into objective, scope, constraints, unknowns, risks, deliverables, and likely domain.
- Classify whether the request is planning-only, code-changing, destructive, deployment-related, financial, or production-sensitive.

Inputs:

- user text
- active project
- selected files
- recent mission history
- project memory

Outputs:

- `IntentFrame`

```json
{
  "objective": "string",
  "scope": [],
  "constraints": [],
  "unknowns": [],
  "deliverables": [],
  "risk_level": "low|medium|high|critical",
  "execution_allowed": false
}
```

### Mission Compiler

Responsibility:

- Convert intent into Arceus Mission Language.
- Build an execution graph.
- Detect required capabilities.
- Define acceptance criteria and evidence requirements.
- Decide what requires human approval before execution.

Output:

- `CompiledMission`

```json
{
  "mission_id": "uuid",
  "aml_version": "1.0",
  "objective": {},
  "requirements": [],
  "constraints": [],
  "risks": [],
  "required_capabilities": [],
  "execution_graph": {},
  "approval_gates": [],
  "evidence_contract": []
}
```

### Arceus Mission Language

AML is the internal contract between user intent and runtime execution.

Minimal YAML form:

```yaml
mission:
  name: "Improve authentication reliability"
  type: "software_engineering"
objective:
  summary: "Make login session recovery reliable"
constraints:
  - "No production secret access"
  - "Only modify approved auth paths"
quality:
  security: "high"
  reliability: "high"
  ux: "medium"
organization:
  mode: "dynamic"
approval:
  required: true
deliverables:
  - code
  - tests
  - work_receipt
  - rollback_snapshot
  - evidence
```

### Capability Engine

Responsibility:

- Maintain curated capability catalog.
- Map mission requirements to capabilities.
- Select specialist profiles or department services.
- Surface capability gaps before execution.

Current source:

- `backend/services/agent/os_kernel/generation2.py`

Required next step:

- Move catalog definitions into `os_kernel/capability_catalog.py` once stable.

### Organization Builder

Responsibility:

- Assemble a mission organization from required capabilities.
- Include humans, AI specialists, shared departments, and external reviewers when policy permits.
- Ensure implementers cannot be their only reviewers.

Inputs:

- compiled mission
- participant registry
- capability catalog
- department services
- policies
- availability

Outputs:

- `OrganizationPlan`
- candidate structures
- selected structure
- known gaps
- rationale

### Execution Graph

Responsibility:

- Represent work as a dependency graph, not a flat checklist.
- Connect requirements, decisions, tasks, artifacts, checks, approvals, and deployments.

Node types:

- requirement
- unknown
- decision
- task
- artifact
- review
- approval
- tool_run
- verification
- deployment
- lesson

Edge types:

- depends_on
- produces
- reviews
- approves
- verifies
- supersedes
- learns_from

### Context Compiler

Responsibility:

- Select the minimum useful context for each participant and task.
- Avoid leaking private or irrelevant data.
- Include current decisions, applicable lessons, scoped files, relevant artifacts, and policy limits.

Context levels:

- task
- mission
- project
- organization
- global

Output:

```json
{
  "participant_id": "uuid",
  "task_id": "uuid",
  "allowed_context": [],
  "excluded_context": [],
  "policy_notes": [],
  "token_budget": 12000
}
```

### Runtime Scheduler

Responsibility:

- Run mission graph nodes durably.
- Support pause, resume, cancel, retry, checkpoint, and restart recovery.
- Prevent duplicate tool actions after retry.

Required properties:

- idempotency key per tool action
- event-sourced state transitions
- task locks
- lease expiry
- dead-letter handling

### Policy And Approval Engine

Responsibility:

- Evaluate RBAC and ABAC.
- Enforce environment authority, repository scope, data sensitivity, risk, human approval, and separation of duties.

Current source:

- `backend/services/agent/os_kernel/policies.py`
- `backend/services/agent/os_kernel/generation3.py`

Required next step:

- Split Generation 3 permission contracts into `permissions/` once routes and persistence are introduced.

### Tool Runtime

Responsibility:

- Execute file, terminal, git, browser, model, deployment, and secret operations through policy-gated adapters.
- Store tool call evidence.
- Redact secrets from events and logs.

Tool run contract:

```json
{
  "tool_run_id": "uuid",
  "task_id": "uuid",
  "participant_id": "uuid",
  "tool": "scoped_file_writer",
  "input_hash": "sha256",
  "output_hash": "sha256",
  "status": "completed|failed|blocked",
  "evidence_ids": []
}
```

### Event Engine

Responsibility:

- Append immutable events for all material actions.
- Rebuild mission, task, approval, artifact, and responsibility-chain state from events.

Event classes:

- mission_created
- mission_compiled
- organization_planned
- task_created
- task_assigned
- handoff_requested
- handoff_acknowledged
- decision_proposed
- review_submitted
- approval_vote_cast
- tool_run_requested
- tool_run_completed
- artifact_created
- verification_completed
- deployment_requested
- deployment_blocked
- lesson_promoted

### Knowledge Engine

Responsibility:

- Store structured knowledge with source, evidence, trust, scope, sensitivity, freshness, and applicability.
- Prevent unverified lessons from becoming established rules.

Knowledge item:

```json
{
  "knowledge_id": "uuid",
  "scope": "task|mission|project|department|organization|tenant|global",
  "trust_level": "unverified|peer_reviewed|tool_verified|human_approved|environment_observed",
  "sensitivity": "public|internal|confidential|restricted",
  "source": {},
  "content": {},
  "evidence_ids": [],
  "applicability": {},
  "supersedes_id": null
}
```

### Learning Engine

Responsibility:

- Record mission outcomes, specialist performance, model performance, tool reliability, user corrections, and reusable lessons.
- Feed future capability selection and context compilation.

## 4. Database Design

Use additive migrations only.

Core tables:

- `missions`
- `compiled_missions`
- `execution_graph_nodes`
- `execution_graph_edges`
- `participants`
- `role_bindings`
- `authority_bindings`
- `organization_plans`
- `mission_tasks`
- `task_handoffs`
- `decisions`
- `artifacts`
- `evidence`
- `approval_policies`
- `approval_votes`
- `kernel_events`
- `knowledge_items`
- `tool_runs`
- `model_runs`
- `responsibility_chains`
- `runtime_checkpoints`

Every tenant-owned table includes:

- `tenant_id`
- `created_at`
- `updated_at`

Sensitive tables include:

- immutable audit events
- actor participant ID
- policy decision reference

## 5. API Design

Kernel APIs:

```text
POST /api/v1/kernel/missions/compile
GET  /api/v1/kernel/missions/{mission_id}
POST /api/v1/kernel/missions/{mission_id}/approve-plan
POST /api/v1/kernel/missions/{mission_id}/run
POST /api/v1/kernel/missions/{mission_id}/pause
POST /api/v1/kernel/missions/{mission_id}/resume
GET  /api/v1/kernel/missions/{mission_id}/events
GET  /api/v1/kernel/missions/{mission_id}/graph
GET  /api/v1/kernel/missions/{mission_id}/receipt
```

Context and knowledge:

```text
POST /api/v1/kernel/context/compile
GET  /api/v1/kernel/knowledge
POST /api/v1/kernel/knowledge
POST /api/v1/kernel/knowledge/{knowledge_id}/promote
POST /api/v1/kernel/knowledge/{knowledge_id}/supersede
```

Participants and policy:

```text
GET  /api/v1/kernel/participants
POST /api/v1/kernel/participants
POST /api/v1/kernel/policies/evaluate
POST /api/v1/kernel/approvals/{approval_id}/votes
```

All mutating endpoints require:

- authenticated user
- tenant scope
- idempotency key when retryable
- policy decision
- event emission

## 6. State Machines

Mission states:

```text
DRAFT
  -> COMPILED
  -> PLAN_REVIEW
  -> READY
  -> RUNNING
  -> PAUSED
  -> REVIEWING
  -> VERIFYING
  -> AWAITING_APPROVAL
  -> COMPLETED
```

Failure branches:

```text
RUNNING -> BLOCKED
RUNNING -> FAILED
PAUSED -> RUNNING
FAILED -> READY
ANY_ACTIVE -> CANCELLED
```

Task states:

```text
BACKLOG -> READY -> ASSIGNED -> IN_PROGRESS -> SUBMITTED -> UNDER_REVIEW -> APPROVED -> VERIFYING -> COMPLETED
```

Approval states:

```text
PENDING -> PARTIALLY_APPROVED -> APPROVED
PENDING -> REJECTED
APPROVED -> INVALIDATED
```

Knowledge states:

```text
proposed -> active -> superseded
proposed -> rejected
active -> archived
```

## 7. UI Design Targets

Desktop Code MVP should expose kernel state through:

- Mission composer with AML preview.
- Compiled mission panel.
- Capability requirements panel.
- Organization plan panel.
- Execution graph view.
- Work receipt.
- Responsibility chain drawer.
- Evidence drawer.
- Approval queue.
- Undo and rollback surface.

Do not expose raw kernel complexity to first-time users. The UI should explain:

- what Arceus understood
- what it will do
- who or what will do it
- what evidence proves it
- what needs approval
- how to undo

## 8. Implementation Milestones

### Milestone 0: Freeze Vision

Deliverables:

- This EDS reviewed.
- Generation 2 and Generation 3 current slices committed cleanly.
- No Generation 4 work until kernel MVP passes.

Acceptance:

- Team can explain Arceus Core in one diagram.
- Current untracked architecture files are organized into clean commits.

### Milestone 1: Mission Compiler MVP

Deliverables:

- `IntentFrame`
- `CompiledMission`
- AML parser/serializer
- execution graph model
- compiler tests

Acceptance:

- "Improve auth reliability" compiles into AML, capabilities, graph, approval gates, and evidence contract.

### Milestone 2: Runtime Checkpoint MVP

Deliverables:

- event-backed mission checkpoint
- idempotent graph node execution
- pause/resume
- restart replay test

Acceptance:

- mission resumes after process restart without duplicate tool action.

### Milestone 3: Context Compiler MVP

Deliverables:

- context selection rules
- project memory retrieval
- redaction and sensitivity filter
- context budget enforcement

Acceptance:

- AI auth specialist receives auth-scoped context only.

### Milestone 4: Tool Runtime MVP

Deliverables:

- scoped file tool adapter
- terminal adapter policy gate
- evidence capture
- redaction
- idempotency

Acceptance:

- safe file change creates artifact, evidence, receipt, rollback snapshot.

### Milestone 5: Human-AI Governance MVP

Deliverables:

- participant persistence
- role bindings
- permission evaluation route
- approval quorum route
- responsibility chain read model

Acceptance:

- AI approval cannot satisfy human-required gate.
- production deploy blocked without production authority and security review.

### Milestone 6: Desktop Proof Loop

Deliverables:

- open folder
- compile mission
- form organization
- execute safe scoped change
- show receipt
- run checks
- rollback
- PR flow

Acceptance:

- Arceus changes its own codebase in a branch with evidence and rollback.

## 9. Testing Plan

Unit:

- intent parsing
- AML serialization
- mission graph validation
- capability detection
- context filtering
- policy decisions
- quorum decisions
- event replay
- idempotency

Integration:

- compile mission
- build organization
- assign human and AI tasks
- execute handoff
- run tool with policy
- attach evidence
- review and approve
- restart and resume

Security:

- cross-tenant context blocked
- AI cannot approve as human
- dev role cannot deploy production
- secrets never appear in logs/events
- author self-approval blocked
- stale approval invalidated

End-to-end:

- create auth improvement mission
- compile
- approve plan
- implement safe scoped change
- review
- verify
- rollback or PR

## 10. Rollback Strategy

Code rollback:

- keep kernel APIs behind versioned routes
- keep additive tables only
- do not remove current workspace APIs

Runtime rollback:

- pause active kernel missions
- preserve event log
- rebuild read models from events

Product rollback:

- hide kernel panels behind feature flag
- keep existing workspace flow accessible

## 11. Immediate Next Actions

1. Review this EDS.
2. Commit current Generation 2, Generation 3, and EDS files in clean module commits.
3. Implement Milestone 1: Mission Compiler MVP.
4. Add tests before route wiring.
5. Only then expose compiler output in the desktop workspace.

