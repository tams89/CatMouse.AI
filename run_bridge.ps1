# CatMouse.AI Bridge Background Runner
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptDir

Write-Host "Starting CatMouse.AI Prey Detection Bridge on port 8095..." -ForegroundColor Green
uv run --with paho-mqtt --with pyyaml --with requests python "$scriptDir\config\prey_detection_bridge.py"
