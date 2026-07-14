param(
  [string]$DatabaseUrl = $env:DATABASE_URL,
  [string]$OutputDir = ".\backups",
  [string]$Tag = "",
  [int]$RetentionDays = 30,
  [string]$LatestName = "arceus-latest.dump",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not $DatabaseUrl) {
  throw "DATABASE_URL is required."
}

function Redact-DatabaseUrl([string]$Value) {
  return $Value -replace "://([^:@/]+):([^@/]+)@", '://$1:[REDACTED]@'
}

function Safe-Tag([string]$Value) {
  if (-not $Value) { return "" }
  return ($Value.Trim() -replace "[^0-9A-Za-z._-]", "-")
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$timestamp = Get-Date -Format "yyyyMMdd-HHmmss"
$safeTag = Safe-Tag $Tag
$suffix = if ($safeTag) { "-$safeTag" } else { "" }
$file = Join-Path $OutputDir "arceus-postgres-$timestamp$suffix.dump"
$metadataFile = "$file.metadata.json"
$latestFile = Join-Path $OutputDir $LatestName
$latestMetadataFile = "$latestFile.metadata.json"

$plan = [pscustomobject]@{
  action = "backup"
  output_file = $file
  latest_file = $latestFile
  metadata_file = $metadataFile
  retention_days = $RetentionDays
  database_url = Redact-DatabaseUrl $DatabaseUrl
  dry_run = [bool]$DryRun
}

if ($DryRun) {
  $plan | ConvertTo-Json -Depth 4
  Write-Host "Dry run only. No pg_dump command executed."
  exit 0
}

$pgDump = Get-Command pg_dump -ErrorAction SilentlyContinue
if (-not $pgDump) {
  throw "pg_dump is required. Install PostgreSQL client tools and ensure pg_dump is on PATH."
}

Write-Host "Creating compressed PostgreSQL backup: $file"
& pg_dump $DatabaseUrl --format=custom --no-owner --no-privileges --file $file

if (-not (Test-Path $file)) {
  throw "Backup file was not created."
}

$hash = Get-FileHash -Algorithm SHA256 -Path $file
$item = Get-Item $file
$metadata = [pscustomobject]@{
  created_at = (Get-Date).ToUniversalTime().ToString("o")
  tag = $safeTag
  file = $file
  latest_file = $latestFile
  bytes = $item.Length
  sha256 = $hash.Hash
  database_url = Redact-DatabaseUrl $DatabaseUrl
  pg_dump = $pgDump.Source
  format = "custom"
  no_owner = $true
  no_privileges = $true
}
$metadata | ConvertTo-Json -Depth 5 | Set-Content -Path $metadataFile -Encoding UTF8
Copy-Item -LiteralPath $file -Destination $latestFile -Force
Copy-Item -LiteralPath $metadataFile -Destination $latestMetadataFile -Force

if ($RetentionDays -gt 0) {
  $cutoff = (Get-Date).AddDays(-$RetentionDays)
  Get-ChildItem -Path $OutputDir -Filter "arceus-postgres-*.dump" -File |
    Where-Object { $_.LastWriteTime -lt $cutoff } |
    ForEach-Object {
      Remove-Item -LiteralPath $_.FullName -Force
      $oldMetadata = "$($_.FullName).metadata.json"
      if (Test-Path $oldMetadata) {
        Remove-Item -LiteralPath $oldMetadata -Force
      }
    }
}

Write-Host "Backup complete: $file"
Write-Host "Latest backup pointer: $latestFile"
Write-Host "Metadata: $metadataFile"
