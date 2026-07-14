param(
  [Parameter(Mandatory=$true)]
  [string]$BackupFile,
  [string]$DatabaseUrl = $env:DATABASE_URL,
  [string]$Confirm = ""
)

$ErrorActionPreference = "Stop"

if (-not $DatabaseUrl) {
  throw "DATABASE_URL is required."
}
if (-not (Test-Path $BackupFile)) {
  throw "Backup file not found: $BackupFile"
}
if ($Confirm -ne "RESTORE_ARCEUS_DATABASE") {
  throw "Refusing restore. Re-run with -Confirm RESTORE_ARCEUS_DATABASE"
}

$pgRestore = Get-Command pg_restore -ErrorAction SilentlyContinue
if (-not $pgRestore) {
  throw "pg_restore is required. Install PostgreSQL client tools and ensure pg_restore is on PATH."
}

Write-Host "Restoring PostgreSQL backup into target DATABASE_URL..."
& pg_restore --clean --if-exists --no-owner --no-privileges --dbname $DatabaseUrl $BackupFile

Write-Host "Restore complete."
