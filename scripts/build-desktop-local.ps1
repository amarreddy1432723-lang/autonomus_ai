param(
  [string]$DesktopDir = ".\desktop"
)

$ErrorActionPreference = "Stop"

$resolvedDesktop = Resolve-Path $DesktopDir
Push-Location $resolvedDesktop
try {
  $env:CSC_IDENTITY_AUTO_DISCOVERY = "false"
  npx electron-builder --win --publish never --config electron-builder.local.yml
} finally {
  Pop-Location
}
