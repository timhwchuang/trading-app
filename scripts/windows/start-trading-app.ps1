param(
    [Parameter(Mandatory = $false)]
    [string]$ProjectRoot = "C:\trading-app"
)

$ErrorActionPreference = "Stop"
$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$srcDir = Join-Path $ProjectRoot "src"

if (-not (Test-Path $venvPython)) {
    throw "找不到 venv Python: $venvPython"
}
if (-not (Test-Path $srcDir)) {
    throw "找不到 src 目錄: $srcDir"
}

Set-Location $srcDir
& $venvPython -m live