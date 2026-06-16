param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [string]$TaskName = "trading-app-vwap"
)

$ErrorActionPreference = "Stop"
$startScript = Join-Path $ProjectRoot "scripts\windows\start-trading-app.ps1"

if (-not (Test-Path $startScript)) {
    throw "找不到 start-trading-app.ps1: $startScript"
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$startScript`" -ProjectRoot `"$ProjectRoot`""

$trigger = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit ([TimeSpan]::Zero)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force
Write-Host "已註冊工作排程器任務: $TaskName"