param(
  [string]$BackendUrl = $env:SMOKE_BACKEND_URL,
  [string]$FrontendUrl = $env:SMOKE_FRONTEND_URL,
  [string]$AdminUserId = $env:SMOKE_ADMIN_USER_ID,
  [switch]$SkipFrontendBuild,
  [switch]$SkipPytest,
  [switch]$SkipMigrationCheck,
  [switch]$RunAudit,
  [switch]$StrictSmoke
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$startedAt = Get-Date
$results = New-Object System.Collections.Generic.List[object]

if (-not $BackendUrl) { $BackendUrl = "http://localhost:8003" }
if (-not $FrontendUrl) { $FrontendUrl = "http://localhost:3000" }

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

Step "Admin release readiness endpoint" {
  if (-not $AdminUserId) {
    throw "Set SMOKE_ADMIN_USER_ID or pass -AdminUserId to verify admin release readiness."
  }
  $admin = Invoke-JsonHealth "$BackendUrl/api/v1/admin/release-readiness" -Headers @{"x-user-id"=$AdminUserId}
  Write-Host $admin.Content
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
    "ops/prometheus/arceus-alerts.yml"
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

Write-Host "Completed in $([math]::Round($elapsed.TotalMinutes, 2)) minutes." -ForegroundColor Green
if ($warnings.Count -gt 0) {
  Write-Host "Warnings remain. Run with -StrictSmoke to make smoke/readiness warnings fail the script." -ForegroundColor Yellow
}
