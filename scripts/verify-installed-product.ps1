param(
  [string]$InstallerPath = $(Join-Path (Split-Path -Parent $PSScriptRoot) "desktop\dist\Arceus Code-1.0.0-Setup.exe"),
  [string]$BackendUrl = $(if ($env:SMOKE_BACKEND_URL) { $env:SMOKE_BACKEND_URL } else { "https://agent-production-8568.up.railway.app" }),
  [string]$FrontendUrl = $(if ($env:SMOKE_FRONTEND_URL) { $env:SMOKE_FRONTEND_URL } else { "https://frontend-production-fbde.up.railway.app" }),
  [string]$OutputPath = $(Join-Path (Split-Path -Parent $PSScriptRoot) ".verify\installed-product-summary.json"),
  [switch]$SkipInstall,
  [switch]$KeepRunning,
  [switch]$Strict
)

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot
$screenshotsDir = Join-Path $repoRoot "screenshots\installed-product"
$logsDir = Join-Path $repoRoot "logs\installed-product"
$videosDir = Join-Path $repoRoot "videos\installed-product"
New-Item -ItemType Directory -Force -Path $screenshotsDir, $logsDir, $videosDir, (Split-Path -Parent $OutputPath) | Out-Null

$checks = New-Object System.Collections.Generic.List[object]
$artifacts = New-Object System.Collections.Generic.List[object]

function Add-Check {
  param([string]$Name, [bool]$Ok, [string]$Severity, [string]$Detail)
  $script:checks.Add([pscustomobject]@{
    name = $Name
    ok = $Ok
    severity = $Severity
    detail = $Detail
  }) | Out-Null
}

function Add-Artifact {
  param([string]$Kind, [string]$Path, [string]$Description)
  if ($Path -and (Test-Path $Path)) {
    $script:artifacts.Add([pscustomobject]@{
      kind = $Kind
      path = (Resolve-Path $Path).Path
      description = $Description
    }) | Out-Null
  }
}

function Test-Http {
  param([string]$Uri, [int]$Attempts = 3)
  $last = @{ ok = $false; detail = "not attempted"; content = "" }
  for ($attempt = 1; $attempt -le $Attempts; $attempt += 1) {
    try {
      $response = Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 25
      return @{ ok = ($response.StatusCode -ge 200 -and $response.StatusCode -lt 400); detail = "$($response.StatusCode) $($response.StatusDescription)"; content = $response.Content }
    } catch {
      $last = @{ ok = $false; detail = "attempt $attempt/${Attempts}: $($_.Exception.Message)"; content = "" }
      if ($attempt -lt $Attempts) { Start-Sleep -Seconds 2 }
    }
  }
  return $last
}

function Capture-Screen {
  param([string]$Name)
  $path = Join-Path $screenshotsDir $Name
  try {
    Add-Type -AssemblyName System.Windows.Forms
    Add-Type -AssemblyName System.Drawing
    $bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
    $bitmap = [System.Drawing.Bitmap]::new($bounds.Width, $bounds.Height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
    $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose()
    $bitmap.Dispose()
    Add-Artifact "screenshot" $path "Desktop screenshot: $Name"
    return $path
  } catch {
    Add-Check "Screenshot capture: $Name" $false "warning" $_.Exception.Message
    return $null
  }
}

function Ensure-WindowApi {
  if ("ArceusInstalledSmokeWin32" -as [type]) { return }
  Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;

public static class ArceusInstalledSmokeWin32 {
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT {
    public int Left;
    public int Top;
    public int Right;
    public int Bottom;
  }

  [DllImport("user32.dll")]
  public static extern IntPtr GetForegroundWindow();

  [DllImport("user32.dll")]
  public static extern bool SetForegroundWindow(IntPtr hWnd);

  [DllImport("user32.dll")]
  public static extern bool BringWindowToTop(IntPtr hWnd);

  [DllImport("user32.dll")]
  public static extern bool SetWindowPos(IntPtr hWnd, IntPtr hWndInsertAfter, int X, int Y, int cx, int cy, uint uFlags);

  [DllImport("user32.dll")]
  public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

  [DllImport("user32.dll")]
  public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId);

  [DllImport("user32.dll", CharSet = CharSet.Unicode)]
  public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);

  [DllImport("user32.dll")]
  public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);

  [DllImport("user32.dll")]
  public static extern bool PrintWindow(IntPtr hwnd, IntPtr hdcBlt, uint nFlags);
}
"@
}

function Set-AppWindowForeground {
  param([IntPtr]$Handle)
  try {
    Ensure-WindowApi
    $SW_RESTORE = 9
    $SW_SHOW = 5
    $SWP_NOMOVE = 0x0002
    $SWP_NOSIZE = 0x0001
    $HWND_TOPMOST = [IntPtr]::new(-1)
    $HWND_NOTOPMOST = [IntPtr]::new(-2)
    [ArceusInstalledSmokeWin32]::ShowWindow($Handle, $SW_RESTORE) | Out-Null
    [ArceusInstalledSmokeWin32]::ShowWindow($Handle, $SW_SHOW) | Out-Null
    [ArceusInstalledSmokeWin32]::BringWindowToTop($Handle) | Out-Null
    [ArceusInstalledSmokeWin32]::SetWindowPos($Handle, $HWND_TOPMOST, 0, 0, 0, 0, ($SWP_NOMOVE -bor $SWP_NOSIZE)) | Out-Null
    Start-Sleep -Milliseconds 200
    [ArceusInstalledSmokeWin32]::SetWindowPos($Handle, $HWND_NOTOPMOST, 0, 0, 0, 0, ($SWP_NOMOVE -bor $SWP_NOSIZE)) | Out-Null
    [ArceusInstalledSmokeWin32]::SetForegroundWindow($Handle) | Out-Null
    Start-Sleep -Seconds 2
    return $true
  } catch {
    Add-Check "Bring installed app to foreground" $false "warning" $_.Exception.Message
    return $false
  }
}

function Get-ForegroundWindowInfo {
  try {
    Ensure-WindowApi
    $handle = [ArceusInstalledSmokeWin32]::GetForegroundWindow()
    $processId = [uint32]0
    [ArceusInstalledSmokeWin32]::GetWindowThreadProcessId($handle, [ref]$processId) | Out-Null
    $titleBuilder = [System.Text.StringBuilder]::new(512)
    [ArceusInstalledSmokeWin32]::GetWindowText($handle, $titleBuilder, $titleBuilder.Capacity) | Out-Null
    $process = if ($processId -gt 0) { Get-Process -Id $processId -ErrorAction SilentlyContinue } else { $null }
    return [pscustomobject]@{
      process_id = $processId
      process_name = if ($process) { $process.ProcessName } else { "" }
      title = $titleBuilder.ToString()
    }
  } catch {
    return [pscustomobject]@{ process_id = 0; process_name = ""; title = $_.Exception.Message }
  }
}

function Test-ArceusForeground {
  $foreground = Get-ForegroundWindowInfo
  $ok = ($foreground.process_name -eq "Arceus Code" -or $foreground.title -like "*Arceus Code*")
  Add-Check "Installed desktop window foreground" $ok "warning" "process=$($foreground.process_name); title=$($foreground.title); pid=$($foreground.process_id)"
  return $ok
}

function Capture-AppWindow {
  param([IntPtr]$Handle, [string]$Name)
  $path = Join-Path $screenshotsDir $Name
  try {
    Ensure-WindowApi
    Add-Type -AssemblyName System.Drawing
    $rect = New-Object ArceusInstalledSmokeWin32+RECT
    if (-not [ArceusInstalledSmokeWin32]::GetWindowRect($Handle, [ref]$rect)) {
      throw "Could not read installed app window bounds."
    }
    $width = [Math]::Max(1, $rect.Right - $rect.Left)
    $height = [Math]::Max(1, $rect.Bottom - $rect.Top)
    $bitmap = [System.Drawing.Bitmap]::new($width, $height)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $hdc = $graphics.GetHdc()
    try {
      $printed = [ArceusInstalledSmokeWin32]::PrintWindow($Handle, $hdc, 2)
    } finally {
      $graphics.ReleaseHdc($hdc)
    }
    if (-not $printed) {
      $graphics.CopyFromScreen([System.Drawing.Point]::new($rect.Left, $rect.Top), [System.Drawing.Point]::Empty, [System.Drawing.Size]::new($width, $height))
    }
    $bitmap.Save($path, [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose()
    $bitmap.Dispose()

    # Electron GPU windows can report a successful PrintWindow call while returning
    # a blank white surface. Fall back to a bounded screen capture in that case.
    if (-not (Test-ScreenshotNonBlank $path)) {
      $fallbackName = [System.IO.Path]::GetFileNameWithoutExtension($Name) + "-screen-crop.png"
      $fallbackPath = Join-Path $screenshotsDir $fallbackName
      $fallbackBitmap = [System.Drawing.Bitmap]::new($width, $height)
      $fallbackGraphics = [System.Drawing.Graphics]::FromImage($fallbackBitmap)
      $fallbackGraphics.CopyFromScreen([System.Drawing.Point]::new($rect.Left, $rect.Top), [System.Drawing.Point]::Empty, [System.Drawing.Size]::new($width, $height))
      $fallbackBitmap.Save($fallbackPath, [System.Drawing.Imaging.ImageFormat]::Png)
      $fallbackGraphics.Dispose()
      $fallbackBitmap.Dispose()
      Add-Artifact "screenshot" $fallbackPath "Installed app window screen-crop fallback: $fallbackName"
      return $fallbackPath
    }

    Add-Artifact "screenshot" $path "Installed app window capture: $Name"
    return $path
  } catch {
    Add-Check "Window capture: $Name" $false "warning" $_.Exception.Message
    return $null
  }
}

function Test-ScreenshotNonBlank {
  param([string]$Path)
  try {
    Add-Type -AssemblyName System.Drawing
    $bitmap = [System.Drawing.Bitmap]::FromFile((Resolve-Path $Path).Path)
    $width = $bitmap.Width
    $height = $bitmap.Height
    $samples = @{}
    $stepX = [Math]::Max(1, [int]($width / 80))
    $stepY = [Math]::Max(1, [int]($height / 50))
    for ($x = 0; $x -lt $width; $x += $stepX) {
      for ($y = 0; $y -lt $height; $y += $stepY) {
        $pixel = $bitmap.GetPixel($x, $y)
        $key = "$([int]($pixel.R / 16))-$([int]($pixel.G / 16))-$([int]($pixel.B / 16))"
        $samples[$key] = $true
      }
    }
    $contentSamples = 0
    $nonWhiteContentSamples = 0
    $contentStartX = [Math]::Min($width - 1, 160)
    $contentStartY = [Math]::Min($height - 1, 90)
    for ($x = $contentStartX; $x -lt ($width - 40); $x += $stepX) {
      for ($y = $contentStartY; $y -lt ($height - 40); $y += $stepY) {
        $pixel = $bitmap.GetPixel($x, $y)
        $contentSamples += 1
        if (-not ($pixel.R -gt 245 -and $pixel.G -gt 245 -and $pixel.B -gt 245)) {
          $nonWhiteContentSamples += 1
        }
      }
    }
    $bitmap.Dispose()
    $nonWhiteRatio = if ($contentSamples -gt 0) { $nonWhiteContentSamples / $contentSamples } else { 0 }
    return ($samples.Keys.Count -gt 8 -and $nonWhiteRatio -gt 0.01)
  } catch {
    return $false
  }
}

function Stop-ExistingArceus {
  $processes = @(Get-Process -Name "Arceus Code","NEXUS OS" -ErrorAction SilentlyContinue)
  foreach ($process in $processes) {
    try {
      $process.CloseMainWindow() | Out-Null
    } catch {
      # Continue to force-stop below.
    }
  }
  Start-Sleep -Seconds 2
  $remaining = @(Get-Process -Name "Arceus Code","NEXUS OS" -ErrorAction SilentlyContinue)
  foreach ($process in $remaining) {
    try {
      Stop-Process -Id $process.Id -Force
    } catch {
      # Best effort: launch verification will catch remaining single-instance failures.
    }
  }
  return $processes.Count
}

function Find-InstalledExe {
  $candidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Arceus Code\Arceus Code.exe"),
    (Join-Path $env:ProgramFiles "Arceus Code\Arceus Code.exe"),
    (Join-Path ${env:ProgramFiles(x86)} "Arceus Code\Arceus Code.exe"),
    (Join-Path $repoRoot "desktop\dist\win-unpacked\Arceus Code.exe")
  )
  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path $candidate)) {
      return (Resolve-Path $candidate).Path
    }
  }
  return $null
}

Write-Host "Installed Arceus product verification" -ForegroundColor Cyan

$stoppedCount = Stop-ExistingArceus
Add-Check "Existing installed app processes closed" $true "ok" "closed=$stoppedCount"

$installerExists = Test-Path $InstallerPath
Add-Check "Installer artifact exists" $installerExists "blocker" $InstallerPath
if ($installerExists) {
  $hash = (Get-FileHash -Algorithm SHA256 -Path $InstallerPath).Hash.ToLowerInvariant()
  $installerItem = Get-Item $InstallerPath
  Add-Check "Installer checksum generated" ($hash.Length -eq 64) "blocker" $hash
  Add-Check "Installer size plausible" ($installerItem.Length -gt 50MB) "blocker" "$([math]::Round($installerItem.Length / 1MB, 1)) MB"
}

$download = Test-Http "$FrontendUrl/download"
Add-Check "Public download page reachable" $download.ok "blocker" "$FrontendUrl/download - $($download.detail)"
$manifest = Test-Http "$BackendUrl/api/v1/downloads/latest"
Add-Check "Public download manifest reachable" $manifest.ok "blocker" "$BackendUrl/api/v1/downloads/latest - $($manifest.detail)"
if ($manifest.ok) {
  try {
    $manifestJson = $manifest.content | ConvertFrom-Json
    $windows = @($manifestJson.downloads.windows)[0]
    $windowsUrl = if ([string]::IsNullOrWhiteSpace($windows.url)) { "missing url" } else { $windows.url }
    Add-Check "Manifest Windows installer available" ($windows.available -eq $true -and [string]::IsNullOrWhiteSpace($windows.url) -eq $false) "blocker" $windowsUrl
    Add-Check "Manifest checksum matches local artifact" ($installerExists -and $windows.checksum_sha256 -eq $hash) "warning" "manifest=$($windows.checksum_sha256); local=$hash"
    Add-Check "Manifest version present" ([string]::IsNullOrWhiteSpace($manifestJson.version) -eq $false) "blocker" $manifestJson.version
  } catch {
    Add-Check "Download manifest parse" $false "blocker" $_.Exception.Message
  }
}

if ($installerExists -and -not $SkipInstall) {
  try {
    $installLog = Join-Path $logsDir "installer-silent.log"
    $process = Start-Process -FilePath (Resolve-Path $InstallerPath).Path -ArgumentList "/S" -PassThru -Wait -WindowStyle Hidden
    "installer_exit_code=$($process.ExitCode)" | Set-Content -Path $installLog -Encoding UTF8
    Add-Artifact "log" $installLog "Silent installer exit code"
    Add-Check "Silent installer completed" ($process.ExitCode -eq 0) "blocker" "exit=$($process.ExitCode)"
  } catch {
    Add-Check "Silent installer completed" $false "blocker" $_.Exception.Message
  }
} elseif ($SkipInstall) {
  Add-Check "Silent installer completed" $false "warning" "Skipped by -SkipInstall."
}

$exe = Find-InstalledExe
$usingUnpackedFallback = $exe -and $exe.Contains("desktop\dist\win-unpacked")
$exeDetail = if ($exe) { $exe } else { "not found" }
Add-Check "Installed Arceus executable found" ($exe -and -not $usingUnpackedFallback) "blocker" $exeDetail
if ($usingUnpackedFallback) {
  Add-Check "Unpacked executable fallback found" $true "warning" $exe
}

$appProcess = $null
if ($exe) {
  Capture-Screen "00-before-launch.png" | Out-Null
  try {
    $appProcess = Start-Process -FilePath $exe -PassThru
    Start-Sleep -Seconds 30
    $liveProcesses = @(Get-Process -Name "Arceus Code" -ErrorAction SilentlyContinue)
    $windowProcess = @($liveProcesses | Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -First 1)
    if ($windowProcess.Count -gt 0) {
      Set-AppWindowForeground ([IntPtr]$windowProcess[0].MainWindowHandle) | Out-Null
    }
    Add-Check "Installed desktop process started" ($liveProcesses.Count -gt 0) "blocker" "pid=$($appProcess.Id); live=$($liveProcesses.Count); window=$($windowProcess.Count)"
    Add-Check "Installed desktop window visible" ($windowProcess.Count -gt 0) "blocker" ($(if ($windowProcess.Count -gt 0) { $windowProcess[0].MainWindowTitle } else { "no main window" }))
    if ($windowProcess.Count -gt 0) { Test-ArceusForeground | Out-Null }
    $launchScreenshot = $null
    $launchScreenshotOk = $false
    for ($attempt = 1; $attempt -le 3; $attempt += 1) {
      $name = if ($attempt -eq 1) { "01-installed-app-launched.png" } else { "01-installed-app-launched-$attempt.png" }
      $launchScreenshot = if ($windowProcess.Count -gt 0) { Capture-AppWindow ([IntPtr]$windowProcess[0].MainWindowHandle) $name } else { Capture-Screen $name }
      $launchScreenshotOk = ($launchScreenshot -and (Test-ScreenshotNonBlank $launchScreenshot))
      if ($launchScreenshotOk) { break }
      if ($windowProcess.Count -gt 0) {
        Set-AppWindowForeground ([IntPtr]$windowProcess[0].MainWindowHandle) | Out-Null
        Test-ArceusForeground | Out-Null
      }
      Start-Sleep -Seconds 10
    }
    $launchScreenshotDetail = if ($launchScreenshot) { $launchScreenshot } else { "missing screenshot" }
    Add-Check "Installed desktop screenshot nonblank" $launchScreenshotOk "blocker" $launchScreenshotDetail
  } catch {
    Add-Check "Installed desktop process started" $false "blocker" $_.Exception.Message
  }
}

$userDataRoots = @(
  (Join-Path $env:APPDATA "Arceus Code"),
  (Join-Path $env:APPDATA "arceus-desktop-os"),
  (Join-Path $env:LOCALAPPDATA "Arceus Code"),
  (Join-Path $env:LOCALAPPDATA "arceus-desktop-os")
)
foreach ($root in $userDataRoots) {
  if (-not $root -or -not (Test-Path $root)) { continue }
  Get-ChildItem -Path $root -Filter "*.log" -File -Recurse -ErrorAction SilentlyContinue | ForEach-Object {
    $target = Join-Path $logsDir ("desktop-" + ($_.Name -replace '[^\w\.-]', '_'))
    Copy-Item -Path $_.FullName -Destination $target -Force
    Add-Artifact "log" $target "Copied desktop log from $($_.FullName)"
  }
}

if (-not $KeepRunning -and $exe) {
  try {
    $liveProcesses = @(Get-Process -Name "Arceus Code" -ErrorAction SilentlyContinue)
    foreach ($process in $liveProcesses) {
      try { $process.CloseMainWindow() | Out-Null } catch {}
    }
    Start-Sleep -Seconds 4
    $remaining = @(Get-Process -Name "Arceus Code" -ErrorAction SilentlyContinue)
    foreach ($process in $remaining) {
      try {
        Stop-Process -Id $process.Id -Force -ErrorAction Stop
        Start-Sleep -Milliseconds 250
      } catch {
        # The renderer/gpu child may have exited naturally between enumeration and stop.
      }
    }
    Add-Check "Installed desktop shutdown" $true "blocker" "closed=$($liveProcesses.Count); forced=$($remaining.Count)"
    Capture-Screen "02-after-shutdown.png" | Out-Null
  } catch {
    Add-Check "Installed desktop shutdown" $false "blocker" $_.Exception.Message
  }
} elseif ($KeepRunning) {
  Add-Check "Installed desktop shutdown" $false "warning" "Skipped by -KeepRunning."
}

$summary = [pscustomobject]@{
  generated_at = (Get-Date).ToUniversalTime().ToString("o")
  frontend_url = $FrontendUrl
  backend_url = $BackendUrl
  installer_path = if ($installerExists) { (Resolve-Path $InstallerPath).Path } else { $InstallerPath }
  installed_executable = $exe
  checks = $checks
  artifacts = $artifacts
}
$summary | ConvertTo-Json -Depth 8 | Set-Content -Path $OutputPath -Encoding UTF8
Add-Artifact "summary" $OutputPath "Installed product verification summary"

$checks | Format-Table name, ok, severity, detail -AutoSize
Write-Host "Summary written to $OutputPath" -ForegroundColor DarkGray
Write-Host "Screenshots: $screenshotsDir" -ForegroundColor DarkGray
Write-Host "Logs: $logsDir" -ForegroundColor DarkGray
Write-Host "Videos: $videosDir" -ForegroundColor DarkGray

$blockers = @($checks | Where-Object { $_.severity -eq "blocker" -and -not $_.ok })
if ($blockers.Count -gt 0) {
  $message = "Installed product verification failed: $($blockers.Count) blocker(s)."
  if ($Strict) { throw $message }
  Write-Warning $message
  exit 1
}

Write-Host "Installed product verification passed." -ForegroundColor Green
