#!/usr/bin/env pwsh
<#
.SYNOPSIS
    One-command local development startup for Arceus AI OS.

.DESCRIPTION
    Starts PostgreSQL + Redis via Docker Compose (optional), applies
    Alembic migrations, then launches all 3 backend services and the
    Next.js frontend in parallel with colour-coded log prefixes.

.PARAMETER NoDocker
    Skip Docker Compose and assume Postgres/Redis are already running.

.PARAMETER BackendOnly
    Only start the three backend FastAPI services (no frontend).

.PARAMETER FrontendOnly
    Only start the Next.js dev server (no backend services).

.EXAMPLE
    .\scripts\start-dev.ps1
    .\scripts\start-dev.ps1 -NoDocker
    .\scripts\start-dev.ps1 -FrontendOnly
#>

param(
    [switch]$NoDocker,
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path "$PSScriptRoot\..").Path
$BackendDir  = Join-Path $ProjectRoot "backend"
$FrontendDir = Join-Path $ProjectRoot "frontend"

# --- Colours ---
function Write-Tag([string]$Tag, [string]$Msg, [ConsoleColor]$Color = "Cyan") {
    $prev = $Host.UI.RawUI.ForegroundColor
    $Host.UI.RawUI.ForegroundColor = $Color
    Write-Host "[$Tag] $Msg"
    $Host.UI.RawUI.ForegroundColor = $prev
}

Write-Tag "start-dev" "Arceus AI OS — Local Development Startup" Magenta
Write-Tag "start-dev" "Project root: $ProjectRoot" Gray

# --- 1. Docker Compose (Postgres + Redis) ---
if (-not $NoDocker -and -not $FrontendOnly) {
    Write-Tag "docker" "Starting Postgres + Redis via Docker Compose..." Yellow
    Push-Location $ProjectRoot
    try {
        docker compose up -d postgres redis 2>&1 | ForEach-Object { Write-Tag "docker" $_ DarkYellow }
        # Give Postgres a moment to be ready
        Start-Sleep -Seconds 3
        Write-Tag "docker" "Containers started." Green
    } catch {
        Write-Tag "docker" "Docker Compose failed — $($_.Exception.Message)" Red
        Write-Tag "docker" "Re-run with -NoDocker if Postgres is already running." Yellow
    }
    Pop-Location
}

# --- 2. Alembic migrations ---
if (-not $FrontendOnly) {
    Write-Tag "alembic" "Applying database migrations..." Yellow
    Push-Location $BackendDir
    try {
        python -m alembic upgrade head 2>&1 | ForEach-Object { Write-Tag "alembic" $_ DarkYellow }
        Write-Tag "alembic" "Migrations applied." Green
    } catch {
        Write-Tag "alembic" "Migration failed (may be OK if DB is fresh): $($_.Exception.Message)" Yellow
    }
    Pop-Location
}

# --- 3. Launch processes ---
$jobs = @()

if (-not $FrontendOnly) {
    # Auth Service :8001
    $jobs += Start-Job -Name "auth" -ScriptBlock {
        param($dir)
        Set-Location $dir
        uvicorn services.auth.main:app --host 0.0.0.0 --port 8001 --reload 2>&1 |
            ForEach-Object { "[auth  ] $_" }
    } -ArgumentList $BackendDir

    # Goals Service :8002
    $jobs += Start-Job -Name "goals" -ScriptBlock {
        param($dir)
        Set-Location $dir
        uvicorn services.goals.main:app --host 0.0.0.0 --port 8002 --reload 2>&1 |
            ForEach-Object { "[goals ] $_" }
    } -ArgumentList $BackendDir

    # Agent Service :8003
    $jobs += Start-Job -Name "agent" -ScriptBlock {
        param($dir)
        Set-Location $dir
        uvicorn services.agent.main:app --host 0.0.0.0 --port 8003 --reload 2>&1 |
            ForEach-Object { "[agent ] $_" }
    } -ArgumentList $BackendDir

    Write-Tag "start-dev" "Backend services starting on :8001 :8002 :8003" Green
}

if (-not $BackendOnly) {
    # Next.js frontend :3004
    $jobs += Start-Job -Name "frontend" -ScriptBlock {
        param($dir)
        Set-Location $dir
        npm run dev 2>&1 | ForEach-Object { "[ui    ] $_" }
    } -ArgumentList $FrontendDir

    Write-Tag "start-dev" "Frontend starting on :3004" Green
}

Write-Tag "start-dev" "All processes launched. Press Ctrl+C to stop." Magenta
Write-Host ""
Write-Host "  Auth   → http://localhost:8001/api/v1/health"
Write-Host "  Goals  → http://localhost:8002/api/v1/health"
Write-Host "  Agent  → http://localhost:8003/api/v1/health"
Write-Host "  UI     → http://localhost:3004"
Write-Host ""

# --- 4. Stream all job output with colour-coded prefixes ---
$colorMap = @{
    "auth"     = "Cyan"
    "goals"    = "Green"
    "agent"    = "Yellow"
    "frontend" = "Magenta"
}

try {
    while ($true) {
        foreach ($job in $jobs) {
            $output = Receive-Job -Job $job -ErrorAction SilentlyContinue
            if ($output) {
                $col = $colorMap[$job.Name] ?? "White"
                $output | ForEach-Object {
                    $prev = $Host.UI.RawUI.ForegroundColor
                    $Host.UI.RawUI.ForegroundColor = $col
                    Write-Host $_
                    $Host.UI.RawUI.ForegroundColor = $prev
                }
            }
        }
        # Check if all jobs died unexpectedly
        $running = $jobs | Where-Object { $_.State -eq "Running" }
        if ($running.Count -eq 0) {
            Write-Tag "start-dev" "All processes have exited." Red
            break
        }
        Start-Sleep -Milliseconds 200
    }
} finally {
    Write-Tag "start-dev" "Stopping all services..." Yellow
    $jobs | Stop-Job -ErrorAction SilentlyContinue
    $jobs | Remove-Job -Force -ErrorAction SilentlyContinue
    Write-Tag "start-dev" "Done." Green
}
