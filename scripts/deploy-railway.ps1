param(
  [string]$Environment = $env:RAILWAY_ENVIRONMENT,
  [string]$Project = $env:RAILWAY_PROJECT,
  [string]$Service = $env:RAILWAY_SERVICE,
  [string]$BackendUrl = $env:SMOKE_BACKEND_URL,
  [string]$FrontendUrl = $env:SMOKE_FRONTEND_URL,
  [string]$AdminUserId = $env:SMOKE_ADMIN_USER_ID,
  [string]$ReleaseVersion = $(if ($env:RELEASE_VERSION) { $env:RELEASE_VERSION } elseif ($env:ARCEUS_RELEASE_VERSION) { $env:ARCEUS_RELEASE_VERSION } else { "" }),
  [switch]$SkipReleaseGate
)

$ErrorActionPreference = "Stop"

if (-not $env:RAILWAY_TOKEN) {
  $status = & railway status 2>&1
  if ($status -match "Not logged in") {
    throw "RAILWAY_TOKEN or active Railway CLI login session is required."
  }
}

$railway = Get-Command railway -ErrorAction SilentlyContinue
if (-not $railway) {
  throw "Railway CLI is not installed. Run: npm install -g @railway/cli"
}

if (-not $SkipReleaseGate) {
  $targetEnvironment = if ($Environment) { $Environment } else { "production" }
  $allowWarnings = $targetEnvironment -ne "production"
  Write-Host "Running pre-deploy release gate for $targetEnvironment..."
  & "$PSScriptRoot\verify-release-gate.ps1" -Environment $targetEnvironment -Phase predeploy -ReleaseVersion $ReleaseVersion -AllowWarnings:$allowWarnings
}

$args = @("up", "--detach")
if ($Environment) { $args += @("--environment", $Environment) }
if ($Project) { $args += @("--project", $Project) }
if ($Service) { $args += @("--service", $Service) }

Write-Host "Deploying Arceus with Railway CLI..."
& railway @args

if ($BackendUrl -or $FrontendUrl) {
  Write-Host "Running smoke tests after deploy..."
  & "$PSScriptRoot\smoke-test.ps1" -BackendUrl $BackendUrl -FrontendUrl $FrontendUrl -AdminUserId $AdminUserId
}

Write-Host "Deploy complete."
