param(
  [string]$DatabaseUrl = $env:DATABASE_URL,
  [string]$OutputDir = ".\backups",
  [string]$Tag = ""
)

$ErrorActionPreference = "Stop"

if (-not $DatabaseUrl) {
  throw "DATABASE_URL is required."
}

$pgDump = Get-Command pg_dump -ErrorAction SilentlyContinue
if (-not $pgDump) {
  throw "pg_dump is required. Install PostgreSQL client tools and ensure pg_dump is on PATH."
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$suffix = if ($Tag) { "-$Tag" } else { "" }
$file = Join-Path $OutputDir "arceus-postgres-$timestamp$suffix.dump"

Write-Host "Creating compressed PostgreSQL backup: $file"
& pg_dump $DatabaseUrl --format=custom --no-owner --no-privileges --file $file

if (-not (Test-Path $file)) {
  throw "Backup file was not created."
}

Write-Host "Backup complete: $file"
