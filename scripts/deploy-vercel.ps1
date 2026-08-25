param(
  [string]$Token = $env:VERCEL_TOKEN,
  [string]$Scope = $env:VERCEL_SCOPE,
  [switch]$Prod = $true
)

$ErrorActionPreference = "Stop"

$frontendDir = Join-Path $PSScriptRoot "..\frontend"
if (-not (Test-Path $frontendDir)) {
  throw "Frontend directory not found at $frontendDir"
}

Set-Location $frontendDir

Write-Host "Verifying Vercel CLI..."
$args = @("--yes")

if ($Prod) {
  $args += @("--prod")
}

if ($Token) {
  $args += @("--token", $Token)
}

if ($Scope) {
  $args += @("--scope", $Scope)
}

Write-Host "Deploying frontend to Vercel..."
& npx --yes vercel @args

Write-Host "Vercel deployment finished."
