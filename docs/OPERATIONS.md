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

Run this before a production release to confirm external provider secrets are present:

```powershell
.\scripts\verify-provider-config.ps1 -Environment production -Strict
```

## Health And Readiness
- `/api/v1/health`: process is alive.
- `/api/v1/ready`: database and Redis dependency status.
- `/api/v1/production/readiness`: production configuration audit.

## Backups
- PostgreSQL: daily automated backup and monthly restore drill.
- Redis: treated as cache/job runtime; durable job records must persist in PostgreSQL.
- Object storage: versioning enabled for user uploads and job artifacts.

Before any production deploy that includes migrations, run:

```powershell
.\scripts\backup-postgres.ps1 -DatabaseUrl $env:DATABASE_URL -Tag pre-release
```

Every backup writes:

- a compressed custom-format dump
- a matching `.metadata.json` file with SHA256 and size
- an `arceus-latest.dump` pointer for emergency restore runbooks

Verify a backup file before a restore drill:

```powershell
.\scripts\restore-postgres.ps1 -BackupFile .\backups\arceus-latest.dump -VerifyOnly
```

Restore requires an explicit destructive confirmation:

```powershell
.\scripts\restore-postgres.ps1 -DatabaseUrl $env:DATABASE_URL -BackupFile .\backups\arceus-latest.dump -Confirm RESTORE_ARCEUS_DATABASE
```

No destructive migration may ship without a fresh backup, a restore note, and a rollback decision in the release notes.

## Monitoring
- Alert when API health fails.
- Alert when readiness is blocked.
- Alert on high error rate, dead-letter job growth, and deployment failure.
- Capture request ID and trace ID in every backend response and log entry.
