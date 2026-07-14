# Arceus 100% Ready Acceptance Checklist

This checklist is the release gate for Arceus Code, PA, Interview, and the production engineering platform. Items are split into automated checks, manual product checks, and external-provider checks.

## Core Developer Loop

| Criterion | Verification | Status |
| --- | --- | --- |
| Open local folder -> file tree appears within 1 second | Electron manual smoke test with real project | Manual |
| Edit file externally -> tree updates within 1 second | Electron watcher smoke test | Manual |
| Open terminal -> `npm run dev` -> output within 200ms | Electron terminal smoke test | Manual |
| Ask agent to refactor -> work receipt + diff viewer | Workspace agent smoke test | Manual |
| Accept some hunks, reject others -> only accepted hunks applied | Patch review integration test/manual | Manual |
| Rollback -> all changes undone including new files | Patch rollback integration test/manual | Manual |
| Run checks -> build/lint/test results in activity panel | Workspace checks test/manual | Manual |
| Create PR from Arceus -> appears on GitHub within 10 seconds | Requires GitHub App test repo | External |

## Infrastructure

| Criterion | Verification | Status |
| --- | --- | --- |
| Restart backend mid-job -> Celery worker continues | Celery integration test | Manual/External |
| Sandbox cannot reach internet without explicit allow | Docker sandbox test | Manual |
| Sandbox runs non-root and cannot exceed 512MB | Docker sandbox test | Manual |
| Free user exceeds quota -> 402 + upgrade modal | Billing route test + workspace UI test | Manual |
| Admin can see active jobs and kill any job | Admin dashboard/manual API test | Manual |

## Intelligence

| Criterion | Verification | Status |
| --- | --- | --- |
| TypeScript type error -> red squiggle within 2 seconds | LSP/Monaco manual test | Manual |
| Hover function -> JSDoc popup | LSP/Monaco manual test | Manual |
| Build passes -> Playwright screenshot -> no blank page | Preview verification test | Manual |
| JS console error -> badge shown in preview panel | Preview verification test | Manual |

## Product

| Criterion | Verification | Status |
| --- | --- | --- |
| First-time user completes 5-step guided tour in under 5 minutes | UX walkthrough | Needed |
| Team member invited -> joins project -> edits files | Collaboration manual test | Manual |
| SSO login with Google Workspace completes without password | Requires configured OIDC provider | External |
| New desktop app version -> auto-update prompt appears | GitHub Release + packaged app test | External |
| `brew install --cask nexus-code` works | Homebrew Cask submission | External |
| Grafana shows live job queue depth and error rate | Prometheus/Grafana deployment | External |

## Automated Release Commands

Run from the repository root:

```powershell
./scripts/acceptance-check.ps1
```

Optional environment variables:

```powershell
$env:SMOKE_BACKEND_URL="http://localhost:8003"
$env:SMOKE_FRONTEND_URL="http://localhost:3000"
$env:RUN_NPM_AUDIT="true"
./scripts/acceptance-check.ps1
```

## External Setup Required Before Claiming 100%

- GitHub App installed on a test organization/repository.
- Stripe test mode configured with webhook secret.
- Google Workspace OIDC configured for an organization.
- Sentry DSNs configured for backend and frontend.
- Prometheus/Grafana deployed and scraping `/metrics`.
- Windows EV certificate or code-signing certificate configured in GitHub Actions.
- Apple Developer ID certificate and notarization credentials configured.
- Homebrew Cask and winget manifests submitted and accepted.
