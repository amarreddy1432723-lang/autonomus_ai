param(
  [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
  [switch]$StrictExternal
)

$ErrorActionPreference = "Stop"
$failures = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

function Fail([string]$Message) { $script:failures.Add($Message) | Out-Null }
function Warn([string]$Message) { $script:warnings.Add($Message) | Out-Null }
function Require-File([string]$RelativePath) {
  $path = Join-Path $RepoRoot $RelativePath
  if (-not (Test-Path $path)) { Fail "Missing $RelativePath" }
  return $path
}
function Require-Text([string]$Text, [string]$Needle, [string]$Label) {
  if (-not $Text.Contains($Needle)) { Fail "$Label missing '$Needle'" }
}
function Require-JsonValue($Object, [string]$Path, $Expected) {
  $value = $Object
  foreach ($part in $Path.Split(".")) {
    if ($part -match "^\d+$") {
      $index = [int]$part
      if ($null -eq $value -or $value.Count -le $index) {
        Fail "desktop/package.json missing $Path"
        return
      }
      $value = $value[$index]
    } else {
      if ($null -eq $value.$part) {
        Fail "desktop/package.json missing $Path"
        return
      }
      $value = $value.$part
    }
  }
  if ($value -ne $Expected) { Fail "desktop/package.json $Path expected '$Expected' but found '$value'" }
}

$packagePath = Require-File "desktop/package.json"
$mainPath = Require-File "desktop/main.js"
$preloadPath = Require-File "desktop/preload.js"
$workflowPath = Require-File ".github/workflows/release.yml"
$entitlementsPath = Require-File "desktop/build/entitlements.mac.plist"
$manifestRoot = "manifests/a/Arceus/Code/1.0.0"
$manifestVersionPath = Require-File "$manifestRoot/Arceus.Code.yaml"
$manifestInstallerPath = Require-File "$manifestRoot/Arceus.Code.installer.yaml"
$manifestLocalePath = Require-File "$manifestRoot/Arceus.Code.locale.en-US.yaml"

$package = Get-Content $packagePath -Raw | ConvertFrom-Json
Require-JsonValue $package "name" "arceus-desktop-os"
Require-JsonValue $package "build.appId" "dev.arceus.code"
Require-JsonValue $package "build.productName" "Arceus Code"
Require-JsonValue $package "build.win.target" "nsis"
Require-JsonValue $package "build.publish.0.provider" "github"
if (-not $package.scripts.dist) { Fail "desktop/package.json missing scripts.dist" }
if (-not $package.dependencies."electron-updater") { Fail "desktop/package.json missing electron-updater dependency" }
if (-not ($package.build.mac.target -contains "dmg")) { Fail "desktop/package.json mac target must include dmg" }
if (-not ($package.build.mac.target -contains "zip")) { Fail "desktop/package.json mac target must include zip for auto-update feeds" }
if (-not ($package.build.linux.target -contains "AppImage")) { Fail "desktop/package.json linux target must include AppImage" }
if (-not ($package.build.linux.target -contains "deb")) { Fail "desktop/package.json linux target must include deb" }

$main = Get-Content $mainPath -Raw
Require-Text $main "electron-updater" "desktop/main.js" "auto updater import"
Require-Text $main "checkForUpdatesAndNotify" "desktop/main.js" "auto updater startup check"
Require-Text $main "desktop-update-status" "desktop/main.js" "renderer update status IPC"
Require-Text $main "desktop-install-update" "desktop/main.js" "install update IPC"
Require-Text $main "quitAndInstall" "desktop/main.js" "restart and install"

$preload = Get-Content $preloadPath -Raw
Require-Text $preload "installUpdate" "desktop/preload.js" "install update bridge"
Require-Text $preload "onUpdateStatus" "desktop/preload.js" "update status bridge"
Require-Text $preload "onUpdateReady" "desktop/preload.js" "update ready bridge"

$workflow = Get-Content $workflowPath -Raw
Require-Text $workflow "desktop-release" ".github/workflows/release.yml" "desktop release job"
Require-Text $workflow "npm run dist -- --publish always" ".github/workflows/release.yml" "artifact publish command"
Require-Text $workflow "prepare-desktop-release.ps1" ".github/workflows/release.yml" "version sync step"
Require-Text $workflow "generate-release-download-env.ps1" ".github/workflows/release.yml" "download env generation"
Require-Text $workflow "WIN_CSC_LINK" ".github/workflows/release.yml" "Windows signing env"
Require-Text $workflow "APPLE_ID" ".github/workflows/release.yml" "Apple signing env"

$versionManifest = Get-Content $manifestVersionPath -Raw
$installerManifest = Get-Content $manifestInstallerPath -Raw
$localeManifest = Get-Content $manifestLocalePath -Raw
foreach ($manifest in @($versionManifest, $installerManifest, $localeManifest)) {
  Require-Text $manifest "PackageIdentifier: Arceus.Code" "winget manifest" "package identifier"
  Require-Text $manifest "PackageVersion: 1.0.0" "winget manifest" "package version"
}
Require-Text $installerManifest "InstallerType: nullsoft" "winget installer manifest" "NSIS installer type"
Require-Text $installerManifest "https://github.com/arceus-ai/arceus-code/releases/download/arceus-code-v1.0.0/" "winget installer manifest" "release download URL"
Require-Text $localeManifest "PackageName: Arceus Code" "winget locale manifest" "package name"

if ($installerManifest.Contains("REPLACE_WITH_RELEASE_SHA256")) {
  if ($StrictExternal) {
    Fail "winget InstallerSha256 still has placeholder value"
  } else {
    Warn "winget InstallerSha256 is still a placeholder until the signed release artifact exists"
  }
}
if (-not ($env:WIN_CSC_LINK -or $env:CSC_LINK)) { Warn "Windows signing secret not present in this shell" }
if (-not ($env:APPLE_ID -and $env:APPLE_APP_SPECIFIC_PASSWORD -and $env:APPLE_TEAM_ID)) { Warn "Apple notarization secrets not present in this shell" }

Write-Host "Desktop release verification" -ForegroundColor Cyan
Write-Host "Package: $($package.build.productName) $($package.version)"
Write-Host "Entitlements: $entitlementsPath"
Write-Host "Winget manifest: $manifestRoot"
foreach ($warning in $warnings) { Write-Warning $warning }

if ($failures.Count -gt 0) {
  foreach ($failure in $failures) { Write-Error $failure }
  throw "$($failures.Count) desktop release verification issue(s) found."
}

Write-Host "Desktop release surface is configured." -ForegroundColor Green
