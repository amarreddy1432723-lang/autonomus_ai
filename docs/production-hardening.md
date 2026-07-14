# Arceus Production Hardening Runbook

This checklist turns local Arceus into a production deployment. The app now exposes the same gates in `/admin` through release readiness and billing health.

## Required Production Auth

Set production auth to Clerk-only:

```powershell
APP_ENV=production
ALLOW_DEMO_USER=false
ALLOW_DEV_AUTH_FALLBACK=false
CLERK_ISSUER=https://your-clerk-issuer
CLERK_JWKS_URL=https://your-clerk-issuer/.well-known/jwks.json
CLERK_AUDIENCE=your-audience
JWT_SECRET=<strong random secret>
APP_ENCRYPTION_KEY=<strong random secret>
NEXT_PUBLIC_APP_ENV=production
NEXT_PUBLIC_REQUIRE_AUTH=true
NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY=pk_live_...
```

With `APP_ENV=production`, the backend refuses startup if critical auth/secrets are unsafe. In production Clerk mode, backend APIs reject both `x-user-id` development fallback and legacy local JWT tokens; only verified Clerk session tokens are accepted.

## Stripe Billing

Install/configure:

```powershell
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_STARTER_MONTHLY=price_...
STRIPE_PRICE_STARTER_ANNUAL=price_...
STRIPE_PRICE_PRO_MONTHLY=price_...
STRIPE_PRICE_PRO_ANNUAL=price_...
STRIPE_PRICE_ENTERPRISE_MONTHLY=price_...
STRIPE_PRICE_ENTERPRISE_ANNUAL=price_...
```

Webhook events to enable:

- `checkout.session.completed`
- `customer.subscription.created`
- `customer.subscription.updated`
- `customer.subscription.deleted`
- `invoice.payment_failed`

## Rate Limits

Keep `RATE_LIMIT_ENABLED=true`. Tune route classes with:

```powershell
RATE_LIMIT_AUTH_BURST=30
RATE_LIMIT_MODEL_BURST=20
RATE_LIMIT_CODE_RUNTIME_BURST=20
RATE_LIMIT_ADMIN_BURST=120
RATE_LIMIT_DEFAULT_BURST=120
```

Redis is required for production rate-limit enforcement.

## Deploy

Use GitHub Actions release workflow or locally:

```powershell
$env:RAILWAY_TOKEN="..."
$env:RAILWAY_PROJECT="..."
$env:RAILWAY_SERVICE="..."
$env:SMOKE_BACKEND_URL="https://api.example.com"
$env:SMOKE_FRONTEND_URL="https://app.example.com"
.\scripts\deploy-railway.ps1 -Environment production
```

## Smoke Test

```powershell
.\scripts\smoke-test.ps1 `
  -BackendUrl "https://api.example.com" `
  -FrontendUrl "https://app.example.com" `
  -AdminUserId "<admin-user-uuid>"
```

## Backups

Before releases with migrations:

```powershell
.\scripts\backup-postgres.ps1 -DatabaseUrl $env:DATABASE_URL -Tag pre-release
```

Restore requires explicit confirmation:

```powershell
.\scripts\restore-postgres.ps1 -BackupFile .\backups\arceus-postgres.dump -Confirm RESTORE_ARCEUS_DATABASE
```

## Observability

Set:

```powershell
SENTRY_DSN=https://...
PROMETHEUS_METRICS_ENABLED=true
APP_RELEASE=<git-sha-or-tag>
```

Scrape `/metrics` for every service. Alert on:

- `/api/v1/ready` not `ready`
- Redis unavailable
- job dead-letter growth
- error rate above 1%
- P99 API latency above 3s

## Desktop Signing

For GitHub release builds:

```powershell
WIN_CSC_LINK=<base64-or-url-to-cert>
WIN_CSC_KEY_PASSWORD=<password>
APPLE_ID=<apple-id>
APPLE_APP_SPECIFIC_PASSWORD=<password>
APPLE_TEAM_ID=<team-id>
```

Run `npm run dist` in `desktop/` to produce signed installers when credentials are present.

## Download Manifest

The public `/download` page reads `GET /api/v1/downloads/latest`. Configure release artifacts after a signed GitHub Release is published:

```powershell
ARCEUS_RELEASE_VERSION=arceus-code-v1.0.0
ARCEUS_RELEASE_CHANNEL=stable
ARCEUS_RELEASE_SIGNED=true
ARCEUS_RELEASE_NOTES_URL=https://github.com/<org>/<repo>/releases/tag/arceus-code-v1.0.0
ARCEUS_UPDATE_FEED_URL=https://github.com/<org>/<repo>/releases/latest
ARCEUS_DOWNLOAD_WINDOWS_X64_INSTALLER_URL=https://github.com/<org>/<repo>/releases/download/arceus-code-v1.0.0/Arceus-Code-Setup.exe
ARCEUS_DOWNLOAD_WINDOWS_X64_INSTALLER_SHA256=<sha256>
ARCEUS_DOWNLOAD_MACOS_ARM64_DMG_URL=https://github.com/<org>/<repo>/releases/download/arceus-code-v1.0.0/Arceus-Code-arm64.dmg
ARCEUS_DOWNLOAD_MACOS_X64_DMG_URL=https://github.com/<org>/<repo>/releases/download/arceus-code-v1.0.0/Arceus-Code-x64.dmg
ARCEUS_DOWNLOAD_LINUX_X64_APPIMAGE_URL=https://github.com/<org>/<repo>/releases/download/arceus-code-v1.0.0/Arceus-Code.AppImage
ARCEUS_DOWNLOAD_LINUX_X64_DEB_URL=https://github.com/<org>/<repo>/releases/download/arceus-code-v1.0.0/arceus-code_amd64.deb
ARCEUS_DOWNLOAD_LINUX_X64_RPM_URL=https://github.com/<org>/<repo>/releases/download/arceus-code-v1.0.0/arceus-code.rpm
```

If a URL is missing, the page marks that platform artifact as pending instead of serving a broken installer link.
