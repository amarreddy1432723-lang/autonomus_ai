# Repository Intelligence Engine

Part 33 adds the first practical Repository Intelligence Engine slice for Arceus.

## Implemented

- Local repository discovery from a bounded `root_path`.
- Language mix detection from extensions and shebangs.
- Package manager, build system, framework, documentation, configuration, and test discovery.
- Lightweight symbol extraction for Python, TypeScript, JavaScript, Go, Java, C#, and Rust.
- Import/dependency relationship extraction.
- Test-to-production-file mapping by naming convention.
- Architecture inference with confidence, signals, risks, and recommendations.
- In-memory index cache for fast symbol/search/dependency retrieval during the current service process.

## API

- `POST /api/v1/repository/index`
- `GET /api/v1/repository/profile?repository_id=...`
- `GET /api/v1/repository/symbols?repository_id=...`
- `GET /api/v1/repository/dependencies?repository_id=...`
- `GET /api/v1/repository/tests?repository_id=...`
- `GET /api/v1/repository/architecture?repository_id=...`
- `GET /api/v1/repository/search?repository_id=...&q=...`

## Current Limits

- The index is process-local and should be moved into durable graph/index tables.
- Parsing is regex/AST-lite rather than tree-sitter/LSP-backed normalized ASTs.
- Call graph and type hierarchy extraction are not complete yet.
- Embeddings and semantic chunk summaries are intentionally deferred to the Context Engine.
- Incremental file watcher integration still needs to push changed file batches into the indexer.

## Next

Part 34 should use this graph as the structured retrieval source for mission-aware context assembly.
