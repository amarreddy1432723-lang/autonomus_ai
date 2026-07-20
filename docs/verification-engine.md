# Arceus Verification Engine

Book II Part 43 adds an autonomous verification and quality-gate facade.

## API Surface

- `GET /api/v1/verification-engine/checks`
- `POST /api/v1/verification-engine/plan`
- `POST /api/v1/verification-engine/contracts/validate`
- `POST /api/v1/verification-engine/tests/discover`
- `POST /api/v1/verification-engine/run`
- `POST /api/v1/verification-engine/review`
- `POST /api/v1/verification-engine/release-readiness`
- `GET /api/v1/verification-engine/worker-jobs`
- `POST /api/v1/verification-engine/evidence-producers/run`
- `POST /api/v1/verification-engine/worker-jobs/{job_id}/complete`
- `POST /api/v1/verification-engine/mission-control/release-gate`

## What It Provides

- Deterministic quality gate evaluation for build, test, security, review, performance, accessibility, architecture, and release checks.
- A curated verification check registry with deterministic/review-based metadata, required tools, subject support, and produced evidence types.
- Risk-aware verification plans for source changes, migrations, deployment changes, release candidates, security-sensitive work, and UI changes.
- Output contract validation so AI/task artifacts can be checked for required fields, unsupported fields, and primitive type mismatches before downstream execution.
- Test discovery from package scripts, repository file conventions, and framework hints.
- Evidence scoring based on validation status and trust level.
- Autonomous semantic review findings for security-sensitive changes, migrations, UI accessibility gaps, and missing tests.
- Release blocker calculation from required gates, review verdicts, high/critical findings, and human approval requirements.
- Repair-loop recommendations when verification fails.
- Durable verification worker jobs created from planned checks when the mission exists in the runtime database.
- Evidence producer intake for lint, build, test, security, Playwright, GitHub checks, contract validation, and independent review outputs.
- Persisted verification runs, queryable verification findings, evidence producer runs, and release-readiness gates.
- Mission Control PR/deploy blocking through an explicit `allowed` release gate decision.

## Relationship To Existing Verification Governance

The existing `verification` module persists verification plans, evidence, quality gates, trust scores, and completion certificates. This module now adds production persistence for verification-engine outcomes:

- `arceus_verification_runs.result` stores the full verification receipt.
- `arceus_verification_findings` stores queryable blockers and warnings.
- `arceus_verification_worker_jobs` stores durable planned checks for workers.
- `arceus_evidence_producer_runs` stores lint/build/test/security/Playwright/GitHub producer executions.
- `arceus_release_readiness_gates` stores the latest PR/deploy/release gate decision.

## Worker And Mission Control Flow

1. Mission Control calls `POST /api/v1/verification-engine/plan`.
2. The engine persists one queued `arceus_verification_worker_jobs` row per planned check.
3. Durable workers claim/run the lint, build, test, security, Playwright, and GitHub check jobs.
4. Workers report outputs through `POST /api/v1/verification-engine/worker-jobs/{job_id}/complete`.
5. The producer output becomes immutable evidence and updates the worker job.
6. Mission Control calls `POST /api/v1/verification-engine/run` to evaluate gates with attached evidence.
7. Mission Control calls `POST /api/v1/verification-engine/release-readiness` after review and human approval.
8. PR/deploy buttons must call `POST /api/v1/verification-engine/mission-control/release-gate` and remain blocked unless `allowed=true`.

## Remaining Production Steps

- Add actual worker handlers that claim queued `arceus_verification_worker_jobs` rows and execute the mapped command/scanner/browser/GitHub checks.
- Hydrate `VerificationRunRequest.evidence` automatically from mission evidence instead of requiring the UI to pass evidence inline.
- Show persisted findings and readiness blockers directly in Mission Control.
