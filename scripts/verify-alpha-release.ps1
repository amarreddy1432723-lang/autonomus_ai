param(
  [string]$RepoRoot,
  [string]$SummaryPath,
  [switch]$StrictExternal
)

$ErrorActionPreference = "Stop"
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $PSScriptRoot }
if (-not $SummaryPath) { $SummaryPath = Join-Path $RepoRoot ".verify\alpha-release-summary.json" }

$checks = New-Object System.Collections.Generic.List[object]

function Add-Check {
  param(
    [string]$Name,
    [bool]$Ok,
    [string]$Severity,
    [string]$Detail
  )
  $checks.Add([pscustomobject]@{
    name = $Name
    ok = $Ok
    severity = if ($Ok) { "ok" } else { $Severity }
    detail = $Detail
  }) | Out-Null
}

function Resolve-PathFromRoot {
  param([string]$RelativePath)
  return Join-Path $RepoRoot $RelativePath
}

function Test-File {
  param([string]$RelativePath, [string]$Description, [string]$Severity = "blocker")
  $path = Resolve-PathFromRoot $RelativePath
  Add-Check $Description (Test-Path $path) $Severity $RelativePath
}

function Test-Text {
  param(
    [string]$RelativePath,
    [string]$Pattern,
    [string]$Description,
    [string]$Severity = "blocker"
  )
  $path = Resolve-PathFromRoot $RelativePath
  if (-not (Test-Path $path)) {
    Add-Check $Description $false $Severity "$RelativePath is missing."
    return
  }
  $content = Get-Content $path -Raw
  Add-Check $Description ([bool]($content -match $Pattern)) $Severity "$RelativePath must contain pattern: $Pattern"
}

function Read-JsonFile {
  param([string]$RelativePath)
  $path = Resolve-PathFromRoot $RelativePath
  if (-not (Test-Path $path)) { return $null }
  return Get-Content $path -Raw | ConvertFrom-Json
}

Write-Host "Alpha release verification" -ForegroundColor Cyan

$desktopPackage = Read-JsonFile "desktop/package.json"
if ($null -eq $desktopPackage) {
  Add-Check "Desktop package metadata" $false "blocker" "desktop/package.json"
} else {
  Add-Check "Desktop product name" ($desktopPackage.build.productName -eq "Arceus Code") "blocker" "desktop/package.json build.productName"
  Add-Check "Desktop app id" ($desktopPackage.build.appId -eq "dev.arceus.code") "blocker" "desktop/package.json build.appId"
  Add-Check "Desktop version set" (-not [string]::IsNullOrWhiteSpace($desktopPackage.version)) "blocker" "desktop/package.json version"
  Add-Check "Windows NSIS target" ($desktopPackage.build.win.target -eq "nsis") "blocker" "desktop/package.json build.win.target"
  Add-Check "Desktop shortcut enabled" ($desktopPackage.build.nsis.createDesktopShortcut -eq $true) "blocker" "desktop/package.json build.nsis.createDesktopShortcut"
  Add-Check "Start Menu shortcut enabled" ($desktopPackage.build.nsis.createStartMenuShortcut -eq $true) "blocker" "desktop/package.json build.nsis.createStartMenuShortcut"
  Add-Check "Shortcut name set" ($desktopPackage.build.nsis.shortcutName -eq "Arceus Code") "warning" "desktop/package.json build.nsis.shortcutName"
  Add-Check "Release repo configured" ($desktopPackage.build.publish[0].owner -eq "amarreddy1432723-lang" -and $desktopPackage.build.publish[0].repo -eq "autonomus_ai") "blocker" "desktop/package.json build.publish"
}

Test-Text "desktop/main.js" "checkForUpdatesAndNotify" "Auto updater check is wired"
Test-Text "desktop/main.js" "desktop-install-update" "Restart and update IPC exists"
Test-Text "desktop/main.js" "desktop\.logs\.export" "Desktop diagnostics export IPC exists"
Test-Text "desktop/main.js" "render-process-gone" "Renderer crash marker is captured"
Test-Text "desktop/main.js" "unhandledRejection" "Main process rejection marker is captured"
Test-Text "desktop/main.js" "crashes" "Crash marker directory is used"
Test-Text "desktop/main.js" "arceus-desktop\.log" "Desktop log file is written"
Test-Text "desktop/main.js" "desktop-auth-session\.bin" "Desktop auth session is persisted"

Test-Text "desktop/preload.js" "exportLogs" "Renderer can call Export Logs"
Test-Text "desktop/preload.js" "desktop\.auth\.read" "Renderer can read desktop auth"
Test-Text "desktop/preload.js" "desktop\.auth\.write" "Renderer can write desktop auth"
Test-Text "desktop/preload.js" "desktop\.auth\.clear" "Renderer can clear desktop auth"
Test-Text "frontend/src/types/electron.d.ts" "exportLogs" "TypeScript desktop API includes Export Logs"

$requiredScripts = @(
  "scripts/verify-desktop-release.ps1",
  "scripts/verify-installed-product.ps1",
  "scripts/verify-desktop-isolation.ps1",
  "scripts/publish-desktop-release.ps1",
  "scripts/generate-release-download-env.ps1",
  "scripts/verify-prototype-p0.ps1",
  "scripts/verify-release-candidate.ps1",
  "scripts/full-verify.ps1"
)
foreach ($script in $requiredScripts) {
  Test-File $script "Release script exists: $script"
}

$requiredDocs = @(
  "docs/alpha-release.md",
  "docs/private-alpha-guide.md",
  "docs/known-issues.md",
  "docs/feedback.md",
  "docs/getting-started.md",
  "docs/distribution.md",
  "docs/desktop-qa-checklist.md",
  "docs/production-hardening.md"
)
foreach ($doc in $requiredDocs) {
  Test-File $doc "Alpha documentation exists: $doc"
}
Test-File "docs/releases/rc1-certification.md" "RC1 certification report exists"

Test-Text "docs/alpha-release.md" "Open an existing repository" "Alpha checklist covers repository open"
Test-Text "docs/alpha-release.md" "Undo changes" "Alpha checklist covers rollback"
Test-Text "docs/private-alpha-guide.md" "Export Diagnostics" "Tester guide covers diagnostics"
Test-Text "docs/known-issues.md" "Report Immediately" "Known issues document has escalation list"
Test-Text "docs/feedback.md" "What Not To Send" "Feedback guide protects sensitive data"

Test-File "frontend/src/app/download/page.tsx" "Download page exists"
Test-Text "frontend/src/app/download/page.tsx" "SHA-256|sha256|checksum" "Download page surfaces checksum"
Test-Text "frontend/src/app/download/page.tsx" "Installer pending release|Download" "Download page has installer state"
Test-File "frontend/src/app/launch/page.tsx" "Desktop launch page exists"
Test-File "frontend/src/app/onboarding/page.tsx" "Onboarding page exists"
Test-File "frontend/src/app/mission-control/page.tsx" "Mission Control page exists"
Test-Text "frontend/src/lib/frontendBoundaries.ts" "desktopCodeAlphaPrefixes" "Desktop Alpha route allowlist exists"
Test-Text "frontend/src/lib/frontendBoundaries.ts" "/mission-control" "Desktop Alpha route allowlist includes Mission Control"
Test-Text "frontend/src/components/DesktopCodeRouteGuard.tsx" "router\.replace\('/workspace'\)" "Desktop hidden routes recover to workspace"
Test-Text "desktop/main.js" "DESKTOP_CODE_ALLOWED_ROUTE_PREFIXES" "Electron native route allowlist exists"
Test-Text "desktop/main.js" "/mission-control" "Electron native route allowlist includes Mission Control"
Test-File "frontend/src/components/mission-control/MissionControlProductView.tsx" "Product Mission Control component exists"
Test-File "frontend/src/components/mission-control/DiffViewer.tsx" "Mission Control diff viewer exists"
Test-File "frontend/src/components/mission-control/ChangeSummary.tsx" "Mission Control change summary exists"
Test-File "frontend/src/components/mission-control/VerificationPanel.tsx" "Mission Control verification panel exists"
Test-File "frontend/src/components/mission-control/MissionReport.tsx" "Mission Control mission report exists"
Test-Text "frontend/src/components/mission-control/ChangeSummary.tsx" "Search changed files" "Patch review supports file search"
Test-Text "frontend/src/components/mission-control/ChangeSummary.tsx" "Filter by operation" "Patch review supports operation filters"
Test-Text "frontend/src/components/mission-control/ChangeSummary.tsx" "Filter by risk" "Patch review supports risk filters"
Test-Text "frontend/src/components/mission-control/DiffViewer.tsx" "Side by side" "Patch review supports side-by-side toggle"
Test-Text "frontend/src/components/mission-control/DiffViewer.tsx" "file-specific verification" "Patch review surfaces file verification context"
Test-Text "frontend/src/app/mission-control/page.tsx" "change-set/review" "Mission Control patch review buttons call backend mutation endpoint"
Test-Text "frontend/src/app/mission-control/page.tsx" "change-set/execute" "Mission Control apply and rollback buttons call backend filesystem executor"
Test-Text "frontend/src/app/mission-control/page.tsx" "workspace_root" "Mission Control passes trusted workspace root to filesystem executor"
Test-Text "backend/services/agent/arceus_runtime/evidence/routes.py" "change-set/review" "Backend change-set review endpoint exists"
Test-Text "backend/services/agent/arceus_runtime/evidence/routes.py" "review.complete" "Backend change-set review endpoint is permission-gated"
Test-Text "backend/services/agent/arceus_runtime/evidence/routes.py" "_normalize_change_set_content" "Backend normalizes worker change-set diffs"
Test-Text "backend/services/agent/arceus_runtime/evidence/routes.py" "change-set/execute" "Backend change-set filesystem executor endpoint exists"
Test-Text "backend/services/agent/arceus_runtime/evidence/routes.py" "tool.execute" "Backend filesystem executor is policy-gated"
Test-Text "backend/services/agent/arceus_runtime/evidence/routes.py" "CHANGE_SET_PATH_ESCAPE" "Backend filesystem executor blocks path escapes"
Test-Text "backend/services/agent/arceus_runtime/evidence/routes.py" "CHANGE_SET_HASH_MISMATCH" "Backend filesystem executor enforces stale-hash protection"
Test-Text "backend/services/agent/arceus_runtime/evidence/api_schemas.py" "apply_payload" "Backend change-set schema stores apply payloads"
Test-Text "backend/services/agent/arceus_runtime/evidence/api_schemas.py" "rollback_payload" "Backend change-set schema stores rollback payloads"
Test-Text "backend/services/agent/task_runtime/routes.py" "change_set: TaskChangeSetRequest" "Task runtime completion accepts inline change sets"
Test-Text "frontend/src/components/mission-control/MissionReport.tsx" "Markdown" "Mission report exports Markdown"
Test-Text "frontend/src/components/mission-control/MissionReport.tsx" "JSON" "Mission report exports JSON"
Test-Text "frontend/src/components/mission-control/MissionReport.tsx" "PDF" "Mission report supports PDF print export"

$externalSeverity = if ($StrictExternal) { "blocker" } else { "warning" }
Add-Check "Windows signing certificate configured" (-not [string]::IsNullOrWhiteSpace($env:WIN_CSC_LINK) -or -not [string]::IsNullOrWhiteSpace($env:WINDOWS_CERTIFICATE_SUBJECT_NAME)) $externalSeverity "Set WIN_CSC_LINK/WIN_CSC_KEY_PASSWORD or WINDOWS_CERTIFICATE_SUBJECT_NAME before public release."
Add-Check "Release download URL configured" (-not [string]::IsNullOrWhiteSpace($env:ARCEUS_DOWNLOAD_WINDOWS_X64_INSTALLER_URL)) $externalSeverity "Set ARCEUS_DOWNLOAD_WINDOWS_X64_INSTALLER_URL on hosted services."
Add-Check "Release checksum configured" (-not [string]::IsNullOrWhiteSpace($env:ARCEUS_DOWNLOAD_WINDOWS_X64_INSTALLER_SHA256)) $externalSeverity "Set ARCEUS_DOWNLOAD_WINDOWS_X64_INSTALLER_SHA256 on hosted services."
Add-Check "Arceus auth JWT secret configured" (-not [string]::IsNullOrWhiteSpace($env:JWT_SECRET) -or -not [string]::IsNullOrWhiteSpace($env:JWT_SECRET_KEY)) $externalSeverity "Set JWT_SECRET or JWT_SECRET_KEY for first-party auth."
Add-Check "Backend Sentry DSN configured" (-not [string]::IsNullOrWhiteSpace($env:SENTRY_DSN)) $externalSeverity "Set SENTRY_DSN for backend crash reporting."
Add-Check "Frontend Sentry DSN configured" (-not [string]::IsNullOrWhiteSpace($env:NEXT_PUBLIC_SENTRY_DSN)) $externalSeverity "Set NEXT_PUBLIC_SENTRY_DSN for browser crash reporting."

$summaryDir = Split-Path -Parent $SummaryPath
if ($summaryDir) {
  New-Item -ItemType Directory -Force -Path $summaryDir | Out-Null
}

$blockers = @($checks | Where-Object { -not $_.ok -and $_.severity -eq "blocker" })
$warnings = @($checks | Where-Object { -not $_.ok -and $_.severity -eq "warning" })
$status = if ($blockers.Count -gt 0) { "blocked" } elseif ($warnings.Count -gt 0) { "warnings" } else { "ready" }

$summary = [pscustomobject]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  status = $status
  blockers = $blockers.Count
  warnings = $warnings.Count
  strict_external = [bool]$StrictExternal
  checks = $checks
}

$checks | Format-Table -AutoSize
$summary | ConvertTo-Json -Depth 6 | Set-Content -Path $SummaryPath -Encoding UTF8
Write-Host "Summary written to $SummaryPath" -ForegroundColor Green

if ($blockers.Count -gt 0) {
  throw "Alpha release verification failed: $($blockers.Count) blocker(s), $($warnings.Count) warning(s)."
}

if ($warnings.Count -gt 0) {
  Write-Host "Alpha release verification completed with $($warnings.Count) warning(s)." -ForegroundColor Yellow
} else {
  Write-Host "Alpha release verification passed." -ForegroundColor Green
}
