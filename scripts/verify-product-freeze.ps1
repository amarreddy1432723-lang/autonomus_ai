param(
  [string]$BackendUrl = $env:SMOKE_BACKEND_URL,
  [string]$FrontendUrl = $env:SMOKE_FRONTEND_URL,
  [string]$SummaryPath = $env:PRODUCT_FREEZE_SUMMARY_PATH,
  [switch]$SkipFrontendBuild,
  [switch]$RunBackendTests,
  [switch]$RunCoreLoop,
  [switch]$StrictSmoke
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$startedAt = Get-Date
$results = New-Object System.Collections.Generic.List[object]

if (-not $BackendUrl) { $BackendUrl = "http://localhost:8003" }
if (-not $FrontendUrl) { $FrontendUrl = "http://localhost:3000" }
if (-not $SummaryPath) { $SummaryPath = Join-Path $repoRoot ".verify\product-freeze-summary.json" }

function Add-Result {
  param(
    [string]$Name,
    [bool]$Ok,
    [string]$Severity,
    [string]$Detail = ""
  )
  $script:results.Add([pscustomobject]@{
    name = $Name
    ok = [bool]$Ok
    severity = $Severity
    detail = $Detail
  }) | Out-Null
}

function Step {
  param(
    [string]$Name,
    [scriptblock]$Body,
    [string]$Severity = "blocker",
    [switch]$Optional
  )
  Write-Host "`n==> $Name" -ForegroundColor Cyan
  try {
    $detail = & $Body
    Add-Result $Name $true $(if ($Optional) { "warning" } else { $Severity }) "$detail"
    Write-Host "OK: $Name" -ForegroundColor Green
  } catch {
    $message = $_.Exception.Message
    if ($Optional -and -not $StrictSmoke) {
      Add-Result $Name $false "warning" $message
      Write-Warning "$Name failed/skipped: $message"
      return
    }
    Add-Result $Name $false $Severity $message
    throw
  }
}

function Assert-Path {
  param([string]$RelativePath)
  $path = Join-Path $repoRoot $RelativePath
  if (-not (Test-Path $path)) {
    throw "Missing required product-freeze surface: $RelativePath"
  }
  return $RelativePath
}

function Invoke-HttpOk {
  param([string]$Uri)
  $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 10
  if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 400) {
    throw "$Uri returned $($response.StatusCode)"
  }
  return "$Uri -> $($response.StatusCode)"
}

Write-Host "Arceus v1.0 product-freeze verification" -ForegroundColor White

Step "Product roadmap freeze document" {
  Assert-Path "docs\v1-product-roadmap.md"
}

Step "Core runtime regression checklist" {
  Assert-Path "docs\core-loop-regression-checklist.md"
}

Step "Backend compile" {
  Push-Location $repoRoot
  python -m compileall backend/services | Out-Host
  Pop-Location
  "backend/services compileall passed"
}

if ($RunBackendTests) {
  Step "Backend test suite" {
    Push-Location $repoRoot
    python -m pytest backend -q | Out-Host
    Pop-Location
    "backend pytest passed"
  }
}

Step "Desktop syntax" {
  Push-Location $repoRoot
  node --check desktop/main.js
  node --check desktop/preload.js
  Pop-Location
  "desktop main/preload syntax passed"
}

Step "Mission observability proof" {
  Push-Location $repoRoot
  $raw = python scripts\verify-mission-observability.py
  Pop-Location
  $payload = $raw | ConvertFrom-Json
  if (-not [bool]$payload.ok) {
    $failed = @($payload.checks | Where-Object { -not $_.ok })
    throw "Mission observability failed: $(@($failed).Count) failed check(s)"
  }
  "checks=$(@($payload.checks).Count)"
}

Step "Parallel scheduler proof" {
  Push-Location $repoRoot
  $raw = python scripts\verify-parallel-scheduler.py
  Pop-Location
  $payload = $raw | ConvertFrom-Json
  if (-not [bool]$payload.ok) {
    $failed = @($payload.checks | Where-Object { -not $_.ok })
    throw "Parallel scheduler failed: $(@($failed).Count) failed check(s)"
  }
  "checks=$(@($payload.checks).Count)"
}

Step "Scheduler recovery proof" {
  Push-Location $repoRoot
  $raw = python scripts\verify-scheduler-recovery.py
  Pop-Location
  $payload = $raw | ConvertFrom-Json
  if (-not [bool]$payload.ok) {
    $failed = @($payload.checks | Where-Object { -not $_.ok })
    throw "Scheduler recovery failed: $(@($failed).Count) failed check(s)"
  }
  "checks=$(@($payload.checks).Count)"
}

Step "Interrupted execution recovery proof" {
  Push-Location $repoRoot
  $raw = node scripts\verify-interrupted-execution-recovery.js
  Pop-Location
  $payload = $raw | ConvertFrom-Json
  if (-not [bool]$payload.ok) {
    $failed = @($payload.checks | Where-Object { -not $_.ok })
    throw "Interrupted recovery failed: $(@($failed).Count) failed check(s)"
  }
  "checks=$(@($payload.checks).Count)"
}

Step "Desktop worker coordinator proof" {
  Push-Location $repoRoot
  $raw = node scripts\verify-worker-coordinator.js
  Pop-Location
  $payload = $raw | ConvertFrom-Json
  if (-not [bool]$payload.ok) {
    throw "Worker coordinator failed."
  }
  "accepted=$($payload.accepted); claimed=$($payload.claimed); completed=$($payload.completed); overlap=$($payload.overlap)"
}

Step "Desktop release surface" {
  Push-Location $repoRoot
  .\scripts\verify-desktop-release.ps1 | Out-Host
  Pop-Location
  "desktop release verifier passed"
}

Step "Database operations surface" {
  Push-Location $repoRoot
  .\scripts\verify-database-operations.ps1 | Out-Host
  Pop-Location
  "database operations verifier passed"
}

if (-not $SkipFrontendBuild) {
  Step "Frontend production build" {
    Push-Location (Join-Path $repoRoot "frontend")
    npm run build | Out-Host
    Pop-Location
    "frontend production build passed"
  }
}

Step "Backend health" {
  Invoke-HttpOk "$BackendUrl/api/v1/health"
} -Optional

Step "Backend readiness" {
  Invoke-HttpOk "$BackendUrl/api/v1/ready"
} -Optional

Step "Workspace route" {
  Invoke-HttpOk "$FrontendUrl/workspace"
} -Optional

if ($RunCoreLoop) {
  Step "Full core loop" {
    Push-Location $repoRoot
    .\scripts\verify-core-loop.ps1 -BackendUrl $BackendUrl -FrontendUrl $FrontendUrl -Strict:$StrictSmoke | Out-Host
    Pop-Location
    "core loop verifier passed"
  }
}

$blockers = @($results | Where-Object { $_.ok -ne $true -and $_.severity -eq "blocker" })
$warnings = @($results | Where-Object { $_.ok -ne $true -and $_.severity -ne "blocker" })
$summary = [pscustomobject]@{
  ready = $blockers.Count -eq 0
  started_at = $startedAt.ToUniversalTime().ToString("o")
  finished_at = (Get-Date).ToUniversalTime().ToString("o")
  blockers = $blockers.Count
  warnings = $warnings.Count
  next_phase = if ($blockers.Count -eq 0) { "Phase 2 - User Experience and onboarding" } else { "Stay in Phase 1 - Product Freeze" }
  results = $results
}

$summaryDir = Split-Path -Parent $SummaryPath
if ($summaryDir -and -not (Test-Path $summaryDir)) {
  New-Item -ItemType Directory -Force -Path $summaryDir | Out-Null
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -Path $SummaryPath -Encoding UTF8

$results | Format-Table -AutoSize
Write-Host "`nSummary written to $SummaryPath" -ForegroundColor Cyan
if ($blockers.Count -gt 0) {
  throw "Product freeze verification failed: $($blockers.Count) blocker(s)."
}
Write-Host "Product freeze verification passed." -ForegroundColor Green
