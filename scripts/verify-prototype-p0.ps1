param(
  [string]$BackendUrl = $(if ($env:SMOKE_BACKEND_URL) { $env:SMOKE_BACKEND_URL } else { "http://127.0.0.1:8003" }),
  [string]$FrontendUrl = $(if ($env:SMOKE_FRONTEND_URL) { $env:SMOKE_FRONTEND_URL } else { "http://localhost:3000" }),
  [string]$OutputPath = $(if ($env:PROTOTYPE_P0_SUMMARY_PATH) { $env:PROTOTYPE_P0_SUMMARY_PATH } else { ".verify\prototype-p0-summary.json" }),
  [switch]$RunLiveCoreLoop,
  [switch]$Strict
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$results = New-Object System.Collections.Generic.List[object]

function Resolve-RepoPath([string]$Path) {
  if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
  return Join-Path $repoRoot $Path
}

function Read-Text([string]$Path) {
  $resolved = Resolve-RepoPath $Path
  if (-not (Test-Path $resolved)) { return "" }
  return Get-Content $resolved -Raw
}

function Has-Text([string]$Path, [string]$Pattern) {
  return (Read-Text $Path) -match $Pattern
}

function Add-Check {
  param(
    [string]$Name,
    [bool]$Ok,
    [string]$Severity,
    [string]$Detail,
    [string]$Action = ""
  )
  $script:results.Add([pscustomobject]@{
    name = $Name
    ok = $Ok
    severity = if ($Ok) { "ok" } else { $Severity }
    detail = $Detail
    action = $Action
  }) | Out-Null
}

function Require-File([string]$RelativePath, [string]$Name, [string]$Action = "") {
  $exists = Test-Path (Resolve-RepoPath $RelativePath)
  Add-Check $Name $exists "blocker" $RelativePath $Action
}

function Require-Text([string]$RelativePath, [string]$Pattern, [string]$Name, [string]$Action = "") {
  $ok = Has-Text $RelativePath $Pattern
  Add-Check $Name $ok "blocker" "$RelativePath / $Pattern" $Action
}

Write-Host "Arceus P0 prototype readiness verification" -ForegroundColor Cyan

Require-File "frontend/src/app/onboarding/page.tsx" "First-run onboarding route"
Require-Text "frontend/src/app/onboarding/page.tsx" "\[1,\s*2,\s*3\]\.map" "Three-plan generation visible"
Require-Text "frontend/src/app/onboarding/page.tsx" "Balanced implementation" "Plan comparison copy visible"
Require-Text "frontend/src/app/onboarding/page.tsx" "Analyze Mission" "Natural-language mission CTA visible"
Require-Text "frontend/src/app/onboarding/page.tsx" "analyzeRepository" "Repository selection starts analysis"
Require-Text "frontend/src/stores/repository-store.ts" "/api/v1/repositories/analyze" "Repository analysis API wired"

Require-Text "frontend/src/stores/cognitive-mission-store.ts" "/api/v1/missions/compile-cognitive" "Mission compile API wired"
Require-Text "frontend/src/stores/mission-store.ts" "/api/v1/missions/persisted" "Durable mission creation wired"
Require-Text "frontend/src/stores/mission-store.ts" "/approve" "Explicit mission approval wired"
Require-Text "backend/services/agent/cognitive_execution.py" "compile-cognitive" "Backend cognitive compile endpoint"
Require-Text "backend/services/agent/cognitive_execution.py" "AWAITING_APPROVAL" "Mission waits for approval"
Require-Text "backend/services/agent/cognitive_architecture.py" "Multiple strategies were compared" "Backend strategy comparison signal"

Require-File "frontend/src/app/mission-control/page.tsx" "Mission Control route"
Require-File "frontend/src/components/mission-control/MissionControlProductView.tsx" "Mission Control product view"
Require-Text "frontend/src/app/mission-control/page.tsx" "/api/v1/task-runtime/missions/.*/observability" "Mission Control observability API wired"
Require-Text "frontend/src/app/mission-control/page.tsx" "release-gate" "Release gate checked from Mission Control"
Require-Text "backend/services/agent/task_runtime/routes.py" "observability" "Backend runtime observability endpoint"
Require-Text "scripts/verify-phase2-mission-control.ps1" "MissionControlProductView" "Mission Control UI verifier"

Require-Text "scripts/verify-core-loop.ps1" "Mission scheduler assignment" "Scheduler execution proof in core loop"
Require-Text "scripts/verify-core-loop.ps1" "Task tool evidence persistence" "Evidence persistence proof in core loop"
Require-Text "scripts/verify-core-loop.ps1" "Task change-set artifact" "Patch/change-set proof in core loop"
Require-Text "scripts/verify-core-loop.ps1" "Interrupted execution recovery proof" "Interrupted-session recovery proof"
Require-Text "scripts/verify-core-loop.ps1" "Mission observability proof" "Live Mission Control proof"
Require-Text "scripts/verify-core-loop.ps1" "Controlled desktop task execution" "Desktop worker controlled execution proof"

Require-Text "frontend/src/app/workspace/page.tsx" "/apply-safe" "Safe apply endpoint wired in workspace"
Require-Text "backend/services/agent/main.py" "/api/v1/code/sessions/{session_id}/apply-safe" "Backend safe apply endpoint"
Require-Text "frontend/src/app/workspace/page.tsx" "/rollback" "Rollback endpoint wired in workspace"
Require-Text "backend/services/agent/main.py" "/api/v1/code/sessions/{session_id}/rollback" "Backend rollback endpoint"
Require-Text "frontend/src/app/workspace/WorkReceipt.tsx" "Undo changes" "Undo changes receipt action"
Require-File "backend/test_patch_rollback.py" "Patch rollback regression test"

Require-Text "frontend/src/app/workspace/ActivityPanel.tsx" "rollbackPanel" "Rollback history panel"
Require-Text "frontend/src/app/workspace/PreviewPanel.tsx" "Re-verify" "Preview verification UI"
Require-Text "backend/services/agent/preview_verifier.py" "VerificationReport" "Preview verification backend"
Require-Text "backend/services/agent/arceus_runtime/verification_engine/routes.py" "mission-control/release-gate" "Release verification gate endpoint"

Require-File "desktop/package.json" "Desktop package config"
Require-File "desktop/main.js" "Desktop main process"
Require-File "desktop/preload.js" "Desktop preload bridge"
Require-File "scripts/verify-desktop-release.ps1" "Desktop release verifier"
Require-File "scripts/publish-desktop-release.ps1" "Desktop release publish script"
Require-File "frontend/src/app/download/page.tsx" "Download page"
Require-Text "frontend/src/app/download/page.tsx" "DownloadAction" "Download button component"
Require-Text "frontend/src/app/download/page.tsx" "/api/v1/downloads/latest" "Download manifest API wired"
Require-Text "backend/services/agent/routes_public.py" "/api/v1/downloads/latest" "Backend download manifest endpoint"
Require-Text "backend/services/agent/downloads.py" "ARCEUS_DOWNLOAD" "Release download env support"

Require-File "frontend/src/app/auth/desktop/page.tsx" "Desktop auth page"
Require-Text "frontend/src/components/DesktopAuthBridge.tsx" "/api/v1/auth/desktop/exchange" "Desktop auth exchange bridge"
Require-Text "frontend/src/utils/api.ts" "readDesktopAuthState" "Desktop auth token attached to API client"
Require-Text "backend/services/auth/main.py" "/api/v1/auth/desktop/code" "Backend desktop auth code endpoint"
Require-Text "backend/services/auth/main.py" "/api/v1/auth/desktop/exchange" "Backend desktop auth exchange endpoint"

Require-File "scripts/verify-release-gate.ps1" "Release gate verifier"
Require-File "scripts/full-verify.ps1" "Full verification gate"
Require-File "scripts/verify-product-freeze.ps1" "Product freeze gate"
Require-File "scripts/verify-core-loop.ps1" "Core loop verifier"

if ($RunLiveCoreLoop) {
  try {
    Push-Location $repoRoot
    .\scripts\verify-core-loop.ps1 -BackendUrl $BackendUrl -FrontendUrl $FrontendUrl -Strict | Out-Host
    Pop-Location
    Add-Check "Live P0 core loop" $true "ok" "verify-core-loop.ps1 passed"
  } catch {
    Pop-Location -ErrorAction SilentlyContinue
    Add-Check "Live P0 core loop" $false "blocker" $_.Exception.Message "Start backend/frontend/Docker dependencies, then rerun with -RunLiveCoreLoop."
  }
} else {
  Add-Check "Live P0 core loop" $true "info" "Skipped. Run with -RunLiveCoreLoop to execute repository -> mission -> scheduler -> evidence -> recovery proof."
}

$blockers = @($results | Where-Object { $_.ok -ne $true -and $_.severity -eq "blocker" })
$warnings = @($results | Where-Object { $_.ok -ne $true -and $_.severity -eq "warning" })
$ready = $blockers.Count -eq 0

$resolvedOutput = Resolve-RepoPath $OutputPath
$outDir = Split-Path -Parent $resolvedOutput
if ($outDir) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }

$report = [pscustomobject]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  ready = $ready
  blockers = $blockers.Count
  warnings = $warnings.Count
  live_core_loop_executed = [bool]$RunLiveCoreLoop
  backend_url = $BackendUrl
  frontend_url = $FrontendUrl
  checks = $results
}

$report | ConvertTo-Json -Depth 8 | Set-Content -Path $resolvedOutput -Encoding UTF8

$results | Format-Table name, ok, severity, detail -AutoSize
Write-Host "Summary written to $resolvedOutput" -ForegroundColor DarkGray

if (-not $ready) {
  $message = "P0 prototype gate blocked: $($blockers.Count) blocker(s), $($warnings.Count) warning(s)."
  if ($Strict) { throw $message }
  Write-Warning $message
  exit 1
}

Write-Host "P0 prototype static gate passed." -ForegroundColor Green
if (-not $RunLiveCoreLoop) {
  Write-Host "Run .\scripts\verify-prototype-p0.ps1 -RunLiveCoreLoop after services are up for the full live proof." -ForegroundColor Yellow
}
