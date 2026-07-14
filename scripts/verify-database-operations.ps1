param(
  [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot)
)

$ErrorActionPreference = "Stop"
$failures = New-Object System.Collections.Generic.List[string]

function Fail([string]$Message) { $script:failures.Add($Message) | Out-Null }
function Require-File([string]$RelativePath) {
  $path = Join-Path $RepoRoot $RelativePath
  if (-not (Test-Path $path)) { Fail "Missing $RelativePath" }
  return $path
}
function Require-Text([string]$Text, [string]$Needle, [string]$Label) {
  if (-not $Text.Contains($Needle)) { Fail "$Label missing '$Needle'" }
}

$backupPath = Require-File "scripts/backup-postgres.ps1"
$restorePath = Require-File "scripts/restore-postgres.ps1"
$operationsPath = Require-File "docs/OPERATIONS.md"
$hardeningPath = Require-File "docs/production-hardening.md"

$backup = Get-Content $backupPath -Raw
$restore = Get-Content $restorePath -Raw
$operations = Get-Content $operationsPath -Raw
$hardening = Get-Content $hardeningPath -Raw

Require-Text $backup "[switch]`$DryRun" "backup-postgres.ps1" "dry-run mode"
Require-Text $backup "metadata.json" "backup-postgres.ps1" "backup metadata"
Require-Text $backup "Get-FileHash -Algorithm SHA256" "backup-postgres.ps1" "backup checksum"
Require-Text $backup "arceus-latest.dump" "backup-postgres.ps1" "latest backup pointer"
Require-Text $backup "RetentionDays" "backup-postgres.ps1" "backup retention"
Require-Text $backup "pg_dump" "backup-postgres.ps1" "pg_dump invocation"

Require-Text $restore "[switch]`$VerifyOnly" "restore-postgres.ps1" "verify-only mode"
Require-Text $restore "RESTORE_ARCEUS_DATABASE" "restore-postgres.ps1" "destructive confirmation guard"
Require-Text $restore "Get-FileHash -Algorithm SHA256" "restore-postgres.ps1" "restore checksum verification"
Require-Text $restore "pg_restore" "restore-postgres.ps1" "pg_restore invocation"

Require-Text $operations "monthly restore drill" "docs/OPERATIONS.md" "restore drill policy"
Require-Text $operations "No destructive migration" "docs/OPERATIONS.md" "destructive migration policy"
Require-Text $hardening "backup-postgres.ps1" "docs/production-hardening.md" "backup command"
Require-Text $hardening "restore-postgres.ps1" "docs/production-hardening.md" "restore command"

$env:DATABASE_URL = "postgresql://user:pass@db.example.com:5432/arceus"
$dryRun = & powershell -NoProfile -ExecutionPolicy Bypass -File $backupPath -DatabaseUrl $env:DATABASE_URL -DryRun
if (-not (($dryRun | Out-String).Contains('"dry_run":  true') -or ($dryRun | Out-String).Contains('"dry_run": true'))) {
  Fail "backup-postgres.ps1 dry-run did not report dry_run=true"
}

if ($failures.Count -gt 0) {
  foreach ($failure in $failures) { Write-Error $failure }
  throw "$($failures.Count) database operations verification issue(s) found."
}

Write-Host "Database backup/restore operations are configured." -ForegroundColor Green
