param(
  [ValidateSet("local", "development", "staging", "production", "prod")]
  [string]$Environment = $(if ($env:APP_ENV) { $env:APP_ENV } else { "local" }),
  [switch]$Strict,
  [string]$OutputPath = $env:PROVIDER_CONFIG_REPORT_PATH
)

$ErrorActionPreference = "Stop"
$normalizedEnvironment = if ($Environment -eq "prod") { "production" } elseif ($Environment -eq "development") { "local" } else { $Environment }
$checks = New-Object System.Collections.Generic.List[object]

function Test-Configured([string]$Name, [switch]$AllowPlaceholder) {
  $value = [Environment]::GetEnvironmentVariable($Name)
  if (-not $value -or -not $value.Trim()) { return $false }
  if ($AllowPlaceholder) { return $true }
  return $value -notmatch "^(your-|<|REPLACE_|mock-|local-dev|supersecretkeyforlocaldevelopmentonlychangeinprod!)"
}

function Add-Check {
  param(
    [string]$Area,
    [string]$Name,
    [string[]]$Vars,
    [string]$Severity = "blocker",
    [string]$Action = ""
  )
  $missing = @($Vars | Where-Object { -not (Test-Configured $_) })
  $checks.Add([pscustomobject]@{
    area = $Area
    name = $Name
    ok = $missing.Count -eq 0
    severity = if ($missing.Count -eq 0) { "ok" } else { $Severity }
    missing = $missing
    action = if ($missing.Count -eq 0) { "" } elseif ($Action) { $Action } else { "Set: $($missing -join ', ')" }
  }) | Out-Null
}

$live = $normalizedEnvironment -in @("staging", "production")

Add-Check "runtime" "Live environment flags" @("APP_ENV", "JWT_SECRET", "APP_ENCRYPTION_KEY", "DATABASE_URL", "REDIS_URL") -Severity "blocker"
Add-Check "auth" "Clerk backend auth" @("CLERK_ISSUER", "CLERK_JWKS_URL") -Severity "blocker" -Action "Configure Clerk issuer/JWKS for backend token verification."
Add-Check "auth" "Clerk frontend auth" @("NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY", "NEXT_PUBLIC_REQUIRE_AUTH") -Severity "blocker" -Action "Configure Clerk publishable key and require auth in frontend."
Add-Check "billing" "Stripe checkout and webhooks" @("STRIPE_SECRET_KEY", "STRIPE_WEBHOOK_SECRET") -Severity "blocker"
Add-Check "billing" "Stripe price IDs" @("STRIPE_PRICE_STARTER_MONTHLY", "STRIPE_PRICE_STARTER_ANNUAL", "STRIPE_PRICE_PRO_MONTHLY", "STRIPE_PRICE_PRO_ANNUAL", "STRIPE_PRICE_ENTERPRISE_MONTHLY", "STRIPE_PRICE_ENTERPRISE_ANNUAL") -Severity "blocker"
Add-Check "github" "GitHub App" @("GITHUB_APP_ID", "GITHUB_APP_PRIVATE_KEY", "GITHUB_APP_NAME", "GITHUB_APP_SLUG", "GITHUB_APP_WEBHOOK_SECRET") -Severity "blocker"
Add-Check "observability" "Sentry" @("SENTRY_DSN", "NEXT_PUBLIC_SENTRY_DSN", "APP_RELEASE", "NEXT_PUBLIC_APP_RELEASE") -Severity "warning"
Add-Check "deploy" "Railway deploy and smoke" @("RAILWAY_TOKEN", "RAILWAY_PROJECT", "RAILWAY_SERVICE", "SMOKE_BACKEND_URL", "SMOKE_FRONTEND_URL", "SMOKE_ADMIN_USER_ID") -Severity "warning"
Add-Check "desktop" "Windows signing" @("WIN_CSC_LINK", "WIN_CSC_KEY_PASSWORD") -Severity "warning"
Add-Check "desktop" "Apple notarization" @("APPLE_ID", "APPLE_APP_SPECIFIC_PASSWORD", "APPLE_TEAM_ID") -Severity "warning"
Add-Check "release" "Download artifact env" @("ARCEUS_RELEASE_VERSION", "ARCEUS_RELEASE_NOTES_URL", "ARCEUS_UPDATE_FEED_URL") -Severity "warning"

if ($live) {
  $unsafeFlags = @()
  if (([Environment]::GetEnvironmentVariable("ALLOW_DEMO_USER") -or "").ToLowerInvariant() -eq "true") { $unsafeFlags += "ALLOW_DEMO_USER" }
  if (([Environment]::GetEnvironmentVariable("ALLOW_DEV_AUTH_FALLBACK") -or "").ToLowerInvariant() -eq "true") { $unsafeFlags += "ALLOW_DEV_AUTH_FALLBACK" }
  if (([Environment]::GetEnvironmentVariable("NEXT_PUBLIC_REQUIRE_AUTH") -or "").ToLowerInvariant() -ne "true") { $unsafeFlags += "NEXT_PUBLIC_REQUIRE_AUTH" }
  $checks.Add([pscustomobject]@{
    area = "auth"
    name = "Live auth safety flags"
    ok = $unsafeFlags.Count -eq 0
    severity = if ($unsafeFlags.Count -eq 0) { "ok" } else { "blocker" }
    missing = $unsafeFlags
    action = if ($unsafeFlags.Count -eq 0) { "" } else { "Disable demo/dev auth and require frontend auth for live environments." }
  }) | Out-Null
}

$blockers = @($checks | Where-Object { $_.ok -ne $true -and $_.severity -eq "blocker" })
$warnings = @($checks | Where-Object { $_.ok -ne $true -and $_.severity -eq "warning" })
$report = [pscustomobject]@{
  environment = $normalizedEnvironment
  strict = [bool]$Strict
  ready = $blockers.Count -eq 0 -and (-not $Strict -or $warnings.Count -eq 0)
  blockers = $blockers.Count
  warnings = $warnings.Count
  checks = $checks
}

if ($OutputPath) {
  $dir = Split-Path -Parent $OutputPath
  if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $report | ConvertTo-Json -Depth 6 | Set-Content -Path $OutputPath -Encoding UTF8
}

Write-Host "Provider configuration report" -ForegroundColor Cyan
$checks | Format-Table area, name, ok, severity, missing -AutoSize

if ($blockers.Count -gt 0) {
  if ($Strict -or $live) {
    throw "$($blockers.Count) provider configuration blocker(s) found."
  }
  Write-Warning "$($blockers.Count) provider configuration blocker(s) found."
}
if ($Strict -and $warnings.Count -gt 0) {
  throw "$($warnings.Count) provider configuration warning(s) found in strict mode."
}
Write-Host "Provider configuration check completed." -ForegroundColor Green
