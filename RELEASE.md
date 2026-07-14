# Arceus Release And Rollback Runbook

## Branching
- Work happens on feature branches.
- `main` is protected and requires PR review plus passing CI.
- Release tags use `arceus-code-vX.Y.Z`.

## Release Flow
1. Merge PR after CI passes.
2. GitHub Actions builds backend/frontend/desktop checks.
3. Staging deploy starts automatically from `main`.
4. Smoke tests verify:
   - backend `/api/v1/health`
   - backend `/api/v1/ready`
   - frontend `/hub`
   - workspace route
5. Production deploy requires manual approval.
6. Post-deploy smoke tests run again.

## Migration Policy
- Alembic migrations must pass against a fresh PostgreSQL database in CI.
- Destructive migrations require a backup and an explicit rollback note.
- Production migrations run once before service startup.

## Rollback Flow
1. Identify the last healthy image tag or commit SHA.
2. Pause risky background jobs if the release affects jobs, billing, GitHub, sandbox, or local filesystem operations.
3. Redeploy the previous image or commit.
4. Verify `/api/v1/health`, `/api/v1/ready`, and critical product routes.
5. Record the rollback reason and follow-up fix.

## Desktop Release
- Build installers from tagged releases.
- Attach installers to GitHub Releases.
- Sync `desktop/package.json` to the tag with `scripts/prepare-desktop-release.ps1`.
- Generate checksums and download-page env values with `scripts/generate-release-download-env.ps1`.
- Add signing and auto-update before broad public distribution.

Local dry run:

```powershell
.\scripts\prepare-desktop-release.ps1 -ReleaseVersion arceus-code-v1.2.3
cd .\desktop
npm ci
npm run dist
cd ..
.\scripts\generate-release-download-env.ps1 -ArtifactsDir .\desktop\dist -ReleaseVersion arceus-code-v1.2.3 -OwnerRepo arceus-ai/arceus-code -Signed
```

After GitHub Actions publishes desktop artifacts, copy the generated `release-download-env-*.ps1` values into the production environment so `/download` shows real installer URLs and SHA-256 checksums.
