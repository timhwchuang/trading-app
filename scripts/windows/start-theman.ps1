# Deprecated alias — use start-trading-app.ps1
param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = "Stop"
$startScript = Join-Path $PSScriptRoot "start-trading-app.ps1"
& $startScript -ProjectRoot $ProjectRoot