param(
  [Parameter(Mandatory=$true)]
  [string]$BackupFile,
  [string]$DatabaseUrl = $env:DATABASE_URL,
  [string]$Confirm = "",
  [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"

if (-not $VerifyOnly -and -not $DatabaseUrl) {
  throw "DATABASE_URL is required."
}
if (-not (Test-Path $BackupFile)) {
  throw "Backup file not found: $BackupFile"
}
if (-not $VerifyOnly -and $Confirm -ne "RESTORE_ARCEUS_DATABASE") {
  throw "Refusing restore. Re-run with -Confirm RESTORE_ARCEUS_DATABASE"
}

$pgRestore = Get-Command pg_restore -ErrorAction SilentlyContinue
if (-not $pgRestore -and -not $VerifyOnly) {
  throw "pg_restore is required. Install PostgreSQL client tools and ensure pg_restore is on PATH."
}

$item = Get-Item $BackupFile
$hash = Get-FileHash -Algorithm SHA256 -Path $BackupFile
$metadataFile = "$BackupFile.metadata.json"
$metadata = $null
if (Test-Path $metadataFile) {
  $metadata = Get-Content $metadataFile -Raw | ConvertFrom-Json
  if ($metadata.sha256 -and $metadata.sha256 -ne $hash.Hash) {
    throw "Backup SHA256 does not match metadata. Expected $($metadata.sha256), got $($hash.Hash)."
  }
}

if ($VerifyOnly) {
  $report = [pscustomobject]@{
    action = "verify_restore_input"
    backup_file = $BackupFile
    bytes = $item.Length
    sha256 = $hash.Hash
    metadata_found = [bool]$metadata
    metadata_created_at = $metadata.created_at
    pg_restore_available = [bool]$pgRestore
  }
  $report | ConvertTo-Json -Depth 5
  Write-Host "Verify only. No database restore executed."
  exit 0
}

Write-Host "Restoring PostgreSQL backup into target DATABASE_URL..."
& pg_restore --clean --if-exists --no-owner --no-privileges --dbname $DatabaseUrl $BackupFile

Write-Host "Restore complete."
