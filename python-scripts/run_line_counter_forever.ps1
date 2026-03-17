$ErrorActionPreference = 'Continue'

# Update these if needed
$PythonExe = "C:\office-AI\python-scripts\.venv\Scripts\python.exe"
$ScriptPath = "C:\office-AI\python-scripts\line_counter.py"
$RtspUrl = "rtsp://admin:India123#@192.168.2.103:554/cam/realmonitor?channel=2&subtype=0"
$ModelPath = "C:\office-AI\python-scripts\yolov8n.pt"
$RoiFile = "C:\office-AI\python-scripts\roi_cam2.json"
$BackendUrl = "http://localhost:3001/api/entries"
$SaveCropsDir = "C:\office-AI\python-scripts\crossings"

while ($true) {
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Starting line_counter.py"

    & $PythonExe $ScriptPath `
        --url $RtspUrl `
        --model $ModelPath `
        --conf 0.18 `
        --roi-file $RoiFile `
        --line-x-margin 120 `
        --post `
        --backend $BackendUrl `
        --save-crops $SaveCropsDir `
        --save-faces-only `
        --crossing-only

    $code = $LASTEXITCODE
    Write-Host "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] Detector stopped. Exit code: $code"
    Write-Host "Restarting in 5 seconds..."
    Start-Sleep -Seconds 5
}
