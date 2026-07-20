# Arceus Planning Intelligence and Autonomous Decision Engine

Part 40 adds the executive planning layer that turns a goal into scored strategy options before mission execution.

## API Surface

- `POST /api/v1/planning-intelligence/plan`
- `POST /api/v1/planning-intelligence/simulate`
- `POST /api/v1/planning-intelligence/next-action`
- `POST /api/v1/planning-intelligence/replan`
- `POST /api/v1/planning-intelligence/validate`

## Current Capabilities

- Goal interpretation from objective, constraints, repository intelligence, and success criteria.
- Goal tree generation with explicit uncertainty.
- Alternative generation using the existing organization/workflow planner.
- Strategy scoring across risk, cost, speed, confidence, autonomy level, and constraint fit.
- Approval-aware next action selection.
- Budget/deadline simulation.
- Dynamic replanning triggers for failed tasks, policy blocks, budget changes, and user feedback.
- Plan validation for measurable acceptance criteria and verification methods.

## Decision Model

Each strategy receives:

- risk score
- cost score
- speed score
- confidence
- decision score
- required approvals
- constraint violations
- simulation output

Mandatory constraint violations block execution and produce a `revise_constraints_or_scope` next action. Otherwise, approval gates are requested before execution when autonomy/risk requires them.

## Production Next Steps

- Persist planning decisions as durable artifacts and decisions.
- Connect planning to mission compiler outputs and memory search automatically.
- Add richer plan templates from successful past missions.
- Add real cost/model/tool estimates from the gateway ledger.
- Add frontend Mission Control surfaces for comparing alternatives and approving plans.
