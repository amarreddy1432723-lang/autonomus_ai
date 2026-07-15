param(
  [string]$BackendUrl = $env:SMOKE_BACKEND_URL,
  [string]$FrontendUrl = $env:SMOKE_FRONTEND_URL,
  [string]$AdminUserId = $env:SMOKE_ADMIN_USER_ID,
  [string]$SummaryPath = $env:FULL_VERIFY_SUMMARY_PATH,
  [switch]$SkipFrontendBuild,
  [switch]$SkipPytest,
  [switch]$SkipMigrationCheck,
  [switch]$CheckProviders,
  [switch]$RunAudit,
  [switch]$StrictSmoke
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$startedAt = Get-Date
$results = New-Object System.Collections.Generic.List[object]

if (-not $BackendUrl) { $BackendUrl = "http://localhost:8003" }
if (-not $FrontendUrl) { $FrontendUrl = "http://localhost:3000" }
if (-not $SummaryPath) { $SummaryPath = Join-Path $repoRoot ".verify\full-verify-summary.json" }

function Add-Result {
  param(
    [string]$Name,
    [string]$Status,
    [double]$Seconds,
    [string]$Detail = ""
  )
  $script:results.Add([pscustomobject]@{
    Step = $Name
    Status = $Status
    Seconds = [math]::Round($Seconds, 2)
    Detail = $Detail
  }) | Out-Null
}

function Step {
  param(
    [string]$Name,
    [scriptblock]$Body,
    [switch]$Optional
  )
  Write-Host "`n==> $Name" -ForegroundColor Cyan
  $timer = [System.Diagnostics.Stopwatch]::StartNew()
  try {
    & $Body
    $timer.Stop()
    Add-Result $Name "OK" $timer.Elapsed.TotalSeconds
    Write-Host "OK: $Name" -ForegroundColor Green
  } catch {
    $timer.Stop()
    $message = $_.Exception.Message
    if ($Optional -and -not $StrictSmoke) {
      Add-Result $Name "WARN" $timer.Elapsed.TotalSeconds $message
      Write-Warning "$Name skipped/failed: $message"
      return
    }
    Add-Result $Name "FAILED" $timer.Elapsed.TotalSeconds $message
    throw
  }
}

function Invoke-JsonHealth {
  param([string]$Uri, [hashtable]$Headers = @{})
  $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -Headers $Headers -TimeoutSec 15
  if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 300) {
    throw "$Uri returned $($response.StatusCode)"
  }
  return $response
}

function Invoke-JsonObject {
  param([string]$Uri, [hashtable]$Headers = @{})
  $response = Invoke-JsonHealth $Uri $Headers
  return $response.Content | ConvertFrom-Json
}

function Require-Ready {
  param($Payload, [string]$Name)
  if ($null -eq $Payload.ready) {
    throw "$Name response is missing ready field."
  }
  if ($Payload.ready -ne $true) {
    $detail = if ($Payload.summary) { ($Payload.summary | ConvertTo-Json -Compress) } elseif ($Payload.blockers) { ($Payload.blockers | ConvertTo-Json -Compress) } else { ($Payload | ConvertTo-Json -Compress) }
    throw "$Name is not ready: $detail"
  }
}

function Require-Field {
  param($Payload, [string]$Field, [string]$Name)
  if ($null -eq $Payload.$Field) {
    throw "$Name response missing $Field."
  }
}

function Resolve-ArceusFrontendUrl {
  param([string]$PreferredUrl)
  $candidates = @($PreferredUrl)
  for ($port = 3000; $port -le 3010; $port++) {
    $candidate = "http://localhost:$port"
    if ($candidates -notcontains $candidate) { $candidates += $candidate }
  }
  foreach ($candidate in $candidates) {
    try {
      $response = Invoke-WebRequest -Uri "$candidate/hub" -UseBasicParsing -TimeoutSec 4
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
        return $candidate
      }
    } catch {
      # Keep scanning.
    }
  }
  return $PreferredUrl
}

Step "Backend compile" {
  Push-Location $repoRoot
  python -m compileall backend/services
  Pop-Location
}

if (-not $SkipPytest) {
  Step "Backend test suite" {
    Push-Location $repoRoot
    python -m pytest backend -q
    Pop-Location
  }
}

if (-not $SkipMigrationCheck) {
  Step "Alembic migration import check" {
    Push-Location (Join-Path $repoRoot "backend")
    python -m alembic current
    Pop-Location
  } -Optional
}

Step "Desktop syntax" {
  Push-Location $repoRoot
  node --check desktop/main.js
  node --check desktop/preload.js
  Pop-Location
}

Step "Desktop release surface" {
  Push-Location $repoRoot
  .\scripts\verify-desktop-release.ps1
  Pop-Location
}

Step "Database operations surface" {
  Push-Location $repoRoot
  .\scripts\verify-database-operations.ps1
  Pop-Location
}

Step "Observability surface" {
  Push-Location $repoRoot
  .\scripts\verify-observability.ps1 -Strict:$StrictSmoke
  Pop-Location
}

if ($CheckProviders) {
  Step "External provider configuration" {
    Push-Location $repoRoot
    .\scripts\verify-provider-config.ps1 -Environment $(if ($env:APP_ENV) { $env:APP_ENV } else { "local" }) -Strict:$StrictSmoke
    Pop-Location
  } -Optional
}

if (-not $SkipFrontendBuild) {
  Step "Frontend production build" {
    Push-Location (Join-Path $repoRoot "frontend")
    npm run build
    Pop-Location
  }
}

Step "Backend health and readiness" {
  Invoke-JsonHealth "$BackendUrl/api/v1/health" | Out-Null
  $ready = Invoke-JsonHealth "$BackendUrl/api/v1/ready"
  Write-Host $ready.Content
} -Optional

Step "Production readiness endpoint" {
  $prod = Invoke-JsonHealth "$BackendUrl/api/v1/production/readiness"
  Write-Host $prod.Content
} -Optional

Step "Admin release readiness gate" {
  if (-not $AdminUserId) {
    throw "Set SMOKE_ADMIN_USER_ID or pass -AdminUserId to verify admin release readiness."
  }
  $admin = Invoke-JsonObject "$BackendUrl/api/v1/admin/release-readiness" -Headers @{"x-user-id"=$AdminUserId}
  Require-Field $admin "checks" "Admin release readiness"
  Require-Field $admin "runbook" "Admin release readiness"
  Require-Ready $admin "Admin release readiness"
  Write-Host ($admin | ConvertTo-Json -Depth 6)
} -Optional

Step "Admin billing gate" {
  if (-not $AdminUserId) {
    throw "Set SMOKE_ADMIN_USER_ID or pass -AdminUserId to verify admin billing health."
  }
  $billing = Invoke-JsonObject "$BackendUrl/api/v1/admin/billing-health" -Headers @{"x-user-id"=$AdminUserId}
  Require-Field $billing "stripe_secret_configured" "Admin billing health"
  Require-Ready $billing "Admin billing health"
  Write-Host ($billing | ConvertTo-Json -Depth 6)
} -Optional

Step "Admin observability gate" {
  if (-not $AdminUserId) {
    throw "Set SMOKE_ADMIN_USER_ID or pass -AdminUserId to verify admin observability health."
  }
  $observability = Invoke-JsonObject "$BackendUrl/api/v1/admin/observability-health" -Headers @{"x-user-id"=$AdminUserId}
  Require-Field $observability "checks" "Admin observability health"
  Require-Field $observability "prometheus" "Admin observability health"
  Require-Field $observability "grafana" "Admin observability health"
  Require-Ready $observability "Admin observability health"
  Write-Host ($observability | ConvertTo-Json -Depth 8)
} -Optional

Step "Admin rate-limit gate" {
  if (-not $AdminUserId) {
    throw "Set SMOKE_ADMIN_USER_ID or pass -AdminUserId to verify admin rate-limit health."
  }
  $limits = Invoke-JsonObject "$BackendUrl/api/v1/admin/rate-limits" -Headers @{"x-user-id"=$AdminUserId}
  Require-Field $limits "profiles" "Admin rate-limit health"
  $profileNames = @($limits.profiles | ForEach-Object { $_.name })
  foreach ($required in @("auth", "model", "upload", "code_runtime", "pa", "interview", "admin", "default")) {
    if ($profileNames -notcontains $required) {
      throw "Admin rate-limit health missing route class '$required'."
    }
  }
  if ($limits.enabled -ne $true) {
    throw "Rate limits are disabled."
  }
  if ($StrictSmoke -and $limits.enforcing -ne $true) {
    throw "Rate limits are not enforcing. Configure Redis or enable fail-closed before production."
  }
  Write-Host ($limits | ConvertTo-Json -Depth 8)
} -Optional

Step "Frontend route smoke" {
  $resolvedFrontend = Resolve-ArceusFrontendUrl $FrontendUrl
  $hub = Invoke-WebRequest -Uri "$resolvedFrontend/hub" -UseBasicParsing -TimeoutSec 15
  if ($hub.StatusCode -lt 200 -or $hub.StatusCode -ge 400) { throw "Hub returned $($hub.StatusCode)" }
  $workspace = Invoke-WebRequest -Uri "$resolvedFrontend/workspace" -UseBasicParsing -TimeoutSec 15
  if ($workspace.StatusCode -lt 200 -or $workspace.StatusCode -ge 400) { throw "Workspace returned $($workspace.StatusCode)" }
  Write-Host "Frontend smoke passed at $resolvedFrontend"
} -Optional

Step "Acceptance surface files exist" {
  $required = @(
    "frontend/src/app/workspace/WorkspaceTerminalPanel.tsx",
    "frontend/src/app/workspace/FileTree.tsx",
    "frontend/src/app/workspace/WorkReceipt.tsx",
    "frontend/src/app/workspace/DiffViewer.tsx",
    "frontend/src/app/workspace/PreviewPanel.tsx",
    "frontend/src/app/workspace/GitPanel.tsx",
    "frontend/src/app/admin/page.tsx",
    "backend/services/agent/terminal.py",
    "backend/services/agent/preview_verifier.py",
    "backend/services/agent/github_service.py",
    "backend/services/agent/billing.py",
    "backend/services/shared/security.py",
    "backend/worker/celery_app.py",
    "backend/Dockerfile.sandbox",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    "ops/prometheus/prometheus.yml",
    "ops/prometheus/arceus-alerts.yml",
    "ops/grafana/arceus-code-overview.json",
    "scripts/verify-desktop-release.ps1",
    "scripts/verify-database-operations.ps1",
    "scripts/verify-provider-config.ps1",
    ".env.production.example",
    "scripts/backup-postgres.ps1",
    "scripts/restore-postgres.ps1",
    "manifests/a/Arceus/Code/1.0.0/Arceus.Code.yaml",
    "manifests/a/Arceus/Code/1.0.0/Arceus.Code.installer.yaml",
    "manifests/a/Arceus/Code/1.0.0/Arceus.Code.locale.en-US.yaml"
  )
  foreach ($relative in $required) {
    $path = Join-Path $repoRoot $relative
    if (-not (Test-Path $path)) { throw "Missing required surface: $relative" }
  }
}

if ($RunAudit) {
  Step "Frontend dependency audit" {
    Push-Location (Join-Path $repoRoot "frontend")
    npm audit --audit-level=high
    Pop-Location
  } -Optional

  Step "Desktop dependency audit" {
    Push-Location (Join-Path $repoRoot "desktop")
    npm audit --audit-level=high
    Pop-Location
  } -Optional
}

$elapsed = (Get-Date) - $startedAt
Write-Host "`nFull verification summary" -ForegroundColor Cyan
$results | Format-Table -AutoSize

$failed = @($results | Where-Object { $_.Status -eq "FAILED" })
$warnings = @($results | Where-Object { $_.Status -eq "WARN" })
if ($failed.Count -gt 0) {
  throw "$($failed.Count) verification step(s) failed."
}

$summaryDir = Split-Path -Parent $SummaryPath
if ($summaryDir) {
  New-Item -ItemType Directory -Force -Path $summaryDir | Out-Null
}
$summary = [pscustomobject]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  backend_url = $BackendUrl
  frontend_url = $FrontendUrl
  strict_smoke = [bool]$StrictSmoke
  status = if ($warnings.Count -gt 0) { "warnings" } else { "ready" }
  failed = $failed.Count
  warnings = $warnings.Count
  elapsed_seconds = [math]::Round($elapsed.TotalSeconds, 2)
  results = $results
}
$summary | ConvertTo-Json -Depth 6 | Set-Content -Path $SummaryPath -Encoding UTF8

Write-Host "Completed in $([math]::Round($elapsed.TotalMinutes, 2)) minutes." -ForegroundColor Green
Write-Host "Summary written to $SummaryPath" -ForegroundColor Green
if ($warnings.Count -gt 0) {
  Write-Host "Warnings remain. Run with -StrictSmoke to make smoke/readiness warnings fail the script." -ForegroundColor Yellow
}
