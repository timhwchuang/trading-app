param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = "Stop"
$venvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$manScript = Join-Path $ProjectRoot "src\man.py"

if (-not (Test-Path $venvPython)) {
    throw "找不到 venv Python: $venvPython"
}
if (-not (Test-Path $manScript)) {
    throw "找不到 man.py: $manScript"
}

Set-Location (Join-Path $ProjectRoot "src")
& $venvPython $manScript
