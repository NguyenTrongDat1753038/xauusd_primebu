#Requires -Version 5.1

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("xauusd_prod", "eurgbp_prod", "btcusd_prod", "eurgbp_prod_high_risk")]
    [string]$BotName
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$env:PYTHONIOENCODING = "utf-8"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonExe = Join-Path $ProjectRoot "ta_env\Scripts\python.exe"
$BotScript = Join-Path $ProjectRoot "production\run_live.py"

if (-not (Test-Path $PythonExe)) {
    Write-Host "Python not found" -ForegroundColor Red
    exit 1
}

Write-Host "Starting bot: $BotName" -ForegroundColor Green
& $PythonExe $BotScript $BotName
