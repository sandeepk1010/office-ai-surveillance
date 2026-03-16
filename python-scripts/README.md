# Python scripts

Place small utility scripts here. Example: `monitor.py` fetches `http://localhost:3000/api/dashboard` and prints a short summary.

Run examples:

```powershell
# Quick summary monitor (uses backend dashboard)
python python-scripts\monitor.py

# RTSP monitor (option A: provide full URL via env)
$env:RTSP_URL='rtsp://admin:India123%23@192.168.1.245:554/cam/realmonitor?channel=1&subtype=0'
python python-scripts\rtsp_monitor.py

# RTSP monitor (option B: provide pieces via env variables)
$env:RTSP_USER='admin'
$env:RTSP_PASS='India123#'
$env:RTSP_HOST='192.168.1.245'
$env:RTSP_PORT='554'
python python-scripts\rtsp_monitor.py --channel 1 --subtype 0
```

Install Python requirements:

```powershell
cd python-scripts
pip install -r requirements.txt
```

Note: Keep credentials out of source files. Use environment variables or a secure vault. The examples above show how to run the monitor locally; replace values with your real credentials.

Line-crossing office in/out detector (GStreamer + YOLO):

```powershell
# example using RTSP env
$env:RTSP_URL='rtsp://admin:India123%23@192.168.1.245:554/cam/realmonitor?channel=1&subtype=0'
python python-scripts\line_counter.py --post --line-fraction 0.45 --model yolov8n.pt
```

Wrappers

Use the provided wrappers to run the monitor more easily:

PowerShell:
```powershell
.\run_line_counter.ps1 -Url "rtsp://..." -Post -Display -LineFraction 0.45
```

CMD:
```cmd
run_line_counter.bat --url "rtsp://..." --post --display --line-fraction 0.45
```


Options:
- `--post` : actually POST `{'employee_id': null, 'type': 'in'|'out'}` to the backend `--backend` URL (default `http://localhost:3000/api/entries`).
- `--display` : currently reserved in GStreamer mode and not used for preview rendering.
- `--line-fraction` : vertical position of the ROI line as fraction of frame height (0 = top, 1 = bottom).
- `--model` : YOLO model path/name (default `yolov8n.pt`).
- `--conf` : YOLO confidence threshold (default `0.35`).

Note: The script uses YOLO person detections plus a simple centroid tracker and can produce false positives/duplicates in crowded scenes; tune `--conf` and `--match-distance` for your camera and scene.
