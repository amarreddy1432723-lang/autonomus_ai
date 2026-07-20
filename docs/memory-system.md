# Arceus Memory System and Knowledge Graph

Part 39 extends the existing enterprise memory fabric into a practical persistent intelligence layer. It uses the existing tenant-scoped `ArceusMemoryItem` table as the durable source of truth and projects graph facts from verified memories.

## API Surface

- `POST /api/v1/memory/store`
- `POST /api/v1/memory/search`
- `GET /api/v1/memory/{id}`
- `DELETE /api/v1/memory/{id}`
- `POST /api/v1/memory/summarize`
- `POST /api/v1/memory/consolidate`
- `POST /api/v1/memory/extract`
- `GET /api/v1/memory/conflicts`
- `POST /api/v1/memory/{id}/feedback`
- `GET /api/v1/memory/{id}/graph`
- `GET /api/v1/memory/retention/policies`

## Current Implementation

- Memory classification for semantic, procedural, episodic, strategic, compliance, personal, project, mission, working, and organizational memories.
- Confidence scoring from source reliability, evidence, and human feedback.
- Fact extraction for simple subject-relation-object statements.
- Graph projection from memories into nodes and edges.
- Conflict detection for competing facts about the same subject/relation.
- Consolidation through the existing summarize path.
- Retention policy metadata for each memory class.
- Feedback loops that promote correct memories and dispute incorrect/outdated ones.

## Retrieval Priority

Search currently ranks by:

- authorized sensitivity
- memory type and scope filters
- lexical relevance
- mission context overlap
- confidence
- importance
- lifecycle status

This keeps retrieval explainable and safe while leaving room for future vector/embedding search.

## Production Next Steps

- Add a real vector index for long-form semantic recall.
- Persist graph nodes and graph edges in dedicated tables.
- Connect mission completion events to automatic memory extraction.
- Add reviewer-driven memory approval workflows.
- Add background consolidation and retention jobs.
- Add telemetry for lookup latency, recall quality, feedback, and reuse success.
