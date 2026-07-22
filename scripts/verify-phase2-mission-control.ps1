$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$componentDir = Join-Path $root "frontend/src/components/mission-control"
$page = Join-Path $root "frontend/src/app/mission-control/page.tsx"
$css = Join-Path $componentDir "MissionControlProduct.module.css"
$copy = Join-Path $componentDir "statusCopy.ts"

Write-Host "Phase 2.2 Mission Control verification"

$requiredFiles = @(
  "MissionHeader.tsx",
  "MissionProgress.tsx",
  "WorkforcePanel.tsx",
  "WorkerCard.tsx",
  "TaskDag.tsx",
  "TaskNode.tsx",
  "MissionTimeline.tsx",
  "TimelineEvent.tsx",
  "RepositoryLocks.tsx",
  "MissionMetrics.tsx",
  "EvidenceExplorer.tsx",
  "RecoveryCenter.tsx",
  "MissionControls.tsx",
  "MissionCompletion.tsx",
  "MissionControlProductView.tsx",
  "types.ts",
  "statusCopy.ts",
  "MissionControlProduct.module.css"
)

$missing = @()
foreach ($file in $requiredFiles) {
  $path = Join-Path $componentDir $file
  if (-not (Test-Path $path)) {
    $missing += $file
  }
}

if ($missing.Count -gt 0) {
  throw "Missing Mission Control files: $($missing -join ', ')"
}

$pageText = Get-Content $page -Raw
if ($pageText -notmatch "MissionControlProductView") {
  throw "Mission Control page does not render MissionControlProductView."
}

$copyText = Get-Content $copy -Raw
$requiredCopy = @(
  "Waiting for approval",
  "Agents working",
  "Needs your attention",
  "task.assignment.created",
  "path.reservation.acquired",
  "change_set.created",
  "verification.completed"
)

foreach ($needle in $requiredCopy) {
  if ($copyText -notmatch [regex]::Escape($needle)) {
    throw "Missing Mission Control copy mapping: $needle"
  }
}

$cssText = Get-Content $css -Raw
$requiredSelectors = @(
  ".missionHeader",
  ".workerCard",
  ".taskNode",
  ".timelineItem",
  ".lockItem",
  ".recoveryItem",
  ".metric",
  ".completion"
)

foreach ($selector in $requiredSelectors) {
  if ($cssText -notmatch [regex]::Escape($selector)) {
    throw "Missing Mission Control CSS selector: $selector"
  }
}

Write-Host "OK: Mission Control product components exist"
Write-Host "OK: Mission Control page renders product view"
Write-Host "OK: Runtime status and event copy is mapped"
Write-Host "OK: Product layout CSS selectors exist"
