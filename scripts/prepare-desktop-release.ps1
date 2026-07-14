param(
  [Parameter(Mandatory = $true)]
  [string]$ReleaseVersion,

  [string]$DesktopDir = ".\desktop"
)

$ErrorActionPreference = "Stop"

function Convert-ToSemver([string]$value) {
  $candidate = $value.Trim()
  $candidate = $candidate -replace "^refs/tags/", ""
  $candidate = $candidate -replace "^arceus-code-v", ""
  $candidate = $candidate -replace "^v", ""
  if ($candidate -notmatch "^\d+\.\d+\.\d+(-[0-9A-Za-z.-]+)?$") {
    throw "ReleaseVersion '$ReleaseVersion' does not contain a valid semver version."
  }
  return $candidate
}

$semver = Convert-ToSemver $ReleaseVersion
$resolvedDesktop = Resolve-Path $DesktopDir

Push-Location $resolvedDesktop
try {
  npm version $semver --no-git-tag-version --allow-same-version
  Write-Host "Prepared Arceus Code desktop package version $semver"
} finally {
  Pop-Location
}
