param(
  [string]$BackendUrl = $(if ($env:SMOKE_BACKEND_URL) { $env:SMOKE_BACKEND_URL } else { "http://localhost:8003" }),
  [string]$PrometheusUrl = $(if ($env:PROMETHEUS_URL) { $env:PROMETHEUS_URL } else { "http://localhost:9090" }),
  [string]$GrafanaUrl = $(if ($env:GRAFANA_URL) { $env:GRAFANA_URL } else { "http://localhost:3001" }),
  [string]$OutputPath = $(if ($env:OBSERVABILITY_VERIFY_SUMMARY_PATH) { $env:OBSERVABILITY_VERIFY_SUMMARY_PATH } else { ".verify\observability-summary.json" }),
  [switch]$CheckRuntime,
  [switch]$Strict
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$items = New-Object System.Collections.Generic.List[object]

function Resolve-RepoPath([string]$Path) {
  if ([System.IO.Path]::IsPathRooted($Path)) { return $Path }
  return Join-Path $repoRoot $Path
}

function Add-Item {
  param(
    [string]$Name,
    [bool]$Ok,
    [string]$Severity = "blocker",
    [string]$Detail = "",
    [string]$Action = ""
  )
  $items.Add([pscustomobject]@{
    name = $Name
    ok = $Ok
    severity = if ($Ok) { "ok" } else { $Severity }
    detail = $Detail
    action = $Action
  }) | Out-Null
}

function Test-Configured([string]$Name) {
  $value = [Environment]::GetEnvironmentVariable($Name)
  return [bool]($value -and $value.Trim() -and $value -notmatch "^(REPLACE|https://REPLACE|local|mock|example)")
}

function Test-HttpOk([string]$Url) {
  try {
    $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 8
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 400
  } catch {
    return $false
  }
}

$prometheusConfig = Resolve-RepoPath "ops\prometheus\prometheus.yml"
$alertRules = Resolve-RepoPath "ops\prometheus\arceus-alerts.yml"
$grafanaDashboard = Resolve-RepoPath "ops\grafana\arceus-code-overview.json"
$grafanaDatasource = Resolve-RepoPath "ops\grafana\provisioning\datasources\prometheus.yml"
$grafanaProvider = Resolve-RepoPath "ops\grafana\provisioning\dashboards\arceus.yml"
$runbook = Resolve-RepoPath "docs\observability.md"

Add-Item "Backend Sentry DSN" (Test-Configured "SENTRY_DSN") "warning" "SENTRY_DSN enables backend exception capture." "Set SENTRY_DSN in production and staging."
Add-Item "Frontend Sentry DSN" (Test-Configured "NEXT_PUBLIC_SENTRY_DSN") "warning" "NEXT_PUBLIC_SENTRY_DSN enables browser exception capture." "Set NEXT_PUBLIC_SENTRY_DSN in frontend env."
Add-Item "Release tag" ((Test-Configured "APP_RELEASE") -or (Test-Configured "GIT_SHA")) "warning" "APP_RELEASE or GIT_SHA connects errors to a deploy." "Set APP_RELEASE from the CI tag or commit SHA."
Add-Item "Prometheus config" (Test-Path $prometheusConfig) "blocker" "ops/prometheus/prometheus.yml" "Add Prometheus scrape config."
Add-Item "Prometheus alert rules" (Test-Path $alertRules) "blocker" "ops/prometheus/arceus-alerts.yml" "Add alert rules for service, error, latency, queue, worker, and dead-letter signals."
Add-Item "Grafana dashboard" (Test-Path $grafanaDashboard) "blocker" "ops/grafana/arceus-code-overview.json" "Add importable Grafana dashboard JSON."
Add-Item "Grafana datasource provisioning" (Test-Path $grafanaDatasource) "blocker" "ops/grafana/provisioning/datasources/prometheus.yml" "Provision Prometheus as Grafana datasource."
Add-Item "Grafana dashboard provisioning" (Test-Path $grafanaProvider) "blocker" "ops/grafana/provisioning/dashboards/arceus.yml" "Provision Arceus dashboard provider."
Add-Item "Observability runbook" (Test-Path $runbook) "blocker" "docs/observability.md" "Document setup, checks, alerts, and incident response."

if (Test-Path $alertRules) {
  $alertText = Get-Content $alertRules -Raw
  foreach ($alertName in @(
    "ArceusServiceDown",
    "ArceusApiHighErrorRate",
    "ArceusApiP99LatencyHigh",
    "ArceusWorkerQueueDepthHigh",
    "ArceusWorkerDown",
    "ArceusDeadLetterJobs"
  )) {
    Add-Item "Alert coverage: $alertName" ($alertText -match [regex]::Escape($alertName)) "blocker" "Required alert $alertName" "Add $alertName to ops/prometheus/arceus-alerts.yml."
  }
}

if ($CheckRuntime) {
  Add-Item "Backend /metrics reachable" (Test-HttpOk "$BackendUrl/metrics") "blocker" "$BackendUrl/metrics" "Start agent-service with PROMETHEUS_METRICS_ENABLED=true."
  Add-Item "Prometheus runtime reachable" (Test-HttpOk "$PrometheusUrl/-/ready") "blocker" "$PrometheusUrl/-/ready" "Run docker compose -f docker-compose.prod-smoke.yml --profile observability up -d."
  Add-Item "Prometheus targets reachable" (Test-HttpOk "$PrometheusUrl/targets") "warning" "$PrometheusUrl/targets" "Check scrape targets in Prometheus."
  Add-Item "Grafana runtime reachable" (Test-HttpOk "$GrafanaUrl/api/health") "warning" "$GrafanaUrl/api/health" "Open Grafana on port 3001 or set GRAFANA_URL."
}

$blockers = @($items | Where-Object { $_.ok -ne $true -and $_.severity -eq "blocker" })
$warnings = @($items | Where-Object { $_.ok -ne $true -and $_.severity -eq "warning" })
$ready = $blockers.Count -eq 0 -and (-not $Strict -or $warnings.Count -eq 0)

$report = [pscustomobject]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  ready = $ready
  blockers = $blockers.Count
  warnings = $warnings.Count
  check_runtime = [bool]$CheckRuntime
  commands = @{
    start_stack = "docker compose -f docker-compose.prod-smoke.yml --profile observability up -d"
    prometheus_targets = "$PrometheusUrl/targets"
    grafana = $GrafanaUrl
    admin_gate = "$BackendUrl/api/v1/admin/observability-health"
  }
  items = $items
}

$resolvedOutput = Resolve-RepoPath $OutputPath
$outDir = Split-Path -Parent $resolvedOutput
if ($outDir) { New-Item -ItemType Directory -Force -Path $outDir | Out-Null }
$report | ConvertTo-Json -Depth 8 | Set-Content -Path $resolvedOutput -Encoding UTF8

Write-Host "Observability verification" -ForegroundColor Cyan
$items | Format-Table name, ok, severity, detail -AutoSize
Write-Host "Summary written to $resolvedOutput" -ForegroundColor Green

if (-not $ready) {
  throw "Observability verification failed: $($blockers.Count) blocker(s), $($warnings.Count) warning(s)."
}

Write-Host "Observability verification passed." -ForegroundColor Green
