# Arceus Production Operations

## Environments
- `local`: developer machine, Electron, local Docker PostgreSQL/Redis.
- `staging`: automatic deploy from `main` after CI.
- `production`: manual approval after staging smoke tests.

## Required Managed Services
- PostgreSQL with pgvector.
- Redis for rate limits, jobs, and short-lived state.
- Object storage for uploaded files/artifacts.
- Clerk for production auth.
- Stripe for billing.
- GitHub App for repo/PR operations.
- LLM provider keys stored in environment secrets.

## Health And Readiness
- `/api/v1/health`: process is alive.
- `/api/v1/ready`: database and Redis dependency status.
- `/api/v1/production/readiness`: production configuration audit.

## Backups
- PostgreSQL: daily automated backup and monthly restore drill.
- Redis: treated as cache/job runtime; durable job records must persist in PostgreSQL.
- Object storage: versioning enabled for user uploads and job artifacts.

## Monitoring
- Alert when API health fails.
- Alert when readiness is blocked.
- Alert on high error rate, dead-letter job growth, and deployment failure.
- Capture request ID and trace ID in every backend response and log entry.
