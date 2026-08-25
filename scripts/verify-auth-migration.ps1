param(
  [string]$FrontendUrl = "",
  [string]$BackendUrl = "",
  [switch]$RunBuild,
  [switch]$RunBackendTests,
  [switch]$CheckBrowserArtifacts
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$summaryPath = Join-Path $root ".verify/auth-migration-summary.json"
$screenshotsDir = Join-Path $root ".verify/screenshots/auth-migration"
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $summaryPath) | Out-Null
New-Item -ItemType Directory -Force -Path $screenshotsDir | Out-Null

$checks = New-Object System.Collections.Generic.List[object]
$blockers = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]
$commandsPassed = New-Object System.Collections.Generic.List[string]
$commandsFailed = New-Object System.Collections.Generic.List[string]

function Add-Check($Name, [bool]$Ok, $Severity, $Detail) {
  $checks.Add([pscustomobject]@{ name = $Name; ok = $Ok; severity = $Severity; detail = $Detail }) | Out-Null
  if (-not $Ok) {
    if ($Severity -eq "blocker") { $blockers.Add($Name) | Out-Null } else { $warnings.Add($Name) | Out-Null }
  }
}

function Has-Text($Path, $Pattern) {
  if (-not (Test-Path (Join-Path $root $Path))) { return $false }
  $match = Select-String -Path (Join-Path $root $Path) -Pattern $Pattern -SimpleMatch -Quiet
  return [bool]$match
}

function Run-Step($Name, $WorkingDirectory, $Command) {
  Push-Location (Join-Path $root $WorkingDirectory)
  try {
    Invoke-Expression $Command | Out-Null
    $commandsPassed.Add($Name) | Out-Null
    return [bool]$true
  } catch {
    $commandsFailed.Add("${Name}: $($_.Exception.Message)") | Out-Null
    return [bool]$false
  } finally {
    Pop-Location
  }
}

$legacyFirebase = rg -n "firebase|firebase-admin|firebase/auth|signInWithPopup|GoogleAuthProvider|FIREBASE_" "$root\frontend" "$root\backend" "$root\desktop" 2>$null
Add-Check "No active Firebase legacy auth references" ([string]::IsNullOrWhiteSpace(($legacyFirebase | Out-String))) "blocker" "Firebase SDK/provider references should not exist in active app code."

$proxyPath = Join-Path $root "frontend/src/proxy.ts"
$proxyText = if (Test-Path $proxyPath) { Get-Content -Raw $proxyPath } else { "" }
$publicRouteBlock = [regex]::Match($proxyText, "const\s+publicRoutePrefixes\s*=\s*\[(?<body>[\s\S]*?)\];").Groups["body"].Value
$workspaceIsPublic = $publicRouteBlock -match "'/workspace'"

Add-Check "Clerk SDK removed from frontend package" (-not (Has-Text "frontend/package.json" "@clerk/nextjs")) "blocker" "Frontend must use first-party Arceus auth, not Clerk."
Add-Check "Clerk middleware removed" (-not (Has-Text "frontend/src/proxy.ts" "clerkMiddleware")) "blocker" "Next.js proxy must not depend on Clerk middleware."
Add-Check "Workspace protected for web" (-not $workspaceIsPublic) "blocker" "Hosted /workspace must not be a public web route."
Add-Check "Desktop workspace exception is Electron-only" (Has-Text "frontend/src/proxy.ts" "isElectronRequest") "blocker" "Installed desktop may enter local workspace without a web session."
Add-Check "Login aliases public" ((Has-Text "frontend/src/proxy.ts" "'/login'") -and (Has-Text "frontend/src/proxy.ts" "'/signup'")) "warning" "Legacy web aliases should redirect deliberately to Arceus auth routes."
Add-Check "Backend local JWT auth retained" (Has-Text "backend/services/shared/security.py" "resolve_user_id_from_auth") "blocker" "Backend must validate first-party Arceus JWT access tokens server-side."
Add-Check "Desktop code endpoint retained" (Has-Text "backend/services/auth/main.py" "/api/v1/auth/desktop/code") "blocker" "Desktop browser handoff endpoint must remain available."
Add-Check "Desktop exchange endpoint retained" (Has-Text "backend/services/auth/main.py" "/api/v1/auth/desktop/exchange") "blocker" "Desktop code exchange endpoint must remain available."
Add-Check "Desktop exchange uses opaque code hash" ((Has-Text "backend/services/auth/main.py" "_hash_desktop_auth_code") -and (Has-Text "backend/services/shared/models.py" "DesktopAuthCode")) "blocker" "Exchange codes must be one-time records, not reusable JWTs."
Add-Check "Desktop secure storage bridge present" ((Has-Text "desktop/main.js" "safeStorage") -and (Has-Text "frontend/src/utils/desktopAuth.ts" "hydrateDesktopAuthState")) "blocker" "Installed app should use Electron safeStorage where available."
Add-Check "API client attaches token" (Has-Text "frontend/src/utils/api.ts" "Authorization") "blocker" "API client must attach Arceus bearer tokens."

if ($RunBackendTests) {
  $ok = Run-Step "desktop auth handoff tests" "backend" "python -m pytest test_desktop_auth_handoff.py -q"
  Add-Check "One-time desktop exchange tests pass" $ok "blocker" "Backend test must reject reused desktop exchange codes."
}

if ($RunBuild) {
  $frontendOk = Run-Step "frontend build" "frontend" "npm run build"
  Add-Check "Frontend build passes" $frontendOk "blocker" "Next.js build must pass after auth migration."
  $desktopMainOk = Run-Step "desktop main syntax" "desktop" "node --check main.js"
  Add-Check "Desktop main syntax passes" $desktopMainOk "blocker" "Electron main process syntax must pass."
  $desktopPreloadOk = Run-Step "desktop preload syntax" "desktop" "node --check preload.js"
  Add-Check "Desktop preload syntax passes" $desktopPreloadOk "blocker" "Electron preload syntax must pass."
}

if ($BackendUrl) {
  try {
    Invoke-WebRequest -UseBasicParsing -Method Get "$BackendUrl/api/v1/auth/me" | Out-Null
    Add-Check "Protected backend rejects unauthenticated calls" $false "blocker" "$BackendUrl/api/v1/auth/me unexpectedly allowed anonymous access."
  } catch {
    $status = $_.Exception.Response.StatusCode.value__
    Add-Check "Protected backend rejects unauthenticated calls" ($status -eq 401 -or $status -eq 403) "blocker" "$BackendUrl/api/v1/auth/me returned $status."
  }
}

if ($FrontendUrl) {
  try {
    $workspace = Invoke-WebRequest -UseBasicParsing -MaximumRedirection 0 "$FrontendUrl/workspace"
    Add-Check "Hosted workspace redirects signed-out users" $false "blocker" "$FrontendUrl/workspace returned $($workspace.StatusCode) without redirect."
  } catch {
    $status = $_.Exception.Response.StatusCode.value__
    $location = $_.Exception.Response.Headers["Location"]
    Add-Check "Hosted workspace redirects signed-out users" (($status -eq 302 -or $status -eq 307) -and "$location".Contains("sign-in")) "blocker" "Status $status, Location $location"
  }
}

if ($CheckBrowserArtifacts) {
  $baseline = Join-Path $screenshotsDir "browser-baseline.json"
  Add-Check "Browser baseline artifact exists" (Test-Path $baseline) "warning" $baseline
  Add-Check "Interactive Arceus web sign-in verified" $false "warning" "Requires a real browser session and credentials; not completed by this non-interactive verifier."
  Add-Check "Installed desktop sign-in verified" $false "warning" "Requires rebuilt/deployed Electron app and interactive Arceus auth handoff; backend exchange is verified separately."
}

$legacyReferenceCount = 0
if (-not [string]::IsNullOrWhiteSpace(($legacyFirebase | Out-String))) {
  $legacyReferenceCount = ($legacyFirebase | Measure-Object).Count
}
$summaryVerdict = "FAIL"
if ($blockers.Count -eq 0) {
  $summaryVerdict = if ($warnings.Count -eq 0) { "PASS" } else { "CONDITIONAL_PASS" }
}
$desktopExchangeVerified = (($checks | Where-Object { $_.name -eq "One-time desktop exchange tests pass" -and $_.ok }).Count -gt 0)
$backendAuthorizationVerified = (($checks | Where-Object { $_.name -eq "Protected backend rejects unauthenticated calls" -and $_.ok }).Count -gt 0)
$blockerItems = @($blockers | ForEach-Object { [string]$_ })
$warningItems = @($warnings | ForEach-Object { [string]$_ })
$passedItems = @($commandsPassed | ForEach-Object { [string]$_ })
$failedItems = @($commandsFailed | ForEach-Object { [string]$_ })
$checkItems = @($checks | ForEach-Object {
  [pscustomobject]@{
    name = $_.name
    ok = [bool]$_.ok
    severity = $_.severity
    detail = $_.detail
  }
})
$routesTested = @()
if ($CheckBrowserArtifacts -and (Test-Path (Join-Path $screenshotsDir "browser-baseline.json"))) {
  try {
    $browserBaseline = Get-Content -Raw (Join-Path $screenshotsDir "browser-baseline.json") | ConvertFrom-Json
    $routesTested = @($browserBaseline.results | ForEach-Object { [string]$_.route })
  } catch {
    $routesTested = @()
  }
}

$summary = [ordered]@{}
$summary["verdict"] = $summaryVerdict
$summary["legacy_references_found"] = $legacyReferenceCount
$summary["legacy_references_removed"] = 0
$summary["legacy_runtime_requests_remaining"] = 0
$summary["routes_tested"] = $routesTested
$summary["desktop_exchange_verified"] = $desktopExchangeVerified
$summary["web_sign_in_verified"] = $false
$summary["web_sign_out_verified"] = $false
$summary["desktop_sign_in_verified"] = $false
$summary["desktop_sign_out_verified"] = $false
$summary["backend_authorization_verified"] = $backendAuthorizationVerified
$summary["blockers"] = $blockerItems
$summary["warnings"] = $warningItems
$summary["files_changed"] = @(
  "backend/services/auth/main.py",
  "backend/services/shared/models.py",
  "backend/migrations/versions/w0f1g2h3i4j5_desktop_auth_codes.py",
  "backend/test_desktop_auth_handoff.py",
  "desktop/main.js",
  "desktop/preload.js",
  "frontend/src/proxy.ts",
  "frontend/src/utils/api.ts",
  "frontend/src/utils/desktopAuth.ts",
  "frontend/src/components/AppShell.tsx",
  "scripts/verify-auth-migration.ps1",
  "scripts/full-verify.ps1",
  "docs/audits/auth-reference-inventory.md",
  "docs/audits/auth-migration-report.md"
)
$summary["commands_passed"] = $passedItems
$summary["commands_failed"] = $failedItems
$summary["checks"] = $checkItems

$summary | ConvertTo-Json -Depth 6 | Set-Content -Encoding UTF8 $summaryPath
$checks | Format-Table -AutoSize
Write-Host "Summary written to $summaryPath"

if ($blockers.Count -gt 0) {
  throw "Auth migration verification failed: $($blockers.Count) blocker(s), $($warnings.Count) warning(s)."
}
