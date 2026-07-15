param(
  [string]$RedisUrl = $env:UPSTASH_REDIS_URL,
  [string[]]$Services = @("auth", "goals", "agent"),
  [string]$Environment = $(if ($env:RAILWAY_ENVIRONMENT) { $env:RAILWAY_ENVIRONMENT } else { "production" }),
  [string]$AgentUrl = $(if ($env:SMOKE_BACKEND_URL) { $env:SMOKE_BACKEND_URL } else { "https://agent-production-8568.up.railway.app" }),
  [switch]$SkipRedeploy
)

$ErrorActionPreference = "Stop"

if (-not $RedisUrl -or -not $RedisUrl.Trim()) {
  throw "Set UPSTASH_REDIS_URL or pass -RedisUrl. Use the Upstash Redis TLS URL, usually rediss://default:<password>@<host>:6379."
}

if ($RedisUrl -notmatch "^redis(s)?://") {
  throw "RedisUrl must start with redis:// or rediss://."
}

$railway = Get-Command railway -ErrorAction SilentlyContinue
if (-not $railway) {
  throw "Railway CLI is not installed. Run: npm install -g @railway/cli"
}

Write-Host "Setting REDIS_URL on Railway services..." -ForegroundColor Cyan
foreach ($service in $Services) {
  Write-Host "  - $service"
  railway variable set REDIS_URL="$RedisUrl" --service $service --environment $Environment --skip-deploys | Out-Null
  railway variable set CELERY_BROKER_URL="$RedisUrl" --service $service --environment $Environment --skip-deploys | Out-Null
  railway variable set CELERY_RESULT_BACKEND="$RedisUrl" --service $service --environment $Environment --skip-deploys | Out-Null
}

if (-not $SkipRedeploy) {
  Write-Host "Redeploying services..." -ForegroundColor Cyan
  foreach ($service in $Services) {
    railway redeploy --service $service --environment $Environment --from-source --yes | Out-Null
  }
}

Write-Host "Waiting for agent readiness..." -ForegroundColor Cyan
$deadline = (Get-Date).AddMinutes(6)
$last = $null
while ((Get-Date) -lt $deadline) {
  try {
    $response = Invoke-WebRequest -Uri "$AgentUrl/api/v1/ready" -UseBasicParsing -TimeoutSec 20
    $payload = $response.Content | ConvertFrom-Json
    $last = $payload
    if ($payload.dependencies.redis -eq "ok") {
      Write-Host "Upstash Redis is connected. Agent readiness:" -ForegroundColor Green
      $payload | ConvertTo-Json -Depth 5
      exit 0
    }
    Write-Host "Redis status: $($payload.dependencies.redis). Retrying..."
  } catch {
    Write-Host "Readiness check failed: $($_.Exception.Message). Retrying..."
  }
  Start-Sleep -Seconds 15
}

if ($last) {
  $last | ConvertTo-Json -Depth 5
}
throw "Timed out waiting for agent-service Redis readiness at $AgentUrl/api/v1/ready."
