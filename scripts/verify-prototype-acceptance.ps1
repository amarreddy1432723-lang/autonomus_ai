param(
  [string]$BackendUrl = $(if ($env:SMOKE_BACKEND_URL) { $env:SMOKE_BACKEND_URL } else { "http://127.0.0.1:8003" }),
  [string]$FrontendUrl = $(if ($env:SMOKE_FRONTEND_URL) { $env:SMOKE_FRONTEND_URL } else { "http://localhost:3000" }),
  [string]$OutputPath = $(if ($env:PROTOTYPE_ACCEPTANCE_SUMMARY_PATH) { $env:PROTOTYPE_ACCEPTANCE_SUMMARY_PATH } else { ".verify\prototype-acceptance-summary.json" }),
  [switch]$AlreadyRunningServices,
  [switch]$StartDockerDeps,
  [switch]$RunLiveCoreLoop,
  [switch]$SkipFrontendBuild,
  [switch]$SkipDesktop,
  [switch]$Strict
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$startedAt = Get-Date
$results = New-Object System.Collections.Generic.List[object]

function Resolve-RepoPath([string]$Path) {
  if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
  return Join-Path $repoRoot $Path
}

function Add-Result {
  param(
    [string]$Name,
    [string]$Status,
    [string]$Severity,
    [string]$Detail = "",
    [double]$Seconds = 0
  )
  $script:results.Add([pscustomobject]@{
    name = $Name
    status = $Status
    ok = $Status -eq "passed" -or $Status -eq "skipped"
    severity = $Severity
    detail = $Detail
    seconds = [math]::Round($Seconds, 2)
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
  $timer = [System.Diagnostics.Stopwatch]::StartNew()
  try {
    & $Body
    $timer.Stop()
    Add-Result $Name "passed" "ok" "" $timer.Elapsed.TotalSeconds
    Write-Host "OK: $Name" -ForegroundColor Green
  } catch {
    $timer.Stop()
    $message = $_.Exception.Message
    if ($Optional -and -not $Strict) {
      Add-Result $Name "warning" "warning" $message $timer.Elapsed.TotalSeconds
      Write-Warning $message
      return
    }
    Add-Result $Name "failed" $Severity $message $timer.Elapsed.TotalSeconds
    if ($Severity -eq "blocker" -or $Strict) { throw }
  }
}

function Test-HttpRoute {
  param([string]$Url, [string]$Route)
  $uri = "$Url$Route"
  $response = Invoke-WebRequest -Uri $uri -UseBasicParsing -TimeoutSec 15
  if ($response.StatusCode -lt 200 -or $response.StatusCode -ge 500) {
    throw "$uri returned $($response.StatusCode)"
  }
  return "$($response.StatusCode) $($response.StatusDescription)"
}

Write-Host "Arceus prototype acceptance verification" -ForegroundColor Cyan

if ($StartDockerDeps) {
  Step "Start Docker dependencies" {
    Push-Location $repoRoot
    docker compose up -d postgres redis
    Pop-Location
  }
}

Step "Static P0 readiness" {
  Push-Location $repoRoot
  .\scripts\verify-prototype-p0.ps1 -Strict
  Pop-Location
}

Step "Product freeze gate" {
  Push-Location $repoRoot
  .\scripts\verify-product-freeze.ps1 -SkipFrontendBuild
  Pop-Location
}

Step "Onboarding gate" {
  Push-Location $repoRoot
  .\scripts\verify-phase2-onboarding.ps1
  Pop-Location
}

Step "Mission Control gate" {
  Push-Location $repoRoot
  .\scripts\verify-phase2-mission-control.ps1
  Pop-Location
}

if (-not $SkipDesktop) {
  Step "Desktop syntax and release surface" {
    Push-Location $repoRoot
    node --check desktop/main.js
    node --check desktop/preload.js
    .\scripts\verify-desktop-release.ps1
    Pop-Location
  }
}

if (-not $SkipFrontendBuild) {
  Step "Frontend production build" {
    Push-Location (Join-Path $repoRoot "frontend")
    npm run build
    Pop-Location
  }
}

if ($AlreadyRunningServices) {
  Step "Backend readiness smoke" {
    Test-HttpRoute $BackendUrl "/api/v1/health" | Out-Host
    Test-HttpRoute $BackendUrl "/api/v1/ready" | Out-Host
  } -Optional

  Step "Frontend route smoke" {
    foreach ($route in @("/", "/download", "/onboarding", "/workspace", "/mission-control", "/settings")) {
      $detail = Test-HttpRoute $FrontendUrl $route
      Write-Host "$route $detail"
    }
  } -Optional
}

if ($RunLiveCoreLoop) {
  Step "Live core loop acceptance" {
    Push-Location $repoRoot
    .\scripts\verify-prototype-p0.ps1 -RunLiveCoreLoop -BackendUrl $BackendUrl -FrontendUrl $FrontendUrl -Strict
    Pop-Location
  }
} else {
  Add-Result "Live core loop acceptance" "skipped" "info" "Pass -RunLiveCoreLoop when backend/frontend/Docker services are running." 0
}

$failed = @($results | Where-Object { $_.status -eq "failed" })
$warnings = @($results | Where-Object { $_.status -eq "warning" })
$blockers = @($results | Where-Object { $_.status -eq "failed" -and $_.severity -eq "blocker" })
$elapsed = (Get-Date) - $startedAt
$verdict = if ($blockers.Count -gt 0) { "NO-GO" } elseif ($warnings.Count -gt 0 -or -not $RunLiveCoreLoop) { "CONDITIONAL GO" } else { "GO" }

$resolvedOutput = Resolve-RepoPath $OutputPath
$outDir = Split-Path -Parent $resolvedOutput
if ($outDir) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }

$report = [pscustomobject]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  verdict = $verdict
  blockers = $blockers.Count
  warnings = $warnings.Count
  tests_passed = @($results | Where-Object { $_.status -eq "passed" }).Count
  tests_failed = $failed.Count
  live_core_loop_status = if ($RunLiveCoreLoop) { if ($blockers.Count -eq 0) { "passed_or_warning" } else { "failed" } } else { "skipped" }
  backend_url = $BackendUrl
  frontend_url = $FrontendUrl
  elapsed_seconds = [math]::Round($elapsed.TotalSeconds, 2)
  results = $results
}

$report | ConvertTo-Json -Depth 8 | Set-Content -Path $resolvedOutput -Encoding UTF8

$results | Format-Table name, status, severity, seconds, detail -AutoSize
Write-Host "Summary written to $resolvedOutput" -ForegroundColor DarkGray
Write-Host "Prototype acceptance verdict: $verdict" -ForegroundColor $(if ($verdict -eq "NO-GO") { "Red" } elseif ($verdict -eq "CONDITIONAL GO") { "Yellow" } else { "Green" })

if ($blockers.Count -gt 0) {
  throw "Prototype acceptance blocked: $($blockers.Count) blocker(s)."
}
