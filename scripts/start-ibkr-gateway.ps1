<#
.SYNOPSIS
    IBKR Client Portal Gateway Startup Script (Windows PowerShell)
.DESCRIPTION
    Supports both Docker mode and local Java mode.
    Port-equivalent of scripts/start-ibkr-gateway.sh for Windows.
.PARAMETER Mode
    --docker, --local, --stop, or --auto (default)
#>

param(
    [string]$Mode = "auto"
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$GatewayPort = if ($env:IBKR_GATEWAY_PORT) { $env:IBKR_GATEWAY_PORT } else { "5000" }
$GatewayDir = Join-Path $ProjectDir "clientportal"
$DockerImage = if ($env:IBKR_DOCKER_IMAGE) { $env:IBKR_DOCKER_IMAGE } else { "gnzsnz/ib-gateway:latest" }
$ContainerName = "ibkr-gateway"
$PidFile = Join-Path $ProjectDir ".ibkr-gateway.pid"

function Log-Info  { param($msg) Write-Host "[IBKR] $msg" -ForegroundColor Green }
function Log-Warn  { param($msg) Write-Host "[IBKR] $msg" -ForegroundColor Yellow }
function Log-Error { param($msg) Write-Host "[IBKR] $msg" -ForegroundColor Red }

function Test-PortInUse {
    param([int]$Port)
    $conn = Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue
    return ($null -ne $conn)
}

function Stop-Gateway {
    Log-Info "Stopping IBKR Gateway..."
    # Stop Docker container
    try { docker rm -f $ContainerName 2>$null | Out-Null } catch {}
    # Stop local Java process (kill process tree: cmd.exe -> java.exe)
    if (Test-Path $PidFile) {
        $parentPid = Get-Content $PidFile -ErrorAction SilentlyContinue
        if ($parentPid) {
            $targetPid = [int]$parentPid
            # Find and kill child processes first (java.exe)
            try {
                Get-CimInstance Win32_Process -Filter "ParentProcessId = $targetPid" -ErrorAction SilentlyContinue |
                    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            } catch {}
            # Then kill parent (cmd.exe)
            try { Stop-Process -Id $targetPid -Force -ErrorAction SilentlyContinue } catch {}
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
    # Also kill any orphaned gateway java processes
    try {
        Get-Process java -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*clientportal*GatewayStart*" } |
            Stop-Process -Force -ErrorAction SilentlyContinue
    } catch {}
    Log-Info "Gateway stopped."
}

function Start-Docker {
    # Check Docker available
    if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
        Log-Error "Docker not found. Install Docker Desktop for Windows."
        return $false
    }

    # Check image exists
    $imageCheck = docker image inspect $DockerImage 2>&1
    if ($LASTEXITCODE -ne 0) {
        Log-Warn "Docker image $DockerImage not found locally. Pulling..."
        docker pull $DockerImage
        if ($LASTEXITCODE -ne 0) {
            Log-Error "Failed to pull $DockerImage"
            return $false
        }
    }

    # Stop existing container
    try { docker rm -f $ContainerName 2>$null | Out-Null } catch {}

    Log-Info "Starting IBKR Gateway via Docker (port $GatewayPort)..."

    $ibkrUser = if ($env:IBKR_USER) { $env:IBKR_USER } else { "" }
    $ibkrPass = if ($env:IBKR_PASS) { $env:IBKR_PASS } else { "" }
    $tradingMode = if ($env:IBKR_TRADING_MODE) { $env:IBKR_TRADING_MODE } else { "paper" }
    $acceptIncoming = if ($env:IBKR_ACCEPT_INCOMING) { $env:IBKR_ACCEPT_INCOMING } else { "" }

    docker run -d `
        --name $ContainerName `
        -p "${GatewayPort}:5000" `
        -e "TWS_USERID=$ibkrUser" `
        -e "TWS_PASSWORD=$ibkrPass" `
        -e "TRADING_MODE=$tradingMode" `
        -e "TWS_ACCEPT_INCOMING=$acceptIncoming" `
        --restart unless-stopped `
        $DockerImage

    if ($LASTEXITCODE -ne 0) {
        Log-Error "Failed to start Docker container"
        return $false
    }

    Log-Info "Container '$ContainerName' started."
    Log-Info "Login at: https://localhost:${GatewayPort}"
    return $true
}

function Start-Local {
    if (-not (Test-Path $GatewayDir)) {
        Log-Error "Gateway not found at $GatewayDir"
        Log-Warn "Download from: https://download2.interactivebrokers.com/portal/clientportal.gw.zip"
        Log-Warn "Then extract to: $GatewayDir"
        return $false
    }

    # Check Java
    if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
        Log-Error "Java not found. Install JRE from https://adoptium.net/"
        return $false
    }

    Log-Info "Starting IBKR Gateway via Java (port $GatewayPort)..."

    # Copy custom conf if available
    $confFile = Join-Path $ScriptDir "ibkr-gateway.conf.yaml"
    $targetConf = Join-Path $GatewayDir "root\conf.yaml"
    if (Test-Path $confFile) {
        Copy-Item $confFile $targetConf -Force
    }

    # Launch Java directly (bypasses run.bat/run.sh for reliable cross-platform behavior)
    $classpath = "$GatewayDir\root;$GatewayDir\dist\ibgroup.web.core.iblink.router.clientportal.gw.jar;$GatewayDir\build\lib\runtime\*"
    $javaArgs = @(
        "-server",
        "-Dvertx.disableDnsResolver=true",
        "-Djava.net.preferIPv4Stack=true",
        "-Dvertx.logger-delegate-factory-class-name=io.vertx.core.logging.SLF4JLogDelegateFactory",
        "-Dnologback.statusListenerClass=ch.qos.logback.core.status.OnConsoleStatusListener",
        "-classpath", $classpath,
        "ibgroup.web.core.clientportal.gw.GatewayStart"
    )

    $proc = Start-Process -FilePath "java" -ArgumentList $javaArgs -WorkingDirectory $GatewayDir -PassThru -WindowStyle Hidden

    $proc.Id | Out-File $PidFile -Encoding ascii
    Log-Info "Gateway started (PID: $($proc.Id))"
    Log-Info "Login at: https://localhost:${GatewayPort}"
    return $true
}

# === Main ===

# Normalize mode parameter
$Mode = $Mode -replace "^-+", ""

# Check if already running (skip if mode is stop)
if ($Mode -notin "stop", "s" -and (Test-PortInUse -Port ([int]$GatewayPort))) {
    Log-Info "IBKR Gateway already running on port $GatewayPort"
    exit 0
}

switch ($Mode) {
    { $_ -in "docker", "d" } {
        $result = Start-Docker
        if (-not $result) { exit 1 }
    }
    { $_ -in "local", "l" } {
        $result = Start-Local
        if (-not $result) { exit 1 }
    }
    { $_ -in "stop", "s" } {
        Stop-Gateway
        exit 0
    }
    default {
        # Auto mode: try Docker first, then local
        $started = $false

        # Check if Docker image is available
        if (Get-Command docker -ErrorAction SilentlyContinue) {
            $imageCheck = docker image inspect $DockerImage 2>&1
            if ($LASTEXITCODE -eq 0) {
                $started = Start-Docker
            }
        }

        if (-not $started -and (Test-Path $GatewayDir)) {
            $started = Start-Local
        }

        if (-not $started) {
            Log-Warn "IBKR Gateway not available."
            Log-Warn "Options:"
            Log-Warn "  1. Install Docker Desktop and pull image: docker pull $DockerImage"
            Log-Warn "  2. Download gateway: https://download2.interactivebrokers.com/portal/clientportal.gw.zip"
            Log-Warn "     Extract to: $GatewayDir"
            Log-Warn "App will start without IBKR Gateway. Dashboard will show 'not connected'."
            exit 0
        }
    }
}

# Wait for gateway to be ready
Log-Info "Waiting for Gateway to be ready..."
for ($i = 1; $i -le 15; $i++) {
    if (Test-PortInUse -Port ([int]$GatewayPort)) {
        Log-Info "Gateway is ready! Login at https://localhost:${GatewayPort}"
        exit 0
    }
    Start-Sleep -Seconds 2
}

Log-Warn "Gateway started but port $GatewayPort not yet responding."
Log-Warn "It may take a moment to initialize. Check https://localhost:${GatewayPort}"
exit 0
