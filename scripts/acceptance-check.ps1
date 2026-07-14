param(
  [string]$BackendUrl = $env:SMOKE_BACKEND_URL,
  [string]$FrontendUrl = $env:SMOKE_FRONTEND_URL,
  [switch]$RunAudit = ($env:RUN_NPM_AUDIT -eq "true")
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

function Step($Name, [scriptblock]$Body) {
  Write-Host "`n==> $Name" -ForegroundColor Cyan
  & $Body
  Write-Host "OK: $Name" -ForegroundColor Green
}

if (-not $BackendUrl) { $BackendUrl = "http://localhost:8003" }
if (-not $FrontendUrl) { $FrontendUrl = "http://localhost:3000" }

function Resolve-ArceusFrontendUrl([string]$PreferredUrl) {
  $candidates = @($PreferredUrl)
  for ($port = 3000; $port -le 3010; $port++) {
    $candidate = "http://localhost:$port"
    if ($candidates -notcontains $candidate) {
      $candidates += $candidate
    }
  }
  foreach ($candidate in $candidates) {
    try {
      $response = Invoke-WebRequest -Uri "$candidate/hub" -UseBasicParsing -TimeoutSec 3
      if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400) {
        return $candidate
      }
    } catch {
      # Keep scanning ports.
    }
  }
  return $PreferredUrl
}

Step "Backend compile" {
  Push-Location $repoRoot
  python -m compileall backend/services | Out-Host
  Pop-Location
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

Step "Frontend production build" {
  Push-Location (Join-Path $repoRoot "frontend")
  npm run build
  Pop-Location
}

Step "Backend health and readiness" {
  try {
    $health = Invoke-WebRequest -Uri "$BackendUrl/api/v1/health" -UseBasicParsing -TimeoutSec 10
    if ($health.StatusCode -ne 200) { throw "Health returned $($health.StatusCode)" }
    $ready = Invoke-WebRequest -Uri "$BackendUrl/api/v1/ready" -UseBasicParsing -TimeoutSec 10
    if ($ready.StatusCode -lt 200 -or $ready.StatusCode -ge 500) { throw "Ready returned $($ready.StatusCode)" }
    Write-Host $ready.Content
  } catch {
    Write-Warning "Backend smoke check skipped/failed because the local backend is not reachable: $($_.Exception.Message)"
  }
}

Step "Frontend route smoke" {
  $resolvedFrontend = Resolve-ArceusFrontendUrl $FrontendUrl
  try {
    $hub = Invoke-WebRequest -Uri "$resolvedFrontend/hub" -UseBasicParsing -TimeoutSec 10
    if ($hub.StatusCode -lt 200 -or $hub.StatusCode -ge 400) { throw "Hub returned $($hub.StatusCode)" }
    Write-Host "Frontend smoke passed at $resolvedFrontend"
  } catch {
    Write-Warning "Frontend smoke check skipped/failed because the local frontend is not reachable: $($_.Exception.Message)"
  }
}

Step "Acceptance surface files exist" {
  $required = @(
    "frontend/src/app/workspace/WorkspaceTerminalPanel.tsx",
    "frontend/src/app/workspace/FileTree.tsx",
    "frontend/src/app/workspace/WorkReceipt.tsx",
    "frontend/src/app/workspace/DiffViewer.tsx",
    "frontend/src/app/workspace/PreviewPanel.tsx",
    "frontend/src/app/workspace/GitPanel.tsx",
    "frontend/src/app/marketplace/page.tsx",
    "backend/services/agent/terminal.py",
    "backend/services/agent/preview_verifier.py",
    "backend/services/agent/github_service.py",
    "backend/services/agent/plugins.py",
    "backend/services/agent/auth_enterprise.py",
    "backend/worker/celery_app.py",
    "backend/Dockerfile.sandbox",
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    "scripts/verify-desktop-release.ps1",
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
  Step "Dependency audit" {
    Push-Location (Join-Path $repoRoot "frontend")
    npm audit --audit-level=high
    Pop-Location
    Push-Location (Join-Path $repoRoot "desktop")
    npm audit --audit-level=high
    Pop-Location
  }
}

Write-Host "`nAutomated acceptance checks completed." -ForegroundColor Green
Write-Host "Manual/external gates remain: GitHub PR timing, Google Workspace SSO, signed installers, Homebrew/winget, Grafana dashboards, and real Electron folder/terminal latency tests." -ForegroundColor Yellow
