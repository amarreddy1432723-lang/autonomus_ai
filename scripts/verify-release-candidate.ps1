param(
  [string]$BuildVersion = $(if ($env:ARCEUS_RELEASE_VERSION) { $env:ARCEUS_RELEASE_VERSION } else { "0.1.0-alpha" }),
  [string]$InstallerPath = $(Join-Path (Split-Path -Parent $PSScriptRoot) "desktop\dist\Arceus Code-1.0.0-Setup.exe"),
  [string]$HostedFrontendUrl = $(if ($env:SMOKE_FRONTEND_URL) { $env:SMOKE_FRONTEND_URL } else { "https://frontend-production-fbde.up.railway.app" }),
  [string]$HostedBackendUrl = $(if ($env:SMOKE_BACKEND_URL) { $env:SMOKE_BACKEND_URL } else { "https://agent-production-8568.up.railway.app" }),
  [string]$AuthBackendUrl = $(if ($env:SMOKE_AUTH_URL) { $env:SMOKE_AUTH_URL } else { "https://auth-production-dae4.up.railway.app" }),
  [string]$RuntimeFrontendUrl = $(if ($env:RC_RUNTIME_FRONTEND_URL) { $env:RC_RUNTIME_FRONTEND_URL } else { $HostedFrontendUrl }),
  [string]$RuntimeBackendUrl = $(if ($env:RC_RUNTIME_BACKEND_URL) { $env:RC_RUNTIME_BACKEND_URL } else { "http://127.0.0.1:8003" }),
  [string]$SummaryPath = $(Join-Path (Split-Path -Parent $PSScriptRoot) ".verify\release-candidate-summary.json"),
  [string]$ReportPath = $(Join-Path (Split-Path -Parent $PSScriptRoot) "docs\releases\rc1-certification.md"),
  [switch]$StartLocalRuntime,
  [switch]$SkipInstall,
  [switch]$SkipDesktopLaunch,
  [switch]$SkipLiveMission,
  [switch]$KeepDesktopRunning,
  [switch]$StrictExternal
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$startedAt = Get-Date
$checks = New-Object System.Collections.Generic.List[object]
$phases = New-Object System.Collections.Generic.List[object]
$artifacts = New-Object System.Collections.Generic.List[object]
$localRuntimeProcess = $null

function Add-Check {
  param(
    [string]$Phase,
    [string]$Name,
    [bool]$Ok,
    [string]$Severity,
    [string]$Detail
  )
  $script:checks.Add([pscustomobject]@{
    phase = $Phase
    name = $Name
    ok = [bool]$Ok
    severity = if ($Ok) { "ok" } else { $Severity }
    detail = $Detail
  }) | Out-Null
}

function Add-Artifact {
  param([string]$Kind, [string]$Path, [string]$Description)
  if (-not [string]::IsNullOrWhiteSpace($Path) -and (Test-Path $Path)) {
    $script:artifacts.Add([pscustomobject]@{
      kind = $Kind
      path = (Resolve-Path $Path).Path
      description = $Description
    }) | Out-Null
  }
}

function Add-Phase {
  param(
    [string]$Name,
    [string]$Status,
    [double]$Seconds,
    [string]$Detail = ""
  )
  $script:phases.Add([pscustomobject]@{
    name = $Name
    status = $Status
    seconds = [math]::Round($Seconds, 2)
    detail = $Detail
  }) | Out-Null
}

function Invoke-Phase {
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
    Add-Phase $Name "PASS" $timer.Elapsed.TotalSeconds
    Write-Host "PASS: $Name" -ForegroundColor Green
  } catch {
    $timer.Stop()
    $message = $_.Exception.Message
    if ($Optional) {
      Add-Phase $Name "WARN" $timer.Elapsed.TotalSeconds $message
      Add-Check $Name $Name $false "warning" $message
      Write-Warning "$Name warning: $message"
      return
    }
    Add-Phase $Name "FAIL" $timer.Elapsed.TotalSeconds $message
    Add-Check $Name $Name $false "blocker" $message
    Write-Host "$Name failed: $message" -ForegroundColor Red
  }
}

function Test-Http {
  param([string]$Uri, [int]$TimeoutSec = 25)
  try {
    $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec $TimeoutSec
    return @{ ok = ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400); detail = "$($response.StatusCode) $($response.StatusDescription)"; content = $response.Content }
  } catch {
    return @{ ok = $false; detail = $_.Exception.Message; content = "" }
  }
}

function Wait-HttpReady {
  param(
    [string]$Uri,
    [int]$TimeoutSeconds = 60
  )
  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  do {
    $result = Test-Http $Uri 5
    if ($result.ok) { return $true }
    Start-Sleep -Seconds 2
  } while ((Get-Date) -lt $deadline)
  return $false
}

function Start-LocalRuntimeIfRequested {
  if (-not $StartLocalRuntime) { return }
  $ready = Test-Http "$RuntimeBackendUrl/api/v1/health" 5
  if ($ready.ok) {
    Add-Check "Local runtime startup" "Agent runtime already reachable" $true "ok" "$RuntimeBackendUrl/api/v1/health - $($ready.detail)"
    return
  }

  Push-Location $repoRoot
  try {
    docker compose up -d postgres redis | Out-Host
  } finally {
    Pop-Location
  }

  $backendDir = Join-Path $repoRoot "backend"
  $command = @(
    '$env:ALLOW_DEV_AUTH_FALLBACK="true";',
    '$env:ALLOW_DEMO_USER="true";',
    '$env:NEXT_PUBLIC_REQUIRE_AUTH="false";',
    'python -m uvicorn services.agent.main:app --host 127.0.0.1 --port 8003'
  ) -join " "
  $script:localRuntimeProcess = Start-Process `
    -FilePath "powershell" `
    -ArgumentList "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $command `
    -WorkingDirectory $backendDir `
    -WindowStyle Hidden `
    -PassThru

  $started = Wait-HttpReady "$RuntimeBackendUrl/api/v1/health" 90
  Add-Check "Local runtime startup" "Agent runtime started" $started "blocker" "pid=$($script:localRuntimeProcess.Id); url=$RuntimeBackendUrl"
  if (-not $started) {
    throw "Local agent runtime did not become healthy at $RuntimeBackendUrl."
  }
}

function Stop-LocalRuntimeIfStarted {
  if ($null -eq $script:localRuntimeProcess) { return }
  try {
    $process = Get-Process -Id $script:localRuntimeProcess.Id -ErrorAction SilentlyContinue
    if ($process) {
      Stop-Process -Id $process.Id -Force -ErrorAction SilentlyContinue
      Add-Check "Local runtime cleanup" "Started local runtime stopped" $true "ok" "pid=$($process.Id)"
    }
  } catch {
    Add-Check "Local runtime cleanup" "Started local runtime stopped" $false "warning" $_.Exception.Message
  }
}

function Read-SummaryChecks {
  param([string]$Path)
  if (-not (Test-Path $Path)) { return @() }
  try {
    $json = Get-Content $Path -Raw | ConvertFrom-Json
    if ($json.checks) { return @($json.checks) }
    if ($json.results) { return @($json.results) }
    return @()
  } catch {
    return @()
  }
}

function Require-SubSummary {
  param(
    [string]$Phase,
    [string]$Path
  )
  if (-not (Test-Path $Path)) {
    Add-Check $Phase "Summary exists" $false "blocker" $Path
    throw "Expected summary was not written: $Path"
  }
  Add-Artifact "summary" $Path "$Phase summary"
  $summaryChecks = Read-SummaryChecks $Path
  $failed = @($summaryChecks | Where-Object {
    ($_.ok -eq $false -and $_.severity -eq "blocker") -or ($_.Status -eq "FAILED")
  })
  Add-Check $Phase "Summary has no blocker failures" ($failed.Count -eq 0) "blocker" "$($failed.Count) blocker failure(s) in $Path"
  if ($failed.Count -gt 0) {
    throw "$Phase summary has $($failed.Count) blocker failure(s)."
  }
}

function Write-CertificationReport {
  param([string]$Path)
  $blockers = @($script:checks | Where-Object { -not $_.ok -and $_.severity -eq "blocker" })
  $warnings = @($script:checks | Where-Object { -not $_.ok -and $_.severity -eq "warning" })
  $status = if ($blockers.Count -gt 0) { "NO-GO" } elseif ($warnings.Count -gt 0) { "PASS WITH WARNINGS" } else { "PASS" }
  $elapsed = (Get-Date) - $script:startedAt

  $lines = New-Object System.Collections.Generic.List[string]
  $lines.Add("# Arceus RC1 Certification") | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add("| Field | Value |") | Out-Null
  $lines.Add("| --- | --- |") | Out-Null
  $lines.Add("| Build | $BuildVersion |") | Out-Null
  $lines.Add("| Overall | $status |") | Out-Null
  $lines.Add("| Generated | $((Get-Date).ToUniversalTime().ToString("o")) |") | Out-Null
  $lines.Add("| Hosted Frontend | $HostedFrontendUrl |") | Out-Null
  $lines.Add("| Hosted Backend | $HostedBackendUrl |") | Out-Null
  $lines.Add("| Auth Backend | $AuthBackendUrl |") | Out-Null
  $lines.Add("| Runtime Frontend | $RuntimeFrontendUrl |") | Out-Null
  $lines.Add("| Runtime Backend | $RuntimeBackendUrl |") | Out-Null
  $lines.Add("| Duration | $([math]::Round($elapsed.TotalSeconds, 2)) seconds |") | Out-Null
  $lines.Add("| Blockers | $($blockers.Count) |") | Out-Null
  $lines.Add("| Warnings | $($warnings.Count) |") | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add("## Phase Results") | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add("| Phase | Status | Seconds | Detail |") | Out-Null
  $lines.Add("| --- | --- | ---: | --- |") | Out-Null
  foreach ($phase in $script:phases) {
    $detail = ($phase.detail -replace "\|", "/" -replace "`r?`n", " ")
    $lines.Add("| $($phase.name) | $($phase.status) | $($phase.seconds) | $detail |") | Out-Null
  }
  $lines.Add("") | Out-Null
  $lines.Add("## Certification Checks") | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add("| Phase | Check | Status | Severity | Detail |") | Out-Null
  $lines.Add("| --- | --- | --- | --- | --- |") | Out-Null
  foreach ($check in $script:checks) {
    $checkStatus = if ($check.ok) { "PASS" } else { "FAIL" }
    $detail = ($check.detail -replace "\|", "/" -replace "`r?`n", " ")
    $lines.Add("| $($check.phase) | $($check.name) | $checkStatus | $($check.severity) | $detail |") | Out-Null
  }
  $lines.Add("") | Out-Null
  $lines.Add("## Artifacts") | Out-Null
  $lines.Add("") | Out-Null
  if ($script:artifacts.Count -eq 0) {
    $lines.Add("No artifacts were produced.") | Out-Null
  } else {
    foreach ($artifact in $script:artifacts) {
      $lines.Add("- $($artifact.kind): $($artifact.path) - $($artifact.description)") | Out-Null
    }
  }
  $lines.Add("") | Out-Null
  $lines.Add("## Exit Criteria") | Out-Null
  $lines.Add("") | Out-Null
  $lines.Add("- Packaged Windows application completes the release flow.") | Out-Null
  $lines.Add("- Hosted control plane is reachable.") | Out-Null
  $lines.Add("- Repository analysis, mission compilation, scheduler, worker, evidence, change-set, apply, rollback, and recovery proofs pass.") | Out-Null
  $lines.Add("- Desktop Alpha route isolation remains enforced.") | Out-Null

  $dir = Split-Path -Parent $Path
  if ($dir) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
  $lines -join [Environment]::NewLine | Set-Content -Path $Path -Encoding UTF8
  Add-Artifact "report" $Path "RC1 certification report"
}

Write-Host "Arceus RC1.2 installed product certification" -ForegroundColor Cyan

Invoke-Phase "Website and download" {
  $download = Test-Http "$HostedFrontendUrl/download"
  Add-Check "Website and download" "Download page reachable" $download.ok "blocker" "$HostedFrontendUrl/download - $($download.detail)"
  if (-not $download.ok) { throw "Download page is not reachable." }

  $manifest = Test-Http "$HostedBackendUrl/api/v1/downloads/latest"
  Add-Check "Website and download" "Download manifest reachable" $manifest.ok "blocker" "$HostedBackendUrl/api/v1/downloads/latest - $($manifest.detail)"
  if (-not $manifest.ok) { throw "Download manifest is not reachable." }

  $manifestJson = $manifest.content | ConvertFrom-Json
  $windows = @($manifestJson.downloads.windows)[0]
  $available = $windows.available -eq $true -and -not [string]::IsNullOrWhiteSpace($windows.url)
  Add-Check "Website and download" "Windows installer available in manifest" $available "blocker" "$(if ($windows) { $windows.url } else { "missing windows manifest" })"
  if (-not $available) { throw "Windows installer is not available in the hosted manifest." }
}

Invoke-Phase "Alpha readiness surface" {
  $alphaSummary = Join-Path $repoRoot ".verify\rc-alpha-release-summary.json"
  Push-Location $repoRoot
  .\scripts\verify-alpha-release.ps1 -SummaryPath $alphaSummary -StrictExternal:$StrictExternal
  Pop-Location
  Require-SubSummary "Alpha readiness surface" $alphaSummary
}

Invoke-Phase "Desktop route isolation" {
  $isolationSummary = Join-Path $repoRoot ".verify\rc-desktop-isolation-summary.json"
  Push-Location $repoRoot
  .\scripts\verify-desktop-isolation.ps1 -FrontendUrl $HostedFrontendUrl -SummaryPath $isolationSummary -CheckHosted
  Pop-Location
  Require-SubSummary "Desktop route isolation" $isolationSummary
}

Invoke-Phase "Installation and launch" {
  if ($SkipDesktopLaunch) {
    Add-Check "Installation and launch" "Installed desktop launch executed" $false "blocker" "Skipped by -SkipDesktopLaunch."
    throw "Desktop launch was skipped. RC1.2 certification requires the installed app."
  }
  $installedSummary = Join-Path $repoRoot ".verify\rc-installed-product-summary.json"
  Push-Location $repoRoot
  .\scripts\verify-installed-product.ps1 `
    -InstallerPath $InstallerPath `
    -BackendUrl $HostedBackendUrl `
    -FrontendUrl $HostedFrontendUrl `
    -OutputPath $installedSummary `
    -SkipInstall:$SkipInstall `
    -KeepRunning:$KeepDesktopRunning `
    -Strict
  Pop-Location
  Require-SubSummary "Installation and launch" $installedSummary
}

Invoke-Phase "Authentication surface" {
  $signIn = Test-Http "$HostedFrontendUrl/sign-in"
  Add-Check "Authentication surface" "Sign-in page reachable" $signIn.ok "blocker" "$HostedFrontendUrl/sign-in - $($signIn.detail)"
  $signUp = Test-Http "$HostedFrontendUrl/sign-up"
  Add-Check "Authentication surface" "Sign-up page reachable" $signUp.ok "blocker" "$HostedFrontendUrl/sign-up - $($signUp.detail)"
  $authReject = Test-Http "$AuthBackendUrl/api/v1/auth/me"
  $rejects = -not $authReject.ok -or $authReject.detail -match "401|403"
  Add-Check "Authentication surface" "Protected auth API rejects missing token" $rejects "blocker" "$AuthBackendUrl/api/v1/auth/me - $($authReject.detail)"
  if (-not ($signIn.ok -and $signUp.ok -and $rejects)) { throw "Authentication surface is not ready." }
}

Invoke-Phase "Repository to runtime proof" {
  if ($SkipLiveMission) {
    Add-Check "Repository to runtime proof" "Live mission proof executed" $false "blocker" "Skipped by -SkipLiveMission."
    throw "Live mission proof was skipped. RC1.2 certification requires repository -> mission -> worker -> rollback proof."
  }
  Start-LocalRuntimeIfRequested
  $coreSummary = Join-Path $repoRoot ".verify\rc-core-loop-summary.json"
  Push-Location $repoRoot
  .\scripts\verify-core-loop.ps1 -BackendUrl $RuntimeBackendUrl -FrontendUrl $RuntimeFrontendUrl -SummaryPath $coreSummary -StartDockerDeps:$StartLocalRuntime -Strict
  Pop-Location
  Require-SubSummary "Repository to runtime proof" $coreSummary
}

Invoke-Phase "Recovery proof" {
  Push-Location $repoRoot
  $raw = node scripts\verify-interrupted-execution-recovery.js
  Pop-Location
  $payload = $raw | ConvertFrom-Json
  $failed = @($payload.checks | Where-Object { -not $_.ok })
  Add-Check "Recovery proof" "Interrupted execution recovery checks pass" ($payload.ok -eq $true -and $failed.Count -eq 0) "blocker" "checks=$(@($payload.checks).Count); failed=$($failed.Count)"
  if ($payload.ok -ne $true -or $failed.Count -gt 0) { throw "Interrupted execution recovery failed." }
}

Invoke-Phase "Performance budget" {
  $installedSummaryPath = Join-Path $repoRoot ".verify\rc-installed-product-summary.json"
  if (Test-Path $installedSummaryPath) {
    $installed = Get-Content $installedSummaryPath -Raw | ConvertFrom-Json
    $launchCheck = @($installed.checks | Where-Object { $_.name -eq "Installed desktop process started" } | Select-Object -First 1)
    Add-Check "Performance budget" "Desktop launch evidence captured" ($launchCheck.Count -gt 0 -and $launchCheck[0].ok -eq $true) "blocker" "$(if ($launchCheck.Count -gt 0) { $launchCheck[0].detail } else { "missing launch check" })"
  } else {
    Add-Check "Performance budget" "Desktop launch evidence captured" $false "blocker" "Installed product summary missing."
  }
}

Write-CertificationReport $ReportPath
Stop-LocalRuntimeIfStarted

$summaryDir = Split-Path -Parent $SummaryPath
if ($summaryDir) { New-Item -ItemType Directory -Force -Path $summaryDir | Out-Null }
$blockers = @($checks | Where-Object { -not $_.ok -and $_.severity -eq "blocker" })
$warnings = @($checks | Where-Object { -not $_.ok -and $_.severity -eq "warning" })
$summary = [pscustomobject]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  build_version = $BuildVersion
  status = if ($blockers.Count -gt 0) { "blocked" } elseif ($warnings.Count -gt 0) { "warnings" } else { "passed" }
  blockers = $blockers.Count
  warnings = $warnings.Count
  hosted_frontend_url = $HostedFrontendUrl
  hosted_backend_url = $HostedBackendUrl
  auth_backend_url = $AuthBackendUrl
  runtime_frontend_url = $RuntimeFrontendUrl
  runtime_backend_url = $RuntimeBackendUrl
  installer_path = $InstallerPath
  report_path = $ReportPath
  phases = $phases
  checks = $checks
  artifacts = $artifacts
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -Path $SummaryPath -Encoding UTF8
Add-Artifact "summary" $SummaryPath "RC1.2 certification summary"

Write-Host "`nRC1.2 certification checks" -ForegroundColor Cyan
$checks | Format-Table phase, name, ok, severity, detail -AutoSize
Write-Host "Summary written to $SummaryPath" -ForegroundColor DarkGray
Write-Host "Certification report written to $ReportPath" -ForegroundColor DarkGray

if ($blockers.Count -gt 0) {
  throw "RC1.2 certification failed: $($blockers.Count) blocker(s), $($warnings.Count) warning(s)."
}

if ($warnings.Count -gt 0) {
  Write-Host "RC1.2 certification passed with $($warnings.Count) warning(s)." -ForegroundColor Yellow
} else {
  Write-Host "RC1.2 certification passed." -ForegroundColor Green
}
