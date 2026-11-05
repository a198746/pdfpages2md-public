#requires -Version 5.1
<#
.SYNOPSIS
    Stop the pdfpages2md service started by deploy.ps1.
#>
[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$PidFile = Join-Path $Root ".server.pid"

if (-not (Test-Path $PidFile)) {
    Write-Host "No .server.pid found; nothing to stop."
    exit 0
}

$serverPid = (Get-Content $PidFile -Raw).Trim()
if (-not $serverPid) {
    Remove-Item $PidFile -Force
    Write-Host "Empty .server.pid; removed."
    exit 0
}

$process = Get-Process -Id $serverPid -ErrorAction SilentlyContinue
if (-not $process) {
    Remove-Item $PidFile -Force
    Write-Host "PID $serverPid is not running; removed stale .server.pid."
    exit 0
}

Stop-Process -Id $serverPid -Force
$process.WaitForExit(10000) | Out-Null
Remove-Item $PidFile -Force
Write-Host "Stopped pdfpages2md (PID $serverPid)."
