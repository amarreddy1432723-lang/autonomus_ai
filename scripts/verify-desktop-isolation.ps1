param(
  [string]$RepoRoot,
  [string]$FrontendUrl = $env:SMOKE_FRONTEND_URL,
  [string]$SummaryPath,
  [switch]$CheckHosted
)

$ErrorActionPreference = "Stop"
if (-not $RepoRoot) { $RepoRoot = Split-Path -Parent $PSScriptRoot }
if (-not $SummaryPath) { $SummaryPath = Join-Path $RepoRoot ".verify\desktop-isolation-summary.json" }

$allowedRoutes = @(
  "/launch",
  "/onboarding",
  "/workspace",
  "/mission-control",
  "/settings",
  "/auth/desktop",
  "/download"
)

$hiddenRoutes = @(
  "/admin",
  "/hub",
  "/pa",
  "/interview",
  "/marketplace",
  "/memory",
  "/goals",
  "/timeline",
  "/dashboard",
  "/products",
  "/pricing",
  "/docs",
  "/ui-preview"
)

$checks = New-Object System.Collections.Generic.List[object]

function Add-Check {
  param(
    [string]$Name,
    [bool]$Ok,
    [string]$Severity,
    [string]$Detail
  )
  $script:checks.Add([pscustomobject]@{
    name = $Name
    ok = [bool]$Ok
    severity = if ($Ok) { "ok" } else { $Severity }
    detail = $Detail
  }) | Out-Null
}

function Read-RepoFile {
  param([string]$RelativePath)
  $path = Join-Path $RepoRoot $RelativePath
  if (-not (Test-Path $path)) {
    throw "Missing $RelativePath"
  }
  return Get-Content $path -Raw
}

function Get-ArrayBlock {
  param(
    [string]$Content,
    [string]$ArrayName
  )
  $pattern = "(?s)$([regex]::Escape($ArrayName))\s*=\s*\[(.*?)\]"
  $match = [regex]::Match($Content, $pattern)
  if (-not $match.Success) {
    throw "Could not find array $ArrayName"
  }
  return $match.Groups[1].Value
}

function Assert-ContainsAll {
  param(
    [string]$Name,
    [string]$Content,
    [string[]]$Values
  )
  $missing = @($Values | Where-Object { $Content -notmatch [regex]::Escape($_) })
  Add-Check $Name ($missing.Count -eq 0) "blocker" $(if ($missing.Count -eq 0) { "All required routes are present." } else { "Missing: $($missing -join ', ')" })
}

function Assert-ContainsNone {
  param(
    [string]$Name,
    [string]$Content,
    [string[]]$Values
  )
  $found = @($Values | Where-Object { $Content -match [regex]::Escape($_) })
  Add-Check $Name ($found.Count -eq 0) "blocker" $(if ($found.Count -eq 0) { "No hidden routes or legacy labels found." } else { "Found: $($found -join ', ')" })
}

function Invoke-HttpOk {
  param([string]$Uri)
  $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 20
  return ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400)
}

Write-Host "Desktop isolation verification" -ForegroundColor Cyan

$boundaries = Read-RepoFile "frontend\src\lib\frontendBoundaries.ts"
$desktopPrefixes = Get-ArrayBlock $boundaries "desktopCodeAlphaPrefixes"
Assert-ContainsAll "Frontend desktop allowlist contains only Alpha routes" $desktopPrefixes $allowedRoutes
Assert-ContainsNone "Frontend desktop allowlist hides legacy routes" $desktopPrefixes $hiddenRoutes
Add-Check "UI preview is dev-gated" ($boundaries -match "NEXT_PUBLIC_ENABLE_UI_PREVIEWS" -and $boundaries -match "desktopAllowed:\s*false\s*},\s*\r?\n?\s*];") "blocker" "ui-preview must not be production desktop navigation."

$desktopMain = Read-RepoFile "desktop\main.js"
$nativeAllowlist = Get-ArrayBlock $desktopMain "DESKTOP_CODE_ALLOWED_ROUTE_PREFIXES"
Assert-ContainsAll "Electron native allowlist contains Alpha routes" $nativeAllowlist $allowedRoutes
Assert-ContainsNone "Electron native allowlist hides legacy routes" $nativeAllowlist $hiddenRoutes
Add-Check "Electron startup defaults to launch" ($desktopMain -match 'DEFAULT_ROUTE\s*=.*"/launch"') "blocker" "Desktop should enter the Alpha launch flow."

$guard = Read-RepoFile "frontend\src\components\DesktopCodeRouteGuard.tsx"
Add-Check "Desktop route guard redirects hidden routes to workspace" ($guard -match "router\.replace\('/workspace'\)") "blocker" "Hidden desktop routes should recover to /workspace."

$appShell = Read-RepoFile "frontend\src\components\AppShell.tsx"
Add-Check "AppShell redirects hidden desktop routes to workspace" ($appShell -match "router\.replace\('/workspace'\)") "blocker" "AppShell route recovery should use /workspace."
Add-Check "Electron logo opens workspace" ($appShell -match "Open Arceus Code workspace" -and $appShell -match "router\.push\('/workspace'\)") "blocker" "Logo should not open a product switcher in Electron."
Add-Check "Electron sidebar uses Code-only labels" ($appShell -match "Workspace" -and $appShell -match "Mission Control" -and $appShell -match "Settings") "blocker" "Desktop sidebar must expose the three Alpha surfaces."

$activityBar = Read-RepoFile "frontend\src\components\workspace\ActivityBar.tsx"
$legacyVisibleLabels = @(
  "E-commerce Platform",
  "AI SaaS Starter",
  "HealthCare App",
  "FinTrack Dashboard",
  "New Project",
  "Marketplace",
  "Memory",
  "Goals",
  "Timeline",
  "Product Hub",
  "Arceus PA",
  "Arceus Interview",
  "Arjun Reddy",
  "Pro Plan"
)
Assert-ContainsNone "Workspace activity rail removes placeholder/legacy navigation" $activityBar $legacyVisibleLabels
Assert-ContainsAll "Workspace activity rail exposes Alpha shell labels" $activityBar @("Workspace", "Mission Control", "Settings", "Account", "Version", "Connected")

if ($CheckHosted) {
  if (-not $FrontendUrl) { $FrontendUrl = "http://localhost:3000" }
  foreach ($route in $allowedRoutes) {
    $ok = Invoke-HttpOk "$FrontendUrl$route"
    Add-Check "Hosted allowed route loads: $route" $ok "blocker" "$FrontendUrl$route"
  }
}

$summaryDir = Split-Path -Parent $SummaryPath
if ($summaryDir) {
  New-Item -ItemType Directory -Force -Path $summaryDir | Out-Null
}

$blockers = @($checks | Where-Object { -not $_.ok -and $_.severity -eq "blocker" })
$warnings = @($checks | Where-Object { -not $_.ok -and $_.severity -eq "warning" })
$summary = [pscustomobject]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  status = if ($blockers.Count -gt 0) { "blocked" } elseif ($warnings.Count -gt 0) { "warnings" } else { "ready" }
  blockers = $blockers.Count
  warnings = $warnings.Count
  allowed_routes = $allowedRoutes
  hidden_routes = $hiddenRoutes
  checks = $checks
}

$checks | Format-Table -AutoSize
$summary | ConvertTo-Json -Depth 6 | Set-Content -Path $SummaryPath -Encoding UTF8
Write-Host "Summary written to $SummaryPath" -ForegroundColor Green

if ($blockers.Count -gt 0) {
  throw "Desktop isolation verification failed: $($blockers.Count) blocker(s), $($warnings.Count) warning(s)."
}

Write-Host "Desktop isolation verification passed." -ForegroundColor Green
