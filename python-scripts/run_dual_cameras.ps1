# PowerShell launcher for dual camera monitoring
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $scriptPath
& "$scriptPath\..\\.venv\Scripts\Activate.ps1"
python dual_camera_monitor.py --post --display
