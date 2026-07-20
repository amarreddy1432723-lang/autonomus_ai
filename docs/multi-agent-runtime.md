# Multi-Agent Runtime

Part 36 implements the first concrete Multi-Agent Runtime slice. It uses the existing Arceus kernel tables rather than creating a parallel agent database:

- durable agents are `ArceusParticipant` rows
- capabilities are stored on participants
- messages use the collaboration bus
- metrics use performance observations
- assignments update task ownership and emit runtime events

## APIs

- `POST /api/v1/agents/register`
- `GET /api/v1/agents`
- `GET /api/v1/agents/{agent_id}`
- `POST /api/v1/agents/{agent_id}/pause`
- `POST /api/v1/agents/{agent_id}/resume`
- `POST /api/v1/agents/{agent_id}/disable`
- `POST /api/v1/agents/{agent_id}/heartbeat`
- `GET /api/v1/agents/{agent_id}/metrics`
- `POST /api/v1/agents/assign-task`
- `POST /api/v1/agents/messages`

## Assignment Scoring

The scheduler-facing assignment score combines:

- capability match
- availability
- historical performance
- cost score
- current workload

Agents are identities independent of model providers. Model profile and version are stored as agent authorities so a backend engineer can move from one provider to another without becoming a different agent.
