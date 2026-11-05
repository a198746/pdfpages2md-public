#requires -Version 5.1
<#
.SYNOPSIS
    Start the pdfpages2md backend + frontend as one detached local service.

.DESCRIPTION
    backend/server.py serves both the JSON API and the static files in frontend/.
    This script installs the package when needed, starts the server hidden in the
    background, waits until /api/health responds, and records the PID in
    .server.pid so stop.ps1 can stop it again.

.PARAMETER ListenHost
    Bind address. Use 0.0.0.0 to expose the service to the local network.

.PARAMETER Port
    TCP port, default 8000.

.PARAMETER Install
    Force a fresh `pip install -e .` before starting.
#>
[CmdletBinding()]
param(
    [string]$ListenHost = "127.0.0.1",
    [int]$Port = 8000,
    [switch]$Install
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Url = "http://{0}:{1}" -f $ListenHost, $Port
$HealthUrl = "$Url/api/health"
$LogDir = Join-Path $Root ".logs"
$PidFile = Join-Path $Root ".server.pid"

function Test-Health {
    try {
        $response = Invoke-RestMethod -Uri $HealthUrl -TimeoutSec 3
        return [bool]$response.ok
    } catch {
        return $false
    }
}

if (Test-Health) {
    Write-Host "pdfpages2md is already running at $Url"
    exit 0
}

$probeHost = if ($ListenHost -eq "0.0.0.0") { "127.0.0.1" } else { $ListenHost }
$client = New-Object System.Net.Sockets.TcpClient
try {
    $client.Connect($probeHost, $Port)
    $portBusy = $true
} catch {
    $portBusy = $false
} finally {
    $client.Close()
}
if ($portBusy) {
    Write-Error "Port $Port on $probeHost is already in use by another program. Stop it first or choose another -Port."
}

Set-Location $Root
$needsInstall = [bool]$Install
if (-not $needsInstall) {
    python -c "import pdfpages2md, pymupdf4llm" 2>$null | Out-Null
    $needsInstall = $LASTEXITCODE -ne 0
}
if ($needsInstall) {
    Write-Host "Installing project dependencies..."
    python -m pip install -e .
    if ($LASTEXITCODE -ne 0) { throw "pip install -e . failed with exit code $LASTEXITCODE" }
}

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Write-Host "Starting pdfpages2md on $ListenHost`:$Port ..."
$process = Start-Process -FilePath "python" `
    -ArgumentList "-u", "backend/server.py", "--host", $ListenHost, "--port", "$Port" `
    -WorkingDirectory $Root `
    -RedirectStandardOutput (Join-Path $LogDir "server.out.log") `
    -RedirectStandardError (Join-Path $LogDir "server.err.log") `
    -WindowStyle Hidden -PassThru

$process.Id | Set-Content -Path $PidFile -Encoding ascii

$deadline = (Get-Date).AddSeconds(30)
while ((Get-Date) -lt $deadline) {
    if ($process.HasExited) {
        Write-Error "Server exited with code $($process.ExitCode). See $LogDir\server.err.log"
    }
    if (Test-Health) {
        Write-Host "Deployed: $Url  (PID $($process.Id))"
        Write-Host "Frontend and API are served by the same process."
        exit 0
    }
    Start-Sleep -Milliseconds 500
}

Write-Error "Server did not become healthy within 30s. See $LogDir\server.err.log"
