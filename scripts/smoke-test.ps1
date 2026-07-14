param(
  [string]$BackendUrl = $env:SMOKE_BACKEND_URL,
  [string]$FrontendUrl = $env:SMOKE_FRONTEND_URL,
  [string]$AdminUserId = $env:SMOKE_ADMIN_USER_ID
)

$ErrorActionPreference = "Stop"

if (-not $BackendUrl) {
  $BackendUrl = "http://localhost:8003"
}

function Invoke-WithRetry {
  param(
    [string]$Uri,
    [hashtable]$Headers = @{},
    [int]$MaxRetries = 24, # 24 * 10 seconds = 4 minutes max wait for cloud builds
    [int]$DelaySeconds = 10
  )
  for ($i = 1; $i -le $MaxRetries; $i++) {
    try {
      $resp = Invoke-WebRequest -Uri $Uri -UseBasicParsing -Headers $Headers
      if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300) {
        return $resp
      }
    } catch {
      Write-Host "Waiting for service at $Uri... (Attempt $i of $MaxRetries)"
    }
    Start-Sleep -Seconds $DelaySeconds
  }
  throw "Service at $Uri failed to respond within $(($MaxRetries * $DelaySeconds) / 60) minutes."
}

Write-Host "Checking backend health at $BackendUrl"
$health = Invoke-WithRetry -Uri "$BackendUrl/api/v1/health"

Write-Host "Checking backend readiness at $BackendUrl"
$ready = Invoke-WithRetry -Uri "$BackendUrl/api/v1/ready"

$readyBody = $ready.Content | ConvertFrom-Json
if ($readyBody.status -notin @("ready", "degraded")) {
  throw "Readiness check did not pass. Status: $($readyBody.status). Dependencies: $($ready.Content)"
}

Write-Host "Checking production readiness checklist..."
$prod = Invoke-WithRetry -Uri "$BackendUrl/api/v1/production/readiness"

if ($AdminUserId) {
  Write-Host "Checking admin release readiness"
  $admin = Invoke-WithRetry -Uri "$BackendUrl/api/v1/admin/release-readiness" -Headers @{"x-user-id"=$AdminUserId}

  Write-Host "Checking admin billing health"
  $billing = Invoke-WithRetry -Uri "$BackendUrl/api/v1/admin/billing-health" -Headers @{"x-user-id"=$AdminUserId}

  Write-Host "Checking admin observability health"
  $observability = Invoke-WithRetry -Uri "$BackendUrl/api/v1/admin/observability-health" -Headers @{"x-user-id"=$AdminUserId}

  Write-Host "Checking admin rate-limit policy"
  $rateLimits = Invoke-WithRetry -Uri "$BackendUrl/api/v1/admin/rate-limits" -Headers @{"x-user-id"=$AdminUserId}
}

if ($FrontendUrl) {
  Write-Host "Checking frontend at $FrontendUrl/hub"
  $frontend = Invoke-WithRetry -Uri "$FrontendUrl/hub"
  
  Write-Host "Checking admin page at $FrontendUrl/admin"
  $adminPage = Invoke-WithRetry -Uri "$FrontendUrl/admin"
}

Write-Host "Smoke tests passed."
