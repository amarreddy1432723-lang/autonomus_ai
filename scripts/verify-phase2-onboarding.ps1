param(
  [string]$SummaryPath = $env:PHASE2_ONBOARDING_SUMMARY_PATH
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
if (-not $SummaryPath) { $SummaryPath = Join-Path $repoRoot ".verify\phase2-onboarding-summary.json" }
$results = New-Object System.Collections.Generic.List[object]

function Add-Check {
  param([string]$Name, [bool]$Ok, [string]$Detail)
  $script:results.Add([pscustomobject]@{ name = $Name; ok = [bool]$Ok; detail = $Detail }) | Out-Null
}

function Read-Text {
  param([string]$RelativePath)
  $path = Join-Path $repoRoot $RelativePath
  if (-not (Test-Path $path)) { throw "Missing file: $RelativePath" }
  return Get-Content $path -Raw
}

$page = Read-Text "frontend\src\app\onboarding\page.tsx"
$styles = Read-Text "frontend\src\app\onboarding\Onboarding.module.css"
$launch = Read-Text "frontend\src\app\launch\page.tsx"
$guard = Read-Text "frontend\src\components\DesktopCodeRouteGuard.tsx"
$shell = Read-Text "frontend\src\components\AppShell.tsx"
$boundaries = Read-Text "frontend\src\lib\frontendBoundaries.ts"

Add-Check "Onboarding route exists" ($page.Length -gt 1000 -and $styles.Length -gt 1000) "frontend/src/app/onboarding"
Add-Check "Desktop guard allows onboarding" ($guard -match "'/onboarding'") "DesktopCodeRouteGuard.tsx"
Add-Check "Desktop shell treats onboarding as fullscreen" ($shell -match "'/onboarding'") "AppShell.tsx"
Add-Check "Route boundary allows onboarding" ($boundaries -match "prefix: '/onboarding'.*desktopAllowed: true") "frontendBoundaries.ts"
Add-Check "Launch starts onboarding" ($launch -match "router\.push\('/onboarding'\)") "launch primary action"

$requiredCopy = @(
  "Welcome to Arceus",
  "Workspace trust",
  "Telemetry preference",
  "Connect your account",
  "Repository Connection",
  "Open Local Folder",
  "Clone Git Repository",
  "AI Repository Report",
  "What would you like Arceus to do",
  "Strategy",
  "Analyze Mission"
)
foreach ($copy in $requiredCopy) {
  Add-Check "Required copy: $copy" ($page -like "*$copy*") $copy
}

$requiredBehaviors = @(
  "repository.analyzeRepository",
  "electron.workspace.openDirectory",
  "electron.selectDirectory",
  "arceus.onboarding.completed",
  "arceus.telemetry.preference",
  "/workspace?"
)
foreach ($behavior in $requiredBehaviors) {
  Add-Check "Required behavior: $behavior" ($page -like "*$behavior*") $behavior
}

$failed = @($results | Where-Object { -not $_.ok })
$summary = [pscustomobject]@{
  ready = $failed.Count -eq 0
  checks = $results
  failed = $failed.Count
}

$summaryDir = Split-Path -Parent $SummaryPath
if ($summaryDir -and -not (Test-Path $summaryDir)) {
  New-Item -ItemType Directory -Force -Path $summaryDir | Out-Null
}
$summary | ConvertTo-Json -Depth 6 | Set-Content -Path $SummaryPath -Encoding UTF8
$results | Format-Table -AutoSize
Write-Host "`nSummary written to $SummaryPath" -ForegroundColor Cyan
if ($failed.Count -gt 0) {
  throw "Phase 2 onboarding verification failed: $($failed.Count) failed check(s)."
}
Write-Host "Phase 2 onboarding verification passed." -ForegroundColor Green
