# Context Engine

Book II Part 34 adds the first working Context Engine slice.

## Implemented

- Intent analysis for task type, requested files, symbols, languages, frameworks, risk, and expected output.
- Repository-aware retrieval from the Repository Intelligence Engine cache.
- Conversation, memory, Git history, execution-state, test, documentation, and architecture candidates.
- Deterministic ranking with source/task-type weighting.
- Token budgeting with output reserve.
- Secret redaction before prompt assembly.
- Citation metadata for every selected item.
- In-memory context package cache.
- Context expansion against the repository graph.

## API

- `POST /api/v1/context/build`
- `POST /api/v1/context/expand`
- `POST /api/v1/context/rank`
- `GET /api/v1/context/cache`
- `DELETE /api/v1/context/cache`

## Current Limits

- Context packages are cached in process memory, not yet persisted into `arceus_context_packages`.
- Repository retrieval depends on the process-local Repository Intelligence index.
- Semantic embeddings, Git-log adapters, issue trackers, and parallel workers are not connected yet.
- Compression is extractive/snippet-based rather than model-generated recursive summaries.

## Next

Part 35 should call this service from mission execution before model routing, then persist package IDs to execution traces.
