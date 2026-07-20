# Arceus Tool Runtime

The Tool Runtime is the governed action layer between AI agents and external systems. Agents may request actions, but this runtime decides whether the action is allowed, needs review, or is denied before anything touches the filesystem, terminal, GitHub, cloud infrastructure, or other external services.

## Interfaces

- `GET /api/v1/tool-runtime/catalog`
- `POST /api/v1/tool-runtime/authorize`
- `POST /api/v1/tool-runtime/execute`
- `GET /api/v1/tool-runtime/executions`
- `GET /api/v1/tool-runtime/executions/{execution_id}`
- `POST /api/v1/tool-runtime/receipts/verify`

## Current Safety Model

- Read-only tools can run when the caller has required authorities.
- Dry-runs return a receipt without mutating external state.
- Local mutations, repository mutations, external writes, production changes, financial actions, and secret access require review.
- Disabled or unknown tools are denied.
- Secret-like payloads are redacted in policy records, receipts, and output.
- Idempotency keys prevent duplicate tool action after retry.

## Receipt Contract

Each tool request produces a receipt with:

- execution id
- status
- authorization decision
- redacted input and output
- input and output hashes
- audit evidence
- rollback availability
- replay marker when returned from an idempotent retry

## Production Next Steps

- Connect the existing concrete gateway adapters behind the secure facade.
- Add approval records for `require_review` decisions.
- Enforce sandbox selection before mutating tools run.
- Add cancellation/timeout monitors for long-running external actions.
- Attach immutable artifacts for command logs, screenshots, PR URLs, and deployment proofs.
