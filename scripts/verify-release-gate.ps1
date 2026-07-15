param(
  [ValidateSet("staging", "production")]
  [string]$Environment = $(if ($env:RAILWAY_ENVIRONMENT) { $env:RAILWAY_ENVIRONMENT } elseif ($env:APP_ENV -eq "staging") { "staging" } else { "production" }),
  [ValidateSet("predeploy", "postdeploy")]
  [string]$Phase = "predeploy",
  [string]$ReleaseVersion = $(if ($env:RELEASE_VERSION) { $env:RELEASE_VERSION } elseif ($env:ARCEUS_RELEASE_VERSION) { $env:ARCEUS_RELEASE_VERSION } else { "" }),
  [string]$FullVerifySummaryPath = $(if ($env:FULL_VERIFY_SUMMARY_PATH) { $env:FULL_VERIFY_SUMMARY_PATH } else { ".verify\full-verify-summary.json" }),
  [string]$ProviderReportPath = $(if ($env:PROVIDER_CONFIG_REPORT_PATH) { $env:PROVIDER_CONFIG_REPORT_PATH } else { ".verify\provider-config-summary.json" }),
  [string]$OutputPath = $(if ($env:RELEASE_GATE_SUMMARY_PATH) { $env:RELEASE_GATE_SUMMARY_PATH } else { ".verify\release-gate-summary.json" }),
  [switch]$AllowWarnings
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$items = New-Object System.Collections.Generic.List[object]

function Resolve-RepoPath([string]$Path) {
  if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
  return Join-Path $repoRoot $Path
}

function Add-GateItem {
  param(
    [string]$Name,
    [bool]$Ok,
    [string]$Severity = "blocker",
    [string]$Detail = "",
    [string]$Action = ""
  )
  $items.Add([pscustomobject]@{
    name = $Name
    ok = $Ok
    severity = if ($Ok) { "ok" } else { $Severity }
    detail = $Detail
    action = $Action
  }) | Out-Null
}

function Test-Configured([string]$Name) {
  $value = [Environment]::GetEnvironmentVariable($Name)
  return [bool]($value -and $value.Trim() -and $value -notmatch "^(your-|<|REPLACE_|mock-|local-dev|supersecretkeyforlocaldevelopmentonlychangeinprod!)")
}

function Read-JsonFile([string]$Path) {
  $resolved = Resolve-RepoPath $Path
  if (-not (Test-Path $resolved)) { return $null }
  return Get-Content $resolved -Raw | ConvertFrom-Json
}

if (-not $ReleaseVersion) {
  $ReleaseVersion = "unversioned"
}

$releaseVersionOk = $ReleaseVersion -match "^arceus-code-v\d+\.\d+\.\d+(-[A-Za-z0-9.-]+)?$"
Add-GateItem "Release version" $releaseVersionOk "blocker" "ReleaseVersion=$ReleaseVersion" "Use a tag like arceus-code-v1.2.3."

$fullVerify = Read-JsonFile $FullVerifySummaryPath
if ($null -eq $fullVerify) {
  $severity = if ($Phase -eq "postdeploy") { "blocker" } else { "info" }
  Add-GateItem "Full verification summary" ($Phase -ne "postdeploy") $severity "Missing $FullVerifySummaryPath" "Run .\scripts\full-verify.ps1 -CheckProviders -StrictSmoke after deploy."
} else {
  $summaryReady = $fullVerify.status -eq "ready" -and [int]$fullVerify.failed -eq 0
  $warningOk = $AllowWarnings -or [int]$fullVerify.warnings -eq 0
  $severity = if ($Phase -eq "postdeploy") { "blocker" } else { "info" }
  Add-GateItem "Full verification summary" ($summaryReady -and $warningOk) $severity "status=$($fullVerify.status), failed=$($fullVerify.failed), warnings=$($fullVerify.warnings)" "Clear verification failures and warnings, or pass -AllowWarnings only for staging dry runs."
}

Push-Location $repoRoot
try {
  .\scripts\verify-provider-config.ps1 -Environment $Environment -Strict:(!$AllowWarnings) -OutputPath (Resolve-RepoPath $ProviderReportPath) | Out-Host
  $providerReport = Read-JsonFile $ProviderReportPath
  Add-GateItem "Provider configuration" ($providerReport.ready -eq $true) "blocker" "blockers=$($providerReport.blockers), warnings=$($providerReport.warnings)" "Set Clerk, Stripe, GitHub App, Railway, Sentry, signing, and release env secrets."
} catch {
  Add-GateItem "Provider configuration" $false "blocker" $_.Exception.Message "Set production provider secrets from .env.production.example."
}
Pop-Location

Add-GateItem "Railway target" ((Test-Configured "RAILWAY_TOKEN") -and (Test-Configured "RAILWAY_PROJECT") -and (Test-Configured "RAILWAY_SERVICE")) "blocker" "Requires RAILWAY_TOKEN, RAILWAY_PROJECT, RAILWAY_SERVICE" "Configure Railway deployment secrets and variables."
Add-GateItem "Smoke targets" ((Test-Configured "SMOKE_BACKEND_URL") -and (Test-Configured "SMOKE_FRONTEND_URL") -and (Test-Configured "SMOKE_ADMIN_USER_ID")) "blocker" "Requires SMOKE_BACKEND_URL, SMOKE_FRONTEND_URL, SMOKE_ADMIN_USER_ID" "Configure post-deploy smoke endpoints and admin user."
Add-GateItem "Database backup command" (Test-Path (Join-Path $repoRoot "scripts\backup-postgres.ps1")) "blocker" "scripts/backup-postgres.ps1" "Keep backup command available before production migrations."
Add-GateItem "Database restore command" (Test-Path (Join-Path $repoRoot "scripts\restore-postgres.ps1")) "blocker" "scripts/restore-postgres.ps1" "Keep restore command available for rollback drills."
Add-GateItem "Deploy command" (Test-Path (Join-Path $repoRoot "scripts\deploy-railway.ps1")) "blocker" "scripts/deploy-railway.ps1" "Use the reviewed deploy wrapper, not an ad hoc Railway command."
Add-GateItem "Smoke command" (Test-Path (Join-Path $repoRoot "scripts\smoke-test.ps1")) "blocker" "scripts/smoke-test.ps1" "Run post-deploy smoke tests after every deploy."
Push-Location $repoRoot
try {
  .\scripts\verify-observability.ps1 -Strict:(!$AllowWarnings) | Out-Host
  $observabilityReport = Read-JsonFile ".verify\observability-summary.json"
  Add-GateItem "Observability verification" ($observabilityReport.ready -eq $true) "blocker" "blockers=$($observabilityReport.blockers), warnings=$($observabilityReport.warnings)" "Set Sentry envs, Prometheus/Grafana files, and alert coverage before release."
} catch {
  Add-GateItem "Observability verification" $false "blocker" $_.Exception.Message "Run .\scripts\verify-observability.ps1 and clear blockers."
}
Pop-Location
Add-GateItem "Rollback notes" (Test-Path (Join-Path $repoRoot "RELEASE.md")) "warning" "RELEASE.md" "Document migration and rollback notes for this release."

$blockers = @($items | Where-Object { $_.ok -ne $true -and $_.severity -eq "blocker" })
$warnings = @($items | Where-Object { $_.ok -ne $true -and $_.severity -eq "warning" })
$ready = $blockers.Count -eq 0 -and ($AllowWarnings -or $warnings.Count -eq 0)

$report = [pscustomobject]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  environment = $Environment
  phase = $Phase
  release_version = $ReleaseVersion
  ready = $ready
  blockers = $blockers.Count
  warnings = $warnings.Count
  deploy_command = ".\scripts\deploy-railway.ps1 -Environment $Environment -BackendUrl `$env:SMOKE_BACKEND_URL -FrontendUrl `$env:SMOKE_FRONTEND_URL -AdminUserId `$env:SMOKE_ADMIN_USER_ID"
  smoke_command = ".\scripts\smoke-test.ps1 -BackendUrl `$env:SMOKE_BACKEND_URL -FrontendUrl `$env:SMOKE_FRONTEND_URL -AdminUserId `$env:SMOKE_ADMIN_USER_ID"
  rollback_command = "railway rollback"
  items = $items
}

$resolvedOutput = Resolve-RepoPath $OutputPath
$outDir = Split-Path -Parent $resolvedOutput
if ($outDir) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }
$report | ConvertTo-Json -Depth 8 | Set-Content -Path $resolvedOutput -Encoding UTF8

Write-Host "Release gate report" -ForegroundColor Cyan
$items | Format-Table name, ok, severity, detail -AutoSize
Write-Host "Summary written to $resolvedOutput" -ForegroundColor Green

if (-not $ready) {
  throw "Release gate blocked: $($blockers.Count) blocker(s), $($warnings.Count) warning(s)."
}

Write-Host "Release gate passed." -ForegroundColor Green
