param(
  [string]$ReleaseVersion = "arceus-code-v1.0.0",
  [string]$OwnerRepo = "",
  [string]$InstallerPath = ".\desktop\dist\Arceus Code-1.0.0-Setup.exe",
  [string]$AgentService = "agent",
  [switch]$SetRailwayEnv,
  [switch]$Draft,
  [switch]$Prerelease
)

$ErrorActionPreference = "Stop"

function Resolve-CommandPath([string]$Name, [string[]]$FallbackPaths = @()) {
  $command = Get-Command $Name -ErrorAction SilentlyContinue
  if ($command) {
    return $command.Source
  }
  foreach ($path in $FallbackPaths) {
    if (Test-Path $path) {
      return $path
    }
  }
  return $null
}

function Require-CommandPath([string]$Name, [string]$InstallHint, [string[]]$FallbackPaths = @()) {
  $path = Resolve-CommandPath $Name $FallbackPaths
  if (-not $path) {
    throw "$Name is required. $InstallHint"
  }
  return $path
}

function Resolve-GitHubRepo {
  $remote = git remote get-url origin
  if ($remote -match "github\.com[:/](?<owner>[^/]+)/(?<repo>[^/.]+)(\.git)?$") {
    return "$($Matches.owner)/$($Matches.repo)"
  }
  throw "Unable to infer GitHub owner/repo from origin remote. Pass -OwnerRepo owner/repo."
}

$git = Require-CommandPath "git" "Install Git and retry."
$gh = Require-CommandPath "gh" "Install GitHub CLI from https://cli.github.com/, run `gh auth login`, then retry." @(
  "C:\Program Files\GitHub CLI\gh.exe",
  "C:\Program Files (x86)\GitHub CLI\gh.exe"
)

if (-not $OwnerRepo) {
  $OwnerRepo = Resolve-GitHubRepo
}

$installer = Resolve-Path $InstallerPath
$checksum = (Get-FileHash -Algorithm SHA256 -Path $installer).Hash.ToLowerInvariant()
$fileName = Split-Path -Leaf $installer
$encodedFileName = [uri]::EscapeDataString($fileName)
$downloadUrl = "https://github.com/$OwnerRepo/releases/download/$ReleaseVersion/$encodedFileName"
$notesUrl = "https://github.com/$OwnerRepo/releases/tag/$ReleaseVersion"
$updateFeedUrl = "https://github.com/$OwnerRepo/releases/latest"

$releaseExists = $false
try {
  & $gh release view $ReleaseVersion --repo $OwnerRepo *> $null
  $releaseExists = $true
} catch {
  $releaseExists = $false
}

if (-not $releaseExists) {
  $args = @("release", "create", $ReleaseVersion, "--repo", $OwnerRepo, "--title", "Arceus Code $ReleaseVersion", "--notes", "Arceus Code desktop release.")
  if ($Draft) { $args += "--draft" }
  if ($Prerelease) { $args += "--prerelease" }
  & $gh @args
}

& $gh release upload $ReleaseVersion $installer --repo $OwnerRepo --clobber

Write-Host "Uploaded: $downloadUrl"
Write-Host "SHA256: $checksum"

if ($SetRailwayEnv) {
  $railway = Require-CommandPath "railway" "Install Railway CLI and run railway login/link."
  & $railway variables --service $AgentService `
    --set "ARCEUS_RELEASE_VERSION=$ReleaseVersion" `
    --set "ARCEUS_RELEASE_CHANNEL=stable" `
    --set "ARCEUS_RELEASE_SIGNED=false" `
    --set "ARCEUS_RELEASE_NOTES_URL=$notesUrl" `
    --set "ARCEUS_UPDATE_FEED_URL=$updateFeedUrl" `
    --set "ARCEUS_DOWNLOAD_WINDOWS_X64_INSTALLER_URL=$downloadUrl" `
    --set "ARCEUS_DOWNLOAD_WINDOWS_X64_INSTALLER_SHA256=$checksum"

  & $railway redeploy --service $AgentService --environment production --from-source --yes
  Write-Host "Railway download variables set on service '$AgentService'."
}

[pscustomobject]@{
  ReleaseVersion = $ReleaseVersion
  OwnerRepo = $OwnerRepo
  Installer = $installer.Path
  DownloadUrl = $downloadUrl
  Sha256 = $checksum
  RailwayUpdated = [bool]$SetRailwayEnv
} | ConvertTo-Json -Depth 3
